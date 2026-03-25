"""
MCP Adapter API — status, management, and runtime-connect endpoints.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/mcp", tags=["mcp"])

_registry = None

# Static metadata per known server (package name for display/install hints)
_SERVER_META = {
    "puppeteer":    {"package": "@modelcontextprotocol/server-puppeteer"},
    "filesystem":   {"package": "@modelcontextprotocol/server-filesystem"},
    "git":          {"package": "@modelcontextprotocol/server-git"},
    "sqlite":       {"package": "@modelcontextprotocol/server-sqlite"},
    "fetch":        {"package": "@modelcontextprotocol/server-fetch"},
    "memory":       {"package": "@modelcontextprotocol/server-memory"},
    "brave-search": {"package": "@modelcontextprotocol/server-brave-search"},
    "github":       {"package": "@modelcontextprotocol/server-github"},
    "slack":        {"package": "@modelcontextprotocol/server-slack"},
    "gdrive":       {"package": "@modelcontextprotocol/server-gdrive"},
}


def set_registry(reg):
    global _registry
    _registry = reg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_adapters():
    if not _registry:
        return []
    return [t for t in _registry.tools if t.__class__.__name__.startswith("MCPAdapterTool")]


def _find_adapter(name: str):
    for t in _get_adapters():
        if t._server_name == name:
            return t
    return None


def _get_configured_servers():
    try:
        from core.config_manager import get_config
        return get_config().mcp_servers or []
    except Exception:
        return []


def _build_adapter_from_config(target):
    from tools.experimental.MCPAdapterTool import MCPAdapterTool
    return MCPAdapterTool(
        server_name=target.name,
        transport=getattr(target, "transport", "stdio"),
        command=getattr(target, "command", ""),
        server_url=getattr(target, "url", ""),
        rpc_path=getattr(target, "rpc_path", "/rpc"),
        env_key=getattr(target, "env_key", ""),
    )


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
async def mcp_status():
    """Return status of all loaded MCP adapter tools."""
    adapters = []
    for tool in _get_adapters():
        try:
            adapters.append(tool.get_server_info())
        except Exception as e:
            adapters.append({"error": str(e)})
    return {
        "adapters": adapters,
        "total": len(adapters),
        "connected": sum(1 for a in adapters if a.get("connected")),
    }


@router.get("/tools")
async def mcp_tools():
    """List all capabilities exposed by connected MCP adapters."""
    tools = []
    for tool in _get_adapters():
        try:
            info = tool.get_server_info()
            if not info.get("connected"):
                continue
            for cap_name in info.get("tools", []):
                tools.append({"capability": cap_name, "server": info["server_name"], "adapter": tool.name})
        except Exception:
            pass
    return {"tools": tools, "total": len(tools)}


@router.get("/configured")
async def mcp_configured():
    """Return all servers defined in config.yaml with live status + credential state."""
    from core.credential_store import get_credential_store
    store = get_credential_store()
    servers = _get_configured_servers()
    result = []
    for s in servers:
        name = s.name
        meta = _SERVER_META.get(name, {})
        transport = getattr(s, "transport", "stdio")
        env_key = getattr(s, "env_key", "") or ""
        adapter = _find_adapter(name)
        result.append({
            "name": name,
            "transport": transport,
            "command": getattr(s, "command", ""),
            "url": getattr(s, "url", ""),
            "enabled": s.enabled,
            "package": meta.get("package", ""),
            "env_key": env_key or None,
            "credential_set": store.exists(env_key) if env_key else None,
            "loaded": adapter is not None,
            "connected": adapter.is_connected() if adapter else False,
            "tool_count": len(adapter._mcp_tools) if adapter else 0,
            "init_error": adapter._init_error if adapter else None,
        })
    return {"servers": result, "total": len(result)}


@router.get("/processes")
async def mcp_processes():
    """Return status for all managed MCP adapter instances."""
    from core.mcp_process_manager import get_mcp_process_manager
    return {"processes": get_mcp_process_manager().status()}


# ---------------------------------------------------------------------------
# Configure — enable/disable + store credential in one call
# ---------------------------------------------------------------------------

class ConfigureRequest(BaseModel):
    name: str
    enabled: bool
    credential_value: Optional[str] = None


@router.post("/configure")
async def mcp_configure(req: ConfigureRequest):
    """
    Enable or disable a configured server and optionally store its API key.
    On enable with stdio transport: spawns the process and connects immediately.
    """
    servers = _get_configured_servers()
    target = next((s for s in servers if s.name == req.name), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Server '{req.name}' not found in config.yaml")

    env_key = getattr(target, "env_key", "") or ""

    # Store credential if provided
    if req.credential_value and env_key:
        from core.credential_store import get_credential_store
        get_credential_store().set(
            env_key,
            req.credential_value,
            description=f"API key for MCP server '{req.name}'",
            allowed_tools=[f"MCPAdapterTool_{req.name}"],
        )

    # Update enabled flag in config.yaml
    try:
        import yaml
        from pathlib import Path
        config_path = Path("config.yaml")
        raw = yaml.safe_load(config_path.read_text()) or {}
        for entry in raw.get("mcp_servers", []):
            if entry.get("name") == req.name:
                entry["enabled"] = req.enabled
                break
        config_path.write_text(yaml.dump(raw, default_flow_style=False, allow_unicode=True, sort_keys=False))
        from core.config_manager import reload_config
        reload_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config.yaml: {e}")

    # Attempt hot-connect if enabling
    connect_result = None
    if req.enabled and _registry:
        existing = _find_adapter(req.name)
        if existing:
            connected = existing.reconnect()
            connect_result = {"action": "reconnected", "connected": connected, "error": existing._init_error}
        else:
            try:
                adapter = _build_adapter_from_config(target)
                if adapter.is_connected():
                    _registry.register_tool(adapter)
                    from core.mcp_process_manager import get_mcp_process_manager
                    get_mcp_process_manager().register_adapter(req.name, adapter)
                    connect_result = {"action": "connected", "connected": True, "tools": len(adapter._mcp_tools)}
                else:
                    connect_result = {"action": "not_reachable", "connected": False, "error": adapter._init_error}
            except Exception as e:
                connect_result = {"action": "error", "connected": False, "error": str(e)}

    return {
        "success": True,
        "name": req.name,
        "enabled": req.enabled,
        "credential_stored": bool(req.credential_value and env_key),
        "connect_result": connect_result,
    }


# ---------------------------------------------------------------------------
# Start / Stop (trigger adapter spawn on demand)
# ---------------------------------------------------------------------------

@router.post("/start/{name}")
async def mcp_start(name: str):
    """Spawn the MCP adapter process and connect it to the registry."""
    if not _registry:
        raise HTTPException(status_code=503, detail="Registry not available")
    servers = _get_configured_servers()
    target = next((s for s in servers if s.name == name), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found in config.yaml")

    existing = _find_adapter(name)
    if existing:
        connected = existing.reconnect()
        return {"success": connected, "name": name, "action": "reconnected",
                "tools": len(existing._mcp_tools), "error": existing._init_error}

    try:
        adapter = _build_adapter_from_config(target)
    except Exception as e:
        return {"success": False, "name": name, "error": str(e)}

    if adapter.is_connected():
        _registry.register_tool(adapter)
        from core.mcp_process_manager import get_mcp_process_manager
        get_mcp_process_manager().register_adapter(name, adapter)
        return {"success": True, "name": name, "action": "connected", "tools": len(adapter._mcp_tools)}

    return {"success": False, "name": name, "action": "failed", "error": adapter._init_error}


@router.post("/stop/{name}")
async def mcp_stop(name: str):
    """Shut down a loaded MCP adapter and remove it from the registry."""
    adapter = _find_adapter(name)
    if adapter:
        try:
            adapter.shutdown()
        except Exception:
            pass
        if _registry:
            try:
                _registry.tools.remove(adapter)
            except Exception:
                pass
    from core.mcp_process_manager import get_mcp_process_manager
    get_mcp_process_manager().unregister_adapter(name)
    return {"success": True, "name": name}


# ---------------------------------------------------------------------------
# Disconnect / Reconnect
# ---------------------------------------------------------------------------

@router.delete("/disconnect/{name}")
async def mcp_disconnect(name: str):
    """Remove a loaded MCP adapter from the registry."""
    if not _registry:
        raise HTTPException(status_code=503, detail="Registry not available")
    adapter = _find_adapter(name)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"No adapter named '{name}' is loaded.")
    try:
        adapter.shutdown()
        _registry.tools.remove(adapter)
        caps = [k for k, v in list(_registry._capabilities.items())
                if getattr(v, "tool_name", None) == adapter.name or k.startswith(f"{adapter.name}.")]
        for cap in caps:
            _registry._capabilities.pop(cap, None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error removing adapter: {e}")
    return {"success": True, "message": f"Adapter '{name}' disconnected."}


@router.post("/reconnect/{name}")
async def mcp_reconnect(name: str):
    """Re-probe an already-loaded adapter and refresh its tool list."""
    if not _registry:
        raise HTTPException(status_code=503, detail="Registry not available")
    adapter = _find_adapter(name)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"No adapter named '{name}' is loaded.")
    connected = adapter.reconnect()
    return {
        "success": connected,
        "message": f"Reconnected to '{name}' — {len(adapter._mcp_tools)} tools." if connected
                   else f"Could not reconnect to '{name}': {adapter._init_error}",
        "server_info": adapter.get_server_info(),
    }


# ---------------------------------------------------------------------------
# Custom connect (ad-hoc, not in config.yaml)
# ---------------------------------------------------------------------------

class ConnectRequest(BaseModel):
    name: str
    transport: str = "stdio"
    command: str = ""
    url: str = ""
    rpc_path: str = "/rpc"
    env_key: str = ""


@router.post("/connect")
async def mcp_connect(req: ConnectRequest):
    """Attach a custom MCP server at runtime."""
    if not _registry:
        raise HTTPException(status_code=503, detail="Registry not available")
    if _find_adapter(req.name):
        raise HTTPException(status_code=409, detail=f"Adapter '{req.name}' already loaded.")
    try:
        from tools.experimental.MCPAdapterTool import MCPAdapterTool
        adapter = MCPAdapterTool(
            server_name=req.name,
            transport=req.transport,
            command=req.command,
            server_url=req.url,
            rpc_path=req.rpc_path,
            env_key=req.env_key,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not adapter.is_connected():
        return {"success": False, "message": f"Could not connect to '{req.name}'.", "error": adapter._init_error}
    _registry.register_tool(adapter)
    from core.mcp_process_manager import get_mcp_process_manager
    get_mcp_process_manager().register_adapter(req.name, adapter)
    return {"success": True, "message": f"Connected — {len(adapter._mcp_tools)} tools.", "server_info": adapter.get_server_info()}
