"""Repository interfaces - Domain contracts for data access."""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class ToolRepository(ABC):
    """Interface for tool registry access."""
    
    @abstractmethod
    def get_capabilities(self, preferred_tools: Optional[set] = None) -> Dict[str, List[Dict]]:
        """Get available tools and their capabilities."""
        pass
    
    @abstractmethod
    def get_tool(self, tool_name: str) -> Any:
        """Get tool instance by name."""
        pass
    
    @abstractmethod
    def tool_exists(self, tool_name: str) -> bool:
        """Check if tool exists."""
        pass


class MemoryRepository(ABC):
    """Interface for memory/plan history access."""
    
    @abstractmethod
    def find_similar_plans(self, goal: str, skill_name: str, top_k: int = 3) -> List[Any]:
        """Find similar past plans."""
        pass
    
    @abstractmethod
    def search_context(self, query: str, skill_name: str) -> str:
        """Search unified memory for planning context."""
        pass
