"""Native tool calling for Mistral and compatible models"""
import json
import requests
from typing import Dict, List, Optional, Any, Tuple

class ToolCallingClient:
    """LLM client with native function calling support"""
    
    def __init__(self, ollama_url: str, model: str, registry):
        self.ollama_url = ollama_url
        self.model = model
        self.registry = registry
    
    def call_with_tools(self, user_message: str, conversation_history: List[Dict] = None) -> Tuple[bool, Optional[List[Dict]], Optional[str]]:
        """
        Call LLM with tool definitions, let it select tools automatically
        Returns: (success, tool_calls, response_text)
        """
        
        # Build tool definitions from registry
        tools = self._build_tool_definitions()
        
        # Build messages with system prompt
        messages = [
            {
                "role": "system",
                "content": """You are CUA, an autonomous agent. CRITICAL RULES:
1. ONLY call tools when user explicitly requests an ACTION (analyze, summarize, create, list, read, write)
2. NEVER call tools for conversational questions (what should, can you suggest, what do you think, recommendations)
3. Questions ABOUT the system or asking for suggestions = respond conversationally, NO TOOLS
4. Commands to DO something with data = use appropriate tool

Examples:
- "what tool should we add next?" -> NO TOOLS, respond conversationally
- "summarize this text: [text]" -> USE summarize_text tool
- "can you suggest improvements?" -> NO TOOLS, respond conversationally  
- "list files in directory" -> USE list_files tool"""
            }
        ]
        if conversation_history:
            messages.extend(conversation_history[-5:])
        messages.append({"role": "user", "content": user_message})
        
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "tools": tools,
                "stream": False
            }
            
            response = requests.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                timeout=60
            )
            
            if response.status_code != 200:
                return False, None, f"HTTP {response.status_code}"
            
            result = response.json()
            message = result.get("message", {})
            
            # Check if model wants to call tools
            tool_calls = message.get("tool_calls", [])
            content = message.get("content", "")
            
            # Handle case where Mistral returns JSON in content instead of tool_calls
            if not tool_calls and content.strip().startswith("{"):
                try:
                    import json as json_lib
                    parsed = json_lib.loads(content.strip())
                    if "name" in parsed and "arguments" in parsed:
                        # Convert to tool_calls format
                        tool_calls = [{"function": parsed}]
                except:
                    pass
            
            if tool_calls:
                # Model selected tools - return them
                parsed_calls = []
                for call in tool_calls:
                    func = call.get("function", {})
                    full_name = func.get("name", "")
                    # Parse ToolName_operation_name format
                    if "_" in full_name:
                        parts = full_name.split("_", 1)  # Split only on first underscore
                        tool_name = parts[0]
                        operation = parts[1] if len(parts) > 1 else full_name
                    else:
                        tool_name = full_name
                        operation = full_name
                    
                    parsed_calls.append({
                        "tool": tool_name,
                        "operation": operation,
                        "parameters": func.get("arguments", {})
                    })
                return True, parsed_calls, None
            
            # No tool calls - return text response
            content = message.get("content", "")
            return True, None, content
            
        except Exception as e:
            return False, None, str(e)
    
    def _build_tool_definitions(self) -> List[Dict]:
        """Build OpenAI-compatible tool definitions from registry"""
        tools = []
        
        if not self.registry:
            return tools
        
        for tool in self.registry.tools:
            tool_name = tool.__class__.__name__
            capabilities = tool.get_capabilities() or {}
            
            for op_name, capability in capabilities.items():
                # Build function definition
                properties = {}
                required = []
                
                for param in capability.parameters:
                    properties[param.name] = {
                        "type": self._map_param_type(param.type),
                        "description": param.description
                    }
                    if param.required:
                        required.append(param.name)
                
                tools.append({
                    "type": "function",
                    "function": {
                        "name": f"{tool_name}_{op_name}",
                        "description": f"{capability.description} (Tool: {tool_name})",
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required
                        }
                    }
                })
        
        return tools
    
    def _map_param_type(self, param_type) -> str:
        """Map ParameterType to JSON schema type"""
        type_str = str(param_type).lower()
        if "string" in type_str:
            return "string"
        elif "int" in type_str:
            return "integer"
        elif "float" in type_str or "number" in type_str:
            return "number"
        elif "bool" in type_str:
            return "boolean"
        elif "dict" in type_str or "object" in type_str:
            return "object"
        elif "list" in type_str or "array" in type_str:
            return "array"
        return "string"
