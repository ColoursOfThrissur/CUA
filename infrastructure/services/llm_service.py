"""LLM service wrapper for tools"""
import json
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

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1000, image_path: str = None, format: str = None) -> str:
        """Generate text from prompt, optionally with image for vision models."""
        result = self._call_with_timeout(
            self._client._call_llm, prompt,
            temperature=temperature, max_tokens=max_tokens, expect_json=(format=="json"), image_path=image_path
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

    def generate_structured(
        self,
        prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        container: str = "object",
        repair_attempt: bool = False,
        image_path: str = None,
    ):
        """
        Generate structured output robustly for local reasoning models.

        Qwen reasoning/VL models can place the useful payload in a thinking field,
        wrap JSON in prose/markdown, or emit almost-correct JSON. This helper keeps
        the handling in one place instead of repeating ad hoc extraction logic in
        each tool/agent.

        Args:
            prompt: Primary instruction.
            temperature: Sampling temperature.
            max_tokens: Max output tokens.
            container: "object" or "array".
            repair_attempt: Whether to run one repair pass if parsing fails.
        """
        raw = self._call_with_timeout(
            self._client._call_llm,
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            expect_json=True,
            image_path=image_path,
        )

        parsed = self._coerce_structured(raw, container=container)
        if parsed is not None:
            return parsed

        if not repair_attempt or not raw:
            return [] if container == "array" else {}

        repair_prompt = (
            f"Convert the following output into valid JSON {container} only.\n"
            f"Do not add explanation, markdown, or comments.\n\n"
            f"Original output:\n{raw}"
        )
        repaired = self._call_with_timeout(
            self._client._call_llm,
            repair_prompt,
            temperature=0.0,
            max_tokens=max_tokens,
            expect_json=True,
            image_path=image_path,
        )
        parsed = self._coerce_structured(repaired, container=container)
        return parsed if parsed is not None else ([] if container == "array" else {})

    def _coerce_structured(self, response, *, container: str = "object"):
        """Parse and normalize structured output to the requested container."""
        if response is None:
            return None

        parsed = None
        if isinstance(response, (dict, list)):
            parsed = response
        else:
            parsed = self._client._extract_json(response)

        if parsed is None:
            return None

        if container == "array":
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                for key in ("items", "results", "elements", "steps", "data"):
                    value = parsed.get(key)
                    if isinstance(value, list):
                        return value
            return None

        if container == "object":
            if isinstance(parsed, dict):
                return parsed
            return None

        return parsed
