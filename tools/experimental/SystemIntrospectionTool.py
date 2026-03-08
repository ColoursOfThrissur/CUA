"""
SystemIntrospectionTool - Allows CUA to inspect its own capabilities and tools
"""
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class SystemIntrospectionTool(BaseTool):
    """Provides introspection capabilities for CUA to understand its own tools and capabilities."""
    
    def __init__(self, orchestrator=None):
        self.description = "Query and inspect available tools, capabilities, and system information"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        self.orchestrator = orchestrator
        super().__init__()

    def register_capabilities(self):
        """Register tool capabilities"""
        list_tools_capability = ToolCapability(
            name='list_tools',
            description='List all available tools in the system',
            parameters=[
                Parameter(name='include_experimental', type=ParameterType.BOOLEAN, description='Include experimental tools', required=False, default=True)
            ],
            returns="List of available tool names and descriptions",
            safety_level=SafetyLevel.LOW,
            examples=["list_tools() -> ['FileOperationsTool', 'HttpRequestTool', ...]"],
            dependencies=[]
        )
        self.add_capability(list_tools_capability, self._handle_list_tools)

        get_tool_info_capability = ToolCapability(
            name='get_tool_info',
            description='Get detailed information about a specific tool including its capabilities',
            parameters=[
                Parameter(name='tool_name', type=ParameterType.STRING, description='Name of the tool to inspect', required=True)
            ],
            returns="Detailed tool information including capabilities and parameters",
            safety_level=SafetyLevel.LOW,
            examples=["get_tool_info('FileOperationsTool') -> {capabilities: [...]}"],
            dependencies=[]
        )
        self.add_capability(get_tool_info_capability, self._handle_get_tool_info)

        list_capabilities_capability = ToolCapability(
            name='list_capabilities',
            description='List all capabilities across all tools',
            parameters=[],
            returns="List of all available capabilities",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(list_capabilities_capability, self._handle_list_capabilities)

        get_system_stats_capability = ToolCapability(
            name='get_system_stats',
            description='Get system statistics like tool count, capability count, etc.',
            parameters=[],
            returns="System statistics dictionary",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(get_system_stats_capability, self._handle_get_system_stats)

    def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute tool operation"""
        if operation == 'list_tools':
            return self._handle_list_tools(**kwargs)
        elif operation == 'get_tool_info':
            return self._handle_get_tool_info(**kwargs)
        elif operation == 'list_capabilities':
            return self._handle_list_capabilities(**kwargs)
        elif operation == 'get_system_stats':
            return self._handle_get_system_stats(**kwargs)
        raise ValueError(f"Unsupported operation: {operation}")

    def _handle_list_tools(self, **kwargs):
            include_experimental = kwargs.get('include_experimental', True)

            if not self.orchestrator:
                return {'tools': [], 'error': 'Orchestrator not available'}

            try:
                registry = getattr(self.orchestrator, '_registry', None) or getattr(self.services, 'registry', None)
                if not registry or not hasattr(registry, 'tools'):
                    return {'tools': [], 'error': 'Tool registry not available'}

                tools = []
                for tool_instance in getattr(registry, 'tools', []):
                    tool_name = tool_instance.__class__.__name__
                    module_name = getattr(tool_instance, "__module__", "")
                    is_experimental = module_name.startswith("tools.experimental")

                    if not include_experimental and is_experimental:
                        continue

                    tools.append({
                        'name': tool_name,
                        'description': getattr(tool_instance, 'description', 'No description'),
                        'is_experimental': is_experimental
                    })

                return {
                    'tools': tools,
                    'count': len(tools)
                }
            except Exception as e:
                self.services.logging.error(f"Error handling list tools: {str(e)}")
                return {'tools': [], 'error': str(e)}

    def _handle_get_tool_info(self, **kwargs):
            required_params = ['tool_name']
            missing = [p for p in required_params if p not in kwargs or kwargs[p] in (None, "")]
            if missing:
                raise ValueError(f"Missing required parameters: {', '.join(missing)}")

            tool_name = kwargs['tool_name']

            if not self.orchestrator:
                return {'error': 'Orchestrator not available'}

            try:
                registry = getattr(self.orchestrator, '_registry', None) or getattr(self.services, 'registry', None)
                if not registry or not hasattr(registry, 'get_tool_by_name'):
                    return {'error': 'Tool registry not available'}

                tool_instance = registry.get_tool_by_name(tool_name)
                if not tool_instance:
                    return {'error': f'Tool {tool_name} not found'}
                capabilities = []

                # Get capabilities
                if hasattr(tool_instance, 'capabilities'):
                    for cap_name, cap_obj in tool_instance.capabilities.items():
                        params = []
                        if hasattr(cap_obj, 'parameters'):
                            for param in cap_obj.parameters:
                                params.append({
                                    'name': param.name,
                                    'type': str(param.type),
                                    'description': param.description,
                                    'required': param.required,
                                    'default': getattr(param, 'default', None)
                                })

                        capabilities.append({
                            'name': cap_name,
                            'description': cap_obj.description,
                            'parameters': params,
                            'safety_level': str(cap_obj.safety_level)
                        })

                return {
                    'tool_name': tool_name,
                    'description': getattr(tool_instance, 'description', 'No description'),
                    'capabilities': capabilities,
                    'capability_count': len(capabilities)
                }
            except Exception as e:
                self.services.logging.error(f"Error handling get_tool_info: {str(e)}")
                return {'error': str(e)}

    def _handle_list_capabilities(self, **kwargs):
            if not self.orchestrator:
                return {'capabilities': [], 'error': 'Orchestrator not available'}

            try:
                registry = getattr(self.orchestrator, '_registry', None) or getattr(self.services, 'registry', None)
                if not registry or not hasattr(registry, 'tools'):
                    return {'capabilities': [], 'error': 'Tool registry not available'}

                all_capabilities = []
                for tool_instance in getattr(registry, 'tools', []):
                    tool_name = tool_instance.__class__.__name__
                    if hasattr(tool_instance, 'capabilities'):
                        for cap_name, cap_obj in tool_instance.capabilities.items():
                            all_capabilities.append({
                                'tool': tool_name,
                                'capability': cap_name,
                                'description': cap_obj.description
                            })

                return {
                    'capabilities': all_capabilities,
                    'count': len(all_capabilities)
                }
            except Exception as e:
                self.services.logging.error(f"Error listing capabilities: {str(e)}")
                return {'capabilities': [], 'error': str(e)}

    def _handle_get_system_stats(self, **kwargs):
            if not self.orchestrator:
                return {'error': 'Orchestrator not available'}

            try:
                registry = getattr(self.orchestrator, '_registry', None) or getattr(self.services, 'registry', None)
                if not registry or not hasattr(registry, 'tools'):
                    return {'error': 'Tool registry not available'}

                tools = list(getattr(registry, 'tools', []))
                total_tools = len(tools)
                experimental_tools = sum(1 for t in tools if getattr(t, "__module__", "").startswith("tools.experimental"))
                total_capabilities = 0

                for tool_instance in tools:
                    if hasattr(tool_instance, 'capabilities'):
                        total_capabilities += len(tool_instance.capabilities)

                return {
                    'total_tools': total_tools,
                    'experimental_tools': experimental_tools,
                    'production_tools': total_tools - experimental_tools,
                    'total_capabilities': total_capabilities,
                    'average_capabilities_per_tool': round(total_capabilities / total_tools, 2) if total_tools > 0 else 0
                }
            except Exception as e:
                self.services.logging.error(f"Error in _handle_get_system_stats: {str(e)}")
                return {'error': str(e)}
