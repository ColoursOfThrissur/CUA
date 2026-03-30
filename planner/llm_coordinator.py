"""
LLM Request Coordinator - Ensures sequential execution of LLM calls.

Problem: Multiple agents (Planner, Verifier, Critic) make LLM calls independently,
causing Ollama request backlog (sequential processing creates 20+ second delays).

Solution: Single coordinator with request queue and lock mechanism.
"""
import threading
import time
import logging
from typing import Optional, Callable, Any
from queue import Queue, Empty

logger = logging.getLogger(__name__)


class LLMRequestCoordinator:
    """Coordinates LLM requests across multiple agents to prevent backlog."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern - one coordinator per process."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize coordinator (only once due to singleton)."""
        if self._initialized:
            return
        
        self._request_lock = threading.Lock()
        self._last_request_time = 0
        self._min_delay = 0.1  # 100ms minimum between requests
        self._request_count = 0
        self._total_wait_time = 0
        self._initialized = True
        
        logger.info("LLM Request Coordinator initialized")
    
    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute LLM call with coordination.
        
        Args:
            func: LLM function to call (e.g., llm_client._call_llm)
            *args, **kwargs: Arguments to pass to func
        
        Returns:
            Result from func
        """
        with self._request_lock:
            # Calculate wait time
            time_since_last = time.time() - self._last_request_time
            
            if time_since_last < self._min_delay:
                wait_time = self._min_delay - time_since_last
                logger.debug(f"⏳ [COORDINATOR] Waiting {wait_time:.3f}s before request #{self._request_count + 1} (preventing Ollama backlog)")
                time.sleep(wait_time)
                self._total_wait_time += wait_time
            
            # Execute request
            self._request_count += 1
            request_id = self._request_count
            start_time = time.time()
            
            logger.debug(f"🚀 [COORDINATOR] Executing request #{request_id}")
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.debug(f"✓ [COORDINATOR] Request #{request_id} completed in {duration:.2f}s")
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"✗ [COORDINATOR] Request #{request_id} failed after {duration:.2f}s: {e}")
                raise
            finally:
                self._last_request_time = time.time()
    
    def get_stats(self) -> dict:
        """Get coordinator statistics."""
        return {
            "total_requests": self._request_count,
            "total_wait_time": round(self._total_wait_time, 2),
            "avg_wait_time": round(self._total_wait_time / max(self._request_count, 1), 3),
        }
    
    def reset_stats(self):
        """Reset statistics (useful for testing)."""
        self._request_count = 0
        self._total_wait_time = 0


# Global coordinator instance
_coordinator = None

def get_coordinator() -> LLMRequestCoordinator:
    """Get global coordinator instance."""
    global _coordinator
    if _coordinator is None:
        _coordinator = LLMRequestCoordinator()
    return _coordinator
