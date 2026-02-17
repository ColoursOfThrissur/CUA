"""
HTTP Tool - Network requests capability
"""

import requests
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus


class HTTPTool(BaseTool):
    ALLOWED_DOMAINS = ["localhost", "127.0.0.1", "api.github.com", "pypi.org"]

    def __init__(self):
        self.name = "http_tool"
        self.description = "Make HTTP requests"
        self.capabilities = ["get", "post"]
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

    def execute(self, operation: str, parameters: dict) -> ToolResult:
        if operation == "get":
            return self._get(parameters)
        elif operation == "post":
            return self._post(parameters)
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
            return ToolResult(
                tool_name=self.name,
                capability_name="get",
                status=ResultStatus.FAILURE,
                error_message="URL required"
            )
        
        # Validate URL
        if not self._is_allowed_url(url):
            allowed_domains_str = ', '.join(self.ALLOWED_DOMAINS)
            return ToolResult(
                tool_name=self.name,
                capability_name="get",
                status=ResultStatus.FAILURE,
                error_message=f"URL not allowed. Allowed domains: {allowed_domains_str}"
            )
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                return ToolResult(
                    tool_name=self.name,
                    capability_name="get",
                    status=ResultStatus.FAILURE,
                    error_message=f"HTTP request failed with status code: {response.status_code}"
                )
            
            # Limit the size of the data returned to avoid large payloads
            response_data = response.text[:1000]
            return ToolResult(
                tool_name=self.name,
                capability_name="get",
                status=ResultStatus.SUCCESS,
                data={"status": response.status_code, "body": response_data}
            )
        except requests.exceptions.RequestException as e:
            error_message = str(e)
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
            return ToolResult(
                tool_name=self.name,
                capability_name="post",
                status=ResultStatus.FAILURE,
                error_message="URL required"
            )
        
        # Validate URL
        if not self._is_allowed_url(url):
            allowed_domains_str = ', '.join(self.ALLOWED_DOMAINS)
            return ToolResult(
                tool_name=self.name,
                capability_name="post",
                status=ResultStatus.FAILURE,
                error_message=f"URL not allowed. Allowed domains: {allowed_domains_str}"
            )
        
        try:
            response = requests.post(url, json=data, timeout=10)
            
            if response.status_code >= 400:
                return ToolResult(
                    tool_name=self.name,
                    capability_name="post",
                    status=ResultStatus.FAILURE,
                    error_message=f"HTTP Error: {response.status_code}"
                )
            
            # Limit the body length to first 1000 characters
            response_body = response.text[:1000]
            return ToolResult(
                tool_name=self.name,
                capability_name="post",
                status=ResultStatus.SUCCESS,
                data={"status": response.status_code, "body": response_body}
            )
        except requests.exceptions.RequestException as e:
            error_message = str(e)
            return ToolResult(
                tool_name=self.name,
                capability_name="post",
                status=ResultStatus.FAILURE,
                error_message=error_message
            )

    def _is_allowed_url(self, url: str) -> bool:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                return False
            return any(domain in parsed.netloc for domain in self.ALLOWED_DOMAINS)
        except Exception as e:
            print(f"Error parsing URL {url}: {e}")
            return False