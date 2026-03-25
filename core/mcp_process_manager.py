"""
MCPProcessManager — tracks MCP adapter instances and handles shutdown cleanup.

For stdio transport: the MCPAdapterTool spawns and owns its process.
  The manager just holds references so shutdown() can be called on all of them.

For http transport: the manager can optionally spawn an external npx process
  (only needed if you're running an HTTP-mode MCP server).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MCPProcessManager:
    """Tracks MCP adapter tool instances for clean shutdown."""

    def __init__(self):
        self._adapters: Dict[str, object] = {}   # name → MCPAdapterTool instance
        self._http_procs: Dict[str, subprocess.Popen] = {}  # name → Popen (http-only)
        self._lock = threading.Lock()

    def register_adapter(self, name: str, adapter) -> None:
        """Register a loaded MCPAdapterTool so we can shut it down cleanly."""
        with self._lock:
            self._adapters[name] = adapter

    def unregister_adapter(self, name: str) -> None:
        with self._lock:
            self._adapters.pop(name, None)

    def is_running(self, name: str) -> bool:
        with self._lock:
            adapter = self._adapters.get(name)
        return adapter is not None and getattr(adapter, "_connected", False)

    def stop_all(self) -> None:
        """Shut down all managed adapters and any http processes."""
        with self._lock:
            adapters = list(self._adapters.values())
            procs = list(self._http_procs.items())

        for adapter in adapters:
            try:
                adapter.shutdown()
            except Exception as e:
                logger.warning(f"MCPProcessManager: error shutting down adapter: {e}")

        for name, proc in procs:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            logger.info(f"MCPProcessManager: http server '{name}' stopped")

    def status(self) -> Dict[str, dict]:
        with self._lock:
            return {
                name: {
                    "transport": getattr(adapter, "_transport", "unknown"),
                    "connected": getattr(adapter, "_connected", False),
                    "tool_count": len(getattr(adapter, "_mcp_tools", {})),
                }
                for name, adapter in self._adapters.items()
            }


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------
_manager: Optional[MCPProcessManager] = None


def get_mcp_process_manager() -> MCPProcessManager:
    global _manager
    if _manager is None:
        _manager = MCPProcessManager()
    return _manager
