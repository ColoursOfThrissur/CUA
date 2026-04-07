"""
OCR-based clicking - bypass LLM planning for simple click tasks.

Flow:
1. Screenshot → OCR (pytesseract/easyocr)
2. Find text → Get coordinates
3. Click at coordinates

No LLM, no JSON, no planning.
"""
import logging
import re
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

_WINDOWS_TESSERACT_CANDIDATES = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)
_CONFUSABLE_CHAR_MAP = str.maketrans({
    "0": "o",
    "1": "l",
    "3": "e",
    "4": "a",
    "5": "s",
    "6": "g",
    "7": "t",
    "8": "b",
    "|": "l",
    "!": "l",
})


class OCRClicker:
    """Direct OCR-based clicking without LLM planning."""
    
    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
    
    def find_and_click(self, target_text: str, fuzzy: bool = True) -> Dict:
        """
        Find text on screen via OCR and click it.
        
        Args:
            target_text: Text to find (e.g., "File Explorer", "Library")
            fuzzy: Allow partial matches
        
        Returns:
            {"success": bool, "clicked_at": (x, y), "found_text": str}
        """
        try:
            # 1. Capture screen
            capture_result = self.services.call_tool(
                "ScreenPerceptionTool",
                "capture_screen",
                use_cache=False
            )
            
            if not capture_result.get("success"):
                return {"success": False, "error": "Screenshot failed"}
            
            image_path = capture_result["image_path"]
            
            # 2. Run OCR
            ocr_results = self._run_ocr(image_path)
            
            if not ocr_results:
                return {"success": False, "error": "OCR returned no results"}
            
            # 3. Find target text
            match = self._find_text_match(target_text, ocr_results, fuzzy=fuzzy)
            
            if not match:
                return {
                    "success": False,
                    "error": f"Text '{target_text}' not found on screen",
                    "available_text": [r["text"] for r in ocr_results[:10]]
                }
            
            # 4. Click at coordinates
            x, y = match["center"]
            original_size = capture_result.get("original_size", {}) or {}
            image_width = int(capture_result.get("width", 0) or 0)
            image_height = int(capture_result.get("height", 0) or 0)
            original_width = int(original_size.get("width", image_width) or image_width)
            original_height = int(original_size.get("height", image_height) or image_height)
            x, y = self._scale_to_desktop_coordinates(
                x,
                y,
                image_width=image_width,
                image_height=image_height,
                original_width=original_width,
                original_height=original_height,
            )
            
            click_result = self.services.call_tool(
                "InputAutomationTool",
                "click",
                x=x,
                y=y
            )
            
            return {
                "success": click_result.get("success", False),
                "clicked_at": (x, y),
                "found_text": match["text"],
                "confidence": match.get("confidence", 1.0)
            }
            
        except Exception as e:
            logger.error(f"OCR click failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _run_ocr(self, image_path: str, target_text: str = "") -> List[Dict]:
        """
        Run OCR on image and return text + bounding boxes.
        
        Returns:
            [{"text": str, "bbox": (x1,y1,x2,y2), "center": (x,y), "confidence": float}]
        """
        try:
            # Try pytesseract first (faster, simpler)
            import pytesseract
            from PIL import Image, ImageEnhance, ImageFilter, ImageOps

            self._configure_tesseract_binary(pytesseract)
            
            img = Image.open(image_path)
            results: List[Dict] = []
            seen: Dict[tuple, Dict] = {}

            for variant in self._build_ocr_variants(img, target_text=target_text):
                data = pytesseract.image_to_data(
                    variant["image"],
                    output_type=pytesseract.Output.DICT,
                    config=variant["config"],
                )
                variant_results = self._collect_tesseract_results(
                    data,
                    offset_x=int(variant["offset_x"]),
                    offset_y=int(variant["offset_y"]),
                    scale=float(variant["scale"]),
                )
                for result in variant_results:
                    key = (
                        self._normalize_text(result["text"]),
                        int(result["center"][0] // 8),
                        int(result["center"][1] // 8),
                    )
                    existing = seen.get(key)
                    if existing is None or result["confidence"] > existing["confidence"]:
                        seen[key] = result

            results = list(seen.values())
            if target_text:
                results = self._expand_with_phrase_candidates(results, target_text=target_text)
            logger.info(f"OCR found {len(results)} text elements across enhanced variants")
            return results
            
        except ImportError:
            logger.warning("pytesseract not available, trying easyocr")
            return self._run_easyocr(image_path)
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return []

    def _build_ocr_variants(self, img, *, target_text: str = "") -> List[Dict]:
        """Create a small set of OCR-friendly image variants."""
        variants = [
            {
                "name": "full_default",
                "image": img,
                "offset_x": 0,
                "offset_y": 0,
                "scale": 1.0,
                "config": "--oem 3 --psm 11",
            }
        ]

        full_enhanced = self._preprocess_for_ocr(img, upscale=2.0, threshold=True)
        variants.append(
            {
                "name": "full_enhanced",
                "image": full_enhanced,
                "offset_x": 0,
                "offset_y": 0,
                "scale": 2.0,
                "config": "--oem 3 --psm 6",
            }
        )

        if target_text:
            for name, region in self._build_target_regions(img):
                variants.append(
                    {
                        "name": name,
                        "image": self._preprocess_for_ocr(region["image"], upscale=2.5, threshold=True),
                        "offset_x": int(region["offset_x"]),
                        "offset_y": int(region["offset_y"]),
                        "scale": 2.5,
                        "config": "--oem 3 --psm 6",
                    }
                )

        return variants

    def _build_target_regions(self, img) -> List[Tuple[str, Dict[str, object]]]:
        """Create a small set of generic UI regions that often hold actionable labels."""
        width, height = img.size
        regions: List[Tuple[str, Dict[str, object]]] = []

        def add_region(name: str, box: Tuple[int, int, int, int]) -> None:
            left, top, right, bottom = box
            left = max(0, min(width, left))
            top = max(0, min(height, top))
            right = max(left + 1, min(width, right))
            bottom = max(top + 1, min(height, bottom))
            regions.append(
                (
                    name,
                    {
                        "image": img.crop((left, top, right, bottom)),
                        "offset_x": left,
                        "offset_y": top,
                    },
                )
            )

        add_region("top_strip_enhanced", (0, 0, width, max(1, int(height * 0.35))))
        add_region("left_strip_enhanced", (0, 0, max(1, int(width * 0.4)), height))
        add_region("right_strip_enhanced", (max(0, int(width * 0.6)), 0, width, height))
        add_region("center_band_enhanced", (int(width * 0.15), int(height * 0.15), int(width * 0.85), int(height * 0.85)))
        return regions

    def _preprocess_for_ocr(self, img, *, upscale: float = 2.0, threshold: bool = True):
        """Upscale and boost contrast to make small UI labels more OCR-friendly."""
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps

        working = img.convert("L")
        working = ImageOps.autocontrast(working)

        if upscale and upscale > 1.0:
            working = working.resize(
                (max(1, int(round(working.width * upscale))), max(1, int(round(working.height * upscale)))),
                Image.Resampling.LANCZOS,
            )

        working = ImageEnhance.Contrast(working).enhance(1.8)
        working = ImageEnhance.Sharpness(working).enhance(2.2)
        working = working.filter(ImageFilter.MedianFilter(size=3))

        if threshold:
            working = working.point(lambda px: 255 if px >= 170 else 0)

        return working

    def _collect_tesseract_results(
        self,
        data: Dict,
        *,
        offset_x: int = 0,
        offset_y: int = 0,
        scale: float = 1.0,
    ) -> List[Dict]:
        """Normalize pytesseract output and map variant coordinates back to base image space."""
        results: List[Dict] = []
        n_boxes = len(data["text"])

        for i in range(n_boxes):
            text = str(data["text"][i] or "").strip()
            conf_raw = str(data["conf"][i] or "").strip()
            try:
                conf = float(conf_raw)
            except Exception:
                conf = -1.0

            if not text or conf < 30:
                continue

            x = float(data["left"][i] or 0) / max(scale, 1e-6) + offset_x
            y = float(data["top"][i] or 0) / max(scale, 1e-6) + offset_y
            w = float(data["width"][i] or 0) / max(scale, 1e-6)
            h = float(data["height"][i] or 0) / max(scale, 1e-6)

            left = int(round(x))
            top = int(round(y))
            right = int(round(x + w))
            bottom = int(round(y + h))

            results.append(
                {
                    "text": text,
                    "bbox": (left, top, right, bottom),
                    "center": (int(round((left + right) / 2)), int(round((top + bottom) / 2))),
                    "confidence": max(0.0, min(conf / 100.0, 1.0)),
                }
            )

        return results

    def _expand_with_phrase_candidates(self, results: List[Dict], *, target_text: str) -> List[Dict]:
        """Merge adjacent OCR tokens into short phrases so split UI labels can still match."""
        if not results:
            return []

        target_words = max(1, len(str(target_text or "").split()))
        max_phrase_words = min(4, target_words + 1)
        merged: List[Dict] = list(results)
        seen = {
            (
                self._normalize_text(item.get("text", "")),
                tuple(item.get("bbox", ())),
            )
            for item in results
        }
        lines = self._group_results_by_line(results)
        for line in lines:
            for start in range(len(line)):
                bbox_gap_reference = max(8, int((line[start]["bbox"][3] - line[start]["bbox"][1]) * 1.5))
                phrase = [line[start]]
                for end in range(start + 1, min(len(line), start + max_phrase_words)):
                    previous = line[end - 1]
                    current = line[end]
                    gap = current["bbox"][0] - previous["bbox"][2]
                    if gap > bbox_gap_reference:
                        break
                    phrase.append(current)
                    phrase_text = " ".join(str(item["text"]).strip() for item in phrase if str(item["text"]).strip())
                    normalized = self._normalize_text(phrase_text)
                    if not normalized:
                        continue
                    bbox = (
                        min(int(item["bbox"][0]) for item in phrase),
                        min(int(item["bbox"][1]) for item in phrase),
                        max(int(item["bbox"][2]) for item in phrase),
                        max(int(item["bbox"][3]) for item in phrase),
                    )
                    key = (normalized, bbox)
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(
                        {
                            "text": phrase_text,
                            "bbox": bbox,
                            "center": (
                                int(round((bbox[0] + bbox[2]) / 2)),
                                int(round((bbox[1] + bbox[3]) / 2)),
                            ),
                            "confidence": min(float(item.get("confidence", 0.0) or 0.0) for item in phrase) * 0.98,
                        }
                    )
        return merged

    def _group_results_by_line(self, results: List[Dict]) -> List[List[Dict]]:
        """Group OCR boxes into loose text lines."""
        sorted_results = sorted(results, key=lambda item: (item["center"][1], item["bbox"][0]))
        lines: List[List[Dict]] = []

        for result in sorted_results:
            added = False
            for line in lines:
                reference = line[-1]
                line_height = max(1, int(reference["bbox"][3] - reference["bbox"][1]))
                y_delta = abs(int(result["center"][1]) - int(reference["center"][1]))
                if y_delta <= max(12, int(line_height * 0.75)):
                    line.append(result)
                    line.sort(key=lambda item: item["bbox"][0])
                    added = True
                    break
            if not added:
                lines.append([result])
        return lines
    
    def _run_easyocr(self, image_path: str) -> List[Dict]:
        """Fallback to easyocr if pytesseract unavailable."""
        try:
            import easyocr
            
            reader = easyocr.Reader(['en'], gpu=False)
            results_raw = reader.readtext(image_path)
            
            results = []
            for bbox, text, conf in results_raw:
                # bbox is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                x1, y1 = bbox[0]
                x2, y2 = bbox[2]
                
                results.append({
                    "text": text.strip(),
                    "bbox": (int(x1), int(y1), int(x2), int(y2)),
                    "center": (int((x1 + x2) / 2), int((y1 + y2) / 2)),
                    "confidence": conf
                })
            
            logger.info(f"EasyOCR found {len(results)} text elements")
            return results
            
        except Exception as e:
            logger.error(f"EasyOCR failed: {e}")
            return []

    def _configure_tesseract_binary(self, pytesseract_module) -> None:
        """Point pytesseract at a known Windows install when PATH is missing."""
        current = getattr(pytesseract_module.pytesseract, "tesseract_cmd", "") or ""
        if current and Path(current).exists():
            return
        for candidate in _WINDOWS_TESSERACT_CANDIDATES:
            if candidate.exists():
                pytesseract_module.pytesseract.tesseract_cmd = str(candidate)
                logger.info(f"OCR configured to use Tesseract at {candidate}")
                return
    
    def _find_text_match(self, target: str, ocr_results: List[Dict], fuzzy: bool = True) -> Optional[Dict]:
        """
        Find best match for target text in OCR results.
        
        Args:
            target: Text to find
            ocr_results: OCR output
            fuzzy: Allow partial/case-insensitive matches
        
        Returns:
            Best matching OCR result or None
        """
        target_lower = target.lower()
        target_norm = self._normalize_text(target)
        target_confusable_norm = self._normalize_text(target, resolve_confusables=True)

        # Exact match first
        for result in ocr_results:
            if result["text"].lower() == target_lower:
                return result
            if self._normalize_text(result["text"]) == target_norm:
                return result
            if self._normalize_text(result["text"], resolve_confusables=True) == target_confusable_norm:
                return result
        
        if not fuzzy:
            return None
        
        # Fuzzy match: contains or contained
        best_match = None
        best_score = 0
        
        for result in ocr_results:
            text_lower = result["text"].lower()
            text_norm = self._normalize_text(result["text"])
            text_confusable_norm = self._normalize_text(result["text"], resolve_confusables=True)
            
            # Check if target is in text or text is in target
            if target_lower in text_lower:
                score = len(target_lower) / len(text_lower)
                if score > best_score:
                    best_score = score
                    best_match = result
            elif text_lower in target_lower:
                score = len(text_lower) / len(target_lower)
                if score > best_score:
                    best_score = score
                    best_match = result
            else:
                ratio = SequenceMatcher(None, target_norm, text_norm).ratio() if target_norm and text_norm else 0.0
                confusable_ratio = (
                    SequenceMatcher(None, target_confusable_norm, text_confusable_norm).ratio()
                    if target_confusable_norm and text_confusable_norm
                    else 0.0
                )
                effective_ratio = max(ratio, confusable_ratio)
                weighted_ratio = effective_ratio * (0.45 + float(result.get("confidence", 0.0) or 0.0))
                if effective_ratio >= 0.72 and weighted_ratio > best_score:
                    best_score = weighted_ratio
                    best_match = result

        return best_match if best_score > 0.5 else None

    def _normalize_text(self, value: str, *, resolve_confusables: bool = False) -> str:
        """Normalize OCR text for robust matching."""
        normalized = str(value or "").lower()
        if resolve_confusables:
            normalized = normalized.translate(_CONFUSABLE_CHAR_MAP)
        return re.sub(r"[^a-z0-9]+", "", normalized)

    def _scale_to_desktop_coordinates(
        self,
        x: int,
        y: int,
        *,
        image_width: int,
        image_height: int,
        original_width: int,
        original_height: int,
    ) -> Tuple[int, int]:
        """Map OCR coordinates back to desktop space using the shared automation scaling."""
        try:
            from tools.computer_use.input_automation_tool import InputAutomationTool

            scaler = InputAutomationTool(orchestrator=self.orchestrator)
            return scaler._scale_coordinates(
                x,
                y,
                image_width=image_width,
                image_height=image_height,
                original_width=original_width,
                original_height=original_height,
                use_empirical_correction=False,
            )
        except Exception:
            return x, y
    
    def list_visible_text(self) -> Dict:
        """
        List all visible text on screen (for debugging).
        
        Returns:
            {"success": bool, "text_elements": [str]}
        """
        try:
            capture_result = self.services.call_tool(
                "ScreenPerceptionTool",
                "capture_screen",
                use_cache=False
            )
            
            if not capture_result.get("success"):
                return {"success": False, "error": "Screenshot failed"}
            
            ocr_results = self._run_ocr(capture_result["image_path"])
            
            return {
                "success": True,
                "text_elements": [r["text"] for r in ocr_results],
                "count": len(ocr_results)
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
