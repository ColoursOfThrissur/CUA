"""
GlobTool - sandboxed file discovery for planner-friendly repository search.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any, Dict, List

from tools.tool_capability import Parameter, ParameterType, SafetyLevel, ToolCapability
from tools.tool_interface import BaseTool
from tools.tool_result import ResultStatus, ToolResult


class GlobTool(BaseTool):
    """Find files and directories by glob pattern within allowed roots."""

    def __init__(self, orchestrator=None, allowed_roots: List[str] = None):
        from shared.config.config_manager import get_config

        if allowed_roots is not None:
            if not allowed_roots:
                raise ValueError("allowed_roots cannot be an empty list.")
            if not isinstance(allowed_roots, list) or not all(isinstance(root, str) for root in allowed_roots):
                raise ValueError("allowed_roots must be a list of strings.")
            for root in allowed_roots:
                if not os.path.isdir(root):
                    raise ValueError(f"'{root}' is not a valid directory.")
        self.allowed_roots = allowed_roots or get_config().security.allowed_roots
        super().__init__()
        if orchestrator:
            self.services = orchestrator.get_services(self.__class__.__name__)

    def register_capabilities(self):
        self.add_capability(
            ToolCapability(
                name="glob",
                description="Find files or directories under a root using glob patterns such as **/*.py.",
                parameters=[
                    Parameter("root", ParameterType.FILE_PATH, "Directory to search within."),
                    Parameter("pattern", ParameterType.STRING, "Glob pattern such as **/*.py or src/*.md."),
                    Parameter("include_directories", ParameterType.BOOLEAN, "Include directories in results. Default: false", required=False),
                    Parameter("limit", ParameterType.INTEGER, "Maximum number of matches to return. Default: 200", required=False),
                ],
                returns="Dict with root, pattern, matches, and truncation metadata.",
                safety_level=SafetyLevel.LOW,
                examples=[{"root": ".", "pattern": "**/*.py"}],
            ),
            self._handle_glob,
        )

        self.add_capability(
            ToolCapability(
                name="list_allowed_directories",
                description="List directories this tool may search.",
                parameters=[],
                returns="List of allowed root paths.",
                safety_level=SafetyLevel.LOW,
                examples=[],
            ),
            self._handle_list_allowed_directories,
        )

    def _validate_path(self, path: str) -> bool:
        abs_path = os.path.abspath(os.path.normpath(path))
        for root in self.allowed_roots:
            try:
                abs_root = os.path.abspath(root)
                if os.path.commonpath([abs_path, abs_root]) == abs_root:
                    return True
            except ValueError:
                continue
        return False

    def _check_root(self, path: str) -> str:
        normalized = os.path.abspath(os.path.normpath(path))
        if not self._validate_path(normalized):
            raise ValueError(f"Path '{path}' is outside allowed roots: {self.allowed_roots}")
        if not os.path.isdir(normalized):
            raise NotADirectoryError(f"'{path}' is not a directory")
        return normalized

    def _matches_pattern(self, rel_path: str, pattern: str) -> bool:
        normalized = rel_path.replace("\\", "/")
        if fnmatch.fnmatch(normalized, pattern):
            return True
        if pattern.startswith("**/"):
            return fnmatch.fnmatch(normalized, pattern[3:])
        return False

    def _handle_glob(
        self,
        root: str,
        pattern: str,
        include_directories: bool = False,
        limit: int = 200,
        **kwargs,
    ) -> Dict[str, Any]:
        if not pattern:
            raise ValueError("pattern is required")

        search_root = self._check_root(root)
        max_results = max(1, int(limit or 200))
        matches: List[str] = []
        saw_more = False

        for current_root, dirnames, filenames in os.walk(search_root):
            rel_dir = os.path.relpath(current_root, search_root)
            rel_dir = "" if rel_dir == "." else rel_dir.replace("\\", "/")

            if include_directories:
                for dirname in sorted(dirnames):
                    rel_path = f"{rel_dir}/{dirname}" if rel_dir else dirname
                    if self._matches_pattern(rel_path, pattern):
                        matches.append(rel_path)
                        if len(matches) >= max_results:
                            saw_more = True
                            break
                if saw_more:
                    break

            for filename in sorted(filenames):
                rel_path = f"{rel_dir}/{filename}" if rel_dir else filename
                if self._matches_pattern(rel_path, pattern):
                    matches.append(rel_path)
                    if len(matches) >= max_results:
                        saw_more = True
                        break
            if saw_more:
                break

        return {
            "root": search_root,
            "pattern": pattern,
            "matches": matches,
            "match_count": len(matches),
            "truncated": saw_more,
            "include_directories": bool(include_directories),
        }

    def _handle_list_allowed_directories(self, **kwargs) -> List[str]:
        return [os.path.abspath(root) for root in self.allowed_roots]

    def execute(self, operation: str, parameters: Dict[str, Any]):
        if operation in self._capabilities:
            return self.execute_capability(operation, **(parameters or {}))
        return ToolResult(
            tool_name=self.__class__.__name__,
            capability_name=operation,
            status=ResultStatus.FAILURE,
            error_message=f"Operation '{operation}' not supported",
        )
