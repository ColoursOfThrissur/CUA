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
from typing import Optional, Tuple, List, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

_WINDOWS_TESSERACT_CANDIDATES = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


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
    
    def _run_ocr(self, image_path: str) -> List[Dict]:
        """
        Run OCR on image and return text + bounding boxes.
        
        Returns:
            [{"text": str, "bbox": (x1,y1,x2,y2), "center": (x,y), "confidence": float}]
        """
        try:
            # Try pytesseract first (faster, simpler)
            import pytesseract
            from PIL import Image

            self._configure_tesseract_binary(pytesseract)
            
            img = Image.open(image_path)
            
            # Get detailed OCR data with bounding boxes
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            
            results = []
            n_boxes = len(data['text'])
            
            for i in range(n_boxes):
                text = data['text'][i].strip()
                conf = int(data['conf'][i])
                
                # Skip empty text or low confidence
                if not text or conf < 30:
                    continue
                
                x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                
                results.append({
                    "text": text,
                    "bbox": (x, y, x + w, y + h),
                    "center": (x + w // 2, y + h // 2),
                    "confidence": conf / 100.0
                })
            
            logger.info(f"OCR found {len(results)} text elements")
            return results
            
        except ImportError:
            logger.warning("pytesseract not available, trying easyocr")
            return self._run_easyocr(image_path)
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return []
    
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

        # Exact match first
        for result in ocr_results:
            if result["text"].lower() == target_lower:
                return result
            if self._normalize_text(result["text"]) == target_norm:
                return result
        
        if not fuzzy:
            return None
        
        # Fuzzy match: contains or contained
        best_match = None
        best_score = 0
        
        for result in ocr_results:
            text_lower = result["text"].lower()
            text_norm = self._normalize_text(result["text"])
            
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
                weighted_ratio = ratio * float(result.get("confidence", 0.0) or 0.0)
                if ratio >= 0.72 and weighted_ratio > best_score:
                    best_score = weighted_ratio
                    best_match = result

        return best_match if best_score > 0.5 else None

    def _normalize_text(self, value: str) -> str:
        """Normalize OCR text for robust matching."""
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
    
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
