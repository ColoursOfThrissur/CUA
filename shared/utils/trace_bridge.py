"""Shared trace broadcasting bridge.

Allows application-layer code to emit trace events without importing API modules.
The API websocket layer registers the concrete broadcaster at startup.
"""

from __future__ import annotations

from typing import Callable, Optional


TraceBroadcaster = Callable[[str, str, str, Optional[dict]], None]


def _noop_broadcaster(
    trace_type: str,
    message: str,
    status: str = "in_progress",
    details: Optional[dict] = None,
) -> None:
    """Default broadcaster used before the API layer registers a real one."""
    return None


_broadcast_trace_sync: TraceBroadcaster = _noop_broadcaster


def set_broadcast_trace_sync(broadcaster: Optional[TraceBroadcaster]) -> None:
    """Register the concrete sync broadcaster."""
    global _broadcast_trace_sync
    _broadcast_trace_sync = broadcaster or _noop_broadcaster


def broadcast_trace_sync(
    trace_type: str,
    message: str,
    status: str = "in_progress",
    details: Optional[dict] = None,
) -> None:
    """Forward trace events through the currently registered broadcaster."""
    _broadcast_trace_sync(trace_type, message, status, details)
