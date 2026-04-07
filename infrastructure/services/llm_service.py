"""LLM service wrapper for tools"""
import json
import time
import logging
import re
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
        if image_path:
            result = self._call_with_timeout(
                self._client.vision,
                prompt,
                image_path=image_path,
                temperature=temperature,
                max_tokens=max_tokens,
                expect_json=(format == "json"),
            )
            return result or ""

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

    def vision(self, prompt: str, *, image_path: str, temperature: float = 0.2, max_tokens: int = 1000, expect_json: bool = False) -> str:
        """Generate a vision response through the dedicated client path."""
        result = self._call_with_timeout(
            self._client.vision,
            prompt,
            image_path=image_path,
            temperature=temperature,
            max_tokens=max_tokens,
            expect_json=expect_json,
        )
        return result or ""

    def vision_structured(
        self,
        prompt: str,
        *,
        image_path: str,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        container: str = "object",
        repair_attempt: bool = False,
    ):
        """Structured vision helper that keeps JSON extraction on the vision path."""
        raw = self._call_with_timeout(
            self._client.vision,
            prompt,
            image_path=image_path,
            temperature=temperature,
            max_tokens=max_tokens,
            expect_json=True,
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
        )
        parsed = self._coerce_structured(repaired, container=container)
        return parsed if parsed is not None else ([] if container == "array" else {})

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
        if image_path:
            return self.vision_structured(
                prompt,
                image_path=image_path,
                temperature=temperature,
                max_tokens=max_tokens,
                container=container,
                repair_attempt=repair_attempt,
            )

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
        if isinstance(response, dict):
            for key in ("response", "content", "text", "message", "output", "thinking", "result"):
                if key in response:
                    nested = self._coerce_structured(response.get(key), container=container)
                    if nested is not None:
                        return nested
            parsed = response
        elif isinstance(response, list):
            parsed = response
        else:
            parsed = self._client._extract_json(response)
            if parsed is None:
                text = str(response).strip()
                for candidate in self._candidate_json_strings(text):
                    try:
                        parsed = json.loads(candidate)
                        break
                    except Exception:
                        continue

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

    def _candidate_json_strings(self, text: str):
        """Extract likely JSON substrings from messy local-model output."""
        if not text:
            return []

        candidates = []
        for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL):
            chunk = str(match.group(1) or "").strip()
            if chunk:
                candidates.append(chunk)

        for open_char, close_char in (("{", "}"), ("[", "]")):
            chunk = self._extract_balanced_chunk(text, open_char, close_char)
            if chunk:
                candidates.append(chunk)

        seen = set()
        unique = []
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            unique.append(candidate)
        return unique

    def _extract_balanced_chunk(self, text: str, open_char: str, close_char: str):
        """Return the last balanced JSON-like chunk for the given bracket type."""
        start = None
        depth = 0
        last_complete = None
        in_string = False
        escaped = False

        for index, ch in enumerate(text):
            if ch == "\\" and not escaped:
                escaped = True
                continue
            if ch == '"' and not escaped:
                in_string = not in_string
            escaped = False
            if in_string:
                continue
            if ch == open_char:
                if depth == 0:
                    start = index
                depth += 1
            elif ch == close_char and depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    last_complete = text[start:index + 1].strip()
        return last_complete
