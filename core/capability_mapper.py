"""
Capability Mapper - Builds capability graph from existing tools
"""
import ast
from pathlib import Path
from typing import Dict, Set, List
import json

class CapabilityMapper:
    def __init__(self, tools_dir: str = "tools"):
        self.tools_dir = Path(tools_dir)
        self.capability_graph = {}
    
    def build_capability_graph(self) -> Dict[str, bool]:
        """Scan tools and build capability graph — includes experimental subdirectory."""
        capabilities = {}

        dirs_to_scan = [self.tools_dir, self.tools_dir / "experimental"]
        for scan_dir in dirs_to_scan:
            if not scan_dir.exists():
                continue
            for tool_file in scan_dir.glob("*.py"):
                if tool_file.name.startswith('_'):
                    continue
                tool_caps = self._extract_tool_capabilities(tool_file)
                capabilities.update(tool_caps)

        self.capability_graph = capabilities
        return capabilities
    
    def _extract_tool_capabilities(self, tool_file: Path) -> Dict[str, bool]:
        """Extract capabilities from a single tool"""
        caps = {}
        
        try:
            with open(tool_file) as f:
                tree = ast.parse(f.read())
            
            # Extract from register_capabilities method
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == 'register_capabilities':
                    # Look for ToolCapability definitions
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            if hasattr(child.func, 'id') and child.func.id == 'ToolCapability':
                                # Extract capability name
                                for keyword in child.keywords:
                                    if keyword.arg == 'name':
                                        if isinstance(keyword.value, ast.Constant):
                                            cap_name = keyword.value.value
                                            caps[cap_name] = True
            
            # Extract ALL methods (including private) for duplication analysis
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.name not in ['__init__', 'register_capabilities', 'execute']:
                        caps[f"{tool_file.stem}_{node.name}"] = True
        
        except Exception:
            pass
        
        return caps
    
    def has_capability(self, capability: str) -> bool:
        """Check if capability exists"""
        return self.capability_graph.get(capability, False)
    
    def get_missing_capabilities(self, required: List[str]) -> List[str]:
        """Get list of missing capabilities"""
        return [cap for cap in required if not self.has_capability(cap)]
    
    def save_graph(self, path: str = "data/capability_graph.json"):
        """Save capability graph to disk"""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.capability_graph, f, indent=2)
    
    def load_graph(self, path: str = "data/capability_graph.json"):
        """Load capability graph from disk"""
        try:
            with open(path) as f:
                self.capability_graph = json.load(f)
        except FileNotFoundError:
            self.build_capability_graph()
