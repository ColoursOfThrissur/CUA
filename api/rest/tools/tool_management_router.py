"""Compatibility router export for tools management endpoints."""

from api.rest.tools.tools_management_api import (
    add_cors_headers,
    analyzer,
    exec_logger,
    get_tool_code,
    get_tool_detail,
    get_tool_executions,
    get_tools_list,
    get_tools_summary,
    llm_analyzer,
    router,
    trigger_health_check,
)

__all__ = [
    "add_cors_headers",
    "analyzer",
    "exec_logger",
    "get_tool_code",
    "get_tool_detail",
    "get_tool_executions",
    "get_tools_list",
    "get_tools_summary",
    "llm_analyzer",
    "router",
    "trigger_health_check",
]
