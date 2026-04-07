"""
GrepTool - sandboxed content search without shell dependence.
"""
from __future__ import annotations

import fnmatch
import os
import re
from typing import Any, Dict, List

from tools.tool_capability import Parameter, ParameterType, SafetyLevel, ToolCapability
from tools.tool_interface import BaseTool
from tools.tool_result import ResultStatus, ToolResult


class GrepTool(BaseTool):
    """Search for text in files under allowed roots."""

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
                name="grep",
                description="Search file contents for text or regex matches under a root directory.",
                parameters=[
                    Parameter("root", ParameterType.FILE_PATH, "Directory to search within."),
                    Parameter("query", ParameterType.STRING, "Text or regex pattern to search for."),
                    Parameter("file_pattern", ParameterType.STRING, "Glob filter for files. Default: *", required=False),
                    Parameter("case_sensitive", ParameterType.BOOLEAN, "Match case exactly. Default: false", required=False),
                    Parameter("regex", ParameterType.BOOLEAN, "Treat query as a regex. Default: false", required=False),
                    Parameter("limit", ParameterType.INTEGER, "Maximum number of matches to return. Default: 100", required=False),
                ],
                returns="Dict with match rows including file path, line number, and line text.",
                safety_level=SafetyLevel.LOW,
                examples=[{"root": ".", "query": "TODO", "file_pattern": "**/*.py"}],
            ),
            self._handle_grep,
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

    def _matches_file_pattern(self, rel_path: str, filename: str, pattern: str) -> bool:
        normalized = rel_path.replace("\\", "/")
        if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(filename, pattern):
            return True
        if pattern.startswith("**/"):
            trimmed = pattern[3:]
            return fnmatch.fnmatch(normalized, trimmed) or fnmatch.fnmatch(filename, trimmed)
        return False

    def _iter_candidate_files(self, root: str, file_pattern: str):
        pattern = file_pattern or "*"
        for current_root, _, filenames in os.walk(root):
            rel_dir = os.path.relpath(current_root, root)
            rel_dir = "" if rel_dir == "." else rel_dir.replace("\\", "/")
            for filename in sorted(filenames):
                rel_path = f"{rel_dir}/{filename}" if rel_dir else filename
                if self._matches_file_pattern(rel_path, filename, pattern):
                    yield rel_path, os.path.join(current_root, filename)

    def _handle_grep(
        self,
        root: str,
        query: str,
        file_pattern: str = "*",
        case_sensitive: bool = False,
        regex: bool = False,
        limit: int = 100,
        **kwargs,
    ) -> Dict[str, Any]:
        if not query:
            raise ValueError("query is required")

        search_root = self._check_root(root)
        max_results = max(1, int(limit or 100))
        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = re.compile(query if regex else re.escape(query), flags)

        matches: List[Dict[str, Any]] = []
        files_scanned = 0
        saw_more = False

        for rel_path, abs_path in self._iter_candidate_files(search_root, file_pattern):
            files_scanned += 1
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        if compiled.search(line):
                            matches.append(
                                {
                                    "path": rel_path,
                                    "line_number": line_number,
                                    "line_text": line.rstrip("\n"),
                                }
                            )
                            if len(matches) >= max_results:
                                saw_more = True
                                break
                if saw_more:
                    break
            except OSError:
                continue

        return {
            "root": search_root,
            "query": query,
            "file_pattern": file_pattern or "*",
            "matches": matches,
            "match_count": len(matches),
            "files_scanned": files_scanned,
            "case_sensitive": bool(case_sensitive),
            "regex": bool(regex),
            "truncated": saw_more,
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
