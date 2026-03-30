"""Compatibility router export for pending tool creation endpoints."""

from api.rest.tools.pending_tools_router import (
    RejectRequest,
    approve_tool,
    get_active_tools,
    get_pending_tools,
    get_tool_details,
    pending_tools_manager,
    reject_tool,
    registry_manager,
    router,
    set_pending_tools_manager,
    set_registry_manager_for_pending,
    set_tool_registrar,
    test_tool,
    tool_registrar,
)

__all__ = [
    "RejectRequest",
    "approve_tool",
    "get_active_tools",
    "get_pending_tools",
    "get_tool_details",
    "pending_tools_manager",
    "reject_tool",
    "registry_manager",
    "router",
    "set_pending_tools_manager",
    "set_registry_manager_for_pending",
    "set_tool_registrar",
    "test_tool",
    "tool_registrar",
]
