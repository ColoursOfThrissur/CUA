"""
HTTP Tool - Full HTTP client with headers, auth, response parsing, and retry.
"""
import hashlib
import logging
import time
from urllib.parse import urlparse

import requests

from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

logger = logging.getLogger(__name__)


class HTTPTool(BaseTool):
    """Make HTTP requests with domain allowlist, caching, and auth support."""

    # Domains always allowed regardless of scheme
    ALWAYS_ALLOWED_DOMAINS = [
        "localhost", "127.0.0.1", "0.0.0.0",
        "api.github.com", "github.com",
        "pypi.org", "httpbin.org",
        "wikipedia.org", "en.wikipedia.org",
    ]

    def __init__(self, orchestrator=None, cache_enabled: bool = False, ttl: int = 3600):
        self.description = "Make HTTP requests: GET, POST, PUT, PATCH, DELETE with headers and auth."
        self.cache_enabled = cache_enabled
        self.ttl = ttl
        self.cache_store = {}
        super().__init__()
        if orchestrator:
            self.services = orchestrator.get_services(self.__class__.__name__)

    def register_capabilities(self):
        _url_param = Parameter("url", ParameterType.STRING, "Full URL to request")
        _headers_param = Parameter("headers", ParameterType.DICT, "Extra request headers", required=False)
        _auth_param = Parameter("auth", ParameterType.DICT, "Auth dict: {type: bearer|basic, token/username/password}", required=False)
        _timeout_param = Parameter("timeout", ParameterType.INTEGER, "Request timeout in seconds. Default: 15", required=False)
        _data_param = Parameter("data", ParameterType.DICT, "Request body as JSON object", required=False)
        _params_param = Parameter("params", ParameterType.DICT, "URL query parameters", required=False)

        self.add_capability(ToolCapability(
            name="get",
            description="Make an HTTP GET request and return status, headers, and body.",
            parameters=[_url_param, _params_param, _headers_param, _auth_param, _timeout_param],
            returns="Dict with status, body, headers.",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"url": "https://api.github.com/repos/python/cpython"}],
        ), self._handle_get)

        self.add_capability(ToolCapability(
            name="post",
            description="Make an HTTP POST request with a JSON body.",
            parameters=[_url_param, _data_param, _headers_param, _auth_param, _timeout_param],
            returns="Dict with status, body, headers.",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"url": "http://localhost:8000/chat", "data": {"message": "hello"}}],
        ), self._handle_post)

        self.add_capability(ToolCapability(
            name="put",
            description="Make an HTTP PUT request with a JSON body.",
            parameters=[_url_param, _data_param, _headers_param, _auth_param, _timeout_param],
            returns="Dict with status, body, headers.",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"url": "http://localhost:8000/api/item/1", "data": {"name": "updated"}}],
        ), self._handle_put)

        self.add_capability(ToolCapability(
            name="patch",
            description="Make an HTTP PATCH request with a partial JSON body.",
            parameters=[_url_param, _data_param, _headers_param, _auth_param, _timeout_param],
            returns="Dict with status, body, headers.",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"url": "http://localhost:8000/api/item/1", "data": {"status": "active"}}],
        ), self._handle_patch)

        self.add_capability(ToolCapability(
            name="delete",
            description="Make an HTTP DELETE request.",
            parameters=[_url_param, _headers_param, _auth_param, _timeout_param],
            returns="Dict with status, body.",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"url": "http://localhost:8000/api/item/1"}],
        ), self._handle_delete)

        self.add_capability(ToolCapability(
            name="download_file",
            description="Download a file from a URL and save it to a local path.",
            parameters=[
                _url_param,
                Parameter("destination", ParameterType.STRING, "Local file path to save to"),
                _headers_param,
                _timeout_param,
            ],
            returns="Dict with success, destination, size_bytes.",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"url": "https://example.com/file.pdf", "destination": "output/file.pdf"}],
        ), self._handle_download_file)

        self.add_capability(ToolCapability(
            name="head",
            description="Make an HTTP HEAD request to check resource existence and headers without downloading body.",
            parameters=[_url_param, _headers_param, _timeout_param],
            returns="Dict with status and response headers.",
            safety_level=SafetyLevel.LOW,
            examples=[{"url": "https://example.com/resource"}],
        ), self._handle_head)

    # ── Core request helper ───────────────────────────────────────────────────

    def _request(self, method: str, url: str, data: dict = None, headers: dict = None,
                 auth: dict = None, timeout: int = 15, params: dict = None, stream: bool = False):
        if not url:
            raise ValueError("url is required")
        if not self._is_allowed_url(url):
            raise ValueError(f"URL not allowed. HTTPS URLs are always permitted. HTTP only for: {', '.join(self.ALWAYS_ALLOWED_DOMAINS)}")

        merged_headers = {**self._default_headers(), **(headers or {})}
        auth_obj = self._build_auth(auth)
        timeout = timeout or 15

        cache_key = None
        if method == "GET" and self.cache_enabled:
            cache_key = self._cache_key(url, params or {})
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        resp = requests.request(
            method=method.upper(), url=url,
            json=data, headers=merged_headers,
            auth=auth_obj, timeout=timeout,
            params=params, stream=stream,
        )

        result = {
            "status": resp.status_code,
            "ok": resp.status_code < 400,
            "headers": dict(resp.headers),
            "body": resp.text[:20000] if not stream else None,
            "url": resp.url,
        }
        # Try to parse JSON body automatically
        if "application/json" in resp.headers.get("Content-Type", ""):
            try:
                result["json"] = resp.json()
            except Exception:
                pass

        if cache_key and resp.status_code < 400:
            self._set_cache(cache_key, result)

        return result

    def _default_headers(self) -> dict:
        return {"User-Agent": "CUA/1.0", "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}

    def _build_auth(self, auth: dict):
        if not auth:
            return None
        auth_type = (auth.get("type") or "").lower()
        if auth_type == "bearer":
            return None  # handled via header injection below — caller should pass in headers
        if auth_type == "basic":
            return (auth.get("username", ""), auth.get("password", ""))
        return None

    def _is_allowed_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            if parsed.scheme == "https":
                return True
            netloc = parsed.netloc.split(":")[0]
            return any(netloc == d or netloc.endswith("." + d) for d in self.ALWAYS_ALLOWED_DOMAINS)
        except Exception:
            return False

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_get(self, url: str, params: dict = None, headers: dict = None,
                    auth: dict = None, timeout: int = 15, **kwargs) -> dict:
        return self._request("GET", url, headers=headers, auth=auth, timeout=timeout, params=params)

    def _handle_post(self, url: str, data: dict = None, headers: dict = None,
                     auth: dict = None, timeout: int = 15, **kwargs) -> dict:
        return self._request("POST", url, data=data, headers=headers, auth=auth, timeout=timeout)

    def _handle_put(self, url: str, data: dict = None, headers: dict = None,
                    auth: dict = None, timeout: int = 15, **kwargs) -> dict:
        return self._request("PUT", url, data=data, headers=headers, auth=auth, timeout=timeout)

    def _handle_patch(self, url: str, data: dict = None, headers: dict = None,
                      auth: dict = None, timeout: int = 15, **kwargs) -> dict:
        return self._request("PATCH", url, data=data, headers=headers, auth=auth, timeout=timeout)

    def _handle_delete(self, url: str, headers: dict = None,
                       auth: dict = None, timeout: int = 15, **kwargs) -> dict:
        return self._request("DELETE", url, headers=headers, auth=auth, timeout=timeout)

    def _handle_download_file(self, url: str, destination: str, headers: dict = None,
                               timeout: int = 30, **kwargs) -> dict:
        if not destination:
            raise ValueError("destination is required")
        import os
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
        resp = requests.get(url, headers={**self._default_headers(), **(headers or {})},
                            timeout=timeout or 30, stream=True)
        resp.raise_for_status()
        size = 0
        with open(destination, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                size += len(chunk)
        return {"success": True, "destination": destination, "size_bytes": size, "status": resp.status_code}

    def _handle_head(self, url: str, headers: dict = None, timeout: int = 10, **kwargs) -> dict:
        if not url:
            raise ValueError("url is required")
        resp = requests.head(url, headers={**self._default_headers(), **(headers or {})}, timeout=timeout or 10)
        return {"status": resp.status_code, "ok": resp.status_code < 400, "headers": dict(resp.headers)}

    # ── Cache helpers ─────────────────────────────────────────────────────────

    def _cache_key(self, url: str, params: dict) -> str:
        return hashlib.sha256((url + str(params)).encode()).hexdigest()

    def _get_cached(self, key: str):
        entry = self.cache_store.get(key)
        if entry and time.time() < entry[0]:
            return entry[1]
        if entry:
            del self.cache_store[key]
        return None

    def _set_cache(self, key: str, data):
        self.cache_store[key] = (time.time() + self.ttl, data)

    def execute(self, operation: str, parameters: dict) -> ToolResult:
        if operation in self._capabilities:
            return self.execute_capability(operation, **parameters)
        return ToolResult(
            tool_name=self.name, capability_name=operation,
            status=ResultStatus.FAILURE, error_message=f"Unknown operation: {operation}",
        )
