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
                "content": """You are CUA, an autonomous agent with access to tools. CRITICAL RULES:
1. When user asks you to DO something (open, search, create, list, analyze, summarize, take screenshot), USE TOOLS
2. ONLY respond conversationally for questions ABOUT what to do (suggestions, recommendations, opinions)
3. "can you X" or "open X" or "search X" = ACTION = USE TOOLS
4. "what should I X" or "can you suggest X" = QUESTION = NO TOOLS, respond conversationally

Examples:
- "open google and search X" -> USE BrowserAutomationTool
- "take a screenshot" -> USE BrowserAutomationTool  
- "what tool should we add?" -> NO TOOLS, respond conversationally
- "can you suggest improvements?" -> NO TOOLS, respond conversationally
- "summarize this text" -> USE ContextSummarizerTool"""
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
            if not tool_calls and content:
                print(f"[DEBUG] No tool_calls, checking content: {content[:200]}")
                # Strip markdown code blocks
                stripped = content.strip()
                if stripped.startswith("```"):
                    lines = stripped.split("\n")
                    # Remove first line (```json or ```) and last line (```)
                    if len(lines) > 2:
                        stripped = "\n".join(lines[1:-1]).strip()
                        print(f"[DEBUG] Stripped markdown: {stripped[:200]}")
                
                # Try parsing as single tool call or array of tool calls
                if stripped.startswith("{") or stripped.startswith("["):
                    try:
                        import json as json_lib
                        print(f"[DEBUG] Attempting JSON parse...")
                        parsed = json_lib.loads(stripped)
                        print(f"[DEBUG] Parsed type: {type(parsed)}")
                        
                        # Handle array of tool calls
                        if isinstance(parsed, list):
                            print(f"[DEBUG] Found array with {len(parsed)} items")
                            tool_calls = [{"function": call} for call in parsed if "name" in call]
                            if tool_calls:
                                print(f"[DEBUG] Extracted {len(tool_calls)} tool calls from array")
                                content = ""  # Clear content since we extracted tool calls
                        # Handle single tool call
                        elif isinstance(parsed, dict) and "name" in parsed and "arguments" in parsed:
                            print(f"[DEBUG] Found single tool call: {parsed.get('name')}")
                            tool_calls = [{"function": parsed}]
                            content = ""  # Clear content since we extracted tool calls
                    except Exception as e:
                        print(f"[DEBUG] JSON parse failed: {e}")
                        pass
                # Handle multiple JSON objects separated by newlines (common LLM output)
                elif "{" in stripped:
                    try:
                        import json as json_lib
                        import re
                        # Extract all complete JSON objects using regex
                        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
                        matches = re.findall(json_pattern, stripped, re.DOTALL)
                        calls = []
                        for match in matches:
                            try:
                                parsed = json_lib.loads(match)
                                if "name" in parsed and "arguments" in parsed:
                                    calls.append({"function": parsed})
                            except:
                                pass
                        if calls:
                            tool_calls = calls
                            content = ""  # Clear content since we extracted tool calls
                    except:
                        pass
            
            if tool_calls:
                # Model selected tools - return them (ignore any text content)
                print(f"[DEBUG] Processing {len(tool_calls)} tool calls")
                parsed_calls = []
                for call in tool_calls:
                    func = call.get("function", {})
                    full_name = func.get("name", "")
                    print(f"[DEBUG] Tool call: {full_name}")
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
                print(f"[DEBUG] Returning {len(parsed_calls)} parsed calls")
                return True, parsed_calls, None  # Return None for content when tools are called
            
            # No tool calls - check if content looks like JSON that should be tool calls
            if content and content.strip().startswith("{"):
                print(f"[DEBUG] WARNING: Content looks like JSON but wasn't parsed as tool call: {content[:100]}")
            
            # No tool calls - return text response
            content = message.get("content", "")
            print(f"[DEBUG] No tool calls, returning conversational response: {content[:100]}")
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
