"""
Base code generator interface
"""
from abc import ABC, abstractmethod
from typing import Optional


class BaseCodeGenerator(ABC):
    """Base interface for tool code generation strategies"""
    
    def __init__(self, llm_client, flow):
        self.llm_client = llm_client
        self.flow = flow
    
    @abstractmethod
    def generate(self, template: str, tool_spec: dict) -> Optional[str]:
        """Generate tool code from template and spec"""
        pass
