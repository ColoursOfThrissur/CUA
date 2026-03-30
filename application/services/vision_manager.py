"""
Vision Manager - Handles vision model swapping and batching for computer use.

Ollama Vision API:
- Supports llava, qwen2-vl, moondream models
- Images passed as base64 in 'images' array
- Same /api/generate endpoint as text models
"""

import base64
import time
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from infrastructure.persistence.sqlite.logging import get_logger

logger = get_logger("vision_manager")


@dataclass
class VisionTask:
    """Single vision analysis task"""
    image_path: str
    prompt: str
    task_id: str = ""
    result: Optional[str] = None


class VisionManager:
    """Manages vision model loading/unloading and batching for efficient swaps."""
    
    def __init__(
        self,
        vision_model: str = "llava:7b-q4_0",
        main_model: str = "qwen2.5-coder:14b",
        ollama_url: str = "http://localhost:11434"
    ):
        self.vision_model = vision_model
        self.main_model = main_model
        self.ollama_url = ollama_url
        self.current_model = main_model  # Track which model is loaded
        
        # Batch mode
        self.batch_mode = False
        self.pending_tasks: List[VisionTask] = []
        
        # Stats
        self.swap_count = 0
        self.total_swap_time = 0.0
        self.vision_calls = 0
    
    def enable_batch_mode(self):
        """Enable batching - queue vision calls instead of executing immediately."""
        self.batch_mode = True
        self.pending_tasks = []
        logger.info("Vision batch mode enabled")
    
    def disable_batch_mode(self) -> List[Dict[str, Any]]:
        """Disable batching and execute all pending tasks."""
        if not self.pending_tasks:
            self.batch_mode = False
            return []
        
        logger.info(f"Executing vision batch: {len(self.pending_tasks)} tasks")
        results = self._execute_batch()
        self.pending_tasks = []
        self.batch_mode = False
        return results
    
    def analyze_image(
        self,
        image_path: str,
        prompt: str = "Describe what you see in this image in detail.",
        task_id: str = ""
    ) -> Optional[str]:
        """
        Analyze image with vision model.
        
        If batch_mode is enabled, queues the task and returns None.
        Otherwise executes immediately and returns result.
        """
        if self.batch_mode:
            # Queue for batch execution
            self.pending_tasks.append(VisionTask(
                image_path=image_path,
                prompt=prompt,
                task_id=task_id or f"task_{len(self.pending_tasks)}"
            ))
            logger.debug(f"Queued vision task: {task_id or 'unnamed'}")
            return None
        
        # Execute immediately
        return self._call_vision_model(image_path, prompt)
    
    def _call_vision_model(self, image_path: str, prompt: str) -> Optional[str]:
        """Single vision model call with swap tracking."""
        start = time.time()
        
        # Track if we're swapping models
        swapping = self.current_model != self.vision_model
        if swapping:
            logger.info(f"Swapping from {self.current_model} to {self.vision_model}")
            self.swap_count += 1
        
        # Read image as base64
        try:
            image_data = self._load_image_base64(image_path)
        except Exception as e:
            logger.error(f"Failed to load image {image_path}: {e}")
            return None
        
        # Call Ollama vision API
        try:
            payload = {
                "model": self.vision_model,
                "prompt": prompt,
                "images": [image_data],
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 500,  # Vision responses are typically shorter
                    "num_ctx": 4096,
                },
                "keep_alive": "10m"  # Keep loaded for potential follow-up calls
            }
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                llm_response = result.get("response", "")
                
                self.current_model = self.vision_model
                self.vision_calls += 1
                elapsed = time.time() - start
                
                if swapping:
                    self.total_swap_time += elapsed
                    logger.info(f"Model swap completed in {elapsed:.1f}s")
                else:
                    logger.debug(f"Vision call completed in {elapsed:.1f}s (no swap)")
                
                return llm_response
            else:
                logger.error(f"Vision API returned HTTP {response.status_code}: {response.text[:200]}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"Vision model call timed out after 60s")
            return None
        except Exception as e:
            logger.error(f"Vision model call failed: {e}")
            return None
    
    def _execute_batch(self) -> List[Dict[str, Any]]:
        """Execute all pending vision tasks in sequence (single model load)."""
        if not self.pending_tasks:
            return []
        
        results = []
        batch_start = time.time()
        
        for task in self.pending_tasks:
            result = self._call_vision_model(task.image_path, task.prompt)
            results.append({
                "task_id": task.task_id,
                "image_path": task.image_path,
                "result": result,
                "success": result is not None
            })
        
        batch_elapsed = time.time() - batch_start
        logger.info(
            f"Batch completed: {len(results)} tasks in {batch_elapsed:.1f}s "
            f"(avg {batch_elapsed/len(results):.1f}s per task)"
        )
        
        return results
    
    def ensure_main_model(self):
        """
        Ensure main model is loaded (call after vision operations).
        Triggers a swap back to the main model if currently on vision model.
        """
        if self.current_model != self.main_model:
            logger.info(f"Swapping back to {self.main_model}")
            start = time.time()
            
            try:
                # Dummy call to trigger swap
                payload = {
                    "model": self.main_model,
                    "prompt": "ready",
                    "stream": False,
                    "options": {"num_predict": 1},
                    "keep_alive": "30m"
                }
                
                response = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    self.current_model = self.main_model
                    elapsed = time.time() - start
                    self.swap_count += 1
                    self.total_swap_time += elapsed
                    logger.info(f"Swapped back to {self.main_model} in {elapsed:.1f}s")
                else:
                    logger.warning(f"Failed to swap back to main model: HTTP {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Failed to swap back to main model: {e}")
    
    def _load_image_base64(self, image_path: str) -> str:
        """Load image file and encode as base64."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        with open(path, "rb") as f:
            image_bytes = f.read()
        
        return base64.b64encode(image_bytes).decode("utf-8")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get vision manager statistics."""
        avg_swap_time = self.total_swap_time / self.swap_count if self.swap_count > 0 else 0
        
        return {
            "current_model": self.current_model,
            "vision_model": self.vision_model,
            "main_model": self.main_model,
            "swap_count": self.swap_count,
            "total_swap_time": round(self.total_swap_time, 2),
            "avg_swap_time": round(avg_swap_time, 2),
            "vision_calls": self.vision_calls,
            "batch_mode": self.batch_mode,
            "pending_tasks": len(self.pending_tasks)
        }
    
    def reset_stats(self):
        """Reset statistics counters."""
        self.swap_count = 0
        self.total_swap_time = 0.0
        self.vision_calls = 0
        logger.info("Vision manager stats reset")


# Global instance
_vision_manager: Optional[VisionManager] = None


def get_vision_manager() -> VisionManager:
    """Get or create global vision manager instance."""
    global _vision_manager
    if _vision_manager is None:
        from shared.config.config_manager import get_config
        config = get_config()
        
        # Get vision model from config or use default
        vision_model = getattr(config.llm, 'vision_model', 'llava:7b-q4_0')
        main_model = getattr(config.llm, 'model', 'qwen2.5-coder:14b')
        ollama_url = getattr(config.llm, 'ollama_url', 'http://localhost:11434')
        
        _vision_manager = VisionManager(
            vision_model=vision_model,
            main_model=main_model,
            ollama_url=ollama_url
        )
        logger.info(f"Vision manager initialized: vision={vision_model}, main={main_model}")
    
    return _vision_manager


def reset_vision_manager():
    """Reset global vision manager instance (for testing)."""
    global _vision_manager
    _vision_manager = None
