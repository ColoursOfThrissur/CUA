"""JSON service wrapper for tools"""
import json
from typing import Any

class JSONService:
    """Provides JSON capabilities to tools"""
    
    def parse(self, text: str) -> Any:
        """Parse JSON string"""
        return json.loads(text)
    
    def stringify(self, data: Any, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(data, indent=indent)
    
    def query(self, data: dict, path: str) -> Any:
        """Query JSON using dot notation (e.g., 'user.name')"""
        keys = path.split('.')
        result = data
        for key in keys:
            if isinstance(result, dict):
                result = result.get(key)
            else:
                return None
        return result
