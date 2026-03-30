"""Correlation context manager for request tracing across the system."""
import uuid
import threading
from typing import Optional
from contextvars import ContextVar

# Thread-safe context variable for correlation ID
_correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)

class CorrelationContext:
    """Manages correlation IDs for distributed tracing."""
    
    @staticmethod
    def generate_id() -> str:
        """Generate a new correlation ID."""
        return str(uuid.uuid4())
    
    @staticmethod
    def set_id(correlation_id: str) -> None:
        """Set the correlation ID for current context."""
        _correlation_id.set(correlation_id)
    
    @staticmethod
    def get_id() -> Optional[str]:
        """Get the correlation ID for current context."""
        return _correlation_id.get()
    
    @staticmethod
    def get_or_create_id() -> str:
        """Get existing correlation ID or create new one."""
        correlation_id = _correlation_id.get()
        if not correlation_id:
            correlation_id = CorrelationContext.generate_id()
            _correlation_id.set(correlation_id)
        return correlation_id
    
    @staticmethod
    def clear() -> None:
        """Clear the correlation ID."""
        _correlation_id.set(None)

class CorrelationContextManager:
    """Context manager for correlation ID scope."""
    
    def __init__(self, correlation_id: Optional[str] = None):
        self.correlation_id = correlation_id or CorrelationContext.generate_id()
        self.previous_id = None
    
    def __enter__(self):
        self.previous_id = CorrelationContext.get_id()
        CorrelationContext.set_id(self.correlation_id)
        return self.correlation_id
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.previous_id:
            CorrelationContext.set_id(self.previous_id)
        else:
            CorrelationContext.clear()
        return False

def with_correlation(correlation_id: Optional[str] = None):
    """Decorator to wrap function with correlation context."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with CorrelationContextManager(correlation_id):
                return func(*args, **kwargs)
        return wrapper
    return decorator
