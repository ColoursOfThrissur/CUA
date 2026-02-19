"""
Tool registry as capability graph with validation
"""
from dataclasses import dataclass
from typing import Dict, List, Set, Optional
import networkx as nx

@dataclass
class CapabilityNode:
    tool_name: str
    inputs: List[str]
    outputs: List[str]
    domain: str
    dependencies: List[str]
    risk_level: float
    maturity: str  # experimental, stable, mature
    blast_radius: int = 0

class CapabilityGraph:
    def __init__(self):
        self.graph = nx.DiGraph()
        self.tools: Dict[str, CapabilityNode] = {}
    
    def register_tool(self, node: CapabilityNode) -> tuple[bool, str]:
        """Validate and register new tool"""
        # Check duplicate capability
        if self._has_duplicate_capability(node):
            return False, "Duplicate capability exists"
        
        # Check circular dependency
        if self._creates_circular_dependency(node):
            return False, "Creates circular dependency"
        
        # Check blast radius
        blast_radius = self._calculate_blast_radius(node)
        if blast_radius > 10:
            return False, f"Blast radius too high: {blast_radius}"
        
        # Register
        self.tools[node.tool_name] = node
        self.graph.add_node(node.tool_name, data=node)
        for dep in node.dependencies:
            self.graph.add_edge(node.tool_name, dep)
        
        return True, "Tool registered successfully"
    
    def _has_duplicate_capability(self, node: CapabilityNode) -> bool:
        """Check if capability already exists"""
        for existing in self.tools.values():
            if (existing.domain == node.domain and 
                set(existing.outputs) == set(node.outputs)):
                return True
        return False
    
    def _creates_circular_dependency(self, node: CapabilityNode) -> bool:
        """Check for circular dependencies"""
        temp_graph = self.graph.copy()
        temp_graph.add_node(node.tool_name)
        for dep in node.dependencies:
            temp_graph.add_edge(node.tool_name, dep)
        
        try:
            nx.find_cycle(temp_graph)
            return True
        except nx.NetworkXNoCycle:
            return False
    
    def _calculate_blast_radius(self, node: CapabilityNode) -> int:
        """Calculate impact of tool failure"""
        dependents = set()
        for tool_name in self.tools:
            if node.tool_name in self.tools[tool_name].dependencies:
                dependents.add(tool_name)
                # Add transitive dependents
                dependents.update(self._get_transitive_dependents(tool_name))
        return len(dependents)
    
    def _get_transitive_dependents(self, tool_name: str) -> Set[str]:
        """Get all tools that depend on this tool"""
        if tool_name not in self.graph:
            return set()
        return set(nx.ancestors(self.graph, tool_name))
    
    def promote_experimental(self, tool_name: str) -> tuple[bool, str]:
        """Promote experimental tool to stable"""
        if tool_name not in self.tools:
            return False, "Tool not found"
        
        node = self.tools[tool_name]
        if node.maturity != "experimental":
            return False, f"Tool is already {node.maturity}"
        
        node.maturity = "stable"
        return True, "Tool promoted to stable"
