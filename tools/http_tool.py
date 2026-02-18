"""
HTTP Tool - Network requests capability
"""

import requests
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
import time
import hashlib
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HTTPTool(BaseTool):
    ALLOWED_DOMAINS = ["localhost", "127.0.0.1", "api.github.com", "github.com", "pypi.org", "httpbin.org", "wikipedia.org", "en.wikipedia.org"]

    def __init__(self, cache_enabled=False, ttl=3600):
        self.name = "http_tool"
        self.description = "Make HTTP requests"
        self.capabilities = ["get", "post", "put", "delete"]
        self.cache_enabled = cache_enabled
        self.ttl = ttl
        self.cache_store = {}
        super().__init__()

    def register_capabilities(self):
        """Register HTTP request capabilities"""
        from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

        get_cap = ToolCapability(
            name="get",
            description="Make HTTP GET request",
            parameters=[
                Parameter("url", ParameterType.STRING, "URL to request")
            ],
            returns="Response data",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"url": "http://localhost:8000/health"}]
        )
        self.add_capability(get_cap, self._get)

        post_cap = ToolCapability(
            name="post",
            description="Make HTTP POST request",
            parameters=[
                Parameter("url", ParameterType.STRING, "URL to request"),
                Parameter("data", ParameterType.DICT, "Data to send")
            ],
            returns="Response data",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"url": "http://localhost:8000/api", "data": {}}]
        )
        self.add_capability(post_cap, self._post)

        put_cap = ToolCapability(
            name="put",
            description="Make HTTP PUT request",
            parameters=[
                Parameter("url", ParameterType.STRING, "URL to request"),
                Parameter("data", ParameterType.DICT, "Data to send")
            ],
            returns="Response data",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"url": "http://localhost:8000/api", "data": {}}]
        )
        self.add_capability(put_cap, self._put)

        delete_cap = ToolCapability(
            name="delete",
            description="Make HTTP DELETE request",
            parameters=[
                Parameter("url", ParameterType.STRING, "URL to request")
            ],
            returns="Response data",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"url": "http://localhost:8000/api"}]
        )
        self.add_capability(delete_cap, self._delete)

    def execute(self, operation: str, parameters: dict) -> ToolResult:
        if operation == "get":
            return self._get(parameters)
        elif operation == "post":
            return self._post(parameters)
        elif operation == "put":
            return self._put(parameters)
        elif operation == "delete":
            return self._delete(parameters)
        else:
            return ToolResult(
                tool_name=self.name,
                capability_name=operation,
                status=ResultStatus.FAILURE,
                error_message="Unknown operation"
            )

    def _get(self, params: dict) -> ToolResult:
        url = params.get("url")
        if not url:
            logger.error("URL required for GET request.")
            return ToolResult(
                tool_name=self.name,
                capability_name="get",
                status=ResultStatus.FAILURE,
                error_message="URL required"
            )
        
        # Validate URL
        if not self._is_allowed_url(url):
            allowed_domains_str = ', '.join(self.ALLOWED_DOMAINS)
            logger.error(f"URL not allowed. Allowed domains: {allowed_domains_str}")
            return ToolResult(
                tool_name=self.name,
                capability_name="get",
                status=ResultStatus.FAILURE,
                error_message=f"URL not allowed. Allowed domains: {allowed_domains_str}"
            )
        
        if self.cache_enabled:
            cache_key = self._cache_key(url, params)
            cached_response = self._get_cached(cache_key)
            if cached_response is not None:
                logger.info(f"Returning cached response for URL: {url}")
                return ToolResult(
                    tool_name=self.name,
                    capability_name="get",
                    status=ResultStatus.SUCCESS,
                    data={"status": 200, "body": cached_response}
                )
        
        try:
            start_time = time.time()
            logger.info(f"Making GET request to URL: {url}")
            response = requests.get(url, timeout=10)
            end_time = time.time()
            
            if response.status_code != 200:
                logger.error(f"HTTP request failed with status code: {response.status_code} for URL: {url}")
                return ToolResult(
                    tool_name=self.name,
                    capability_name="get",
                    status=ResultStatus.FAILURE,
                    error_message=f"HTTP request failed with status code: {response.status_code}"
                )
            
            # Limit the size of the data returned to avoid large payloads
            response_data = response.text[:5000]
            
            if self.cache_enabled:
                cache_key = self._cache_key(url, params)
                self._set_cache(cache_key, response_data)
            
            logger.info(f"GET request successful for URL: {url} in {end_time - start_time:.2f}s")
            return ToolResult(
                tool_name=self.name,
                capability_name="get",
                status=ResultStatus.SUCCESS,
                data={"status": response.status_code, "body": response_data}
            )
        except requests.exceptions.RequestException as e:
            error_message = str(e)
            logger.error(f"Request exception for GET request to URL: {url}. Error: {error_message}")
            return ToolResult(
                tool_name=self.name,
                capability_name="get",
                status=ResultStatus.FAILURE,
                error_message=error_message
            )

    def _post(self, params: dict) -> ToolResult:
        url = params.get("url")
        data = params.get("data", {})
        
        if not url:
            logger.error("URL required for POST request.")
            return ToolResult(
                tool_name=self.name,
                capability_name="post",
                status=ResultStatus.FAILURE,
                error_message="URL required"
            )
        
        # Validate URL
        if not self._is_allowed_url(url):
            allowed_domains_str = ', '.join(self.ALLOWED_DOMAINS)
            logger.error(f"URL not allowed. Allowed domains: {allowed_domains_str}")
            return ToolResult(
                tool_name=self.name,
                capability_name="post",
                status=ResultStatus.FAILURE,
                error_message=f"URL not allowed. Allowed domains: {allowed_domains_str}"
            )
        
        try:
            start_time = time.time()
            logger.info(f"Making POST request to URL: {url} with data: {data}")
            response = requests.post(url, json=data, timeout=10)
            end_time = time.time()
            
            if response.status_code >= 400:
                logger.error(f"HTTP Error: {response.status_code} for POST request to URL: {url}")
                return ToolResult(
                    tool_name=self.name,
                    capability_name="post",
                    status=ResultStatus.FAILURE,
                    error_message=f"HTTP Error: {response.status_code}"
                )
            
            # Limit the body length to first 1000 characters
            response_body = response.text[:1000]
            logger.info(f"POST request successful for URL: {url} in {end_time - start_time:.2f}s")
            return ToolResult(
                tool_name=self.name,
                capability_name="post",
                status=ResultStatus.SUCCESS,
                data={"status": response.status_code, "body": response_body}
            )
        except requests.exceptions.RequestException as e:
            error_message = str(e)
            logger.error(f"Request exception for POST request to URL: {url}. Error: {error_message}")
            return ToolResult(
                tool_name=self.name,
                capability_name="post",
                status=ResultStatus.FAILURE,
                error_message=error_message
            )

    def _put(self, params: dict) -> ToolResult:
        url = params.get("url")
        data = params.get("data", {})
        
        if not url:
            logger.error("URL required for PUT request.")
            return ToolResult(
                tool_name=self.name,
                capability_name="put",
                status=ResultStatus.FAILURE,
                error_message="URL required"
            )
        
        # Validate URL
        if not self._is_allowed_url(url):
            allowed_domains_str = ', '.join(self.ALLOWED_DOMAINS)
            logger.error(f"URL not allowed. Allowed domains: {allowed_domains_str}")
            return ToolResult(
                tool_name=self.name,
                capability_name="put",
                status=ResultStatus.FAILURE,
                error_message=f"URL not allowed. Allowed domains: {allowed_domains_str}"
            )
        
        try:
            start_time = time.time()
            logger.info(f"Making PUT request to URL: {url} with data: {data}")
            response = requests.put(url, json=data, timeout=10)
            end_time = time.time()
            
            if response.status_code >= 400:
                logger.error(f"HTTP Error: {response.status_code} for PUT request to URL: {url}")
                return ToolResult(
                    tool_name=self.name,
                    capability_name="put",
                    status=ResultStatus.FAILURE,
                    error_message=f"HTTP Error: {response.status_code}"
                )
            
            # Limit the body length to first 1000 characters
            response_body = response.text[:1000]
            logger.info(f"PUT request successful for URL: {url} in {end_time - start_time:.2f}s")
            return ToolResult(
                tool_name=self.name,
                capability_name="put",
                status=ResultStatus.SUCCESS,
                data={"status": response.status_code, "body": response_body}
            )
        except requests.exceptions.RequestException as e:
            error_message = str(e)
            logger.error(f"Request exception for PUT request to URL: {url}. Error: {error_message}")
            return ToolResult(
                tool_name=self.name,
                capability_name="put",
                status=ResultStatus.FAILURE,
                error_message=error_message
            )

    def _delete(self, params: dict) -> ToolResult:
        url = params.get("url")
        
        if not url:
            logger.error("URL required for DELETE request.")
            return ToolResult(
                tool_name=self.name,
                capability_name="delete",
                status=ResultStatus.FAILURE,
                error_message="URL required"
            )
        
        # Validate URL
        if not self._is_allowed_url(url):
            allowed_domains_str = ', '.join(self.ALLOWED_DOMAINS)
            logger.error(f"URL not allowed. Allowed domains: {allowed_domains_str}")
            return ToolResult(
                tool_name=self.name,
                capability_name="delete",
                status=ResultStatus.FAILURE,
                error_message=f"URL not allowed. Allowed domains: {allowed_domains_str}"
            )
        
        try:
            start_time = time.time()
            logger.info(f"Making DELETE request to URL: {url}")
            response = requests.delete(url, timeout=10)
            end_time = time.time()
            
            if response.status_code >= 400:
                logger.error(f"HTTP Error: {response.status_code} for DELETE request to URL: {url}")
                return ToolResult(
                    tool_name=self.name,
                    capability_name="delete",
                    status=ResultStatus.FAILURE,
                    error_message=f"HTTP Error: {response.status_code}"
                )
            
            # Limit the body length to first 1000 characters
            response_body = response.text[:1000]
            logger.info(f"DELETE request successful for URL: {url} in {end_time - start_time:.2f}s")
            return ToolResult(
                tool_name=self.name,
                capability_name="delete",
                status=ResultStatus.SUCCESS,
                data={"status": response.status_code, "body": response_body}
            )
        except requests.exceptions.RequestException as e:
            error_message = str(e)
            logger.error(f"Request exception for DELETE request to URL: {url}. Error: {error_message}")
            return ToolResult(
                tool_name=self.name,
                capability_name="delete",
                status=ResultStatus.FAILURE,
                error_message=error_message
            )

    def _is_allowed_url(self, url: str) -> bool:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                return False
            # Allow all HTTPS URLs, restrict HTTP to whitelist
            if parsed.scheme == 'https':
                return True
            # HTTP only allowed for whitelisted domains
            return any(
                parsed.netloc == domain or parsed.netloc.endswith('.' + domain)
                for domain in self.ALLOWED_DOMAINS
            )
        except Exception:
            return False

    def _cache_key(self, url: str, params: dict) -> str:
        """Generate a cache key from URL and parameters."""
        key = hashlib.sha256((url + str(params)).encode()).hexdigest()
        return key

    def _get_cached(self, cache_key: str) -> str or None:
        """Retrieve cached response if it exists and is not expired."""
        current_time = time.time()
        if cache_key in self.cache_store:
            expiration_time, data = self.cache_store[cache_key]
            if current_time < expiration_time:
                return data
            else:
                # Remove expired entry
                del self.cache_store[cache_key]
        return None

    def _set_cache(self, cache_key: str, response_data: str):
        """Store the response in the cache with an expiration time."""
        expiration_time = time.time() + self.ttl
        self.cache_store[cache_key] = (expiration_time, response_data)