"""
MCPAdapterTool — bridges any MCP server into CUA's tool registry.

Supports two transports:
  - stdio  (default): spawns the npx process directly, communicates via stdin/stdout
  - http:             posts JSON-RPC 2.0 to a running HTTP MCP server

Configuration (config.yaml):
  mcp_servers:
    - name: memory
      transport: stdio
      command: npx -y @modelcontextprotocol/server-memory
      enabled: true

    - name: my-http-server
      transport: http
      url: http://localhost:3200
      rpc_path: /rpc
      enabled: true
"""
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus


# ---------------------------------------------------------------------------
# HTTP JSON-RPC 2.0 client (unchanged)
# ---------------------------------------------------------------------------

class _HttpRpcClient:
    def __init__(self, base_url: str, timeout: int = 15, rpc_path: str = "/rpc"):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.rpc_path = "/" + rpc_path.lstrip("/")
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
            f"{self.base_url}{self.rpc_path}",
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

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Stdio JSON-RPC 2.0 client
# Spawns the npx process, writes requests to stdin, reads responses from stdout.
# Responses are newline-delimited JSON objects.
# ---------------------------------------------------------------------------

class _StdioRpcClient:
    def __init__(self, command: str, env: Optional[Dict] = None, timeout: int = 30):
        self._command = command
        self._env = env or dict(os.environ)
        self._timeout = timeout
        self._proc: Optional[subprocess.Popen] = None
        self._id = 0
        self._lock = threading.Lock()
        self._pending: Dict[int, queue.Queue] = {}
        self._reader_thread: Optional[threading.Thread] = None
        self._closed = False

    def start(self) -> None:
        """Spawn the process and start the stdout reader thread."""
        use_shell = os.name == "nt"
        self._proc = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=self._env,
            shell=use_shell,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def _read_loop(self) -> None:
        """Continuously read newline-delimited JSON from stdout and dispatch to waiters."""
        while not self._closed:
            try:
                line = self._proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg_id = msg.get("id")
                if msg_id is not None:
                    with self._lock:
                        q = self._pending.pop(msg_id, None)
                    if q:
                        q.put(msg)
            except Exception:
                break

    def call(self, method: str, params: Dict) -> Any:
        if self._proc is None or self._proc.poll() is not None:
            raise RuntimeError("MCP stdio process is not running")

        with self._lock:
            self._id += 1
            call_id = self._id
            response_q: queue.Queue = queue.Queue()
            self._pending[call_id] = response_q

        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": call_id,
            "method": method,
            "params": params,
        }) + "\n"

        try:
            self._proc.stdin.write(payload.encode())
            self._proc.stdin.flush()
        except Exception as e:
            with self._lock:
                self._pending.pop(call_id, None)
            raise RuntimeError(f"Failed to write to MCP stdin: {e}")

        try:
            response = response_q.get(timeout=self._timeout)
        except queue.Empty:
            with self._lock:
                self._pending.pop(call_id, None)
            raise RuntimeError(f"MCP stdio timeout after {self._timeout}s waiting for response to '{method}'")

        if "error" in response:
            raise RuntimeError(f"MCP error {response['error'].get('code')}: {response['error'].get('message')}")
        return response.get("result")

    def close(self) -> None:
        self._closed = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None


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
    Supports stdio (default) and http transports.
    """

    TOOL_NAME = "MCPAdapterTool"

    def __init__(
        self,
        orchestrator=None,
        server_name: str = "",
        server_url: str = "",
        rpc_path: str = "/rpc",
        transport: str = "stdio",
        command: str = "",
        env_key: str = "",
    ):
        self._server_name = server_name
        self._server_url = server_url
        self._rpc_path = rpc_path
        self._transport = transport
        self._command = command
        self._env_key = env_key
        self._rpc = None          # _HttpRpcClient or _StdioRpcClient
        self._mcp_tools: Dict[str, Dict] = {}
        self._connected = False
        self._init_error: Optional[str] = None

        # Resolve from config if not passed directly
        if not self._server_name:
            self._load_from_config()

        super().__init__()  # calls register_capabilities

    def _load_from_config(self) -> None:
        try:
            from shared.config.config_manager import get_config
            servers = get_config().mcp_servers or []
            for s in servers:
                if getattr(s, "enabled", False):
                    self._server_name = s.name
                    self._transport = getattr(s, "transport", "stdio")
                    self._command = getattr(s, "command", "")
                    self._server_url = getattr(s, "url", "")
                    self._rpc_path = getattr(s, "rpc_path", "/rpc")
                    self._env_key = getattr(s, "env_key", "")
                    break
        except Exception:
            pass

    # ------------------------------------------------------------------
    # BaseTool contract
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        suffix = f"_{self._server_name}" if self._server_name else ""
        return f"MCPAdapterTool{suffix}"

    def register_capabilities(self):
        self.add_capability(ToolCapability(
            name="call_tool",
            description="Call a specific tool on the connected MCP server by name with arguments.",
            parameters=[
                Parameter("tool_name", ParameterType.STRING, "Name of the MCP tool to call", required=True),
                Parameter("arguments", ParameterType.DICT, "Arguments to pass to the MCP tool", required=False),
            ],
            returns="MCP tool result with success, result, and server info.",
            safety_level=SafetyLevel.MEDIUM,
            examples=[],
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
            returns="Server name, transport, connection status, and tool count.",
            safety_level=SafetyLevel.LOW,
            examples=[],
        ), self._handle_get_server_info)

        # Build the right client and discover tools
        try:
            self._rpc = self._build_client()
            if self._rpc is None:
                return
            result = self._rpc.call("tools/list", {})
            tools = (result or {}).get("tools") or []
            for tool in tools:
                self._register_mcp_tool(tool)
            self._connected = True
        except Exception as e:
            self._init_error = str(e)
            if self._rpc:
                try:
                    self._rpc.close()
                except Exception:
                    pass
                self._rpc = None

    def _build_client(self):
        if self._transport == "http":
            if not self._server_url:
                return None
            return _HttpRpcClient(self._server_url, rpc_path=self._rpc_path)

        # stdio transport
        if not self._command:
            return None
        env = self._build_env()
        if env is None:
            self._init_error = f"Required credential '{self._env_key}' not set in credential store"
            return None
        client = _StdioRpcClient(self._command, env=env)
        client.start()
        # Puppeteer needs a few seconds to launch Chromium
        wait = 5 if "puppeteer" in self._command else 3
        time.sleep(wait)
        if not client.is_alive():
            raise RuntimeError("MCP stdio process exited immediately after start")
        # MCP initialize handshake (required by newer servers before tools/list)
        try:
            client.call("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "cua", "version": "1.0"},
            })
        except Exception:
            pass  # older servers don't require it
        return client

    def _build_env(self) -> Optional[Dict]:
        env = dict(os.environ)
        if not self._env_key:
            return env
        # Try credential store
        try:
            from infrastructure.persistence.credential_store import get_credential_store
            value = get_credential_store().get(self._env_key)
            if value:
                env[self._env_key] = value
                return env
        except Exception:
            pass
        # Fall back to process env
        if os.environ.get(self._env_key):
            return env
        return None  # required but missing

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

        def _make_handler(name: str):
            def _handler(**kwargs):
                return self._call_mcp(name, kwargs)
            return _handler

        self.add_capability(cap, _make_handler(mcp_name))

    # ------------------------------------------------------------------
    # Handlers
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
            "transport": self._transport,
            "tools": [
                {"name": n, "description": s.get("description", "")}
                for n, s in self._mcp_tools.items()
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
            return {"success": False, "error": "MCP adapter not connected"}
        if not self._connected and self._init_error:
            return {"success": False, "error": f"MCP server unavailable: {self._init_error}"}
        try:
            result = self._rpc.call("tools/call", {"name": tool_name, "arguments": arguments})
            is_error = (result or {}).get("isError", False)
            content = (result or {}).get("content") or []
            text_parts = [
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            payload = "\n".join(text_parts) if text_parts else result
            return {"success": not is_error, "result": payload, "mcp_server": self._server_name, "tool": tool_name}
        except Exception as e:
            return {"success": False, "error": str(e), "tool": tool_name}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        return self._connected

    def reconnect(self) -> bool:
        if self._rpc:
            try:
                self._rpc.close()
            except Exception:
                pass
        self._rpc = None
        self._mcp_tools.clear()
        self._connected = False
        self._init_error = None
        # Re-run capability discovery
        try:
            self._rpc = self._build_client()
            if self._rpc is None:
                return False
            result = self._rpc.call("tools/list", {})
            tools = (result or {}).get("tools") or []
            for tool in tools:
                self._register_mcp_tool(tool)
            self._connected = True
        except Exception as e:
            self._init_error = str(e)
        return self._connected

    def shutdown(self) -> None:
        """Clean up the stdio process on CUA shutdown."""
        if self._rpc:
            try:
                self._rpc.close()
            except Exception:
                pass

    def get_server_info(self) -> Dict:
        return {
            "server_name": self._server_name,
            "transport": self._transport,
            "server_url": self._server_url if self._transport == "http" else "",
            "command": self._command if self._transport == "stdio" else "",
            "connected": self._connected,
            "tool_count": len(self._mcp_tools),
            "tools": list(self._mcp_tools.keys()),
            "init_error": self._init_error,
        }
