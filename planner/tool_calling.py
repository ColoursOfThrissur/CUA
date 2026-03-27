"""Native tool calling for Mistral and compatible models"""
import json
import re
import requests
from typing import Dict, List, Optional, Any, Tuple

class ToolCallingClient:
    """LLM client with native function calling support"""

    def __init__(self, ollama_url: str, model: str, registry):
        self.ollama_url = ollama_url
        self.model = model
        self.registry = registry

        # Resolve provider from config so tool calling also routes correctly
        try:
            from core.config_manager import get_config
            cfg = get_config()
            self.provider = cfg.llm.provider
            self._api_key = cfg.llm.api_key
            self._base_url = cfg.llm.base_url
        except Exception:
            self.provider = "ollama"
            self._api_key = ""
            self._base_url = ""

    def _get_api_provider(self):
        """Build API provider instance on demand."""
        if self.provider == "openai":
            from planner.providers import OpenAIProvider
            return OpenAIProvider(api_key=self._api_key, model=self.model, base_url=self._base_url or None)
        if self.provider == "gemini":
            from planner.providers import GeminiProvider
            return GeminiProvider(api_key=self._api_key, model=self.model)
        return None
    
    def call_with_tools(
        self,
        user_message: str,
        conversation_history: List[Dict] = None,
        skill_context: Optional[Dict[str, Any]] = None,
        allowed_tools: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[List[Dict]], Optional[str]]:
        """
        Call LLM with tool definitions, let it select tools automatically
        Returns: (success, tool_calls, response_text)
        """
        
        # Build tool definitions from registry
        tools = self._build_tool_definitions(allowed_tools=allowed_tools, user_message=user_message)
        
        # Debug: Check if ContextSummarizerTool is available
        context_summarizer_available = any(
            "ContextSummarizerTool" in tool["function"]["name"] for tool in tools
        )
        print(f"[DEBUG] ContextSummarizerTool available: {context_summarizer_available}")
        if skill_context and skill_context.get("category") == "web":
            print(f"[DEBUG] Web research skill detected, ensuring summarization tools are available")
        
        # Build messages with system prompt
        system_content = """You are CUA, an autonomous agent with access to tools. CRITICAL RULES:
1. When user asks you to DO something (open, search, create, list, analyze, summarize, take screenshot), USE TOOLS
2. ONLY respond conversationally for questions ABOUT what to do (suggestions, recommendations, opinions)
3. "can you X" or "open X" or "search X" = ACTION = USE TOOLS
4. "what should I X" or "can you suggest X" = QUESTION = NO TOOLS, respond conversationally
5. For web research tasks, ALWAYS use available summarization tools after fetching content
6. When searching, look for SPECIFIC relevant URLs in search results, not generic homepages

Examples:
- "open google and search X" -> USE BrowserAutomationTool
- "search AGI development and give me a summary" -> USE WebAccessTool (search) + WebAccessTool (fetch specific URL) + ContextSummarizerTool
- "take a screenshot" -> USE BrowserAutomationTool  
- "what tool should we add?" -> NO TOOLS, respond conversationally
- "can you suggest improvements?" -> NO TOOLS, respond conversationally
- "summarize this text" -> USE ContextSummarizerTool

When doing web research:
1. First search for the topic
2. Look at search results and pick the MOST RELEVANT specific URL (not homepage)
3. Fetch that specific URL's content
4. Summarize the fetched content"""
        if skill_context:
            system_content += (
                f"\n\nActive skill: {skill_context.get('skill_name', 'unknown')}"
                f"\nSkill category: {skill_context.get('category', 'unknown')}"
                f"\nPreferred tools: {', '.join(skill_context.get('preferred_tools', [])) or 'none'}"
                f"\nExpected outputs: {', '.join(skill_context.get('output_types', [])) or 'unspecified'}"
                f"\nUse the active skill guidance when selecting tools."
            )
            if allowed_tools:
                system_content += f"\nAllowed tools for this step: {', '.join(allowed_tools)}"
            else:
                # For web research, ensure summarization tools are mentioned
                if skill_context.get("category") == "web":
                    system_content += "\nFor web research: Use WebAccessTool for searching + fetching specific URLs + ContextSummarizerTool for summarization. Always fetch SPECIFIC article URLs, not homepages."
            domain_catalog = skill_context.get("domain_catalog")
            if domain_catalog:
                system_content += (
                    "\n\nDomain planning rules:"
                    "\n- First decide which domain each action belongs to."
                    "\n- A single request may require multiple domains across different steps."
                    "\n- Prefer tools listed under the matching domain, but you may combine domains when necessary."
                    f"\nDomain catalog: {json.dumps(domain_catalog)}"
                )

        messages = [
            {
                "role": "system",
                "content": system_content
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

            # Debug: Log tool definitions being sent
            print(f"[DEBUG] Sending {len(tools)} tool definitions to LLM (provider={self.provider})")
            if tools:
                print(f"[DEBUG] First 3 tools: {[t['function']['name'] for t in tools[:3]]}")
                benchmark_tools = [t for t in tools if 'BenchmarkRunnerTool' in t['function']['name']]
                if benchmark_tools:
                    print(f"[DEBUG] BenchmarkRunnerTool operations: {[t['function']['name'] for t in benchmark_tools]}")

            # Route to API provider or Ollama
            api_provider = self._get_api_provider()
            if api_provider is not None:
                result = api_provider.chat_with_tools(messages=messages, tools=tools)
            else:
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
                allowed_set = set(allowed_tools or [])
                for call in tool_calls:
                    func = call.get("function", {})
                    full_name = func.get("name", "")
                    print(f"[DEBUG] Tool call: {full_name}")
                    # Parse ToolName_operation format.
                    # MCP adapters are registered as MCPAdapterTool_<server> so their
                    # full_name looks like MCPAdapterTool_github_list_repos.
                    # Match against actual registered tool class names first.
                    tool_name = None
                    operation = None
                    if self.registry:
                        for t in self.registry.tools:
                            # Use instance name (e.g. MCPAdapterTool_github) not class name
                            inst = getattr(t, 'name', None)
                            if callable(inst):
                                inst = t.__class__.__name__
                            inst = inst or t.__class__.__name__
                            if full_name.startswith(inst + "_"):
                                tool_name = inst
                                operation = full_name[len(inst) + 1:]
                                break
                    if tool_name is None:
                        # Fallback: split on first underscore
                        if "_" in full_name:
                            parts = full_name.split("_", 1)
                            tool_name = parts[0]
                            operation = parts[1]
                        else:
                            tool_name = full_name
                            operation = full_name
                    wrapped_operation = func.get("arguments", {}).get("operation")
                    wrapped_parameters = func.get("arguments", {}).get("parameters")
                    
                    parsed_call = {
                        "tool": tool_name,
                        "operation": operation,
                        "parameters": wrapped_parameters if wrapped_operation and isinstance(wrapped_parameters, dict) else func.get("arguments", {})
                    }
                    if allowed_set and tool_name not in allowed_set and not any(tool_name.startswith(a) for a in allowed_set):
                        print(f"[DEBUG] Skipping disallowed tool call: {tool_name}")
                        continue
                    parsed_calls.append(parsed_call)
                if not parsed_calls and allowed_set:
                    return False, None, "NO_ALLOWED_TOOL_CALLS"
                print(f"[DEBUG] Returning {len(parsed_calls)} parsed calls")
                return True, parsed_calls, None  # Return None for content when tools are called
            
            # No tool calls - check if content looks like JSON that should be tool calls
            if content and content.strip().startswith("{"):
                print(f"[DEBUG] WARNING: Content looks like JSON but wasn't parsed as tool call: {content[:100]}")
            
            if self._is_clarification_response(content):
                print("[DEBUG] Returning clarification response to UI")
                return True, None, content

            if self._is_actionable_request(user_message):
                print("[DEBUG] Actionable request returned no tool calls")
                return False, None, "NO_TOOL_CALLS_FOR_ACTIONABLE_REQUEST"

            # No tool calls - return text response
            content = message.get("content", "")
            print(f"[DEBUG] No tool calls, returning conversational response: {content[:100]}")
            return True, None, content
            
        except Exception as e:
            return False, None, str(e)
    
    # Maps category keyword-hint keys → tool class names for fallback filtering
    _CATEGORY_TOOLS = {
        "web":          {"WebAccessTool", "ContextSummarizerTool"},
        "automation":   {"BrowserAutomationTool", "WebAccessTool"},
        "computer":     {"FilesystemTool", "ShellTool"},
        "development":  {"FilesystemTool", "ShellTool", "ContextSummarizerTool"},
        "data":         {"HTTPTool", "JSONTool", "DatabaseQueryTool"},
        "productivity": {"LocalCodeSnippetLibraryTool", "LocalRunNoteTool"},
        "finance":      {"FinancialAnalysisTool"},
        "system":       {"SystemHealthTool"},
        "code_analysis": {"CodeAnalysisTool"},
    }
    # Always included regardless of category
    _CORE_TOOLS = {"FilesystemTool", "WebAccessTool", "ShellTool", "JSONTool"}

    _KEYWORD_HINTS = {
        "web":          {"web", "website", "page", "url", "research", "summarize", "search", "google", "fetch", "scrape", "content", "information", "summary", "topic"},
        "automation":   {"automate", "automation", "browser", "click", "form", "button", "screenshot", "navigate", "login", "selenium"},
        "computer":     {"file", "files", "folder", "directory", "command", "shell", "move", "create", "list", "read", "write", "system"},
        "development":  {"code", "repo", "bug", "feature", "refactor", "test", "implement", "function", "class", "debug", "analyze"},
        "data":         {"api", "http", "json", "database", "query", "sql", "parse", "endpoint", "request", "response", "data"},
        "productivity": {"snippet", "note", "notes", "save", "store", "library", "knowledge", "organize", "retrieve"},
        "finance":      {"stock", "ticker", "portfolio", "invest", "market", "trading", "finance", "financial", "crypto"},
        "system":       {"health", "cpu", "ram", "memory", "disk", "ollama", "slow", "performance", "latency", "status", "monitor", "diagnose", "circuit", "breaker", "queue", "pending"},
        "code_analysis": {"analyse", "analyze", "complexity", "maintainability", "refactor", "dead", "unused", "imports", "dependencies", "review", "quality", "issues", "lint", "static"},
    }

    def _infer_category_tools(self, user_message: str) -> Optional[List[str]]:
        """Derive a tool allow-list from message keywords when no skill is matched."""
        tokens = set(re.findall(r"[a-z0-9]+", (user_message or "").lower()))
        best_cat, best_score = None, 0
        for cat, hints in self._KEYWORD_HINTS.items():
            score = len(tokens & hints)
            if score > best_score:
                best_cat, best_score = cat, score
        if not best_cat or best_score == 0:
            return None
        allowed = self._CORE_TOOLS | self._CATEGORY_TOOLS.get(best_cat, set())
        print(f"[DEBUG] Category fallback filter: '{best_cat}' (score={best_score}) → {sorted(allowed)}")
        return list(allowed)

    def _build_tool_definitions(self, allowed_tools: Optional[List[str]] = None, user_message: str = "") -> List[Dict]:
        """Build OpenAI-compatible tool definitions from registry"""
        tools = []
        
        if not self.registry:
            return tools

        if allowed_tools:
            print(f"[DEBUG] Building tool definitions for allowed tools only: {allowed_tools}")
            allowed_set = set(allowed_tools)
            tools_to_process = [
                t for t in self.registry.tools
                if t.__class__.__name__ in allowed_set
                or any(t.__class__.__name__.startswith(a) for a in allowed_set)
            ]
            print(f"[DEBUG] Found {len(tools_to_process)} matching tools out of {len(self.registry.tools)} total")
        else:
            # No skill matched — derive category filter from message keywords
            category_filter = self._infer_category_tools(user_message)
            if category_filter:
                tools_to_process = [t for t in self.registry.tools if t.__class__.__name__ in category_filter]
                print(f"[DEBUG] Category-filtered tools: {len(tools_to_process)} of {len(self.registry.tools)}")
            else:
                print(f"[DEBUG] No filter applied - building definitions for all {len(self.registry.tools)} tools")
                tools_to_process = self.registry.tools

        # Check if WebAccessTool is available (hides raw web tools)
        raw_web_tools_hidden = any(
            tool.__class__.__name__ == "WebAccessTool" for tool in tools_to_process
        )
        
        for tool in tools_to_process:
            tool_name = tool.__class__.__name__
            # For MCP adapters, use the instance name (e.g. MCPAdapterTool_github)
            # so the LLM sees and calls the correct tool
            if hasattr(tool, 'name') and callable(getattr(tool, 'name', None)) is False:
                instance_name = tool.name
            else:
                instance_name = tool_name
            
            # Skip hidden tools when WebAccessTool is available
            if raw_web_tools_hidden and tool_name in {"HTTPTool"}:
                continue

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
                        "name": f"{instance_name}_{op_name}",
                        "description": f"{capability.description} (Tool: {instance_name})",
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required
                        }
                    }
                })
        
        print(f"[DEBUG] Built {len(tools)} tool definitions")
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

    def _is_actionable_request(self, user_message: str) -> bool:
        text = (user_message or "").strip().lower()
        if not text:
            return False

        actionable_markers = (
            "open",
            "play",
            "watch",
            "search",
            "find",
            "click",
            "navigate",
            "go to",
            "take a screenshot",
            "create",
            "move",
            "edit",
            "run",
            "automate",
        )
        informational_markers = (
            "what is",
            "why is",
            "how does",
            "explain",
            "suggest",
            "recommend",
        )

        if any(marker in text for marker in informational_markers):
            return False
        return any(marker in text for marker in actionable_markers)

    def _is_clarification_response(self, content: str) -> bool:
        text = (content or "").strip().lower()
        if not text:
            return False

        clarification_markers = (
            "could you please provide more details",
            "could you clarify",
            "can you clarify",
            "your request is unclear",
            "which one do you mean",
            "are you looking for",
            "do you mean",
            "please provide more details",
        )
        return any(marker in text for marker in clarification_markers)
