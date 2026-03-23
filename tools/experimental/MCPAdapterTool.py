"""
MCPAdapterTool — bridges any MCP (Model Context Protocol) server into CUA's tool registry.

How it works:
  1. On init, calls tools/list on the configured MCP server.
  2. Dynamically registers each MCP tool as a ToolCapability.
  3. Execution proxies the call to tools/call via JSON-RPC 2.0.

Configuration (config.yaml or env):
  mcp_servers:
    - name: puppeteer
      url: http://localhost:3100   # MCP server base URL
      enabled: true
    - name: github
      url: http://localhost:3101
      enabled: false

The adapter can also be instantiated directly:
  MCPAdapterTool(server_name="puppeteer", server_url="http://localhost:3100")
"""
import json
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus


# ---------------------------------------------------------------------------
# Minimal JSON-RPC 2.0 client (no extra deps — uses stdlib urllib)
# ---------------------------------------------------------------------------

class _JsonRpcClient:
    def __init__(self, base_url: str, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._id = 0

    def call(self, method: str, params: Dict) -> Any:
        self._id += 1
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": self._id,
            "method": method,
            "params": params,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/rpc",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"MCP HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"MCP connection failed: {e.reason}")

        if "error" in body:
            raise RuntimeError(f"MCP error {body['error'].get('code')}: {body['error'].get('message')}")
        return body.get("result")


# ---------------------------------------------------------------------------
# MCP schema → CUA ParameterType mapping
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "string":  ParameterType.STRING,
    "integer": ParameterType.INTEGER,
    "number":  ParameterType.INTEGER,
    "boolean": ParameterType.BOOLEAN,
    "array":   ParameterType.LIST,
    "object":  ParameterType.DICT,
}


def _mcp_schema_to_params(input_schema: Dict) -> tuple[List[Parameter], List[str]]:
    """Convert MCP inputSchema (JSON Schema) to CUA Parameter list."""
    props = (input_schema or {}).get("properties") or {}
    required_names = set((input_schema or {}).get("required") or [])
    params: List[Parameter] = []
    for name, schema in props.items():
        params.append(Parameter(
            name=name,
            type=_TYPE_MAP.get(schema.get("type", "string"), ParameterType.STRING),
            description=schema.get("description", name),
            required=name in required_names,
            default=schema.get("default"),
        ))
    return params, list(required_names)


# ---------------------------------------------------------------------------
# MCPAdapterTool
# ---------------------------------------------------------------------------

