"""
MCP Adapter API — status and management endpoints.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/mcp", tags=["mcp"])

_registry = None

def set_registry(reg):
    global _registry
    _registry = reg


@router.get("/status")
async def mcp_status():
    """Return status of all loaded MCP adapter tools."""
    if not _registry:
        return {"adapters": [], "total": 0}

    adapters = []
    for tool in _registry.tools:
        if tool.__class__.__name__.startswith("MCPAdapterTool"):
            try:
                info = tool.get_server_info()
                adapters.append(info)
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
    if not _registry:
        return {"tools": []}

    tools = []
    for tool in _registry.tools:
        if not tool.__class__.__name__.startswith("MCPAdapterTool"):
            continue
        try:
            info = tool.get_server_info()
            if not info.get("connected"):
                continue
            for cap_name in info.get("tools", []):
                tools.append({
                    "capability": cap_name,
                    "server": info["server_name"],
                    "adapter": tool.name,
                })
        except Exception:
            pass

    return {"tools": tools, "total": len(tools)}
