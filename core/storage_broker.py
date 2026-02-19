"""Centralized storage broker for tool read/write operations."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config_manager import get_config


@dataclass
class StoragePolicy:
    mode: str
    workspace_root: Path
    allowed_external_roots: List[Path]


class StorageBroker:
    """Policy-aware storage access helper for generated and legacy tools."""

    def __init__(self, tool_name: str, policy: Optional[StoragePolicy] = None):
        self.tool_name = tool_name
        self.policy = policy or self._default_policy()

    def write_json(self, relative_path: str, payload: Dict[str, Any], ensure_parent: bool = True) -> Path:
        path = self.resolve_path(relative_path, write=True)
        if ensure_parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def read_json(self, relative_path: str) -> Dict[str, Any]:
        path = self.resolve_path(relative_path, write=False)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_files(self, relative_dir: str, pattern: str = "*.json") -> List[Path]:
        path = self.resolve_path(relative_dir, write=False)
        if not path.exists():
            return []
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        return sorted(path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    def resolve_path(self, path_value: str, write: bool) -> Path:
        if not path_value:
            raise ValueError("Path is required")
        raw = Path(path_value)
        candidate = raw if raw.is_absolute() else (self.policy.workspace_root / raw)
        resolved = candidate.resolve()

        if self._is_under(resolved, self.policy.workspace_root):
            return resolved

        if self.policy.mode == "approved_external_paths":
            for root in self.policy.allowed_external_roots:
                if self._is_under(resolved, root.resolve()):
                    return resolved

        action = "write" if write else "read"
        raise PermissionError(
            f"{self.tool_name} cannot {action} outside workspace policy: {resolved}"
        )

    def _default_policy(self) -> StoragePolicy:
        config = get_config()
        workspace_root = Path.cwd().resolve()
        mode = str(getattr(config.security, "storage_mode", "workspace_only"))
        raw_roots = getattr(config.security, "allowed_external_roots", []) or []
        external_roots = [Path(str(item)).resolve() for item in raw_roots if str(item).strip()]
        return StoragePolicy(
            mode=mode,
            workspace_root=workspace_root,
            allowed_external_roots=external_roots,
        )

    @staticmethod
    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except Exception:
            return False


def get_storage_broker(tool_name: str) -> StorageBroker:
    return StorageBroker(tool_name=tool_name)
