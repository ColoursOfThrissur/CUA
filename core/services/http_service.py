"""HTTP service wrapper for tools"""
import requests
from typing import Optional, Dict, Any

class HTTPService:
    """Provides HTTP capabilities to tools"""
    
    def get(self, url: str, headers: Optional[Dict] = None, timeout: int = 30) -> Dict[str, Any]:
        """Make GET request"""
        response = requests.get(url, headers=headers, timeout=timeout)
        return {"status": response.status_code, "body": response.text, "headers": dict(response.headers)}
    
    def post(self, url: str, data: Any = None, json: Any = None, headers: Optional[Dict] = None, timeout: int = 30) -> Dict[str, Any]:
        """Make POST request"""
        response = requests.post(url, data=data, json=json, headers=headers, timeout=timeout)
        return {"status": response.status_code, "body": response.text, "headers": dict(response.headers)}
    
    def put(self, url: str, data: Any = None, json: Any = None, headers: Optional[Dict] = None, timeout: int = 30) -> Dict[str, Any]:
        """Make PUT request"""
        response = requests.put(url, data=data, json=json, headers=headers, timeout=timeout)
        return {"status": response.status_code, "body": response.text, "headers": dict(response.headers)}
    
    def delete(self, url: str, headers: Optional[Dict] = None, timeout: int = 30) -> Dict[str, Any]:
        """Make DELETE request"""
        response = requests.delete(url, headers=headers, timeout=timeout)
        return {"status": response.status_code, "body": response.text, "headers": dict(response.headers)}
