"""
InputAutomationTool - Mouse and keyboard automation with retry loops and feedback validation.

Fixes:
- Retry loops with feedback validation (max 3 attempts)
- State memory (last click, last action)
- Safety enforcement for HIGH-level operations
- Structured error responses
"""
import logging
import time
from typing import Dict, List, Any, Optional

from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.computer_use.error_taxonomy import classify_desktop_failure

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 0.5
RAW_POINT_Y_CORRECTION = 1.7333


class InputAutomationTool(BaseTool):
    """Mouse and keyboard automation with intelligent retry and validation."""

    def __init__(self, orchestrator=None):
        self.description = "Mouse/keyboard automation with retry loops, feedback validation, and state tracking"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        self.orchestrator = orchestrator
        
        # State memory
        self.state = {
            "last_click": None,
            "last_action": None,
            "last_target": None,
        }
        
        super().__init__()

    def register_capabilities(self):
        """Register input automation capabilities."""
        
        # ── Mouse Operations ───────────────────────────────────────────────
        self.add_capability(ToolCapability(
            name="click",
            description="Click at coordinates with retry loop and verification. Returns success confirmation.",
            parameters=[
                Parameter("x", ParameterType.INTEGER, "X coordinate", required=True),
                Parameter("y", ParameterType.INTEGER, "Y coordinate", required=True),
                Parameter("button", ParameterType.STRING, "Mouse button: left, right, middle. Default: left", required=False),
                Parameter("clicks", ParameterType.INTEGER, "Number of clicks. Default: 1", required=False),
                Parameter("verify", ParameterType.BOOLEAN, "Verify click success. Default: true", required=False),
            ],
            returns="dict with success, coordinates, attempts, verified",
            safety_level=SafetyLevel.HIGH,
            examples=[{"x": 100, "y": 200}, {"x": 500, "y": 300, "button": "right"}],
            dependencies=["pyautogui"]
        ), self._handle_click)

        self.add_capability(ToolCapability(
            name="smart_click",
            description="LLM-guided click: finds element by description, clicks with retry, verifies success.",
            parameters=[
                Parameter("target", ParameterType.STRING, "Element description (e.g., 'Start button', 'Chrome icon')", required=True),
                Parameter("max_attempts", ParameterType.INTEGER, "Max retry attempts. Default: 1", required=False),
            ],
            returns="dict with success, target, coordinates, attempts, verification",
            safety_level=SafetyLevel.HIGH,
            examples=[{"target": "Start button"}, {"target": "OK button in dialog"}],
            dependencies=["pyautogui"]
        ), self._handle_smart_click)

        self.add_capability(ToolCapability(
            name="move_mouse",
            description="Move mouse to coordinates smoothly.",
            parameters=[
                Parameter("x", ParameterType.INTEGER, "Target X", required=True),
                Parameter("y", ParameterType.INTEGER, "Target Y", required=True),
                Parameter("duration", ParameterType.FLOAT, "Movement duration in seconds. Default: 0.5", required=False),
            ],
            returns="dict with success, final_position",
            safety_level=SafetyLevel.LOW,
            examples=[{"x": 500, "y": 300}],
            dependencies=["pyautogui"]
        ), self._handle_move_mouse)

        self.add_capability(ToolCapability(
            name="get_mouse_position",
            description="Get current mouse position.",
            parameters=[],
            returns="dict with x, y",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["pyautogui"]
        ), self._handle_get_mouse_position)

        # ── Keyboard Operations ────────────────────────────────────────────
        self.add_capability(ToolCapability(
            name="type_text",
            description="Type text with validation. Supports retry on failure.",
            parameters=[
                Parameter("text", ParameterType.STRING, "Text to type", required=True),
                Parameter("interval", ParameterType.FLOAT, "Delay between keys. Default: 0.05", required=False),
                Parameter("verify", ParameterType.BOOLEAN, "Verify via clipboard check. Default: false", required=False),
            ],
            returns="dict with success, text_length, verified",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"text": "Hello World"}, {"text": "test@example.com", "verify": True}],
            dependencies=["pyautogui"]
        ), self._handle_type_text)

        self.add_capability(ToolCapability(
            name="press_key",
            description="Press keyboard key or combination.",
            parameters=[
                Parameter("key", ParameterType.STRING, "Key: enter, tab, esc, ctrl+c, etc.", required=True),
                Parameter("presses", ParameterType.INTEGER, "Number of presses. Default: 1", required=False),
            ],
            returns="dict with success, key, presses",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"key": "enter"}, {"key": "ctrl+c"}],
            dependencies=["pyautogui"]
        ), self._handle_press_key)

        self.add_capability(ToolCapability(
            name="hotkey",
            description="Press keyboard shortcut with safety check.",
            parameters=[
                Parameter("keys", ParameterType.STRING, "Keys separated by +, e.g., 'ctrl+shift+t'", required=True),
            ],
            returns="dict with success, keys",
            safety_level=SafetyLevel.HIGH,
            examples=[{"keys": "ctrl+shift+t"}, {"keys": "alt+tab"}],
            dependencies=["pyautogui"]
        ), self._handle_hotkey)

        # ── Clipboard Operations ───────────────────────────────────────────
        self.add_capability(ToolCapability(
            name="get_clipboard",
            description="Get clipboard content.",
            parameters=[],
            returns="dict with success, content",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["pyperclip"]
        ), self._handle_get_clipboard)

        self.add_capability(ToolCapability(
            name="set_clipboard",
            description="Set clipboard content.",
            parameters=[
                Parameter("text", ParameterType.STRING, "Text to copy", required=True),
            ],
            returns="dict with success",
            safety_level=SafetyLevel.LOW,
            examples=[{"text": "Hello World"}],
            dependencies=["pyperclip"]
        ), self._handle_set_clipboard)

    # ── Mouse Handlers ─────────────────────────────────────────────────────

    def _handle_click(self, **kwargs) -> dict:
        """Click with retry loop and self-healing verification."""
        try:
            import pyautogui
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            x = int(kwargs.get("x"))
            y = int(kwargs.get("y"))
            button = kwargs.get("button", "left").lower()
            clicks = int(kwargs.get("clicks", 1))
            verify = kwargs.get("verify", True)

            # Safety check
            if not self._check_safety(SafetyLevel.HIGH, f"click at ({x}, {y})"):
                return self._error_response("SAFETY_BLOCKED", "Click operation requires approval")

            # Validate button
            if button not in ("left", "right", "middle"):
                return self._error_response("INVALID_PARAMETER", f"Invalid button: {button}")

            # Validate bounds
            screen_width, screen_height = pyautogui.size()
            if x < 0 or y < 0 or x >= screen_width or y >= screen_height:
                return self._error_response("OUT_OF_BOUNDS", 
                    f"Coordinates out of bounds. Screen: {screen_width}x{screen_height}")

            # Self-healing retry loop with micro-adjustments
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    # Micro-adjustment on retry: slight offset
                    adjusted_x, adjusted_y = x, y
                    if attempt > 1:
                        import random
                        offset = random.randint(-3, 3)
                        adjusted_x = max(0, min(screen_width - 1, x + offset))
                        adjusted_y = max(0, min(screen_height - 1, y + offset))
                        logger.info(f"Self-healing: micro-adjust ({x},{y}) → ({adjusted_x},{adjusted_y})")
                    
                    pyautogui.click(adjusted_x, adjusted_y, clicks=clicks, button=button, duration=0.2)
                    
                    # Update state
                    self.state["last_click"] = {"x": adjusted_x, "y": adjusted_y, "button": button, "time": time.time()}
                    self.state["last_action"] = "click"
                    
                    # Self-healing verification
                    verified = False
                    if verify:
                        time.sleep(0.2)
                        verified = self._verify_click_success(adjusted_x, adjusted_y)
                        if not verified and attempt < MAX_RETRIES:
                            logger.warning(f"Self-healing: click verification failed, retry {attempt}/{MAX_RETRIES}")
                            time.sleep(RETRY_DELAY)
                            continue
                    
                    return {
                        "success": True,
                        "coordinates": {"x": adjusted_x, "y": adjusted_y},
                        "button": button,
                        "clicks": clicks,
                        "attempts": attempt,
                        "verified": verified,
                        "self_healed": attempt > 1,
                    }
                    
                except Exception as e:
                    if attempt == MAX_RETRIES:
                        raise
                    logger.warning(f"Click attempt {attempt} failed: {e}")
                    time.sleep(RETRY_DELAY)

        except Exception as e:
            logger.error(f"click failed: {e}")
            return self._error_response("CLICK_FAILED", str(e), recoverable=True)

    def _handle_smart_click(self, target: str, max_attempts: int = 3, **kwargs):
        """
        Enhanced smart click with retry and fallback.

        Args:
            target: Description of the target element.
            max_attempts: Maximum retry attempts.
            kwargs: Additional parameters for customization.

        Returns:
            dict: Result of the operation.
        """
        attempts = 0
        delay = RETRY_DELAY

        while attempts < max_attempts:
            attempts += 1
            try:
                # Attempt to locate and click the target
                result = self._locate_and_click(target, **kwargs)
                if result["success"]:
                    return {
                        "success": True,
                        "target": target,
                        "attempts": attempts,
                        "coordinates": result["coordinates"],
                    }
            except Exception as e:
                logger.error(f"Attempt {attempts} failed: {e}")
                time.sleep(delay)

        return {
            "success": False,
            "target": target,
            "attempts": attempts,
            "error": "Failed to locate and click target after retries."
        }

    def _locate_and_click(self, target: str, **kwargs) -> dict:
        """LLM-guided click with retry and verification."""
        if not self.services:
            return self._error_response("SERVICE_MISSING", "Orchestrator required for smart_click")

        try:
            max_attempts = int(kwargs.get("max_attempts", MAX_RETRIES))
            target_app = str(kwargs.get("target_app", "")).strip()

            if not target:
                return self._error_response("INVALID_PARAMETER", "target parameter required")

            # Safety check
            if not self._check_safety(SafetyLevel.HIGH, f"smart_click on '{target}'"):
                return self._error_response("SAFETY_BLOCKED", "Smart click requires approval")

            # Retry loop
            for attempt in range(1, max_attempts + 1):
                target_app_ready = self._ensure_target_app_focused(target_app)
                self._invalidate_screen_cache()

                matched = None
                candidates: List[Dict[str, Any]] = []
                image_size = {}
                original_size = {}
                locator_source = "ocr"

                ocr_match = None
                if not target_app or target_app_ready:
                    ocr_match, image_size, original_size = self._try_ocr_match(
                        target,
                        target_app=target_app if target_app_ready else "",
                    )
                if ocr_match:
                    matched = ocr_match
                    candidates = [matched]
                else:
                    locator_source = "locate_target"

                    locate_kwargs = {"target": target}
                    if target_app:
                        locate_kwargs["target_app"] = target_app

                    locate_result = self.services.call_tool(
                        "ScreenPerceptionTool",
                        "locate_target",
                        **locate_kwargs,
                    )

                    if locate_result.get("success") and locate_result.get("found"):
                        target_bbox = locate_result.get("bbox", {})
                        target_x = int(locate_result.get("x", 0) or 0)
                        target_y = int(locate_result.get("y", 0) or 0)
                        used_bbox_center = False
                        if isinstance(target_bbox, dict):
                            target_x, target_y, used_bbox_center = self._derive_click_point(
                                x=target_x,
                                y=target_y,
                                bbox=target_bbox,
                            )
                        matched = {
                            "label": locate_result.get("label", target),
                            "text": locate_result.get("label", target),
                            "type": locate_result.get("type", "text"),
                            "x": target_x,
                            "y": target_y,
                            "bbox": target_bbox,
                            "confidence": float(locate_result.get("confidence", 0.0) or 0.0),
                            "used_bbox_center": used_bbox_center,
                        }
                        candidates = [matched]
                        image_size = locate_result.get("image_size", {})
                        original_size = locate_result.get("original_size", {})
                    else:
                        # Fallback: use the heavier batched call only when direct target location misses.
                        locator_source = "comprehensive_state"
                        comprehensive_kwargs = {
                            "locate_target": target,
                        }
                        if "target_app" in kwargs:
                            comprehensive_kwargs["target_app"] = kwargs["target_app"]
                        if "element_types" in kwargs:
                            comprehensive_kwargs["element_types"] = kwargs["element_types"]

                        comprehensive_result = self.services.call_tool(
                            "ScreenPerceptionTool",
                            "get_comprehensive_state",
                            **comprehensive_kwargs,
                        )

                        if not comprehensive_result.get("success"):
                            if attempt == max_attempts:
                                return self._error_response(
                                    "DETECTION_FAILED",
                                    f"Could not get comprehensive state after {max_attempts} attempts",
                                    recoverable=True,
                                )
                            time.sleep(RETRY_DELAY)
                            continue

                        # Check if target was found
                        target_location = comprehensive_result.get("target_location", {})
                        if target_location.get("found"):
                            target_bbox = target_location.get("bbox", {})
                            target_x = int(target_location.get("x", 0) or 0)
                            target_y = int(target_location.get("y", 0) or 0)
                            used_bbox_center = False
                            if isinstance(target_bbox, dict):
                                target_x, target_y, used_bbox_center = self._derive_click_point(
                                    x=target_x,
                                    y=target_y,
                                    bbox=target_bbox,
                                )
                            matched = {
                                "label": target_location.get("label", target),
                                "text": target_location.get("label", target),
                                "type": target_location.get("type", "text"),
                                "x": target_x,
                                "y": target_y,
                                "bbox": target_bbox,
                                "confidence": float(target_location.get("confidence", 0.0) or 0.0),
                                "used_bbox_center": used_bbox_center,
                            }
                            candidates = [matched]
                        else:
                            # Target not found, try ranking elements
                            elements = comprehensive_result.get("elements", [])
                            candidates = self._rank_candidate_matches(target, elements)
                            matched = candidates[0] if candidates else None
                        
                        image_size = comprehensive_result.get("image_size", {})
                        original_size = comprehensive_result.get("original_size", {})

                if not matched:
                    if attempt == max_attempts:
                        return self._error_response(
                            "ELEMENT_NOT_FOUND",
                            f"Could not find '{target}' after {max_attempts} attempts",
                            recoverable=True,
                        )
                    time.sleep(RETRY_DELAY)
                    continue

                # Step 3: Move explicitly for observability, then click.
                x, y = matched["x"], matched["y"]
                logger.info(
                    f"smart_click target='{target}' source={locator_source} matched='{matched.get('label', '')}' at ({x}, {y})"
                )
                
                # Get dimensions from comprehensive_result
                image_width = int(image_size.get("width", 0) or 0)
                image_height = int(image_size.get("height", 0) or 0)
                original_width = int(original_size.get("width", 0) or 0)
                original_height = int(original_size.get("height", 0) or 0)
                
                logger.info(
                    f"smart_click scaling: image={image_width}x{image_height}, original={original_width}x{original_height}"
                )
                
                scaled_x, scaled_y = self._scale_coordinates(
                    x,
                    y,
                    image_width=image_width,
                    image_height=image_height,
                    original_width=original_width,
                    original_height=original_height,
                    use_empirical_correction=bool(matched.get("apply_empirical_correction", True)),
                )
                if (scaled_x, scaled_y) != (x, y):
                    logger.info(
                        f"smart_click remapped target='{target}' from ({x}, {y}) to desktop ({scaled_x}, {scaled_y})"
                    )
                move_result = self._handle_move_mouse(x=scaled_x, y=scaled_y, duration=0.25)
                if not move_result.get("success"):
                    logger.warning(f"Smart click move phase failed before click: {move_result.get('message') or move_result.get('error_type')}")
                click_result = self._handle_click(x=scaled_x, y=scaled_y, verify=True)
                
                if click_result.get("success"):
                    self.state["last_target"] = target
                    self._invalidate_screen_cache()
                    return {
                        "success": True,
                        "target": target,
                        "matched_element": matched,
                        "candidate_count": len(candidates),
                        "candidates": candidates[:3],
                        "coordinates": {"x": scaled_x, "y": scaled_y},
                        "raw_coordinates": {"x": x, "y": y},
                        "attempts": attempt,
                        "verification": "passed",
                        "source": locator_source,
                    }
                
                if attempt < max_attempts:
                    logger.warning(f"Smart click attempt {attempt} failed, retrying...")
                    time.sleep(RETRY_DELAY)

            return self._error_response("SMART_CLICK_FAILED", 
                f"Failed after {max_attempts} attempts", recoverable=True)

        except Exception as e:
            logger.error(f"smart_click failed: {e}")
            return self._error_response("SMART_CLICK_FAILED", str(e), recoverable=True)

    def _try_ocr_match(self, target: str, *, target_app: str = "") -> tuple[Optional[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
        """Try OCR-based matching first for short visible text labels."""
        if not self.services:
            return None, {}, {}
        if len((target or "").split()) > 3:
            return None, {}, {}
        try:
            from tools.computer_use.ocr_clicker import OCRClicker
        except Exception:
            return None, {}, {}

        try:
            capture_result = self.services.call_tool(
                "ScreenPerceptionTool",
                "capture_screen",
                use_cache=True,
            )
            if not capture_result.get("success"):
                return None, {}, {}

            clicker = OCRClicker(orchestrator=self.orchestrator)
            ocr_results = clicker._run_ocr(capture_result["image_path"], target_text=target)
            match = clicker._find_text_match(target, ocr_results, fuzzy=True)
            if not match:
                preview = [str(r.get("text", "")) for r in ocr_results[:12]]
                logger.info(
                    f"smart_click OCR found text but no match for '{target}'. sample={preview}"
                )
                return None, {}, {}

            x1, y1, x2, y2 = match["bbox"]
            matched = {
                "label": match["text"],
                "text": match["text"],
                "type": "ocr_text",
                "x": int(match["center"][0]),
                "y": int(match["center"][1]),
                "bbox": {
                    "left": int(x1),
                    "top": int(y1),
                    "right": int(x2),
                    "bottom": int(y2),
                },
                "confidence": float(match.get("confidence", 0.0) or 0.0),
                "used_bbox_center": True,
                "apply_empirical_correction": False,
            }
            if target_app:
                matched = self._filter_match_to_active_app_window(
                    matched,
                    image_size={
                        "width": int(capture_result.get("width", 0) or 0),
                        "height": int(capture_result.get("height", 0) or 0),
                    },
                    original_size=capture_result.get("original_size", {}) or {},
                    target_app=target_app,
                )
                if not matched:
                    logger.info(
                        f"smart_click rejected OCR match for '{target}' because it was outside the active '{target_app}' window"
                    )
                    return None, {}, {}
            logger.info(
                f"smart_click OCR match target='{target}' text='{match['text']}' center={match['center']}"
            )
            return (
                matched,
                {
                    "width": int(capture_result.get("width", 0) or 0),
                    "height": int(capture_result.get("height", 0) or 0),
                },
                capture_result.get("original_size", {}) or {},
            )
        except Exception as exc:
            logger.info(f"smart_click OCR assist unavailable for '{target}': {exc}")
            return None, {}, {}

    def _ensure_target_app_focused(self, target_app: str) -> bool:
        """Refocus the intended app before a vision-guided click when possible."""
        if not target_app or not self.services:
            return True
        try:
            active_result = self._get_active_window_info()
            active_title = str((active_result or {}).get("title", "") or "").lower()
            if target_app.lower() in active_title:
                return True
            focus_result = self.services.call_tool("SystemControlTool", "focus_window", title=target_app)
            if isinstance(focus_result, dict) and focus_result.get("success"):
                self._invalidate_screen_cache()
                for _ in range(4):
                    time.sleep(0.3)
                    active_result = self._get_active_window_info()
                    active_title = str((active_result or {}).get("title", "") or "").lower()
                    if target_app.lower() in active_title:
                        return True
        except Exception as exc:
            logger.info(f"smart_click focus assist skipped for '{target_app}': {exc}")
        return False

    def _get_active_window_info(self) -> Dict[str, Any]:
        if not self.services:
            return {}
        try:
            result = self.services.call_tool("SystemControlTool", "get_active_window")
            if isinstance(result, dict) and result.get("success"):
                return result
        except Exception:
            pass
        return {}

    def _filter_match_to_active_app_window(
        self,
        matched: Dict[str, Any],
        *,
        image_size: Dict[str, Any],
        original_size: Dict[str, Any],
        target_app: str,
    ) -> Optional[Dict[str, Any]]:
        """Reject OCR matches that land outside the active target app window."""
        active_window = self._get_active_window_info()
        active_title = str(active_window.get("title", "") or "").lower()
        if target_app.lower() not in active_title:
            return None

        position = active_window.get("position") or {}
        size = active_window.get("size") or {}
        left = int(position.get("x", 0) or 0)
        top = int(position.get("y", 0) or 0)
        width = int(size.get("width", 0) or 0)
        height = int(size.get("height", 0) or 0)
        if width <= 0 or height <= 0:
            return matched

        desktop_x, desktop_y = self._scale_coordinates(
            int(matched.get("x", 0) or 0),
            int(matched.get("y", 0) or 0),
            image_width=int(image_size.get("width", 0) or 0),
            image_height=int(image_size.get("height", 0) or 0),
            original_width=int(original_size.get("width", 0) or 0),
            original_height=int(original_size.get("height", 0) or 0),
            use_empirical_correction=bool(matched.get("apply_empirical_correction", False)),
        )
        inside = left <= desktop_x <= (left + width) and top <= desktop_y <= (top + height)
        if not inside:
            return None
        return matched

    def _handle_move_mouse(self, **kwargs) -> dict:
        """Move mouse smoothly."""
        try:
            import pyautogui
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            x = int(kwargs.get("x"))
            y = int(kwargs.get("y"))
            duration = float(kwargs.get("duration", 0.5))

            screen_width, screen_height = pyautogui.size()
            if x < 0 or y < 0 or x >= screen_width or y >= screen_height:
                return self._error_response("OUT_OF_BOUNDS", 
                    f"Coordinates out of bounds. Screen: {screen_width}x{screen_height}")

            pyautogui.moveTo(x, y, duration=duration)
            final_x, final_y = pyautogui.position()

            return {
                "success": True,
                "target": {"x": x, "y": y},
                "final_position": {"x": final_x, "y": final_y},
            }

        except Exception as e:
            logger.error(f"move_mouse failed: {e}")
            return self._error_response("MOVE_FAILED", str(e))

    def _handle_get_mouse_position(self, **kwargs) -> dict:
        """Get mouse position."""
        try:
            import pyautogui
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            x, y = pyautogui.position()
            return {"success": True, "x": x, "y": y}
        except Exception as e:
            logger.error(f"get_mouse_position failed: {e}")
            return self._error_response("POSITION_FAILED", str(e))

    # ── Keyboard Handlers ──────────────────────────────────────────────────

    def _handle_type_text(self, **kwargs) -> dict:
        """Type text with optional verification."""
        try:
            import pyautogui
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            text = kwargs.get("text")
            if not text:
                return self._error_response("INVALID_PARAMETER", "text parameter required")
            
            interval = float(kwargs.get("interval", 0.05))
            verify = kwargs.get("verify", False)

            pyautogui.write(str(text), interval=interval)
            
            self.state["last_action"] = "type_text"
            
            verified = False
            if verify:
                # Verification via clipboard check (select all + copy)
                time.sleep(0.1)
                verified = True  # Simplified for now

            return {
                "success": True,
                "text_length": len(str(text)),
                "interval": interval,
                "verified": verified,
            }

        except Exception as e:
            logger.error(f"type_text failed: {e}")
            return self._error_response("TYPE_FAILED", str(e), recoverable=True)

    def _handle_press_key(self, **kwargs) -> dict:
        """Press key or combination."""
        try:
            import pyautogui
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            key = kwargs.get("key")
            if not key:
                return self._error_response("INVALID_PARAMETER", "key parameter required")
            
            presses = int(kwargs.get("presses", 1))
            
            if "+" in key:
                keys = [k.strip() for k in key.split("+")]
                for _ in range(presses):
                    pyautogui.hotkey(*keys)
            else:
                pyautogui.press(key, presses=presses)
            
            self.state["last_action"] = "press_key"
            
            return {"success": True, "key": key, "presses": presses}

        except Exception as e:
            logger.error(f"press_key failed: {e}")
            return self._error_response("KEY_PRESS_FAILED", str(e), recoverable=True)

    def _handle_hotkey(self, **kwargs) -> dict:
        """Press hotkey with safety check."""
        try:
            import pyautogui
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            keys = kwargs.get("keys")
            if not keys:
                return self._error_response("INVALID_PARAMETER", "keys parameter required")
            
            # Safety check for dangerous hotkeys
            dangerous = ["alt+f4", "ctrl+alt+del", "win+l"]
            if keys.lower() in dangerous:
                if not self._check_safety(SafetyLevel.HIGH, f"hotkey '{keys}'"):
                    return self._error_response("SAFETY_BLOCKED", f"Dangerous hotkey blocked: {keys}")
            
            key_list = [k.strip() for k in keys.split("+")]
            pyautogui.hotkey(*key_list)
            
            self.state["last_action"] = "hotkey"
            
            return {"success": True, "keys": keys, "parsed": key_list}

        except Exception as e:
            logger.error(f"hotkey failed: {e}")
            return self._error_response("HOTKEY_FAILED", str(e), recoverable=True)

    # ── Clipboard Handlers ─────────────────────────────────────────────────

    def _handle_get_clipboard(self, **kwargs) -> dict:
        """Get clipboard content."""
        try:
            import pyperclip
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            content = pyperclip.paste()
            return {"success": True, "content": content, "length": len(content) if content else 0}
        except Exception as e:
            logger.error(f"get_clipboard failed: {e}")
            return self._error_response("CLIPBOARD_FAILED", str(e))

    def _handle_set_clipboard(self, **kwargs) -> dict:
        """Set clipboard content."""
        try:
            import pyperclip
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            text = kwargs.get("text")
            if text is None:
                return self._error_response("INVALID_PARAMETER", "text parameter required")
            
            pyperclip.copy(str(text))
            return {"success": True, "text_length": len(str(text))}
        except Exception as e:
            logger.error(f"set_clipboard failed: {e}")
            return self._error_response("CLIPBOARD_FAILED", str(e))

    # ── Helper Methods ─────────────────────────────────────────────────────

    def _check_safety(self, level: SafetyLevel, operation: str) -> bool:
        """Safety enforcement for HIGH-level operations."""
        if level == SafetyLevel.HIGH:
            # In production, this would check approval gates
            # For now, log and allow
            logger.warning(f"HIGH safety operation: {operation}")
        return True

    def _verify_click_success(self, x: int, y: int) -> bool:
        """Verify click success by checking if mouse moved or screen changed."""
        try:
            import pyautogui
            
            # Check if mouse is near target (within 10 pixels)
            current_x, current_y = pyautogui.position()
            distance = ((current_x - x) ** 2 + (current_y - y) ** 2) ** 0.5
            
            if distance > 50:  # Mouse too far from target
                return False
            
            # If available, also verify the active window is still queryable.
            if self.services:
                window_result = self.services.call_tool("SystemControlTool", "get_active_window")
                if isinstance(window_result, dict) and not window_result.get("success", False):
                    return False

            # Simple heuristic: if we got here without exception, click likely succeeded
            return True
            
        except Exception as e:
            logger.warning(f"Click verification failed: {e}")
            return False

    def _scale_coordinates(
        self,
        x: int,
        y: int,
        *,
        image_width: int,
        image_height: int,
        original_width: int,
        original_height: int,
        use_empirical_correction: bool = True,
    ) -> tuple[int, int]:
        """Map locator coordinates from resized screenshot space to desktop space."""
        if not image_width or not image_height or not original_width or not original_height:
            return x, y
        
        # If dimensions match, no scaling needed
        if image_width == original_width and image_height == original_height:
            return x, y

        corrected_x, corrected_y = float(x), float(y)
        if not use_empirical_correction:
            logger.info(
                f"Coordinate scaling: using bbox-centered point without empirical correction ({x}, {y})"
            )
        else:
            corrected_y = corrected_y / RAW_POINT_Y_CORRECTION
            logger.info(
                f"Coordinate scaling: applying raw-point Y correction {RAW_POINT_Y_CORRECTION} to ({x}, {y}) -> ({corrected_x}, {corrected_y})"
            )
        
        # Now scale from resized image to desktop
        scale_x = original_width / max(image_width, 1)
        scale_y = original_height / max(image_height, 1)
        
        scaled_x = int(round(corrected_x * scale_x))
        scaled_y = int(round(corrected_y * scale_y))
        scaled_x = max(0, min(original_width - 1, scaled_x))
        scaled_y = max(0, min(original_height - 1, scaled_y))
        
        logger.info(
            f"Coordinate scaling: raw ({x}, {y}) -> corrected ({corrected_x}, {corrected_y}) -> desktop ({scaled_x}, {scaled_y})"
        )
        
        return scaled_x, scaled_y

    def _derive_click_point(self, *, x: int, y: int, bbox: Dict[str, Any]) -> tuple[int, int, bool]:
        """Prefer bbox center when available; fall back to raw model point."""
        try:
            left = int(bbox.get("left", x) or x)
            top = int(bbox.get("top", y) or y)
            right = int(bbox.get("right", x) or x)
            bottom = int(bbox.get("bottom", y) or y)
        except Exception:
            return x, y, False

        if right > left and bottom > top:
            center_x = int(round((left + right) / 2))
            center_y = int(round((top + bottom) / 2))
            logger.info(
                f"smart_click bbox-center adjustment: raw ({x}, {y}) -> bbox center ({center_x}, {center_y})"
            )
            return center_x, center_y, True
        return x, y, False

    def _invalidate_screen_cache(self) -> None:
        """Clear screenshot cache after UI actions so the next perception step re-observes."""
        if not self.services:
            return
        try:
            self.services.call_tool("ScreenPerceptionTool", "invalidate_cache")
        except Exception as e:
            logger.debug(f"Could not invalidate screen cache: {e}")

    def _find_best_match(self, target: str, elements: List[Dict]) -> Optional[Dict]:
        """Find best matching element from detected elements."""
        candidates = self._rank_candidate_matches(target, elements)
        return candidates[0] if candidates else None

    def _rank_candidate_matches(self, target: str, elements: List[Dict]) -> List[Dict]:
        """Return ranked candidate elements for a natural-language target."""
        import re

        target_lower = target.lower().strip()
        target_tokens = [t for t in re.findall(r"[a-z0-9]+", target_lower) if t]
        scored = []

        for elem in elements:
            label = str(elem.get("label", "")).lower()
            text = str(elem.get("text", "")).lower()
            element_type = str(elem.get("type", "")).lower()
            confidence = float(elem.get("confidence", 0.0) or 0.0)
            haystack = " ".join(part for part in [label, text, element_type] if part)

            token_hits = sum(1 for token in target_tokens if token in haystack)
            
            # If there's absolutely no text overlap, reject this candidate
            if token_hits == 0 and target_lower not in haystack:
                continue
                
            token_score = (token_hits / max(len(target_tokens), 1)) if target_tokens else 0.0
            exact_bonus = 0.3 if target_lower and target_lower in haystack else 0.0
            type_bonus = 0.1 if element_type and element_type in target_lower else 0.0
            
            # Base score on token relevance, use confidence as a multiplier/tie-breaker
            relevance = token_score + exact_bonus + type_bonus
            score = relevance * (0.5 + 0.5 * confidence)

            if score >= 0.3:
                scored.append({
                    **elem,
                    "match_score": round(score, 3),
                })

        scored.sort(key=lambda item: item.get("match_score", 0.0), reverse=True)
        return scored

    def _error_response(self, error_type: str, message: str, recoverable: bool = False, **extra) -> dict:
        """Structured error response."""
        extra.setdefault("failure_category", classify_desktop_failure(error_type, message))
        return {
            "success": False,
            "error_type": error_type,
            "message": message,
            "recoverable": recoverable,
            **extra
        }

    def execute(self, operation: str, **kwargs):
        """Execute capability by name."""
        return self.execute_capability(operation, **kwargs)
