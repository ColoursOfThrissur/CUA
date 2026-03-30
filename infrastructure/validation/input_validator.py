"""Input size validation middleware - prevents memory issues."""
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)


class InputSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request body size and prevent memory issues"""
    
    def __init__(self, app, max_body_size: int = 10 * 1024 * 1024):  # 10MB default
        super().__init__(app)
        self.max_body_size = max_body_size
    
    async def dispatch(self, request: Request, call_next):
        # Check Content-Length header
        content_length = request.headers.get("content-length")
        
        if content_length:
            content_length = int(content_length)
            if content_length > self.max_body_size:
                logger.warning(f"Request body too large: {content_length} bytes (max: {self.max_body_size})")
                raise HTTPException(
                    status_code=413,
                    detail=f"Request body too large. Maximum size: {self.max_body_size / 1024 / 1024:.1f}MB"
                )
        
        response = await call_next(request)
        return response


def validate_text_input(text: str, max_length: int = 100000, field_name: str = "input") -> str:
    """Validate text input length"""
    if not text:
        return text
    
    if len(text) > max_length:
        raise ValueError(f"{field_name} too long: {len(text)} chars (max: {max_length})")
    
    return text


def validate_list_size(items: list, max_items: int = 1000, field_name: str = "list") -> list:
    """Validate list size"""
    if not items:
        return items
    
    if len(items) > max_items:
        raise ValueError(f"{field_name} too large: {len(items)} items (max: {max_items})")
    
    return items
