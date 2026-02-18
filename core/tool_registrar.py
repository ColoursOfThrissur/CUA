"""
ToolRegistrar - Dynamically registers tools at runtime
"""
import importlib
import sys
from pathlib import Path
from typing import Dict, Optional, List


class ToolRegistrar:
    def __init__(self, registry):
        self.registry = registry
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
            
            # Find tool class (assumes class name matches file: calculator_tool.py -> CalculatorTool)
            tool_class_name = self._get_tool_class_name(tool_path.stem)
            
            if not hasattr(module, tool_class_name):
                return {'success': False, 'error': f'Class {tool_class_name} not found'}
            
            # Instantiate tool
            tool_class = getattr(module, tool_class_name)
            tool_instance = tool_class()
            
            # Register with registry
            self.registry.register_tool(tool_instance)
            
            # Track registration
            tool_name = tool_instance.name
            self.registered_tools[tool_name] = tool_instance
            
            # Get capabilities
            capabilities = [cap.name for cap in tool_instance.capabilities]
            
            return {
                'success': True,
                'tool_name': tool_name,
                'capabilities': capabilities,
                'class_name': tool_class_name
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def unregister_tool(self, tool_name: str) -> Dict:
        """Remove tool from registry"""
        try:
            if tool_name not in self.registered_tools:
                return {'success': False, 'error': 'Tool not registered'}
            
            # Remove from registry
            self.registry.tools = [t for t in self.registry.tools if t.name != tool_name]
            
            # Remove from tracking
            del self.registered_tools[tool_name]
            
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_tool_class_name(self, file_stem: str) -> str:
        """Convert file name to class name: calculator_tool -> CalculatorTool"""
        parts = file_stem.split('_')
        return ''.join(word.capitalize() for word in parts)
    
    def get_active_tools(self) -> list:
        """Get list of currently registered tools"""
        return [
            {
                'name': tool.name,
                'capabilities': [cap.name for cap in tool.capabilities],
                'description': getattr(tool, 'description', '')
            }
            for tool in self.registry.tools
        ]
