"""
Enhanced filesystem tool with full capability set.
"""
import os
import shutil
import fnmatch
from pathlib import Path
from typing import List, Dict, Any

from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel


class FilesystemTool(BaseTool):
    """Filesystem operations with sandboxed access."""

    def __init__(self, orchestrator=None, allowed_roots: List[str] = None):
        from shared.config.config_manager import get_config
        if allowed_roots is not None:
            if not allowed_roots:
                raise ValueError("allowed_roots cannot be an empty list.")
            if not isinstance(allowed_roots, list) or not all(isinstance(r, str) for r in allowed_roots):
                raise ValueError("allowed_roots must be a list of strings.")
            for root in allowed_roots:
                if not os.path.isdir(root):
                    raise ValueError(f"'{root}' is not a valid directory.")
        self.allowed_roots = allowed_roots or get_config().security.allowed_roots
        super().__init__()
        if orchestrator:
            self.services = orchestrator.get_services(self.__class__.__name__)

    def register_capabilities(self):
        self.add_capability(ToolCapability(
            name="read_file",
            description="Read the full content of a file.",
            parameters=[Parameter("path", ParameterType.FILE_PATH, "Path to the file to read")],
            returns="File content as string.",
            safety_level=SafetyLevel.LOW,
            examples=[{"path": "output/data.txt"}],
        ), self._handle_read_file)

        self.add_capability(ToolCapability(
            name="write_file",
            description="Write content to a file, creating parent directories if needed.",
            parameters=[
                Parameter("path", ParameterType.FILE_PATH, "Path to write to"),
                Parameter("content", ParameterType.STRING, "Content to write"),
            ],
            returns="Success message with file path.",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"path": "output/result.txt", "content": "Hello"}],
        ), self._handle_write_file)

        self.add_capability(ToolCapability(
            name="append_file",
            description="Append content to an existing file without overwriting it.",
            parameters=[
                Parameter("path", ParameterType.FILE_PATH, "Path to the file"),
                Parameter("content", ParameterType.STRING, "Content to append"),
            ],
            returns="Success message.",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"path": "output/log.txt", "content": "new line\n"}],
        ), self._handle_append_file)

        self.add_capability(ToolCapability(
            name="delete_file",
            description="Delete a file or an empty directory.",
            parameters=[Parameter("path", ParameterType.FILE_PATH, "Path to delete")],
            returns="Success message.",
            safety_level=SafetyLevel.HIGH,
            examples=[{"path": "output/old.txt"}],
        ), self._handle_delete_file)

        self.add_capability(ToolCapability(
            name="move_file",
            description="Move or rename a file or directory.",
            parameters=[
                Parameter("source", ParameterType.FILE_PATH, "Source path"),
                Parameter("destination", ParameterType.FILE_PATH, "Destination path"),
            ],
            returns="Success message with new path.",
            safety_level=SafetyLevel.HIGH,
            examples=[{"source": "output/old.txt", "destination": "output/new.txt"}],
        ), self._handle_move_file)

        self.add_capability(ToolCapability(
            name="copy_file",
            description="Copy a file to a new location.",
            parameters=[
                Parameter("source", ParameterType.FILE_PATH, "Source file path"),
                Parameter("destination", ParameterType.FILE_PATH, "Destination path"),
            ],
            returns="Success message with destination path.",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"source": "output/a.txt", "destination": "output/b.txt"}],
        ), self._handle_copy_file)

        self.add_capability(ToolCapability(
            name="list_directory",
            description="List files and subdirectories in a directory.",
            parameters=[
                Parameter("path", ParameterType.FILE_PATH, "Directory path to list", required=False, default="."),
                Parameter("recursive", ParameterType.BOOLEAN, "List recursively. Default: false", required=False),
            ],
            returns="List of file and directory names.",
            safety_level=SafetyLevel.LOW,
            examples=[{"path": "output"}],
        ), self._handle_list_directory)

        # alias
        self.add_capability(ToolCapability(
            name="list_files",
            description="List files in a directory (alias for list_directory).",
            parameters=[
                Parameter("path", ParameterType.FILE_PATH, "Directory path", required=False, default="."),
                Parameter("recursive", ParameterType.BOOLEAN, "List recursively. Default: false", required=False),
            ],
            returns="List of file and directory names.",
            safety_level=SafetyLevel.LOW,
            examples=[{"path": "."}],
        ), self._handle_list_directory)

        self.add_capability(ToolCapability(
            name="create_directory",
            description="Create a directory and all intermediate parent directories.",
            parameters=[Parameter("path", ParameterType.FILE_PATH, "Directory path to create")],
            returns="Success message.",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"path": "output/reports/2024"}],
        ), self._handle_create_directory)

        self.add_capability(ToolCapability(
            name="file_exists",
            description="Check whether a file or directory exists at the given path.",
            parameters=[Parameter("path", ParameterType.FILE_PATH, "Path to check")],
            returns="Dict with exists (bool), is_file, is_dir.",
            safety_level=SafetyLevel.LOW,
            examples=[{"path": "output/result.txt"}],
        ), self._handle_file_exists)

        self.add_capability(ToolCapability(
            name="get_file_info",
            description="Get metadata about a file: size, modified time, permissions.",
            parameters=[Parameter("path", ParameterType.FILE_PATH, "Path to inspect")],
            returns="Dict with size_bytes, modified_at, is_file, is_dir, extension.",
            safety_level=SafetyLevel.LOW,
            examples=[{"path": "output/data.json"}],
        ), self._handle_get_file_info)

        self.add_capability(ToolCapability(
            name="search_files",
            description="Search for files matching a name pattern within a directory.",
            parameters=[
                Parameter("path", ParameterType.FILE_PATH, "Root directory to search in"),
                Parameter("pattern", ParameterType.STRING, "Glob pattern, e.g. *.py or report_*.txt"),
                Parameter("recursive", ParameterType.BOOLEAN, "Search recursively. Default: true", required=False),
            ],
            returns="List of matching file paths.",
            safety_level=SafetyLevel.LOW,
            examples=[{"path": ".", "pattern": "*.json"}],
        ), self._handle_search_files)

        self.add_capability(ToolCapability(
            name="read_json",
            description="Read and parse a JSON file, returning the parsed object.",
            parameters=[Parameter("path", ParameterType.FILE_PATH, "Path to the JSON file")],
            returns="Parsed JSON object.",
            safety_level=SafetyLevel.LOW,
            examples=[{"path": "data/config.json"}],
        ), self._handle_read_json)

        self.add_capability(ToolCapability(
            name="write_json",
            description="Serialize a dict/list to JSON and write it to a file.",
            parameters=[
                Parameter("path", ParameterType.FILE_PATH, "Path to write to"),
                Parameter("data", ParameterType.DICT, "Data to serialize"),
                Parameter("indent", ParameterType.INTEGER, "JSON indent spaces. Default: 2", required=False),
            ],
            returns="Success message.",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"path": "output/result.json", "data": {"key": "value"}}],
        ), self._handle_write_json)

        self.add_capability(ToolCapability(
            name="edit_file",
            description="Make line-based edits to a text file. Each edit replaces exact text with new content. Returns a diff of changes made.",
            parameters=[
                Parameter("path", ParameterType.FILE_PATH, "Path to the file to edit"),
                Parameter("old_text", ParameterType.STRING, "Exact text to find and replace"),
                Parameter("new_text", ParameterType.STRING, "Replacement text"),
                Parameter("dry_run", ParameterType.BOOLEAN, "Preview changes without writing. Default: false", required=False),
            ],
            returns="Diff of changes made, or preview if dry_run=true.",
            safety_level=SafetyLevel.HIGH,
            examples=[{"path": "output/file.txt", "old_text": "foo", "new_text": "bar"}],
        ), self._handle_edit_file)

        self.add_capability(ToolCapability(
            name="directory_tree",
            description="Get a recursive tree view of files and directories as a structured list. Each entry has name, type (file/directory), and children.",
            parameters=[
                Parameter("path", ParameterType.FILE_PATH, "Root directory path"),
                Parameter("exclude_patterns", ParameterType.LIST, "Glob patterns to exclude e.g. ['*.pyc','__pycache__']", required=False),
            ],
            returns="Nested dict tree structure.",
            safety_level=SafetyLevel.LOW,
            examples=[{"path": ".", "exclude_patterns": ["__pycache__", "*.pyc"]}],
        ), self._handle_directory_tree)

        self.add_capability(ToolCapability(
            name="list_directory_with_sizes",
            description="List files and directories with their sizes. Optionally sort by name or size.",
            parameters=[
                Parameter("path", ParameterType.FILE_PATH, "Directory path"),
                Parameter("sort_by", ParameterType.STRING, "Sort by 'name' or 'size'. Default: name", required=False),
            ],
            returns="List of dicts with name, type, size_bytes.",
            safety_level=SafetyLevel.LOW,
            examples=[{"path": ".", "sort_by": "size"}],
        ), self._handle_list_directory_with_sizes)

        self.add_capability(ToolCapability(
            name="read_multiple_files",
            description="Read the contents of multiple files simultaneously. Returns each file's content keyed by path.",
            parameters=[
                Parameter("paths", ParameterType.LIST, "List of file paths to read"),
            ],
            returns="Dict of path → content. Failed reads include an error key.",
            safety_level=SafetyLevel.LOW,
            examples=[{"paths": ["config.yaml", "requirements.txt"]}],
        ), self._handle_read_multiple_files)

        self.add_capability(ToolCapability(
            name="list_allowed_directories",
            description="Returns the list of directories this tool is allowed to access.",
            parameters=[],
            returns="List of allowed root paths.",
            safety_level=SafetyLevel.LOW,
            examples=[],
        ), self._handle_list_allowed_directories)

    # ── Helpers ───────────────────────────────────────────────────────────────

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

    def _check(self, path: str):
        if not self._validate_path(path):
            raise ValueError(f"Path '{path}' is outside allowed roots: {self.allowed_roots}")

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_read_file(self, path: str, **kwargs) -> str:
        self._check(path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"File '{path}' not found")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _handle_write_file(self, path: str, content: str, **kwargs) -> str:
        self._check(path)
        dirpath = os.path.dirname(path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Written to {path}"

    def _handle_append_file(self, path: str, content: str, **kwargs) -> str:
        self._check(path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"File '{path}' not found")
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended to {path}"

    def _handle_delete_file(self, path: str, **kwargs) -> str:
        self._check(path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"'{path}' not found")
        if os.path.isdir(path):
            os.rmdir(path)
        else:
            os.remove(path)
        return f"Deleted {path}"

    def _handle_move_file(self, source: str, destination: str, **kwargs) -> str:
        self._check(source)
        self._check(destination)
        if not os.path.exists(source):
            raise FileNotFoundError(f"Source '{source}' not found")
        dest_dir = os.path.dirname(destination)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
        shutil.move(source, destination)
        return f"Moved {source} → {destination}"

    def _handle_copy_file(self, source: str, destination: str, **kwargs) -> str:
        self._check(source)
        self._check(destination)
        if not os.path.exists(source):
            raise FileNotFoundError(f"Source '{source}' not found")
        dest_dir = os.path.dirname(destination)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(source, destination)
        return f"Copied {source} → {destination}"

    def _handle_list_directory(self, path: str = ".", recursive: bool = False, **kwargs) -> List[str]:
        self._check(path)
        if not os.path.isdir(path):
            raise NotADirectoryError(f"'{path}' is not a directory")
        if recursive:
            items = []
            for root, dirs, files in os.walk(path):
                for d in sorted(dirs):
                    items.append(os.path.relpath(os.path.join(root, d), path) + "/")
                for f in sorted(files):
                    items.append(os.path.relpath(os.path.join(root, f), path))
            return items
        with os.scandir(path) as entries:
            items = [e.name + "/" if e.is_dir() else e.name for e in entries]
        items.sort(key=lambda x: (not x.endswith("/"), x))
        return items

    def _handle_create_directory(self, path: str, **kwargs) -> str:
        self._check(path)
        os.makedirs(path, exist_ok=True)
        return f"Directory created: {path}"

    def _handle_file_exists(self, path: str, **kwargs) -> dict:
        self._check(path)
        exists = os.path.exists(path)
        return {
            "exists": exists,
            "is_file": os.path.isfile(path) if exists else False,
            "is_dir": os.path.isdir(path) if exists else False,
            "path": path,
        }

    def _handle_get_file_info(self, path: str, **kwargs) -> dict:
        self._check(path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"'{path}' not found")
        stat = os.stat(path)
        from datetime import datetime
        return {
            "path": path,
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "is_file": os.path.isfile(path),
            "is_dir": os.path.isdir(path),
            "extension": Path(path).suffix,
        }

    def _handle_search_files(self, path: str, pattern: str, recursive: bool = True, **kwargs) -> List[str]:
        self._check(path)
        if not os.path.isdir(path):
            raise NotADirectoryError(f"'{path}' is not a directory")
        matches = []
        if recursive:
            for root, _, files in os.walk(path):
                for f in files:
                    if fnmatch.fnmatch(f, pattern):
                        matches.append(os.path.relpath(os.path.join(root, f), path))
        else:
            for f in os.listdir(path):
                if fnmatch.fnmatch(f, pattern):
                    matches.append(f)
        return sorted(matches)

    def _handle_read_json(self, path: str, **kwargs):
        import json
        content = self._handle_read_file(path)
        return json.loads(content)

    def _handle_write_json(self, path: str, data, indent: int = 2, **kwargs) -> str:
        import json
        content = json.dumps(data, indent=indent, ensure_ascii=False)
        return self._handle_write_file(path, content)

    def _handle_edit_file(self, path: str, old_text: str, new_text: str, dry_run: bool = False, **kwargs) -> str:
        self._check(path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"File '{path}' not found")
        with open(path, "r", encoding="utf-8") as f:
            original = f.read()
        if old_text not in original:
            raise ValueError(f"Text not found in '{path}': {old_text[:80]!r}")
        updated = original.replace(old_text, new_text, 1)
        # Build a simple unified diff
        import difflib
        diff = "".join(difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""
        ))
        if not dry_run:
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)
        return diff or "(no changes)"

    def _handle_directory_tree(self, path: str, exclude_patterns: list = None, **kwargs) -> dict:
        self._check(path)
        if not os.path.isdir(path):
            raise NotADirectoryError(f"'{path}' is not a directory")
        exclude_patterns = exclude_patterns or []

        def _build(p: Path) -> dict:
            node = {"name": p.name, "type": "directory" if p.is_dir() else "file"}
            if p.is_dir():
                children = []
                try:
                    for child in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name)):
                        if any(fnmatch.fnmatch(child.name, pat) for pat in exclude_patterns):
                            continue
                        children.append(_build(child))
                except PermissionError:
                    pass
                node["children"] = children
            return node

        return _build(Path(path))

    def _handle_list_directory_with_sizes(self, path: str, sort_by: str = "name", **kwargs) -> list:
        self._check(path)
        if not os.path.isdir(path):
            raise NotADirectoryError(f"'{path}' is not a directory")
        entries = []
        with os.scandir(path) as it:
            for e in it:
                stat = e.stat()
                entries.append({
                    "name": e.name,
                    "type": "directory" if e.is_dir() else "file",
                    "size_bytes": stat.st_size,
                })
        key = (lambda x: x["size_bytes"]) if sort_by == "size" else (lambda x: x["name"])
        return sorted(entries, key=key)

    def _handle_read_multiple_files(self, paths: list, **kwargs) -> dict:
        result = {}
        for path in paths:
            try:
                result[path] = self._handle_read_file(path)
            except Exception as e:
                result[path] = {"error": str(e)}
        return result

    def _handle_list_allowed_directories(self, **kwargs) -> list:
        return [os.path.abspath(r) for r in self.allowed_roots]

    def execute(self, operation: str, parameters: Dict[str, Any]):
        if operation in self._capabilities:
            return self.execute_capability(operation, **parameters)
        return ToolResult(
            tool_name=self.__class__.__name__,
            capability_name=operation,
            status=ResultStatus.FAILURE,
            error_message=f"Operation '{operation}' not supported",
        )
