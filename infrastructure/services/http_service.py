"""
HTTP Service - Provides HTTP client functionality for tools
"""

import requests
from typing import Dict, Any, Optional


class HTTPService:
    """HTTP service for making web requests."""
    
    def __init__(self):
        self.session = requests.Session()
        self.timeout = 30
    
    def get(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """Make a GET request."""
        try:
            response = self.session.get(url, headers=headers, timeout=self.timeout, **kwargs)
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "content": response.text,
                "success": response.ok
            }
        except Exception as e:
            return {
                "status_code": 0,
                "error": str(e),
                "success": False
            }
    
    def post(self, url: str, data: Any = None, json: Any = None, headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """Make a POST request."""
        try:
            response = self.session.post(url, data=data, json=json, headers=headers, timeout=self.timeout, **kwargs)
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "content": response.text,
                "success": response.ok
            }
        except Exception as e:
            return {
                "status_code": 0,
                "error": str(e),
                "success": False
            }
    
    def put(self, url: str, data: Any = None, json: Any = None, headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """Make a PUT request."""
        try:
            response = self.session.put(url, data=data, json=json, headers=headers, timeout=self.timeout, **kwargs)
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "content": response.text,
                "success": response.ok
            }
        except Exception as e:
            return {
                "status_code": 0,
                "error": str(e),
                "success": False
            }
    
    def delete(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """Make a DELETE request."""
        try:
            response = self.session.delete(url, headers=headers, timeout=self.timeout, **kwargs)
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "content": response.text,
                "success": response.ok
            }
        except Exception as e:
            return {
                "status_code": 0,
                "error": str(e),
                "success": False
            }
