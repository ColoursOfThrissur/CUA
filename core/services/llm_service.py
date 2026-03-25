"""LLM service wrapper for tools"""
import time
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

logger = logging.getLogger(__name__)

_LLM_TIMEOUT = 30   # seconds per attempt
_LLM_RETRIES = 2


class LLMService:
    """Provides LLM capabilities to tools — with timeout + retry."""

    def __init__(self, llm_client):
        self._client = llm_client

    def _call_with_timeout(self, fn, *args, **kwargs):
        """Run fn(*args, **kwargs) with a hard timeout; retry on transient failure."""
        for attempt in range(_LLM_RETRIES):
            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(fn, *args, **kwargs)
                try:
                    return future.result(timeout=_LLM_TIMEOUT)
                except FuturesTimeout:
                    logger.warning(f"LLM call timed out (attempt {attempt + 1}/{_LLM_RETRIES})")
                    future.cancel()
                except Exception as e:
                    logger.warning(f"LLM call error (attempt {attempt + 1}/{_LLM_RETRIES}): {e}")
            if attempt < _LLM_RETRIES - 1:
                time.sleep(2 ** attempt)
        return None

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """Generate text from prompt."""
        result = self._call_with_timeout(
            self._client._call_llm, prompt,
            temperature=temperature, max_tokens=max_tokens, expect_json=False
        )
        return result or ""

    def generate_json(self, prompt: str, temperature: float = 0.3, max_tokens: int = 1000) -> dict:
        """Generate JSON response."""
        response = self._call_with_timeout(
            self._client._call_llm, prompt,
            temperature=temperature, max_tokens=max_tokens, expect_json=True
        )
        if response:
            return self._client._extract_json(response) or {}
        return {}
