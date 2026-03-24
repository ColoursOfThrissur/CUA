"""
LLM provider implementations for API-key based models (OpenAI, Gemini).
Each provider handles its own HTTP format, auth, and response parsing.
"""
import json
import requests
from typing import Optional, Dict, Any, List


class OpenAIProvider:
    """OpenAI-compatible provider (works for OpenAI, Azure OpenAI, and compatible APIs)."""

    CHAT_ENDPOINT = "https://api.openai.com/v1/chat/completions"
    TOOLS_ENDPOINT = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str, base_url: str = None, timeout: int = 120):
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://api.openai.com").rstrip("/")
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, prompt: str, temperature: float, max_tokens: int, expect_json: bool) -> Optional[str]:
        """Single-turn generation via /v1/chat/completions."""
        messages = [{"role": "user", "content": prompt}]
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 16384,
        }
        if expect_json:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            import logging as _log
            _log.getLogger(__name__).error(f"OpenAI HTTP {resp.status_code}: {resp.text[:300]}")
            return None
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).error(f"OpenAI generate exception: {e}")
            return None

    def chat_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        timeout: int = None,
    ) -> Dict[str, Any]:
        """Chat endpoint with tool definitions. Returns raw response dict."""
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
        }
        resp = requests.post(
            f"{self.base_url}/v1/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=timeout or self.timeout,
        )
        resp.raise_for_status()
        choice = resp.json()["choices"][0]
        msg = choice["message"]
        # Normalise to Ollama-style shape so ToolCallingClient can reuse parsing
        tool_calls_raw = msg.get("tool_calls") or []
        normalised_calls = []
        for tc in tool_calls_raw:
            fn = tc.get("function", {})
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            normalised_calls.append({"function": {"name": fn.get("name", ""), "arguments": args}})
        return {
            "message": {
                "content": msg.get("content", ""),
                "tool_calls": normalised_calls,
            }
        }


class GeminiProvider:
    """Google Gemini provider via REST API."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, model: str, timeout: int = 120):
        self.api_key = api_key
        self.model = model  # e.g. "gemini-1.5-pro"
        self.timeout = timeout

    def _clean_schema_for_gemini(self, schema: dict) -> dict:
        """Strip JSON Schema fields Gemini doesn't support to avoid 400 errors."""
        UNSUPPORTED = {"additionalProperties", "$schema", "$id", "format", "default", "examples"}
        if not isinstance(schema, dict):
            return schema
        cleaned = {}
        for k, v in schema.items():
            if k in UNSUPPORTED:
                continue
            if isinstance(v, dict):
                cleaned[k] = self._clean_schema_for_gemini(v)
            elif isinstance(v, list):
                cleaned[k] = [self._clean_schema_for_gemini(i) if isinstance(i, dict) else i for i in v]
            else:
                cleaned[k] = v
        return cleaned

    def _generate_url(self) -> str:
        return f"{self.BASE_URL}/models/{self.model}:generateContent?key={self.api_key}"

    def _chat_url(self) -> str:
        return f"{self.BASE_URL}/models/{self.model}:generateContent?key={self.api_key}"

    def generate(self, prompt: str, temperature: float, max_tokens: int, expect_json: bool) -> Optional[str]:
        """Single-turn generation."""
        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens or 1024,
            },
        }
        if expect_json:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        try:
            resp = requests.post(self._generate_url(), json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    candidate = candidates[0]
                    finish = candidate.get("finishReason", "")
                    parts = candidate.get("content", {}).get("parts") or []
                    text = "".join(p.get("text", "") for p in parts)
                    import logging as _log
                    _log.getLogger(__name__).info(
                        f"Gemini response: finish={finish}, text_len={len(text)}, "
                        f"tokens_used={data.get('usageMetadata',{}).get('totalTokenCount','?')}"
                    )
                    if finish == "MAX_TOKENS":
                        _log.getLogger(__name__).warning(
                            f"Gemini MAX_TOKENS: response truncated at {len(text)} chars "
                            f"(maxOutputTokens={max_tokens}). Returning None to trigger retry."
                        )
                        return None
                    if text:
                        return text
            else:
                import logging as _log
                _log.getLogger(__name__).error(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")
            return None
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).error(f"Gemini generate exception: {e}")
            return None

    def chat_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        timeout: int = None,
    ) -> Dict[str, Any]:
        """Chat with function declarations. Returns Ollama-normalised shape."""
        # Convert OpenAI-style messages to Gemini contents
        contents = []
        system_text = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_text = content
                continue
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": content}]})

        # Prepend system message as first user turn if present
        if system_text and contents:
            contents[0]["parts"].insert(0, {"text": f"[System]: {system_text}\n\n"})

        # Convert OpenAI tool defs to Gemini function declarations
        function_declarations = []
        for tool in tools:
            fn = tool.get("function", {})
            # Gemini doesn't support additionalProperties or certain format fields
            params = fn.get("parameters", {})
            clean_params = self._clean_schema_for_gemini(params)
            function_declarations.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": clean_params,
            })

        payload: Dict[str, Any] = {
            "contents": contents,
            "tools": [{"functionDeclarations": function_declarations}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 16384},
        }

        resp = requests.post(self._chat_url(), json=payload, timeout=timeout or self.timeout)
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            return {"message": {"content": "", "tool_calls": []}}

        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = []
        tool_calls = []

        for part in parts:
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append({
                    "function": {
                        "name": fc.get("name", ""),
                        "arguments": fc.get("args", {}),
                    }
                })

        return {
            "message": {
                "content": "".join(text_parts),
                "tool_calls": tool_calls,
            }
        }
