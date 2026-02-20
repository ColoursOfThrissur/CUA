"""
HTTP Tool - Network requests capability
"""
import hashlib
import logging
import time
from urllib.parse import urlparse
import requests
from tools.tool_interface import BaseTool
from tools.tool_result import ResultStatus, ToolResult
logger = logging.getLogger(__name__)

class HTTPTool(BaseTool):
    ALLOWED_DOMAINS = ['localhost', '127.0.0.1', 'api.github.com', 'github.com', 'pypi.org', 'httpbin.org', 'wikipedia.org', 'en.wikipedia.org']

    def __init__(self, orchestrator=None, cache_enabled: bool=False, ttl: int=3600):
        self.description = 'Make HTTP requests'
        self.capabilities = ['get', 'post', 'put', 'delete']
        self.cache_enabled = cache_enabled
        self.ttl = ttl
        self.cache_store = {}
        super().__init__()
        if orchestrator:
            self.services = orchestrator.get_services(self.__class__.__name__)

    def register_capabilities(self):
        """Register HTTP request capabilities."""
        from tools.tool_capability import Parameter, ParameterType, SafetyLevel, ToolCapability
        self.add_capability(ToolCapability(name='get', description='Make HTTP GET request', parameters=[Parameter('url', ParameterType.STRING, 'URL to request')], returns='Response data', safety_level=SafetyLevel.MEDIUM, examples=[{'url': 'http://localhost:8000/health'}]), self._get)
        self.add_capability(ToolCapability(name='post', description='Make HTTP POST request', parameters=[Parameter('url', ParameterType.STRING, 'URL to request'), Parameter('data', ParameterType.DICT, 'Data to send')], returns='Response data', safety_level=SafetyLevel.MEDIUM, examples=[{'url': 'http://localhost:8000/api', 'data': {}}]), self._post)
        self.add_capability(ToolCapability(name='put', description='Make HTTP PUT request', parameters=[Parameter('url', ParameterType.STRING, 'URL to request'), Parameter('data', ParameterType.DICT, 'Data to send')], returns='Response data', safety_level=SafetyLevel.MEDIUM, examples=[{'url': 'http://localhost:8000/api', 'data': {}}]), self._put)
        self.add_capability(ToolCapability(name='delete', description='Make HTTP DELETE request', parameters=[Parameter('url', ParameterType.STRING, 'URL to request')], returns='Response data', safety_level=SafetyLevel.MEDIUM, examples=[{'url': 'http://localhost:8000/api'}]), self._delete)

    def execute(self, operation: str, parameters: dict) -> ToolResult:
        if operation == 'get':
            return self._get(parameters)
        if operation == 'post':
            return self._post(parameters)
        if operation == 'put':
            return self._put(parameters)
        if operation == 'delete':
            return self._delete(parameters)
        return ToolResult(tool_name=self.name, capability_name=operation, status=ResultStatus.FAILURE, error_message='Unknown operation')

    def _get(self, params: dict) -> ToolResult:
        url = params.get('url')
        validation_error = self._validate_url(url, 'get')
        if validation_error:
            return validation_error
        if self.cache_enabled:
            cache_key = self._cache_key(url, params)
            cached_response = self._get_cached(cache_key)
            if cached_response is not None:
                logger.info('Returning cached response for URL: %s', url)
                return ToolResult(tool_name=self.name, capability_name='get', status=ResultStatus.SUCCESS, data={'status': 200, 'body': cached_response})
        try:
            start_time = time.time()
            response = requests.get(url, headers=self._build_request_headers(), timeout=10)
            end_time = time.time()
            if response.status_code >= 400:
                return ToolResult(tool_name=self.name, capability_name='get', status=ResultStatus.FAILURE, error_message=f'HTTP Error: {response.status_code}')
            response_data = response.text[:5000]
            if self.cache_enabled:
                self._set_cache(self._cache_key(url, params), response_data)
            logger.info('GET request successful for URL: %s in %.2fs', url, end_time - start_time)
            return ToolResult(tool_name=self.name, capability_name='get', status=ResultStatus.SUCCESS, data={'status': response.status_code, 'body': response_data})
        except requests.exceptions.RequestException as exc:
            return ToolResult(tool_name=self.name, capability_name='get', status=ResultStatus.FAILURE, error_message=str(exc))

    def _post(self, params: dict) -> ToolResult:
        url, data = self._extract_url_and_data(params)
        validation_error = self._validate_url(url, 'post')
        if validation_error:
            return validation_error
        return self._send_with_body('post', url, data)

    def _put(self, params: dict) -> ToolResult:
        url = params.get('url')
        data = params.get('data', {})
        validation_error = self._validate_url(url, 'put')
        if validation_error:
            return validation_error
        return self._send_with_body('put', url, data)

    def _delete(self, params: dict) -> ToolResult:
        url = params.get('url')
        validation_error = self._validate_url(url, 'delete')
        if validation_error:
            return validation_error
        try:
            start_time = time.time()
            response = requests.delete(url, headers=self._build_request_headers(), timeout=10)
            end_time = time.time()
            if response.status_code >= 400:
                return ToolResult(tool_name=self.name, capability_name='delete', status=ResultStatus.FAILURE, error_message=f'HTTP Error: {response.status_code}')
            logger.info('DELETE request successful for URL: %s in %.2fs', url, end_time - start_time)
            return ToolResult(tool_name=self.name, capability_name='delete', status=ResultStatus.SUCCESS, data={'status': response.status_code, 'body': response.text[:1000]})
        except requests.exceptions.RequestException as exc:
            return ToolResult(tool_name=self.name, capability_name='delete', status=ResultStatus.FAILURE, error_message=str(exc))

    def _send_with_body(self, method: str, url: str, data: dict) -> ToolResult:
        try:
            start_time = time.time()
            response = requests.request(method=method.upper(), url=url, json=data, headers=self._build_request_headers(), timeout=10)
            end_time = time.time()
            if response.status_code >= 400:
                return ToolResult(tool_name=self.name, capability_name=method, status=ResultStatus.FAILURE, error_message=f'HTTP Error: {response.status_code}')
            logger.info('%s request successful for URL: %s in %.2fs', method.upper(), url, end_time - start_time)
            return ToolResult(tool_name=self.name, capability_name=method, status=ResultStatus.SUCCESS, data={'status': response.status_code, 'body': response.text[:1000]})
        except requests.exceptions.RequestException as exc:
            return ToolResult(tool_name=self.name, capability_name=method, status=ResultStatus.FAILURE, error_message=str(exc))

    def _validate_url(self, url: str, capability: str):
        if not url:
            return ToolResult(tool_name=self.name, capability_name=capability, status=ResultStatus.FAILURE, error_message='URL required')
        if not self._is_allowed_url(url):
            allowed_domains_str = ', '.join(self.ALLOWED_DOMAINS)
            return ToolResult(tool_name=self.name, capability_name=capability, status=ResultStatus.FAILURE, error_message=f'URL not allowed. Allowed domains: {allowed_domains_str}')
        return None

    def _is_allowed_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                return False
            if parsed.scheme == 'https':
                return True
            return any((parsed.netloc == domain or parsed.netloc.endswith('.' + domain) for domain in self.ALLOWED_DOMAINS))
        except Exception:
            return False

    def _build_request_headers(self) -> dict:
        return {'User-Agent': 'CUA/1.0', 'Accept': 'application/json'}

    def _cache_key(self, url: str, params: dict) -> str:
        return hashlib.sha256((url + str(params)).encode('utf-8')).hexdigest()

    def _get_cached(self, cache_key: str):
        current_time = time.time()
        if cache_key in self.cache_store:
            expiration_time, data = self.cache_store[cache_key]
            if current_time < expiration_time:
                return data
            del self.cache_store[cache_key]
        return None

    def _set_cache(self, cache_key: str, response_data: str):
        self.cache_store[cache_key] = (time.time() + self.ttl, response_data)

    def _put(self, params: dict) -> ToolResult:
        url, data = self._extract_url_and_data(params)
        validation_error = self._validate_url(url, "put")
        if validation_error:
            return validation_error
        return self._send_with_body("put", url, data)



    def _extract_url_and_data(self, params: dict):
        url = params.get("url")
        data = params.get("data", {})
        return url, data