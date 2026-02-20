"""
ToolRegistrar - Dynamically registers tools at runtime
"""
import importlib
import sys
from pathlib import Path
from typing import Dict, Optional, List
from tools.tool_interface import BaseTool


class ToolRegistrar:
    def __init__(self, registry, orchestrator=None):
        self.registry = registry
        self.orchestrator = orchestrator
        self.registered_tools = {}  # {tool_name: tool_instance}
    
    def register_new_tool(self, tool_file_path: str) -> Dict:
        """
        Dynamically import and register tool
        Returns: {success, tool_name, capabilities, error}
        """
        try:
            tool_path = Path(tool_file_path)
            
            if not tool_path.exists():
                return {'success': False, 'error': 'Tool file not found'}
            
            # Convert path to module name: tools/calculator_tool.py -> tools.calculator_tool
            module_name = str(tool_path.with_suffix('')).replace('\\', '.').replace('/', '.')
            
            # Unload if already loaded (for hot-reload)
            if module_name in sys.modules:
                del sys.modules[module_name]
            
            # Import module
            module = importlib.import_module(module_name)
            tool_class = self._resolve_tool_class(module, tool_path.stem)
            if not tool_class:
                return {'success': False, 'error': 'No BaseTool subclass found in module'}

            # Best-effort hot-reload cleanup to avoid stale capability mappings.
            try:
                self.registry.unregister_tool(tool_class.__name__)
            except Exception:
                pass

            # Instantiate tool with orchestrator/registry injection
            try:
                # Try new signature with orchestrator/registry
                print(f"[REGISTRAR] Attempting to instantiate {tool_class.__name__} with orchestrator={self.orchestrator}")
                tool_instance = tool_class(orchestrator=self.orchestrator, registry=self.registry)
                print(f"[REGISTRAR] Success with orchestrator+registry")
            except TypeError as e:
                print(f"[REGISTRAR] TypeError with orchestrator+registry: {e}, trying orchestrator only")
                try:
                    tool_instance = tool_class(orchestrator=self.orchestrator)
                    print(f"[REGISTRAR] Success with orchestrator only")
                except TypeError as e2:
                    print(f"[REGISTRAR] TypeError with orchestrator only: {e2}, trying no args")
                    # Fallback to legacy signature without parameters
                    tool_instance = tool_class()
                    print(f"[REGISTRAR] Success with no args")
            
            # Register with registry
            self.registry.register_tool(tool_instance)
            
            # Track registration
            tool_name = tool_instance.name
            self.registered_tools[tool_name] = tool_instance
            
            # Get capabilities
            capabilities = list(tool_instance.get_capabilities().keys())
            
            return {
                'success': True,
                'tool_name': tool_name,
                'capabilities': capabilities,
                'class_name': tool_class.__name__
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def unregister_tool(self, tool_name: str) -> Dict:
        """Remove tool from registry"""
        try:
            if tool_name not in self.registered_tools:
                return {'success': False, 'error': 'Tool not registered'}
            
            # Remove from registry (best-effort by class name)
            tool_instance = self.registered_tools[tool_name]
            class_name = tool_instance.__class__.__name__
            removed = self.registry.unregister_tool(class_name)
            if not removed:
                return {'success': False, 'error': 'Tool not found in capability registry'}
            
            # Remove from tracking
            del self.registered_tools[tool_name]
            
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_tool_class_name(self, file_stem: str) -> str:
        """Convert file name to class name: calculator_tool -> CalculatorTool"""
        parts = file_stem.split('_')
        return ''.join(word.capitalize() for word in parts)

    def _resolve_tool_class(self, module, file_stem: str):
        """Resolve a BaseTool subclass from imported module."""
        expected = self._get_tool_class_name(file_stem)
        if hasattr(module, expected):
            candidate = getattr(module, expected)
            if isinstance(candidate, type) and issubclass(candidate, BaseTool) and candidate is not BaseTool:
                return candidate

        # Fallback: first BaseTool subclass defined in module.
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, BaseTool) and attr is not BaseTool:
                return attr
        return None
    
    def get_active_tools(self) -> list:
        """Get list of currently registered tools"""
        return [
            {
                'name': tool.name,
                'capabilities': list(tool.get_capabilities().keys()),
                'description': getattr(tool, 'description', '')
            }
            for tool in self.registry.tools
        ]
