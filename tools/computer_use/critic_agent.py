"""
CriticAgent - Failure analysis and plan adaptation.

Responsibilities:
- Analyze WHY execution failed
- Determine HOW to fix the plan
- Provide adaptation strategy
- Learn from failure patterns
"""
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class CriticAgent:
    """Analyzes failures and generates adaptation strategies."""

    def __init__(self, llm_client):
        self.llm = llm_client
        self.failure_patterns = []

    def analyze_and_adapt(self, 
                          original_plan: List[Dict], 
                          execution_result: Dict, 
                          verification_result: Dict,
                          context: Dict) -> Dict:
        """
        Analyze failure and generate adaptation strategy.
        
        Returns:
        {
            "adaptation_strategy": str,
            "root_cause": str,
            "suggested_changes": list,
            "confidence": float,
            "should_replan": bool
        }
        """
        try:
            failure_analysis = verification_result.get("failure_analysis", {})
            failed_step_num = failure_analysis.get("failed_step", 0)
            failure_reason = failure_analysis.get("reason", "UNKNOWN")
            screen_diff = failure_analysis.get("screen_diff", {})
            
            # Determine root cause
            root_cause = self._determine_root_cause(
                failure_reason, 
                screen_diff, 
                execution_result,
                context
            )
            
            # Generate adaptation strategy
            strategy = self._generate_adaptation_strategy(
                root_cause,
                original_plan,
                failed_step_num,
                context
            )
            
            # Store failure pattern for learning
            self._record_failure_pattern({
                "failure_reason": failure_reason,
                "root_cause": root_cause,
                "strategy": strategy,
                "context": context,
            })
            
            return {
                "adaptation_strategy": strategy["type"],
                "root_cause": root_cause,
                "suggested_changes": strategy["changes"],
                "confidence": strategy["confidence"],
                "should_replan": strategy["should_replan"],
                "reasoning": strategy["reasoning"],
            }
            
        except Exception as e:
            logger.error(f"Critic analysis failed: {e}")
            return {
                "adaptation_strategy": "UNKNOWN",
                "root_cause": str(e),
                "suggested_changes": [],
                "confidence": 0.0,
                "should_replan": True,
            }

    def _determine_root_cause(self, 
                             failure_reason: str, 
                             screen_diff: Dict,
                             execution_result: Dict,
                             context: Dict) -> str:
        """
        Determine the root cause of failure.
        
        Root causes:
        - ENVIRONMENT_CHANGED: Screen state different than expected
        - TIMING_ISSUE: Action too fast/slow
        - WRONG_TARGET: Clicked/typed in wrong place
        - MISSING_PREREQUISITE: Required state not met
        - TOOL_LIMITATION: Tool cannot perform action
        """
        
        # Check if screen changed unexpectedly
        if not screen_diff.get("changed") and failure_reason != "ELEMENT_NOT_FOUND":
            return "NO_EFFECT"  # Action had no observable effect
        
        # Check timing
        trace = execution_result.get("trace", [])
        if trace:
            last_step = trace[-1]
            if last_step.get("result", {}).get("error_type") == "TIMEOUT":
                return "TIMING_ISSUE"
        
        # Map failure reasons to root causes
        cause_map = {
            "ELEMENT_NOT_FOUND": "ENVIRONMENT_CHANGED",
            "OUT_OF_BOUNDS": "WRONG_TARGET",
            "WINDOW_NOT_FOCUSED": "MISSING_PREREQUISITE",
            "TIMEOUT": "TIMING_ISSUE",
            "PERMISSION_DENIED": "TOOL_LIMITATION",
        }
        
        return cause_map.get(failure_reason, "UNKNOWN")

    def _generate_adaptation_strategy(self,
                                     root_cause: str,
                                     original_plan: List[Dict],
                                     failed_step_num: int,
                                     context: Dict) -> Dict:
        """
        Generate adaptation strategy based on root cause.
        
        Strategies:
        - RETRY_WITH_DELAY: Same plan, add delays
        - REDETECT_ELEMENTS: Re-scan UI before action
        - ADD_PREREQUISITE: Insert missing setup steps
        - ALTERNATIVE_APPROACH: Different tool/method
        - ABORT: Cannot be fixed
        """
        
        if root_cause == "TIMING_ISSUE":
            return {
                "type": "RETRY_WITH_DELAY",
                "changes": [
                    f"Add 1s delay before step {failed_step_num}",
                    "Increase wait_time parameters"
                ],
                "confidence": 0.8,
                "should_replan": False,
                "reasoning": "Action likely too fast, needs more time for UI to update"
            }
        
        elif root_cause == "ENVIRONMENT_CHANGED":
            return {
                "type": "REDETECT_ELEMENTS",
                "changes": [
                    f"Insert detect_ui_elements before step {failed_step_num}",
                    "Use smart_click instead of hardcoded coordinates"
                ],
                "confidence": 0.9,
                "should_replan": True,
                "reasoning": "UI elements not where expected, need fresh detection"
            }
        
        elif root_cause == "MISSING_PREREQUISITE":
            return {
                "type": "ADD_PREREQUISITE",
                "changes": [
                    f"Insert focus_window before step {failed_step_num}",
                    "Verify window is active before interaction"
                ],
                "confidence": 0.85,
                "should_replan": True,
                "reasoning": "Required state not met, need setup steps"
            }
        
        elif root_cause == "WRONG_TARGET":
            return {
                "type": "ALTERNATIVE_APPROACH",
                "changes": [
                    "Use detect_ui_elements to find correct target",
                    "Try alternative element description"
                ],
                "confidence": 0.7,
                "should_replan": True,
                "reasoning": "Target coordinates incorrect, need different approach"
            }
        
        elif root_cause == "NO_EFFECT":
            return {
                "type": "VERIFY_STATE",
                "changes": [
                    "Capture screen before and after action",
                    "Verify target element is interactable",
                    "Check if action requires different input method"
                ],
                "confidence": 0.6,
                "should_replan": True,
                "reasoning": "Action had no observable effect, may need different approach"
            }
        
        elif root_cause == "TOOL_LIMITATION":
            return {
                "type": "ABORT",
                "changes": [
                    "Action cannot be performed with current tools",
                    "Requires manual intervention or tool enhancement"
                ],
                "confidence": 0.9,
                "should_replan": False,
                "reasoning": "Tool limitation - cannot be fixed by replanning"
            }
        
        else:
            return {
                "type": "REPLAN_FULL",
                "changes": [
                    "Generate completely new plan",
                    "Analyze current screen state",
                    "Consider alternative workflow"
                ],
                "confidence": 0.5,
                "should_replan": True,
                "reasoning": "Unknown failure, need fresh approach"
            }

    def _record_failure_pattern(self, pattern: Dict):
        """Record failure pattern for learning."""
        self.failure_patterns.append({
            **pattern,
            "timestamp": self._get_timestamp(),
        })
        
        # Keep last 100 patterns
        if len(self.failure_patterns) > 100:
            self.failure_patterns = self.failure_patterns[-100:]

    def get_failure_patterns(self, limit: int = 10) -> List[Dict]:
        """Get recent failure patterns."""
        return self.failure_patterns[-limit:]

    def analyze_failure_trends(self) -> Dict:
        """
        Analyze failure patterns to identify trends.
        
        Returns insights like:
        - Most common failure reasons
        - Most effective adaptation strategies
        - Problematic tools/operations
        """
        if not self.failure_patterns:
            return {"trends": [], "insights": []}
        
        # Count failure reasons
        reason_counts = {}
        strategy_success = {}
        
        for pattern in self.failure_patterns:
            reason = pattern.get("failure_reason", "UNKNOWN")
            strategy = pattern.get("strategy", {}).get("type", "UNKNOWN")
            
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            strategy_success[strategy] = strategy_success.get(strategy, 0) + 1
        
        # Sort by frequency
        top_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_strategies = sorted(strategy_success.items(), key=lambda x: x[1], reverse=True)[:5]
        
        insights = []
        
        # Generate insights
        if top_reasons:
            most_common = top_reasons[0]
            insights.append(f"Most common failure: {most_common[0]} ({most_common[1]} occurrences)")
        
        if top_strategies:
            most_used = top_strategies[0]
            insights.append(f"Most used strategy: {most_used[0]} ({most_used[1]} times)")
        
        return {
            "trends": {
                "failure_reasons": dict(top_reasons),
                "adaptation_strategies": dict(top_strategies),
            },
            "insights": insights,
            "total_failures": len(self.failure_patterns),
        }

    def _get_timestamp(self) -> float:
        """Get current timestamp."""
        import time
        return time.time()
