"""File-backed helpers for tool source discovery and persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional


class ToolFileStorage:
    """Small file-storage helper for tool source files.

    The runtime still relies heavily on the live registry and dynamic imports, so
    this class intentionally stays narrow: discover, read, and write tool files.
    """

    def __init__(self, root: str = "tools"):
        self.root = Path(root)

    def list_tool_files(self) -> List[Path]:
        files = list(self.root.glob("*_tool.py"))
        exp_dir = self.root / "experimental"
        if exp_dir.exists():
            files.extend(f for f in exp_dir.glob("*.py") if f.name != "__init__.py")
        cu_dir = self.root / "computer_use"
        if cu_dir.exists():
            files.extend(
                f for f in cu_dir.glob("*.py")
                if f.name != "__init__.py" and not f.name.endswith("_agent.py")
            )
        return sorted({f.resolve() for f in files})

    def read(self, tool_path: str | Path) -> str:
        return Path(tool_path).read_text(encoding="utf-8")

    def write(self, tool_path: str | Path, content: str) -> Path:
        path = Path(tool_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def exists(self, tool_path: str | Path) -> bool:
        return Path(tool_path).exists()


__all__ = ["ToolFileStorage"]