class MCPAdapterTool(BaseTool):
    """
    Dynamically wraps an MCP server as a CUA tool.
    Capabilities are discovered at init time via tools/list.
    """

    TOOL_NAME = "MCPAdapterTool"

    def __init__(self, orchestrator=None, server_name: str = "", server_url: str = ""):
        self._server_name = server_name
        self._server_url = server_url
        self._rpc: Optional[_JsonRpcClient] = None
        self._mcp_tools: Dict[str, Dict] = {}   # mcp_tool_name → schema
        self._connected = False
        self._init_error: Optional[str] = None

        # Resolve config if not passed directly
        if not self._server_url:
            self._server_name, self._server_url = self._load_first_enabled_server()

        if self._server_url:
            self._rpc = _JsonRpcClient(self._server_url)

        super().__init__()  # calls register_capabilities

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_first_enabled_server() -> tuple[str, str]:
        try:
            from core.config_manager import get_config
            cfg = get_config()
            servers = getattr(cfg, "mcp_servers", None) or []
            for s in servers:
                name = s.get("name", "mcp") if isinstance(s, dict) else getattr(s, "name", "mcp")
                url = s.get("url", "") if isinstance(s, dict) else getattr(s, "url", "")
                enabled = s.get("enabled", False) if isinstance(s, dict) else getattr(s, "enabled", False)
                if enabled:
                    return name, url
        except Exception:
            pass
        return "", ""

    # ------------------------------------------------------------------
    # BaseTool contract
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        suffix = f"_{self._server_name}" if self._server_name else ""
        return f"MCPAdapterTool{suffix}"

    def register_capabilities(self):
        # Static capabilities — always present so AST extractor and registry can discover this tool
        self.add_capability(ToolCapability(
            name="call_tool",
            description="Call a specific tool on the connected MCP server by name with arguments.",
            parameters=[
                Parameter("tool_name", ParameterType.STRING, "Name of the MCP tool to call", required=True),
                Parameter("arguments", ParameterType.DICT, "Arguments to pass to the MCP tool", required=False),
            ],
            returns="MCP tool result with success, result, and server info.",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"tool_name": "puppeteer_navigate", "arguments": {"url": "https://example.com"}}],
        ), self._handle_call_tool)

        self.add_capability(ToolCapability(
            name="list_tools",
            description="List all tools available on the connected MCP server.",
            parameters=[],
            returns="List of available MCP tool names and descriptions.",
            safety_level=SafetyLevel.LOW,
            examples=[],
        ), self._handle_list_tools)

        self.add_capability(ToolCapability(
            name="get_server_info",
            description="Get connection status and metadata for the connected MCP server.",
            parameters=[],
            returns="Server name, URL, connection status, and tool count.",
            safety_level=SafetyLevel.LOW,
            examples=[],
        ), self._handle_get_server_info)

        # Dynamic capabilities — discovered from live MCP server at runtime
        if not self._rpc:
            return
        try:
            result = self._rpc.call("tools/list", {})
            tools = (result or {}).get("tools") or []
            for tool in tools:
                self._register_mcp_tool(tool)
            self._connected = True
        except Exception as e:
            self._init_error = str(e)
            print(f"[MCPAdapter] Could not connect to {self._server_url}: {e}")

    def _register_mcp_tool(self, tool_schema: Dict):
        mcp_name: str = tool_schema.get("name", "")
        if not mcp_name:
            return

        params, _ = _mcp_schema_to_params(tool_schema.get("inputSchema") or {})
        cap = ToolCapability(
            name=mcp_name,
            description=tool_schema.get("description", mcp_name),
            parameters=params,
            returns="MCP tool result",
            safety_level=SafetyLevel.MEDIUM,
            examples=[],
        )
        self._mcp_tools[mcp_name] = tool_schema

        # Bind a closure so each capability has its own mcp_name captured
        def _make_handler(name: str):
            def _handler(**kwargs):
                return self._call_mcp(name, kwargs)
            return _handler

        self.add_capability(cap, _make_handler(mcp_name))

    # ------------------------------------------------------------------
    # Static handlers
    # ------------------------------------------------------------------

    def _handle_call_tool(self, tool_name: str, arguments: dict = None, **kwargs) -> dict:
        if not tool_name:
            raise ValueError("tool_name is required")
        return self._call_mcp(tool_name, arguments or {})

    def _handle_list_tools(self, **kwargs) -> dict:
        return {
            "success": True,
            "connected": self._connected,
            "server": self._server_name,
            "tools": [
                {"name": name, "description": schema.get("description", "")}
                for name, schema in self._mcp_tools.items()
            ],
            "count": len(self._mcp_tools),
        }

    def _handle_get_server_info(self, **kwargs) -> dict:
        return self.get_server_info()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, operation: str, **kwargs) -> Any:
        if operation in self._capabilities:
            return self.execute_capability(operation, **kwargs)
        return self._call_mcp(operation, kwargs)

    def _call_mcp(self, tool_name: str, arguments: Dict) -> Dict:
        if not self._rpc:
            return {"success": False, "error": "MCP adapter not configured"}
        if not self._connected and self._init_error:
            return {"success": False, "error": f"MCP server unavailable: {self._init_error}"}

        try:
            result = self._rpc.call("tools/call", {
                "name": tool_name,
                "arguments": arguments,
            })
            # MCP tools/call returns {content: [...], isError: bool}
            is_error = (result or {}).get("isError", False)
            content = (result or {}).get("content") or []
            # Flatten text content blocks into a single string
            text_parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            payload = "\n".join(text_parts) if text_parts else result
            return {
                "success": not is_error,
                "result": payload,
                "mcp_server": self._server_name,
                "tool": tool_name,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "tool": tool_name}

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        return self._connected

    def get_server_info(self) -> Dict:
        return {
            "server_name": self._server_name,
            "server_url": self._server_url,
            "connected": self._connected,
            "tool_count": len(self._mcp_tools),
            "tools": list(self._mcp_tools.keys()),
            "init_error": self._init_error,
        }
