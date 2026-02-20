"""Service facade for generated tools - provides all necessary services."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.storage_broker import StorageBroker
from core.services.llm_service import LLMService
from core.services.http_service import HTTPService
from core.services.filesystem_service import FileSystemService
from core.services.json_service import JSONService
from core.services.shell_service import ShellService


class StorageService:
    """Simple storage interface for tools - auto-scoped to tool name."""
    
    def __init__(self, tool_name: str, storage_broker: StorageBroker):
        self.tool_name = tool_name
        self.broker = storage_broker
        self.base_dir = f"data/{tool_name.lower().replace('tool', '').replace('_', '')}"
    
    def save(self, item_id: str, data: dict) -> dict:
        """Save data with automatic timestamp."""
        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary")
        
        # Add timestamps if not present
        now = TimeService.now_utc()
        if "created_at_utc" not in data:
            data["created_at_utc"] = now
        data["updated_at_utc"] = now
        
        # Ensure ID is in data
        if "id" not in data and item_id:
            data["id"] = item_id
        
        path = f"{self.base_dir}/{self._safe_id(item_id)}.json"
        self.broker.write_json(path, data)
        return data
    
    def get(self, item_id: str) -> dict:
        """Get data by ID."""
        path = f"{self.base_dir}/{self._safe_id(item_id)}.json"
        return self.broker.read_json(path)
    
    def list(self, limit: int = 10, sort_by: str = "created_at_utc") -> List[dict]:
        """List items with limit and sorting."""
        files = self.broker.list_files(self.base_dir, pattern="*.json")
        
        items = []
        for file_path in files[:limit]:
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                items.append(data)
            except Exception:
                continue
        
        # Sort by field if present
        if sort_by and items:
            try:
                items.sort(key=lambda x: x.get(sort_by, ""), reverse=True)
            except Exception:
                pass
        
        return items
    
    def find(self, filter_fn=None, limit: int = 100) -> List[dict]:
        """Find items matching filter function."""
        files = self.broker.list_files(self.base_dir, pattern="*.json")
        items = []
        for file_path in files:
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                if filter_fn is None or filter_fn(data):
                    items.append(data)
                    if len(items) >= limit:
                        break
            except Exception:
                continue
        return items
    
    def count(self) -> int:
        """Count total items."""
        files = self.broker.list_files(self.base_dir, pattern="*.json")
        return len(files)
    
    def update(self, item_id: str, updates: dict) -> dict:
        """Update existing item with partial data."""
        data = self.get(item_id)
        data.update(updates)
        data["updated_at_utc"] = TimeService.now_utc()
        return self.save(item_id, data)
    
    def delete(self, item_id: str) -> bool:
        """Delete item by ID."""
        path = self.broker.resolve_path(f"{self.base_dir}/{self._safe_id(item_id)}.json", write=True)
        if path.exists():
            path.unlink()
            return True
        return False
    
    def exists(self, item_id: str) -> bool:
        """Check if item exists."""
        path = self.broker.resolve_path(f"{self.base_dir}/{self._safe_id(item_id)}.json", write=False)
        return path.exists()
    
    @staticmethod
    def _safe_id(item_id: str) -> str:
        """Sanitize ID for filesystem."""
        return item_id.strip().replace("/", "_").replace("\\", "_")


class TimeService:
    """Time and timestamp utilities."""
    
    @staticmethod
    def now_utc() -> str:
        """Get current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()
    
    @staticmethod
    def now_local() -> str:
        """Get current local timestamp in ISO format."""
        return datetime.now().isoformat()


class IdService:
    """ID generation utilities."""
    
    @staticmethod
    def generate(prefix: str = None) -> str:
        """Generate unique ID with optional prefix."""
        unique = str(uuid.uuid4())[:8]
        if prefix:
            return f"{prefix}_{unique}"
        return unique
    
    @staticmethod
    def uuid() -> str:
        """Generate full UUID."""
        return str(uuid.uuid4())


class ToolServices:
    """Aggregated services provided to tools via orchestrator."""
    
    def __init__(self, tool_name: str, storage_broker: StorageBroker, llm_client=None, allowed_roots=None, orchestrator=None, registry=None):
        self.storage = StorageService(tool_name, storage_broker)
        self.time = TimeService()
        self.ids = IdService()
        self.llm = LLMService(llm_client) if llm_client else None
        self.http = HTTPService()
        self.json = JSONService()
        self.shell = ShellService()
        self.fs = FileSystemService(allowed_roots or [".", "data", "output"])
        self.orchestrator = orchestrator
        self.registry = registry
    
    def call_tool(self, tool_name: str, operation: str, **parameters):
        """Call another tool via orchestrator."""
        if not self.orchestrator or not self.registry:
            raise RuntimeError("Inter-tool calls require orchestrator and registry")
        
        tool = self.registry.get_tool_by_name(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        result = self.orchestrator.execute_tool_step(
            tool=tool,
            tool_name=tool_name,
            operation=operation,
            parameters=parameters,
            context={}
        )
        
        if not result.success:
            raise RuntimeError(f"Tool call failed: {result.error}")
        
        return result.data
    
    def list_tools(self):
        """List available tools."""
        if not self.registry:
            return []
        return [tool.__class__.__name__ for tool in self.registry.tools]
    
    def has_capability(self, capability_name: str):
        """Check if capability exists."""
        if not self.registry:
            return False
        return capability_name in self.registry.get_all_capabilities()
