"""
ExecutorAgent - Plan execution with state tracking.

Responsibilities:
- Execute plan steps sequentially
- Track execution state
- Capture before/after screenshots
- Return detailed execution trace
- NO planning, NO verification logic
"""
import logging
import time
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """Executes plans and tracks execution state."""

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.services = orchestrator.get_services("ExecutorAgent") if orchestrator else None

    def execute_plan(self, plan: List[Dict], capture_state: bool = True) -> Dict:
        """
        Execute plan steps and return detailed trace.
        
        Returns:
        {
            "success": bool,
            "trace": [{"step": int, "tool": str, "operation": str, "result": dict, "before_state": dict, "after_state": dict}],
            "final_state": dict,
            "execution_time": float,
            "failed_step": int (if failed)
        }
        """
        start_time = time.time()
        trace = []
        
        try:
            # Execute each step
            for i, step in enumerate(plan, 1):
                logger.info(f"Executing step {i}/{len(plan)}: {step.get('tool')}.{step.get('operation')}")

                # Capture before state
                before_state = self._capture_state() if capture_state else {}
                
                # Track step execution time
                step_start = time.time()

                # Execute step
                step_result = self._execute_step(step)
                
                # Calculate step duration
                step_duration_ms = (time.time() - step_start) * 1000

                # Capture after state
                after_state = self._capture_state() if capture_state else {}

                # Build trace entry
                expected_effect = self._build_step_expectation(step, before_state)
                trace_entry = {
                    "step": i,
                    "tool": step.get("tool"),
                    "operation": step.get("operation"),
                    "params": step.get("parameters") or step.get("params", {}),
                    "expected_effect": expected_effect,
                    "result": step_result,
                    "success": step_result.get("success", False),
                    "before_state": before_state,
                    "after_state": after_state,
                    "timestamp": time.time(),
                    "duration_ms": step_duration_ms,
                }
                trace.append(trace_entry)
                
                # Record telemetry
                self._record_telemetry(
                    tool=step.get("tool"),
                    operation=step.get("operation"),
                    duration_ms=step_duration_ms,
                    result=step_result,
                )

                # Stop on failure
                if not step_result.get("success"):
                    logger.warning(f"Step {i} failed: {step_result.get('message', 'unknown error')}")
                    
                    execution_time = time.time() - start_time
                    result = {
                        "success": False,
                        "trace": trace,
                        "failed_step": i,
                        "failure_reason": step_result.get("message", "unknown"),
                        "execution_time": execution_time,
                        "final_state": after_state,
                    }
                    
                    return result

                # Brief delay between steps
                time.sleep(0.2)

            # All steps succeeded
            execution_time = time.time() - start_time
            final_state = trace[-1]["after_state"] if trace else {}
            
            result = {
                "success": True,
                "trace": trace,
                "execution_time": execution_time,
                "final_state": final_state,
                "steps_completed": len(trace),
            }
            
            return result

        except Exception as e:
            logger.error(f"Execution failed: {e}")
            execution_time = time.time() - start_time
            
            result = {
                "success": False,
                "trace": trace,
                "error": str(e),
                "execution_time": execution_time,
            }
            
            return result

    def _execute_step(self, step: Dict) -> Dict:
        """Execute a single step via orchestrator with proactive validation and smart retry."""
        try:
            tool = step.get("tool")
            operation = step.get("operation")
            # Support both "parameters" and "params" for compatibility
            params = step.get("parameters") or step.get("params", {})

            if not tool or not operation:
                return {
                    "success": False,
                    "message": "Invalid step: missing tool or operation",
                    "error_type": "INVALID_STEP",
                }

            if not self.services:
                return {
                    "success": False,
                    "message": "Services not available",
                    "error_type": "SERVICE_UNAVAILABLE",
                }

            # PROACTIVE VALIDATION: Check preconditions before execution
            validation_result = self._validate_preconditions(tool, operation, params)
            if not validation_result.get("valid"):
                logger.warning(f"Proactive validation failed: {validation_result.get('reason')}")
                return {
                    "success": False,
                    "message": f"Precondition failed: {validation_result.get('reason')}",
                    "error_type": "PRECONDITION_FAILED",
                    "validation": validation_result,
                }

            # SMART RETRY: Execute with error-type-specific retry strategy
            result = self._execute_with_smart_retry(tool, operation, params)
            
            # Ensure result is a dict
            if not isinstance(result, dict):
                return {
                    "success": False,
                    "message": f"Tool returned invalid result type: {type(result)}",
                    "error_type": "INVALID_RESULT",
                }
            
            return result

        except Exception as e:
            logger.error(f"Step execution failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "message": str(e),
                "error_type": "EXECUTION_ERROR",
            }

    def _capture_state(self) -> Dict:
        """
        Capture current environment state.
        
        Returns:
        {
            "screenshot_path": str,
            "screenshot_hash": str,
            "active_window": str,
            "mouse_position": dict,
            "timestamp": float
        }
        """
        state = {
            "timestamp": time.time(),
        }

        try:
            # Capture screenshot
            screen_result = self.services.call_tool(
                "ScreenPerceptionTool",
                "capture_screen",
                use_cache=False
            )
            if screen_result.get("success"):
                state["screenshot_path"] = screen_result.get("image_path")
                state["screenshot_hash"] = self._hash_image(screen_result.get("image_path"))

            # Get active window
            window_result = self.services.call_tool(
                "SystemControlTool",
                "get_active_window"
            )
            if window_result.get("success"):
                state["active_window"] = window_result.get("title")

            # Get mouse position
            mouse_result = self.services.call_tool(
                "InputAutomationTool",
                "get_mouse_position"
            )
            if mouse_result.get("success"):
                state["mouse_position"] = {"x": mouse_result.get("x"), "y": mouse_result.get("y")}

        except Exception as e:
            logger.warning(f"State capture incomplete: {e}")

        return state

    def _build_step_expectation(self, step: Dict, before_state: Dict) -> Dict:
        """Infer what success should look like for a step."""
        tool = step.get("tool", "")
        operation = step.get("operation", "")
        params = step.get("parameters") or step.get("params", {})

        expectation = {
            "description": step.get("expected_output") or f"{tool}.{operation} should complete successfully",
            "verification_mode": "state_change",
            "signals": [],
        }

        if tool == "SystemControlTool" and operation == "launch_application":
            expectation["verification_mode"] = "window_or_process_change"
            expectation["signals"] = [
                {"type": "window_changed"},
                {"type": "active_window_changed"},
                {"type": "process_started", "name": params.get("name", "")},
            ]
        elif tool == "SystemControlTool" and operation in {"focus_window", "smart_focus_window"}:
            expectation["verification_mode"] = "window_focus"
            expectation["signals"] = [
                {"type": "active_window_matches", "title": params.get("title") or params.get("description", "")},
            ]
        elif tool == "InputAutomationTool" and operation in {"click", "smart_click"}:
            expectation["verification_mode"] = "interaction_effect"
            expectation["signals"] = [
                {"type": "screen_changed"},
                {"type": "active_window_changed"},
            ]
        elif tool == "InputAutomationTool" and operation == "type_text":
            expectation["verification_mode"] = "typing_effect"
            expectation["signals"] = [
                {"type": "screen_changed"},
                {"type": "text_length", "length": len(str(params.get("text", "")))},
            ]
        elif tool == "InputAutomationTool" and operation in {"press_key", "hotkey"}:
            expectation["verification_mode"] = "keypress_effect"
            expectation["signals"] = [
                {"type": "screen_changed"},
                {"type": "active_window_changed"},
            ]
        elif tool == "ScreenPerceptionTool":
            expectation["verification_mode"] = "tool_success"
            expectation["signals"] = [{"type": "tool_success_only"}]

        expectation["before_active_window"] = before_state.get("active_window")
        return expectation

    def _hash_image(self, image_path: str) -> str:
        """Generate hash of image for comparison."""
        try:
            import hashlib
            from PIL import Image
            
            img = Image.open(image_path)
            img_bytes = img.tobytes()
            return hashlib.md5(img_bytes).hexdigest()
        except Exception as e:
            logger.warning(f"Image hashing failed: {e}")
            return ""
    
    def _validate_preconditions(self, tool: str, operation: str, params: Dict) -> Dict:
        """Proactively validate preconditions before execution.
        
        Checks:
        1. Target window still exists (for focus/click operations)
        2. System responsive (not frozen)
        3. Required parameters present
        
        Returns: {"valid": bool, "reason": str}
        """
        try:
            # Check 1: Window operations - verify window exists
            if tool == "SystemControlTool" and operation in {"focus_window", "smart_focus_window"}:
                title = params.get("title") or params.get("description")
                if title:
                    windows_result = self.services.call_tool("SystemControlTool", "list_windows")
                    if windows_result.get("success"):
                        windows = windows_result.get("windows", [])
                        window_titles = [w.get("title", "").lower() for w in windows]
                        if not any(title.lower() in wt for wt in window_titles):
                            return {"valid": False, "reason": f"Target window '{title}' not found"}
            
            # Check 2: System responsiveness - verify active window queryable
            try:
                active_result = self.services.call_tool("SystemControlTool", "get_active_window")
                if not active_result.get("success"):
                    return {"valid": False, "reason": "System unresponsive - cannot query active window"}
            except Exception as e:
                return {"valid": False, "reason": f"System check failed: {e}"}
            
            # Check 3: Required parameters present (basic check)
            if tool == "InputAutomationTool" and operation == "type_text":
                if not params.get("text"):
                    return {"valid": False, "reason": "Missing required parameter: text"}
            
            return {"valid": True, "reason": "All preconditions met"}
            
        except Exception as e:
            logger.warning(f"Precondition validation error: {e}")
            # Don't block execution on validation errors
            return {"valid": True, "reason": f"Validation skipped: {e}"}
    
    def _record_telemetry(self, tool: str, operation: str, duration_ms: float, result: Dict) -> None:
        """Record detailed execution telemetry to database."""
        try:
            from infrastructure.persistence.sqlite.cua_database import get_conn
            from datetime import datetime
            
            # Extract telemetry data
            retry_count = result.get("attempts", 1) - 1  # attempts includes first try
            self_healed = 1 if result.get("self_healed", False) else 0
            error_type = result.get("error_type", "") if not result.get("success") else ""
            cache_hit = 1 if result.get("cached", False) or result.get("cache_type") else 0
            
            now = datetime.now().isoformat()
            
            with get_conn() as conn:
                conn.execute(
                    """INSERT INTO execution_telemetry 
                       (tool_name, operation, duration_ms, retry_count, self_healed, error_type, cache_hit, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (tool, operation, duration_ms, retry_count, self_healed, error_type, cache_hit, now)
                )
                
                # Cleanup old entries (keep last 1000)
                conn.execute(
                    """DELETE FROM execution_telemetry WHERE id NOT IN (
                        SELECT id FROM execution_telemetry ORDER BY timestamp DESC LIMIT 1000
                    )"""
                )
            
        except Exception as e:
            logger.warning(f"Telemetry recording failed: {e}")
    
    def _execute_with_smart_retry(self, tool: str, operation: str, params: Dict, max_retries: int = 2) -> Dict:
        """Execute with error-type-specific retry strategies.
        
        Different retry strategies based on error type:
        - ELEMENT_NOT_FOUND: Wait for UI to load, then retry
        - WINDOW_NOT_ACTIVE: Refocus window, then retry
        - TIMEOUT: Increase timeout, then retry
        - CLICK_FAILED: Already has self-healing in InputAutomationTool
        - Others: Simple retry with delay
        """
        for attempt in range(max_retries + 1):
            # Execute
            result = self.services.call_tool(tool, operation, **params)
            
            # Success - return immediately
            if result.get("success"):
                if attempt > 0:
                    logger.info(f"Smart retry succeeded on attempt {attempt + 1}")
                return result
            
            # Last attempt - return failure
            if attempt == max_retries:
                return result
            
            # Analyze error and apply smart retry strategy
            error_type = result.get("error_type", "")
            error_message = result.get("message", "")
            
            logger.info(f"Smart retry: attempt {attempt + 1}/{max_retries + 1}, error_type={error_type}")
            
            # Strategy 1: ELEMENT_NOT_FOUND - UI might be loading
            if error_type == "ELEMENT_NOT_FOUND" or "not found" in error_message.lower():
                logger.info("Strategy: Wait for UI to load (1.5s)")
                time.sleep(1.5)
                continue
            
            # Strategy 2: WINDOW_NOT_ACTIVE - Refocus window
            if "window" in error_message.lower() and "not" in error_message.lower():
                logger.info("Strategy: Refocus window")
                if tool == "SystemControlTool":
                    # Already trying to focus, just wait
                    time.sleep(0.5)
                else:
                    # Try to refocus active window
                    try:
                        active_result = self.services.call_tool("SystemControlTool", "get_active_window")
                        if active_result.get("success") and active_result.get("title"):
                            self.services.call_tool("SystemControlTool", "focus_window", title=active_result["title"])
                    except Exception:
                        pass
                    time.sleep(0.5)
                continue
            
            # Strategy 3: TIMEOUT - Increase patience
            if error_type == "TIMEOUT" or "timeout" in error_message.lower():
                logger.info("Strategy: Increase timeout tolerance (2s)")
                time.sleep(2.0)
                continue
            
            # Strategy 4: System unresponsive - Wait longer
            if "unresponsive" in error_message.lower() or "frozen" in error_message.lower():
                logger.info("Strategy: Wait for system recovery (3s)")
                time.sleep(3.0)
                continue
            
            # Default: Simple retry with delay
            logger.info("Strategy: Default retry (0.5s delay)")
            time.sleep(0.5)
        
        # Should never reach here
        return result
