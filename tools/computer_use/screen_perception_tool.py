"""
ScreenPerceptionTool - Vision and structured UI detection with caching and optimization.

Fixes:
- Image resizing (max 1024x1024) to prevent VRAM overflow
- Returns image_path + thumbnail instead of full base64
- Vision cache to avoid redundant captures
- Structured UI element detection
- Error classification
"""
import base64
import logging
import time
from io import BytesIO
from typing import Dict, List, Any, Optional
from pathlib import Path

from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

logger = logging.getLogger(__name__)

# Critical optimization constants
MAX_IMAGE_SIZE = (1024, 1024)
THUMBNAIL_SIZE = (256, 256)
CACHE_TTL_SECONDS = 2.0


class ScreenPerceptionTool(BaseTool):
    """Vision and structured UI detection with agent-optimized output."""

    def __init__(self, orchestrator=None):
        self.description = "Screen capture with vision analysis, structured UI detection, and intelligent caching"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        self.orchestrator = orchestrator
        
        # Vision cache
        self._last_screenshot = None
        self._last_screenshot_time = 0
        self._last_analysis = {}
        
        # Semantic cache (persistent)
        self._semantic_cache_enabled = True
        
        super().__init__()

    def register_capabilities(self):
        """Register vision and perception capabilities."""
        
        self.add_capability(ToolCapability(
            name="capture_screen",
            description="Capture screen with optimization: resized to 1024x1024, returns path + thumbnail (not full base64).",
            parameters=[
                Parameter("save_path", ParameterType.STRING, "Path to save screenshot. Default: output/screen_{timestamp}.png", required=False),
                Parameter("add_grid", ParameterType.BOOLEAN, "Add coordinate grid overlay. Default: false", required=False),
                Parameter("use_cache", ParameterType.BOOLEAN, "Use cached screenshot if <2s old. Default: true", required=False),
            ],
            returns="dict with image_path, thumbnail (small base64), width, height, cached",
            safety_level=SafetyLevel.LOW,
            examples=[{"save_path": "output/desktop.png"}, {"add_grid": True}],
            dependencies=["pyautogui", "pillow"]
        ), self._handle_capture_screen)

        self.add_capability(ToolCapability(
            name="invalidate_cache",
            description="Invalidate the in-memory screenshot and analysis cache after UI actions.",
            parameters=[],
            returns="dict with success",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=[]
        ), self._handle_invalidate_cache)

        self.add_capability(ToolCapability(
            name="detect_ui_elements",
            description="Structured UI element detection using vision model. Returns list of elements with coordinates and confidence.",
            parameters=[
                Parameter("element_types", ParameterType.LIST, "Types to detect: button, icon, text, input, window. Default: all", required=False),
                Parameter("screenshot_path", ParameterType.STRING, "Path to screenshot. If not provided, captures new one", required=False),
            ],
            returns="dict with elements list (label, type, x, y, confidence), image_path",
            safety_level=SafetyLevel.LOW,
            examples=[{"element_types": ["button", "icon"]}, {}],
            dependencies=["pyautogui", "pillow"]
        ), self._handle_detect_ui_elements)

        self.add_capability(ToolCapability(
            name="infer_visual_state",
            description="Infer high-level grounded app/view state from a screenshot. More robust than strict element arrays.",
            parameters=[
                Parameter("target_app", ParameterType.STRING, "Optional target app hint such as steam, chrome, vscode", required=False),
                Parameter("screenshot_path", ParameterType.STRING, "Path to screenshot. If not provided, captures new one", required=False),
            ],
            returns="dict with active_app, app visibility/activity, current_view, visible_targets, notes",
            safety_level=SafetyLevel.LOW,
            examples=[{"target_app": "steam"}, {}],
            dependencies=["pyautogui", "pillow"]
        ), self._handle_infer_visual_state)

        self.add_capability(ToolCapability(
            name="locate_target",
            description="Locate a single named target on screen and return click coordinates. More reliable than generic element arrays for actions like clicking Library.",
            parameters=[
                Parameter("target", ParameterType.STRING, "Visible target label/icon to locate", required=True),
                Parameter("target_app", ParameterType.STRING, "Optional target app hint such as steam, chrome, vscode", required=False),
                Parameter("screenshot_path", ParameterType.STRING, "Path to screenshot. If not provided, captures new one", required=False),
            ],
            returns="dict with found, label, x, y, bbox, confidence, image_path",
            safety_level=SafetyLevel.LOW,
            examples=[{"target": "Library", "target_app": "steam"}, {"target": "Steam"}],
            dependencies=["pyautogui", "pillow"]
        ), self._handle_locate_target)

        self.add_capability(ToolCapability(
            name="analyze_screen",
            description="LLM vision analysis of screen content. Optimized: uses cached screenshot if available.",
            parameters=[
                Parameter("prompt", ParameterType.STRING, "Analysis prompt. Default: 'Describe what you see'", required=False),
                Parameter("screenshot_path", ParameterType.STRING, "Path to screenshot. If not provided, uses cache or captures new", required=False),
            ],
            returns="dict with analysis (text), image_path, cached",
            safety_level=SafetyLevel.LOW,
            examples=[{"prompt": "What applications are open?"}, {"prompt": "Find the Chrome icon"}],
            dependencies=["pyautogui", "pillow"]
        ), self._handle_analyze_screen)

        self.add_capability(ToolCapability(
            name="extract_text",
            description="Hybrid OCR + vision extraction of visible text/items from the current screen.",
            parameters=[
                Parameter("prompt", ParameterType.STRING, "What text/items to extract from the screen", required=False),
                Parameter("target_app", ParameterType.STRING, "Optional app hint such as steam, chrome, vscode", required=False),
                Parameter("screenshot_path", ParameterType.STRING, "Path to screenshot. If not provided, captures or reuses current screen", required=False),
            ],
            returns="dict with items, text, source, image_path",
            safety_level=SafetyLevel.LOW,
            examples=[{"prompt": "Extract all visible game titles from the Steam library view", "target_app": "steam"}],
            dependencies=["pyautogui", "pillow", "pytesseract"]
        ), self._handle_extract_text)

        self.add_capability(ToolCapability(
            name="get_visible_text",
            description="Alias for extract_text focused on visible UI text.",
            parameters=[
                Parameter("prompt", ParameterType.STRING, "What text/items to extract from the screen", required=False),
                Parameter("target_app", ParameterType.STRING, "Optional app hint such as steam, chrome, vscode", required=False),
                Parameter("screenshot_path", ParameterType.STRING, "Path to screenshot. If not provided, captures or reuses current screen", required=False),
            ],
            returns="dict with items, text, source, image_path",
            safety_level=SafetyLevel.LOW,
            examples=[{"prompt": "Get all visible text in the Steam library", "target_app": "steam"}],
            dependencies=["pyautogui", "pillow", "pytesseract"]
        ), self._handle_extract_text)

        self.add_capability(ToolCapability(
            name="get_ui_text",
            description="Alias for extract_text focused on actionable UI text.",
            parameters=[
                Parameter("prompt", ParameterType.STRING, "What text/items to extract from the screen", required=False),
                Parameter("target_app", ParameterType.STRING, "Optional app hint such as steam, chrome, vscode", required=False),
                Parameter("screenshot_path", ParameterType.STRING, "Path to screenshot. If not provided, captures or reuses current screen", required=False),
            ],
            returns="dict with items, text, source, image_path",
            safety_level=SafetyLevel.LOW,
            examples=[{"prompt": "Extract visible game titles", "target_app": "steam"}],
            dependencies=["pyautogui", "pillow", "pytesseract"]
        ), self._handle_extract_text)

        self.add_capability(ToolCapability(
            name="get_screen_info",
            description="Get screen resolution and monitor information without capturing.",
            parameters=[],
            returns="dict with width, height, monitor_count, monitors list",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["pyautogui"]
        ), self._handle_get_screen_info)

        self.add_capability(ToolCapability(
            name="capture_region",
            description="Capture specific screen region with optimization.",
            parameters=[
                Parameter("x", ParameterType.INTEGER, "Top-left X coordinate", required=True),
                Parameter("y", ParameterType.INTEGER, "Top-left Y coordinate", required=True),
                Parameter("width", ParameterType.INTEGER, "Region width", required=True),
                Parameter("height", ParameterType.INTEGER, "Region height", required=True),
                Parameter("save_path", ParameterType.STRING, "Path to save. Default: output/region_{timestamp}.png", required=False),
            ],
            returns="dict with image_path, thumbnail, region coordinates",
            safety_level=SafetyLevel.LOW,
            examples=[{"x": 0, "y": 0, "width": 800, "height": 600}],
            dependencies=["pyautogui", "pillow"]
        ), self._handle_capture_region)

        self.add_capability(ToolCapability(
            name="get_comprehensive_state",
            description="OPTIMIZED: Single vision call that returns visual_state + UI elements + target location. 3x faster than separate calls.",
            parameters=[
                Parameter("target_app", ParameterType.STRING, "Target app hint (e.g., steam, chrome)", required=False),
                Parameter("locate_target", ParameterType.STRING, "Optional specific target to locate (e.g., Library button)", required=False),
                Parameter("element_types", ParameterType.LIST, "UI element types to detect. Default: [button, icon, text, window]", required=False),
            ],
            returns="dict with visual_state, elements, target_location (if requested), image_path",
            safety_level=SafetyLevel.LOW,
            examples=[
                {"target_app": "steam"},
                {"target_app": "steam", "locate_target": "Library"},
                {"target_app": "chrome", "element_types": ["button", "icon"]}
            ],
            dependencies=["pyautogui", "pillow"]
        ), self._handle_get_comprehensive_state)

    # ── Core Handlers ──────────────────────────────────────────────────────

    def _handle_capture_screen(self, **kwargs) -> dict:
        """Optimized screen capture with caching and size limits."""
        try:
            import pyautogui
            from PIL import Image, ImageDraw
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            save_path = kwargs.get("save_path")
            add_grid = kwargs.get("add_grid", False)
            use_cache = kwargs.get("use_cache", True)

            # Check cache
            if use_cache and self._is_cache_valid():
                logger.info("Using cached screenshot")
                return {
                    "success": True,
                    "image_path": self._last_screenshot.get("path"),
                    "thumbnail": self._last_screenshot.get("thumbnail"),
                    "width": self._last_screenshot.get("width"),
                    "height": self._last_screenshot.get("height"),
                    "original_size": {
                        "width": self._last_screenshot.get("original_width"),
                        "height": self._last_screenshot.get("original_height"),
                    },
                    "cached": True,
                }

            # Capture screenshot
            screenshot = pyautogui.screenshot()
            original_width, original_height = screenshot.size

            # CRITICAL: Resize to prevent VRAM overflow
            screenshot.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)
            width, height = screenshot.size

            # Add grid if requested
            if add_grid:
                draw = ImageDraw.Draw(screenshot)
                grid_spacing = 100
                for x in range(0, width, grid_spacing):
                    draw.line([(x, 0), (x, height)], fill=(255, 0, 0, 128), width=1)
                    draw.text((x + 2, 2), str(x), fill=(255, 0, 0))
                for y in range(0, height, grid_spacing):
                    draw.line([(0, y), (width, y)], fill=(255, 0, 0, 128), width=1)
                    draw.text((2, y + 2), str(y), fill=(255, 0, 0))

            # Generate paths
            if not save_path:
                timestamp = int(time.time() * 1000)
                save_path = f"output/screen_{timestamp}.png"
            
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)

            # Save full image
            screenshot.save(save_path)

            # Create thumbnail for return
            thumbnail = screenshot.copy()
            thumbnail.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            thumb_buffer = BytesIO()
            thumbnail.save(thumb_buffer, format="PNG")
            thumb_buffer.seek(0)
            thumbnail_b64 = base64.b64encode(thumb_buffer.read()).decode("utf-8")

            # Update cache
            self._last_screenshot = {
                "path": save_path,
                "thumbnail": thumbnail_b64,
                "width": width,
                "height": height,
                "original_width": original_width,
                "original_height": original_height,
            }
            self._last_screenshot_time = time.time()

            return {
                "success": True,
                "image_path": save_path,
                "thumbnail": thumbnail_b64,
                "width": width,
                "height": height,
                "original_size": {"width": original_width, "height": original_height},
                "cached": False,
            }

        except Exception as e:
            logger.error(f"capture_screen failed: {e}")
            return self._error_response("CAPTURE_FAILED", str(e))

    def _handle_detect_ui_elements(self, **kwargs) -> dict:
        """Structured UI element detection using vision model."""
        if not self.services or not self.services.llm:
            return self._error_response("LLM_REQUIRED", "LLM service required for UI detection")

        try:
            element_types = kwargs.get("element_types", ["button", "icon", "text", "input", "window"])
            screenshot_path = self._resolve_screenshot_reference(kwargs.get("screenshot_path"))

            # Get or capture screenshot
            if not screenshot_path:
                capture_result = self._handle_capture_screen(add_grid=True, use_cache=True)
                if not capture_result.get("success"):
                    return capture_result
                screenshot_path = capture_result["image_path"]
                screenshot_width = int(capture_result.get("width", 0) or 0)
                screenshot_height = int(capture_result.get("height", 0) or 0)
                original_size = capture_result.get("original_size") or {}
                original_width = int(original_size.get("width", screenshot_width) or screenshot_width)
                original_height = int(original_size.get("height", screenshot_height) or screenshot_height)
            else:
                screenshot_width, screenshot_height, original_width, original_height = self._resolve_image_dimensions(screenshot_path)

            # Build structured prompt
            prompt = f"""RETURN ONLY VALID JSON ARRAY. NO TEXT. NO EXPLANATION.

Analyze this screenshot and detect visible UI elements.

Target element types: {', '.join(element_types)}

Return ONLY a JSON array with this structure:
[
  {{
    "label": "Chrome icon",
    "text": "Chrome",
    "type": "icon",
    "x": 120,
    "y": 340,
    "bbox": {{"left": 96, "top": 316, "right": 144, "bottom": 364}},
    "confidence": 0.87
  }}
]

RULES:
- Return ONLY the JSON array - no markdown, no explanation
- Start with [ and end with ]
- Include only clearly visible, actionable UI elements
- x,y: center point of element
- bbox: approximate bounds
- confidence: 0.0 to 1.0
- Return [] if nothing relevant visible

JSON ARRAY ONLY. START NOW:
"""

            elements = self.services.llm.generate_structured(
                prompt,
                temperature=0.2,
                max_tokens=1200,
                container="array",
                image_path=screenshot_path,
            )

            if not isinstance(elements, list):
                return self._error_response(
                    "PARSE_FAILED",
                    "LLM did not return a valid JSON array of UI elements",
                    recoverable=True,
                )

            normalized_elements = self._normalize_detected_elements(elements)

            return {
                "success": True,
                "elements": normalized_elements,
                "element_count": len(normalized_elements),
                "image_path": screenshot_path,
                "image_size": {"width": screenshot_width, "height": screenshot_height},
                "original_size": {"width": original_width, "height": original_height},
            }

        except Exception as e:
            logger.error(f"detect_ui_elements failed: {e}")
            return self._error_response("DETECTION_FAILED", str(e), recoverable=True)

    def _handle_analyze_screen(self, **kwargs) -> dict:
        """LLM vision analysis with semantic caching."""
        if not self.services or not self.services.llm:
            return self._error_response("LLM_REQUIRED", "LLM service required for analysis")

        try:
            prompt = kwargs.get("prompt", "Describe what you see on the screen")
            screenshot_path = self._resolve_screenshot_reference(kwargs.get("screenshot_path"))
            cached = False

            # Get or capture screenshot
            cached = False
            if not screenshot_path:
                capture_result = self._handle_capture_screen(use_cache=True)
                if not capture_result.get("success"):
                    return capture_result
                screenshot_path = capture_result["image_path"]
                screenshot_width = int(capture_result.get("width", 0) or 0)
                screenshot_height = int(capture_result.get("height", 0) or 0)
                original_size = capture_result.get("original_size") or {}
                original_width = int(original_size.get("width", screenshot_width) or screenshot_width)
                original_height = int(original_size.get("height", screenshot_height) or screenshot_height)
            else:
                screenshot_width, screenshot_height, original_width, original_height = self._resolve_image_dimensions(screenshot_path)
                cached_info = self._last_screenshot or {}
                cached = str(screenshot_path) == str(cached_info.get("path", ""))

            # SEMANTIC CACHE: Check persistent cache by perceptual hash
            if self._semantic_cache_enabled:
                perceptual_hash = self._compute_perceptual_hash(screenshot_path)
                if perceptual_hash:
                    cached_analysis = self._get_cached_analysis(perceptual_hash)
                    if cached_analysis:
                        logger.info(f"Semantic cache HIT: {perceptual_hash[:12]}")
                        return {
                            "success": True,
                            "analysis": cached_analysis,
                            "image_path": screenshot_path,
                            "cached": True,
                            "cache_type": "semantic",
                        }

            # Check in-memory analysis cache (fallback)
            cache_key = f"{screenshot_path}:{prompt}"
            if cache_key in self._last_analysis:
                logger.info("Using in-memory cached analysis")
                return {
                    "success": True,
                    "analysis": self._last_analysis[cache_key],
                    "image_path": screenshot_path,
                    "cached": True,
                    "cache_type": "memory",
                }

            # Call LLM
            analysis = self.services.llm.generate(
                prompt,
                temperature=0.7,
                max_tokens=500,
                image_path=screenshot_path,
            )

            # Cache result in memory
            self._last_analysis[cache_key] = analysis
            
            # Cache result in persistent semantic cache
            if self._semantic_cache_enabled and perceptual_hash:
                self._save_to_semantic_cache(perceptual_hash, analysis, screenshot_path)

            return {
                "success": True,
                "analysis": analysis,
                "image_path": screenshot_path,
                "cached": False,
            }

        except Exception as e:
            logger.error(f"analyze_screen failed: {e}")
            return self._error_response("ANALYSIS_FAILED", str(e), recoverable=True)

    def _handle_extract_text(self, **kwargs) -> dict:
        """Hybrid OCR + vision extraction for text-first desktop tasks."""
        prompt = str(kwargs.get("prompt", "") or "").strip()
        target_app = str(kwargs.get("target_app", "") or "").strip().lower()
        screenshot_path = self._resolve_screenshot_reference(kwargs.get("screenshot_path"))

        try:
            if not screenshot_path:
                capture_result = self._handle_capture_screen(use_cache=True)
                if not capture_result.get("success"):
                    return capture_result
                screenshot_path = capture_result["image_path"]
            else:
                capture_result = {
                    "image_path": screenshot_path,
                }

            ocr_items = self._extract_text_items_from_ocr(screenshot_path)
            normalized_items = self._filter_extracted_items(ocr_items, prompt=prompt, target_app=target_app)
            active_window_title = self._get_active_window_title()

            # If OCR already gives us strong structured data, return it directly.
            if normalized_items and self._should_trust_ocr_extraction(
                normalized_items,
                prompt=prompt,
                target_app=target_app,
                active_window_title=active_window_title,
            ):
                response = {
                    "success": True,
                    "items": normalized_items,
                    "titles": normalized_items,
                    "text": "\n".join(normalized_items),
                    "source": "ocr",
                    "image_path": screenshot_path,
                    "ocr_count": len(ocr_items),
                }
                if active_window_title:
                    response["active_window_title"] = active_window_title
                if "game" in (prompt or "").lower() or "steam" in target_app or "library" in (prompt or "").lower():
                    response["games"] = normalized_items
                return response

            # Vision fallback for visual-understanding tasks or poor OCR.
            if not self.services or not self.services.llm:
                return {
                    "success": True,
                    "items": [],
                    "titles": [],
                    "text": "",
                    "source": "ocr_empty",
                    "image_path": screenshot_path,
                    "ocr_count": len(ocr_items),
                }

            structured = self.services.llm.generate_structured(
                self._build_extract_text_prompt(prompt=prompt, target_app=target_app, ocr_items=ocr_items),
                temperature=0.1,
                max_tokens=500,
                container="object",
                image_path=screenshot_path,
            )
            if not isinstance(structured, dict):
                return self._error_response(
                    "PARSE_FAILED",
                    "LLM did not return a valid extraction object",
                    recoverable=True,
                )

            items = [
                str(item).strip()
                for item in (structured.get("items") or structured.get("titles") or [])
                if str(item).strip()
            ]
            summary = str(structured.get("summary", "") or "").strip()
            response = {
                "success": True,
                "items": items,
                "titles": items,
                "text": "\n".join(items) if items else summary,
                "summary": summary,
                "source": "vision_hybrid",
                "image_path": screenshot_path,
                "ocr_count": len(ocr_items),
            }
            if active_window_title:
                response["active_window_title"] = active_window_title
            if "game" in (prompt or "").lower() or "steam" in target_app or "library" in (prompt or "").lower():
                response["games"] = items
            return response

        except Exception as e:
            logger.error(f"extract_text failed: {e}")
            return self._error_response("TEXT_EXTRACTION_FAILED", str(e), recoverable=True)

    def _handle_infer_visual_state(self, **kwargs) -> dict:
        """Infer robust scene state from screenshot for controller/policy decisions."""
        if not self.services or not self.services.llm:
            return self._error_response("LLM_REQUIRED", "LLM service required for visual state inference")

        try:
            target_app = str(kwargs.get("target_app", "")).strip().lower()
            screenshot_path = self._resolve_screenshot_reference(kwargs.get("screenshot_path"))
            if not screenshot_path:
                capture_result = self._handle_capture_screen(use_cache=True)
                if not capture_result.get("success"):
                    return capture_result
                screenshot_path = capture_result["image_path"]

            schema_hint = """{
  "active_app": "",
  "target_app_visible": false,
  "target_app_active": false,
  "current_view": "unknown",
  "library_visible": false,
  "visible_targets": [""],
  "notes": ""
}"""
            prompt = (
                "RETURN ONLY VALID JSON. NO TEXT. NO EXPLANATION.\n\n"
                "Analyze this screenshot and return this JSON structure:\n"
                f"{schema_hint}\n\n"
                f"Target app hint: {target_app or 'none'}\n\n"
                "RULES:\n"
                "- current_view: unknown | store | library | editor | browser | desktop\n"
                "- visible_targets: array of visible clickable labels\n"
                "- notes: one short sentence\n"
                "- Return ONLY the JSON object, no markdown\n\n"
                "JSON ONLY. START NOW:\n"
            )

            state = self.services.llm.generate_structured(
                prompt,
                temperature=0.0,
                max_tokens=700,
                container="object",
                image_path=screenshot_path,
            )
            if not isinstance(state, dict):
                return self._error_response(
                    "PARSE_FAILED",
                    "LLM did not return a valid JSON object for visual state",
                    recoverable=True,
                )

            normalized = {
                "active_app": str(state.get("active_app", "")).strip(),
                "target_app_visible": bool(state.get("target_app_visible", state.get("steam_visible", False))),
                "target_app_active": bool(state.get("target_app_active", state.get("steam_active", False))),
                "current_view": str(state.get("current_view", state.get("steam_view", "unknown")) or "unknown").strip().lower(),
                "library_visible": bool(state.get("library_visible", False)),
                "visible_targets": [
                    str(item).strip() for item in (state.get("visible_targets") or []) if str(item).strip()
                ][:20],
                "notes": str(state.get("notes", "")).strip(),
            }
            if normalized["current_view"] not in {"unknown", "store", "library", "editor", "browser", "desktop"}:
                normalized["current_view"] = normalized["current_view"] or "unknown"

            return {
                "success": True,
                "visual_state": normalized,
                "image_path": screenshot_path,
            }
        except Exception as e:
            logger.error(f"infer_visual_state failed: {e}")
            return self._error_response("STATE_INFERENCE_FAILED", str(e), recoverable=True)

    def _build_extract_text_prompt(self, *, prompt: str, target_app: str, ocr_items: List[str]) -> str:
        """Prompt for structured hybrid extraction."""
        ocr_preview = "\n".join(f"- {item}" for item in ocr_items[:40]) or "- none"
        requested = prompt or "Extract the important visible text/items from this screen."
        return (
            "RETURN ONLY VALID JSON. NO TEXT. NO EXPLANATION.\n\n"
            "Analyze this screenshot and return this JSON object:\n"
            '{\n  "items": ["item 1", "item 2"],\n  "summary": "short summary"\n}\n\n'
            f"Task: {requested}\n"
            f"Target app hint: {target_app or 'none'}\n"
            "OCR preview from the same screenshot:\n"
            f"{ocr_preview}\n\n"
            "RULES:\n"
            "- Prefer actual visible items from the screen\n"
            "- Use OCR preview when helpful, but correct OCR mistakes if the image makes the intended text clear\n"
            "- If the request asks for a list, return the list in items\n"
            "- If the screen is visual/non-text, infer the requested visible items and return them in items when possible\n"
            "- Keep summary short\n"
            "- Return ONLY the JSON object\n\n"
            "JSON ONLY. START NOW:\n"
        )

    def _extract_text_items_from_ocr(self, screenshot_path: str) -> List[str]:
        """Run OCR and return cleaned text candidates."""
        try:
            from tools.computer_use.ocr_clicker import OCRClicker
        except Exception:
            return []

        clicker = OCRClicker(orchestrator=self.orchestrator)
        ocr_results = clicker._run_ocr(screenshot_path)
        cleaned: List[str] = []
        seen = set()
        for result in ocr_results:
            text = str(result.get("text", "") or "").strip()
            if not text:
                continue
            normalized = self._normalize_extracted_token(text)
            if not normalized or normalized.lower() in seen:
                continue
            seen.add(normalized.lower())
            cleaned.append(normalized)
        return cleaned

    def _filter_extracted_items(self, items: List[str], *, prompt: str, target_app: str) -> List[str]:
        """Filter OCR tokens into more useful extracted items for common desktop tasks."""
        prompt_lower = (prompt or "").lower()
        target_app = (target_app or "").lower()
        if not items:
            return []

        blocked = {
            "store", "library", "community", "friends", "games", "help", "view",
            "home", "collections", "downloads", "search by name", "add a game",
            "manage downloads", "friends & chat", "stop", "steam", "cua", "agent",
            "forge", "repo", "remote", "tunnels", "ports", "terminal", "extensions",
            "explorer", "search", "vscode", "visual studio code",
        }
        filtered: List[str] = []
        for item in items:
            lower = item.lower()
            if lower in blocked:
                continue
            if len(item) <= 1:
                continue
            if target_app == "steam" and ("game" in prompt_lower or "library" in prompt_lower):
                if item.isupper() and len(item) < 4:
                    continue
            filtered.append(item)

        if target_app == "steam" and ("game" in prompt_lower or "library" in prompt_lower):
            return filtered[:20]
        return filtered[:25]

    def _should_trust_ocr_extraction(
        self,
        items: List[str],
        *,
        prompt: str,
        target_app: str,
        active_window_title: str = "",
    ) -> bool:
        """Reject noisy OCR when the screen or extracted list does not match the task."""
        if not items:
            return False

        prompt_lower = (prompt or "").lower()
        target_app_lower = (target_app or "").lower()
        active_title = (active_window_title or "").lower()
        is_steam_game_request = target_app_lower == "steam" and (
            "game" in prompt_lower or "library" in prompt_lower
        )

        if target_app_lower and active_title and target_app_lower not in active_title:
            return False

        if not is_steam_game_request:
            return True

        quality_items = [item for item in items if self._looks_like_game_title(item)]
        suspicious_items = [item for item in items if item not in quality_items]
        if len(quality_items) < 2:
            return False
        if suspicious_items and len(quality_items) <= len(suspicious_items):
            return False
        return True

    def _looks_like_game_title(self, item: str) -> bool:
        """Heuristic title check so Steam OCR does not pass through random UI noise."""
        value = str(item or "").strip()
        lower = value.lower()
        blocked_fragments = (
            "forge", "repo", "remote", "tunnels", "terminal", "extensions",
            "search", "store", "library", "friends", "community", "downloads",
            "agent", "steam",
        )
        if len(value) < 3:
            return False
        if any(fragment in lower for fragment in blocked_fragments):
            return False
        if sum(ch.isalpha() for ch in value) < 3:
            return False
        if len(value.split()) == 1 and value.isupper() and len(value) <= 5:
            return False
        return True

    def _get_active_window_title(self) -> str:
        """Best-effort active window title for extraction sanity checks."""
        if not self.services:
            return ""
        try:
            result = self.services.call_tool("SystemControlTool", "get_active_window")
            if isinstance(result, dict) and result.get("success"):
                return str(result.get("title", "") or "").strip()
        except Exception as exc:
            logger.debug(f"Active window lookup skipped during extraction: {exc}")
        return ""

    def _normalize_extracted_token(self, text: str) -> str:
        """Normalize OCR token while keeping useful title casing."""
        value = " ".join(str(text or "").strip().split())
        value = value.strip(".,:;|[](){}")
        return value

    def _handle_locate_target(self, **kwargs) -> dict:
        """Locate a specific target and return actionable click coordinates."""
        if not self.services or not self.services.llm:
            return self._error_response("LLM_REQUIRED", "LLM service required for target localization")

        try:
            target = str(kwargs.get("target", "")).strip()
            target_app = str(kwargs.get("target_app", "")).strip().lower()
            screenshot_path = self._resolve_screenshot_reference(kwargs.get("screenshot_path"))
            screenshot_width = 0
            screenshot_height = 0
            original_width = 0
            original_height = 0
            if not target:
                return self._error_response("INVALID_PARAMETER", "target parameter required")
            if not screenshot_path:
                capture_result = self._handle_capture_screen(use_cache=True)
                if not capture_result.get("success"):
                    return capture_result
                screenshot_path = capture_result["image_path"]
                screenshot_width = int(capture_result.get("width", 0) or 0)
                screenshot_height = int(capture_result.get("height", 0) or 0)
                original_size = capture_result.get("original_size") or {}
                original_width = int(original_size.get("width", screenshot_width) or screenshot_width)
                original_height = int(original_size.get("height", screenshot_height) or screenshot_height)
            else:
                screenshot_width, screenshot_height, original_width, original_height = self._resolve_image_dimensions(screenshot_path)

            schema_hint = """{
  "found": false,
  "label": "",
  "type": "text",
  "x": 0,
  "y": 0,
  "bbox": {"left": 0, "top": 0, "right": 0, "bottom": 0},
  "confidence": 0.0,
  "reason": ""
}"""
            prompt = (
                "RETURN ONLY VALID JSON. NO TEXT. NO EXPLANATION.\n\n"
                "Analyze this screenshot and return this JSON structure:\n"
                f"Target to locate: {target}\n"
                f"Target app hint: {target_app or 'none'}\n"
                f"{schema_hint}\n\n"
                "RULES:\n"
                "- Match the best visible UI target for the requested label\n"
                "- Prefer matches inside or belonging to the hinted target app when provided\n"
                "- found=true only if target is visibly present\n"
                "- x,y: center click point\n"
                "- bbox: bounds of visible element\n"
                "- confidence: 0.0 to 1.0\n"
                "- Return ONLY the JSON object\n\n"
                "JSON ONLY. START NOW:\n"
            )

            raw = self.services.llm.generate_structured(
                prompt,
                temperature=0.0,
                max_tokens=500,
                container="object",
                image_path=screenshot_path,
            )
            if not isinstance(raw, dict):
                return self._error_response(
                    "PARSE_FAILED",
                    "LLM did not return a valid JSON object for target localization",
                    recoverable=True,
                )

            found = bool(raw.get("found", False))
            label = str(raw.get("label", "")).strip() or target
            confidence = max(0.0, min(float(raw.get("confidence", 0.0) or 0.0), 1.0))
            bbox = raw.get("bbox") or {}
            if not isinstance(bbox, dict):
                bbox = {}
            x = int(raw.get("x", 0) or 0)
            y = int(raw.get("y", 0) or 0)
            left = int(bbox.get("left", x - 10) or (x - 10))
            top = int(bbox.get("top", y - 10) or (y - 10))
            right = int(bbox.get("right", x + 10) or (x + 10))
            bottom = int(bbox.get("bottom", y + 10) or (y + 10))

            if not found or x <= 0 or y <= 0:
                return {
                    "success": True,
                    "found": False,
                    "target": target,
                    "reason": str(raw.get("reason", "")).strip() or "target not confidently visible",
                    "image_path": screenshot_path,
                }

            return {
                "success": True,
                "found": True,
                "target": target,
                "label": label,
                "type": str(raw.get("type", "text") or "text").strip().lower(),
                "x": x,
                "y": y,
                "bbox": {
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                },
                "confidence": confidence,
                "reason": str(raw.get("reason", "")).strip(),
                "image_path": screenshot_path,
                "image_size": {"width": screenshot_width, "height": screenshot_height},
                "original_size": {"width": original_width, "height": original_height},
            }
        except Exception as e:
            logger.error(f"locate_target failed: {e}")
            return self._error_response("LOCATE_FAILED", str(e), recoverable=True)

    def _handle_invalidate_cache(self, **kwargs) -> dict:
        """Drop screenshot and analysis caches after state-changing actions."""
        self._last_screenshot = None
        self._last_screenshot_time = 0
        self._last_analysis = {}
        return {"success": True}

    def _handle_get_screen_info(self, **kwargs) -> dict:
        """Get screen info without capturing."""
        try:
            import pyautogui
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            width, height = pyautogui.size()
            
            monitors = []
            try:
                from screeninfo import get_monitors
                for i, m in enumerate(get_monitors()):
                    monitors.append({
                        "index": i,
                        "width": m.width,
                        "height": m.height,
                        "x": m.x,
                        "y": m.y,
                        "is_primary": getattr(m, 'is_primary', i == 0),
                    })
            except ImportError:
                monitors = [{"index": 0, "width": width, "height": height, "x": 0, "y": 0, "is_primary": True}]

            return {
                "success": True,
                "width": width,
                "height": height,
                "monitor_count": len(monitors),
                "monitors": monitors,
            }

        except Exception as e:
            logger.error(f"get_screen_info failed: {e}")
            return self._error_response("INFO_FAILED", str(e))

    def _handle_capture_region(self, **kwargs) -> dict:
        """Capture specific region with optimization."""
        try:
            import pyautogui
            from PIL import Image
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            x = int(kwargs.get("x"))
            y = int(kwargs.get("y"))
            width = int(kwargs.get("width"))
            height = int(kwargs.get("height"))
            save_path = kwargs.get("save_path")

            # Validate bounds
            screen_width, screen_height = pyautogui.size()
            if x < 0 or y < 0 or x + width > screen_width or y + height > screen_height:
                return self._error_response("OUT_OF_BOUNDS", 
                    f"Region out of bounds. Screen: {screen_width}x{screen_height}")

            # Capture region
            screenshot = pyautogui.screenshot(region=(x, y, width, height))

            # Resize if needed
            screenshot.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)

            # Generate path
            if not save_path:
                timestamp = int(time.time() * 1000)
                save_path = f"output/region_{timestamp}.png"
            
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            screenshot.save(save_path)

            # Create thumbnail
            thumbnail = screenshot.copy()
            thumbnail.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            thumb_buffer = BytesIO()
            thumbnail.save(thumb_buffer, format="PNG")
            thumb_buffer.seek(0)
            thumbnail_b64 = base64.b64encode(thumb_buffer.read()).decode("utf-8")

            return {
                "success": True,
                "image_path": save_path,
                "thumbnail": thumbnail_b64,
                "region": {"x": x, "y": y, "width": width, "height": height},
            }

        except Exception as e:
            logger.error(f"capture_region failed: {e}")
            return self._error_response("CAPTURE_FAILED", str(e))

    def _handle_get_comprehensive_state(self, **kwargs) -> dict:
        """OPTIMIZED: Single LLM call that returns everything needed for decision-making.
        
        Replaces 3 separate calls:
        - infer_visual_state (5s)
        - detect_ui_elements (5s)
        - locate_target (5s)
        
        With 1 unified call (5s total) = 3x speedup
        """
        if not self.services or not self.services.llm:
            return self._error_response("LLM_REQUIRED", "LLM service required")

        try:
            target_app = str(kwargs.get("target_app", "")).strip().lower()
            locate_target = str(kwargs.get("locate_target", "")).strip()
            element_types = kwargs.get("element_types", ["button", "icon", "text", "window"])

            # Capture screenshot once
            capture_result = self._handle_capture_screen(use_cache=True)
            if not capture_result.get("success"):
                return capture_result
            screenshot_path = capture_result["image_path"]
            screenshot_width = int(capture_result.get("width", 0) or 0)
            screenshot_height = int(capture_result.get("height", 0) or 0)
            original_size = capture_result.get("original_size") or {}
            original_width = int(original_size.get("width", screenshot_width) or screenshot_width)
            original_height = int(original_size.get("height", screenshot_height) or screenshot_height)

            # Build unified prompt
            schema = {
                "visual_state": {
                    "active_app": "",
                    "target_app_visible": False,
                    "target_app_active": False,
                    "current_view": "unknown",
                    "visible_targets": [],
                    "notes": ""
                },
                "elements": [
                    {
                        "label": "Chrome icon",
                        "text": "Chrome",
                        "type": "icon",
                        "x": 120,
                        "y": 340,
                        "bbox": {"left": 96, "top": 316, "right": 144, "bottom": 364},
                        "confidence": 0.87
                    }
                ]
            }
            
            if locate_target:
                schema["target_location"] = {
                    "found": False,
                    "label": "",
                    "x": 0,
                    "y": 0,
                    "bbox": {"left": 0, "top": 0, "right": 0, "bottom": 0},
                    "confidence": 0.0,
                    "reason": ""
                }

            import json
            prompt = f"""RETURN ONLY VALID JSON. NO TEXT. NO EXPLANATION. ONLY JSON.

Analyze this screenshot and return EXACTLY this JSON structure:

{json.dumps(schema, indent=2)}

Target app: {target_app or 'none'}
Element types to detect: {', '.join(element_types)}
{f'Specific target to locate: {locate_target}' if locate_target else ''}

RULES:
1. Return ONLY the JSON object - no markdown, no explanation, no thinking
2. Start with {{ and end with }}
3. Include BOTH "visual_state" and "elements" fields
4. visual_state.current_view: unknown | store | library | editor | browser | desktop
5. visual_state.visible_targets: array of visible clickable labels
6. elements: array with label, type, x, y, bbox, confidence
{f'7. target_location: locate "{locate_target}" and return coordinates' if locate_target else ''}

JSON ONLY. START NOW:
"""

            result = self.services.llm.generate_structured(
                prompt,
                temperature=0.1,
                max_tokens=900,
                container="object",
                image_path=screenshot_path,
            )

            if not isinstance(result, dict):
                return self._error_response("PARSE_FAILED", "LLM did not return valid JSON object")

            # Normalize visual_state
            visual_state_raw = result.get("visual_state", {})
            visual_state = {
                "active_app": str(visual_state_raw.get("active_app", "")).strip(),
                "target_app_visible": bool(visual_state_raw.get("target_app_visible", False)),
                "target_app_active": bool(visual_state_raw.get("target_app_active", False)),
                "current_view": str(visual_state_raw.get("current_view", "unknown") or "unknown").strip().lower(),
                "visible_targets": [
                    str(item).strip() for item in (visual_state_raw.get("visible_targets") or []) if str(item).strip()
                ][:20],
                "notes": str(visual_state_raw.get("notes", "")).strip(),
            }

            # Normalize elements
            elements_raw = result.get("elements", [])
            elements = self._normalize_detected_elements(elements_raw if isinstance(elements_raw, list) else [])

            # Build response
            response = {
                "success": True,
                "visual_state": visual_state,
                "elements": elements,
                "element_count": len(elements),
                "image_path": screenshot_path,
                "image_size": {"width": screenshot_width, "height": screenshot_height},
                "original_size": {"width": original_width, "height": original_height},
            }

            # Add target location if requested
            if locate_target:
                target_loc_raw = result.get("target_location", {})
                if isinstance(target_loc_raw, dict):
                    found = bool(target_loc_raw.get("found", False))
                    if found:
                        bbox = target_loc_raw.get("bbox", {})
                        x = int(target_loc_raw.get("x", 0) or 0)
                        y = int(target_loc_raw.get("y", 0) or 0)
                        response["target_location"] = {
                            "found": True,
                            "target": locate_target,
                            "label": str(target_loc_raw.get("label", locate_target)).strip(),
                            "x": x,
                            "y": y,
                            "bbox": {
                                "left": int(bbox.get("left", x - 10) or (x - 10)),
                                "top": int(bbox.get("top", y - 10) or (y - 10)),
                                "right": int(bbox.get("right", x + 10) or (x + 10)),
                                "bottom": int(bbox.get("bottom", y + 10) or (y + 10)),
                            },
                            "confidence": float(target_loc_raw.get("confidence", 0.0) or 0.0),
                            "reason": str(target_loc_raw.get("reason", "")).strip(),
                        }
                    else:
                        response["target_location"] = {
                            "found": False,
                            "target": locate_target,
                            "reason": str(target_loc_raw.get("reason", "not visible")).strip(),
                        }

            logger.info(f"[COMPREHENSIVE_STATE] Returned visual_state + {len(elements)} elements" + 
                       (f" + target_location({locate_target})" if locate_target else ""))

            return response

        except Exception as e:
            logger.error(f"get_comprehensive_state failed: {e}")
            return self._error_response("COMPREHENSIVE_STATE_FAILED", str(e), recoverable=True)

    # ── Helper Methods ─────────────────────────────────────────────────────

    def _is_cache_valid(self) -> bool:
        """Check if cached screenshot is still valid."""
        if not self._last_screenshot:
            return False
        age = time.time() - self._last_screenshot_time
        return age < CACHE_TTL_SECONDS

    def _resolve_image_dimensions(self, image_path: str) -> tuple[int, int, int, int]:
        """Resolve resized and original dimensions for a screenshot artifact."""
        try:
            path = str(self._resolve_screenshot_reference(image_path) or image_path or "")
            cached = self._last_screenshot or {}
            if path and path == cached.get("path"):
                width = int(cached.get("width", 0) or 0)
                height = int(cached.get("height", 0) or 0)
                original_width = int(cached.get("original_width", width) or width)
                original_height = int(cached.get("original_height", height) or height)
                return width, height, original_width, original_height
        except Exception:
            pass

        try:
            from PIL import Image

            with Image.open(image_path) as img:
                width, height = img.size
            return width, height, width, height
        except Exception:
            return 0, 0, 0, 0

    def _resolve_screenshot_reference(self, screenshot_path: Optional[str]) -> Optional[str]:
        """Resolve placeholders like 'current_screenshot' to the latest captured image path."""
        raw = str(screenshot_path or "").strip()
        if not raw:
            return None
        if raw.lower() in {"current_screenshot", "latest_screenshot", "last_screenshot"}:
            cached = self._last_screenshot or {}
            return cached.get("path")
        return raw

    def _normalize_detected_elements(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize element payloads into a stable artifact shape."""
        normalized = []
        for index, element in enumerate(elements, start=1):
            if not isinstance(element, dict):
                continue

            label = str(element.get("label") or element.get("text") or "").strip()
            text = str(element.get("text") or label).strip()
            element_type = str(element.get("type") or "unknown").strip().lower()
            confidence = float(element.get("confidence", 0.5) or 0.5)
            x = int(element.get("x", 0) or 0)
            y = int(element.get("y", 0) or 0)

            bbox = element.get("bbox") or {}
            if not isinstance(bbox, dict):
                bbox = {}
            left = int(bbox.get("left", x - 10) or (x - 10))
            top = int(bbox.get("top", y - 10) or (y - 10))
            right = int(bbox.get("right", x + 10) or (x + 10))
            bottom = int(bbox.get("bottom", y + 10) or (y + 10))

            normalized.append({
                "element_id": f"ui_{index}",
                "label": label,
                "text": text,
                "type": element_type,
                "x": x,
                "y": y,
                "bbox": {
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                },
                "confidence": max(0.0, min(confidence, 1.0)),
            })
        return normalized
    
    def _compute_perceptual_hash(self, image_path: str) -> Optional[str]:
        """Compute perceptual hash for semantic caching.
        
        Uses average hash (aHash) - fast and good for detecting similar screens.
        Returns 16-char hex string.
        """
        try:
            from PIL import Image
            import hashlib
            
            # Load and resize to 8x8 for perceptual hash
            img = Image.open(image_path).convert('L')  # Grayscale
            img = img.resize((8, 8), Image.Resampling.LANCZOS)
            
            # Compute average
            pixels = list(img.getdata())
            avg = sum(pixels) / len(pixels)
            
            # Build hash: 1 if pixel > avg, 0 otherwise
            bits = ''.join('1' if p > avg else '0' for p in pixels)
            
            # Convert to hex
            hash_int = int(bits, 2)
            hash_hex = format(hash_int, '016x')
            
            return hash_hex
            
        except Exception as e:
            logger.warning(f"Perceptual hash failed: {e}")
            return None
    
    def _get_cached_analysis(self, perceptual_hash: str) -> Optional[str]:
        """Retrieve cached analysis from semantic cache."""
        try:
            from infrastructure.persistence.sqlite.cua_database import get_conn
            from datetime import datetime, timedelta
            
            # Only use cache entries from last 5 minutes
            cutoff = (datetime.now() - timedelta(minutes=5)).isoformat()
            
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT screen_analysis, hit_count FROM screen_cache WHERE perceptual_hash = ? AND last_accessed > ?",
                    (perceptual_hash, cutoff)
                ).fetchone()
                
                if row:
                    # Update hit count and last_accessed
                    conn.execute(
                        "UPDATE screen_cache SET hit_count = hit_count + 1, last_accessed = ? WHERE perceptual_hash = ?",
                        (datetime.now().isoformat(), perceptual_hash)
                    )
                    return row[0]
            
            return None
            
        except Exception as e:
            logger.warning(f"Semantic cache read failed: {e}")
            return None
    
    def _save_to_semantic_cache(self, perceptual_hash: str, analysis: str, image_path: str) -> None:
        """Save analysis to semantic cache."""
        try:
            from infrastructure.persistence.sqlite.cua_database import get_conn
            from datetime import datetime
            
            now = datetime.now().isoformat()
            
            with get_conn() as conn:
                # Insert or replace
                conn.execute(
                    """INSERT OR REPLACE INTO screen_cache 
                       (perceptual_hash, screen_analysis, image_path, hit_count, created_at, last_accessed)
                       VALUES (?, ?, ?, 1, ?, ?)""",
                    (perceptual_hash, analysis, image_path, now, now)
                )
                
                # Cleanup old entries (keep last 100)
                conn.execute(
                    """DELETE FROM screen_cache WHERE id NOT IN (
                        SELECT id FROM screen_cache ORDER BY last_accessed DESC LIMIT 100
                    )"""
                )
            
        except Exception as e:
            logger.warning(f"Semantic cache write failed: {e}")

    def _error_response(self, error_type: str, message: str, recoverable: bool = False, **extra) -> dict:
        """Structured error response with classification."""
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
