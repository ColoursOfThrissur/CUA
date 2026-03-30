"""
VerifierAgent - Execution verification and failure analysis.

Responsibilities:
- Compare before/after screenshots (screen diff)
- Validate step success
- Classify failure reasons
- Provide actionable feedback for replanning
- NO execution, NO planning
"""
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class VerifierAgent:
    """Verifies execution results and analyzes failures."""

    def __init__(self, llm_client):
        self.llm = llm_client
        self.verification_history = []

    def verify_execution(self, execution_result: Dict) -> Dict:
        """
        Verify execution result and analyze any failures.
        
        Returns:
        {
            "verified": bool,
            "confidence": float,
            "failure_analysis": dict (if failed),
            "state_changes": list,
            "recommendations": list
        }
        """
        try:
            trace = execution_result.get("trace", [])
            success = execution_result.get("success", False)

            if success:
                return self._verify_success(trace)
            else:
                return self._analyze_failure(execution_result)

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return {
                "verified": False,
                "error": str(e),
            }

    def _verify_success(self, trace: List[Dict]) -> Dict:
        """Verify successful execution by analyzing state changes.
        
        OPTIMIZATION: Use deterministic state change detection, not LLM calls.
        """
        state_changes = []
        expectation_results = []
        
        for step in trace:
            before = step.get("before_state", {})
            after = step.get("after_state", {})
            
            changes = self._detect_state_changes(before, after)
            if changes:
                state_changes.append({
                    "step": step.get("step"),
                    "changes": changes,
                })
            expectation_results.append(self._evaluate_expected_effect(step, changes))

        # Success verification criteria (deterministic, no LLM needed)
        has_state_changes = len(state_changes) > 0
        all_steps_succeeded = all(s.get("success") for s in trace)
        all_expectations_met = all(r.get("passed", False) for r in expectation_results)

        verified = all_steps_succeeded and (all_expectations_met or has_state_changes)
        confidence = 0.9 if verified else 0.55

        return {
            "verified": verified,
            "confidence": confidence,
            "state_changes": state_changes,
            "expectation_results": expectation_results,
            "total_steps": len(trace),
            "recommendations": [] if verified else ["Observed result did not clearly match expected step effects"],
        }

    def _analyze_failure(self, execution_result: Dict) -> Dict:
        """Analyze failure and classify the reason."""
        trace = execution_result.get("trace", [])
        failed_step_num = execution_result.get("failed_step", 0)
        
        if not trace or failed_step_num == 0:
            return {
                "verified": False,
                "confidence": 0.0,
                "failure_analysis": {
                    "reason": "UNKNOWN",
                    "details": "No trace available",
                },
            }

        failed_step = trace[failed_step_num - 1] if failed_step_num <= len(trace) else {}
        
        # Classify failure
        failure_classification = self._classify_failure(failed_step)
        
        # Analyze screen state
        before_state = failed_step.get("before_state", {})
        after_state = failed_step.get("after_state", {})
        screen_diff = self._compute_screen_diff(before_state, after_state)

        # Generate recommendations
        recommendations = self._generate_recommendations(failure_classification, screen_diff)
        expectation_result = self._evaluate_expected_effect(
            failed_step,
            self._detect_state_changes(before_state, after_state),
        )

        return {
            "verified": False,
            "confidence": 0.8,
            "failure_analysis": {
                "failed_step": failed_step_num,
                "reason": failure_classification["reason"],
                "details": failure_classification["details"],
                "screen_diff": screen_diff,
                "expected_effect": failed_step.get("expected_effect", {}),
                "expectation_result": expectation_result,
            },
            "recommendations": recommendations,
        }

    def _classify_failure(self, failed_step: Dict) -> Dict:
        """
        Classify failure reason into categories.
        
        Categories:
        - ELEMENT_NOT_FOUND: UI element not detected
        - OUT_OF_BOUNDS: Coordinates invalid
        - WINDOW_NOT_FOCUSED: Target window not active
        - TIMEOUT: Operation timed out
        - PERMISSION_DENIED: Insufficient permissions
        - UNKNOWN: Unclassified error
        """
        result = failed_step.get("result", {})
        error_type = result.get("error_type", "")
        message = result.get("message", "").lower()

        # Classification rules
        if "not found" in message or "element" in message:
            return {
                "reason": "ELEMENT_NOT_FOUND",
                "details": "Target UI element could not be located",
                "recoverable": True,
            }
        elif "out of bounds" in message or error_type == "OUT_OF_BOUNDS":
            return {
                "reason": "OUT_OF_BOUNDS",
                "details": "Coordinates outside screen bounds",
                "recoverable": True,
            }
        elif "window" in message or "focus" in message:
            return {
                "reason": "WINDOW_NOT_FOCUSED",
                "details": "Target window not active or not found",
                "recoverable": True,
            }
        elif "timeout" in message:
            return {
                "reason": "TIMEOUT",
                "details": "Operation exceeded time limit",
                "recoverable": True,
            }
        elif "permission" in message or "denied" in message:
            return {
                "reason": "PERMISSION_DENIED",
                "details": "Insufficient permissions for operation",
                "recoverable": False,
            }
        else:
            return {
                "reason": "UNKNOWN",
                "details": message or "Unclassified error",
                "recoverable": True,
            }

    def _detect_state_changes(self, before: Dict, after: Dict) -> List[str]:
        """Detect what changed between before and after states."""
        changes = []

        # Screen changed?
        if before.get("screenshot_hash") != after.get("screenshot_hash"):
            changes.append("screen_content_changed")

        # Window changed?
        if before.get("active_window") != after.get("active_window"):
            changes.append(f"window_changed: {before.get('active_window')} → {after.get('active_window')}")

        # Mouse moved?
        before_mouse = before.get("mouse_position", {})
        after_mouse = after.get("mouse_position", {})
        if before_mouse != after_mouse:
            changes.append(f"mouse_moved: ({before_mouse.get('x')},{before_mouse.get('y')}) → ({after_mouse.get('x')},{after_mouse.get('y')})")

        return changes

    def _compute_screen_diff(self, before_state: Dict, after_state: Dict) -> Dict:
        """
        Compute screen difference using image comparison.
        
        Returns:
        {
            "changed": bool,
            "similarity": float,
            "diff_regions": list (future: bounding boxes of changes)
        }
        """
        before_path = before_state.get("screenshot_path")
        after_path = after_state.get("screenshot_path")

        if not before_path or not after_path:
            return {"changed": False, "similarity": 0.0, "reason": "missing_screenshots"}

        try:
            # Check if numpy is available
            try:
                import numpy as np
            except ImportError:
                logger.warning("numpy not available, using hash-based comparison")
                # Fallback to hash comparison
                before_hash = before_state.get("screenshot_hash")
                after_hash = after_state.get("screenshot_hash")
                changed = before_hash != after_hash
                return {
                    "changed": changed,
                    "similarity": 0.0 if changed else 1.0,
                    "method": "hash_comparison",
                }
            
            from PIL import Image

            # Load images
            before_img = Image.open(before_path).convert("RGB")
            after_img = Image.open(after_path).convert("RGB")

            # Ensure same size
            if before_img.size != after_img.size:
                after_img = after_img.resize(before_img.size)

            # Convert to numpy arrays
            before_arr = np.array(before_img)
            after_arr = np.array(after_img)

            # Compute pixel-wise difference
            diff = np.abs(before_arr.astype(float) - after_arr.astype(float))
            total_diff = np.sum(diff)
            max_diff = before_arr.size * 255  # Max possible difference

            # Similarity score (0.0 = completely different, 1.0 = identical)
            similarity = 1.0 - (total_diff / max_diff)

            # Changed if similarity < 0.95 (5% difference threshold)
            changed = similarity < 0.95

            return {
                "changed": changed,
                "similarity": round(similarity, 3),
                "diff_percentage": round((1.0 - similarity) * 100, 2),
                "method": "pixel_comparison",
            }

        except Exception as e:
            logger.warning(f"Screen diff computation failed: {e}, falling back to hash comparison")
            # Fallback to hash comparison
            before_hash = before_state.get("screenshot_hash")
            after_hash = after_state.get("screenshot_hash")
            changed = before_hash != after_hash
            return {
                "changed": changed,
                "similarity": 0.0 if changed else 1.0,
                "method": "hash_comparison_fallback",
                "error": str(e),
            }

    def _generate_recommendations(self, failure_classification: Dict, screen_diff: Dict) -> List[str]:
        """Generate actionable recommendations based on failure analysis."""
        recommendations = []
        reason = failure_classification.get("reason")

        if reason == "ELEMENT_NOT_FOUND":
            recommendations.append("Use detect_ui_elements to get current screen elements")
            recommendations.append("Try alternative element descriptions or coordinates")
            recommendations.append("Verify target window is visible and active")
        
        elif reason == "OUT_OF_BOUNDS":
            recommendations.append("Capture screen to get current resolution")
            recommendations.append("Recalculate coordinates within screen bounds")
        
        elif reason == "WINDOW_NOT_FOCUSED":
            recommendations.append("Add explicit focus_window step before interaction")
            recommendations.append("Use smart_focus_window for fuzzy matching")
            recommendations.append("Verify window exists with list_windows")
        
        elif reason == "TIMEOUT":
            recommendations.append("Increase wait time between steps")
            recommendations.append("Check if application is responding")
        
        else:
            recommendations.append("Capture current screen state for analysis")
            recommendations.append("Review error message for specific details")

        # Add screen diff insights
        if not screen_diff.get("changed"):
            recommendations.append("⚠️ Screen did not change - action may have had no effect")

        return recommendations

    def _evaluate_expected_effect(self, step_trace: Dict, changes: List[str]) -> Dict:
        """Score whether a step achieved its expected effect."""
        expectation = step_trace.get("expected_effect") or {}
        mode = expectation.get("verification_mode", "state_change")
        before = step_trace.get("before_state", {})
        after = step_trace.get("after_state", {})
        result = step_trace.get("result", {})

        passed = False
        reason = "No matching verification rule"

        if mode == "tool_success":
            passed = bool(result.get("success"))
            reason = "Tool reported success"
        elif mode in {"state_change", "interaction_effect", "keypress_effect", "typing_effect"}:
            passed = bool(changes)
            reason = "Observed UI state change" if passed else "No UI change observed"
        elif mode == "window_focus":
            expected_title = ""
            for signal in expectation.get("signals", []):
                if signal.get("type") == "active_window_matches":
                    expected_title = str(signal.get("title", "")).lower()
                    break
            active_title = str(after.get("active_window", "")).lower()
            passed = bool(expected_title) and expected_title in active_title
            reason = "Active window matches requested target" if passed else "Active window did not match requested target"
        elif mode == "window_or_process_change":
            passed = (
                before.get("active_window") != after.get("active_window")
                or bool(changes)
            )
            reason = "Application/window state changed" if passed else "No app/window state change observed"

        return {
            "step": step_trace.get("step"),
            "tool": step_trace.get("tool"),
            "operation": step_trace.get("operation"),
            "verification_mode": mode,
            "passed": passed,
            "reason": reason,
        }

    def verify_step_success(self, step_trace: Dict, expected_outcome: Optional[str] = None) -> Dict:
        """
        Verify a single step's success using LLM vision analysis.
        
        Args:
            step_trace: Single step from execution trace
            expected_outcome: Optional description of expected result
        """
        try:
            before_state = step_trace.get("before_state", {})
            after_state = step_trace.get("after_state", {})
            
            if not after_state.get("screenshot_path"):
                return {
                    "verified": False,
                    "reason": "No after screenshot available",
                }

            # Use LLM to analyze if action succeeded
            prompt = f"""RETURN ONLY VALID JSON. NO TEXT. NO EXPLANATION.

Analyze if this desktop automation step succeeded:

Step: {step_trace.get('tool')}.{step_trace.get('operation')}
Parameters: {step_trace.get('params')}
Expected: {expected_outcome or 'Action completed successfully'}

Before state: {before_state.get('active_window', 'unknown')}
After state: {after_state.get('active_window', 'unknown')}

Screen changed: {before_state.get('screenshot_hash') != after_state.get('screenshot_hash')}

Return this JSON structure:
{{"success": true, "confidence": 0.85, "reason": "Window changed as expected"}}

RULES:
- Return ONLY the JSON object
- success: true if step achieved its goal
- confidence: 0.0 to 1.0
- reason: brief explanation

JSON ONLY. START NOW:
"""

            analysis = self.llm.generate_structured(
                prompt,
                temperature=0.2,
                max_tokens=200,
                container="object",
            )
            if analysis:
                return {
                    "verified": analysis.get("success", False),
                    "confidence": analysis.get("confidence", 0.5),
                    "reason": analysis.get("reason", ""),
                }

            return {
                "verified": False,
                "reason": "Could not parse LLM response",
            }

        except Exception as e:
            logger.error(f"Step verification failed: {e}")
            return {
                "verified": False,
                "reason": str(e),
            }
