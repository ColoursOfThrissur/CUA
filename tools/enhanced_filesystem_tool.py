"""
Enhanced filesystem tool with capability-based interface.
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Any
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class FilesystemTool(BaseTool):
    """Filesystem operations with sandboxed access."""
    
    def __init__(self, allowed_roots: List[str] = None):
        from core.config_manager import get_config
        try:
            if allowed_roots is not None:
                if not allowed_roots:
                    raise ValueError("allowed_roots cannot be an empty list.")
                if not isinstance(allowed_roots, list) or not all(isinstance(root, str) for root in allowed_roots):
                    raise ValueError("allowed_roots must be a list of strings representing valid paths.")
                import os
                for root in allowed_roots:
                    if not os.path.isdir(root):
                        raise ValueError(f"The path '{root}' is not a valid directory.")
            self.allowed_roots = allowed_roots or get_config().security.allowed_roots
        except (ValueError, TypeError) as e:
            raise ValueError(f"Error initializing FilesystemTool: {e}")
        super().__init__()
        
    def register_capabilities(self):
        """Register filesystem capabilities."""
        
        # Read file capability
        read_capability = ToolCapability(
            name="read_file",
            description="Read content from a file",
            parameters=[
                Parameter("path", ParameterType.FILE_PATH, "Path to file to read")
            ],
            returns="File content as string",
            safety_level=SafetyLevel.LOW,
            examples=[
                {"path": "output/data.txt"},
                {"path": "./config.json"}
            ]
        )
        self.add_capability(read_capability, self._handle_read_file)
        
        # Write file capability
        write_capability = ToolCapability(
            name="write_file",
            description="Write content to a file",
            parameters=[
                Parameter("path", ParameterType.FILE_PATH, "Path to file to write"),
                Parameter("content", ParameterType.STRING, "Content to write to file")
            ],
            returns="Success message with file path",
            safety_level=SafetyLevel.MEDIUM,
            examples=[
                {"path": "output/result.txt", "content": "Hello World"},
                {"path": "./data.json", "content": '{"key": "value"}'}
            ]
        )
        self.add_capability(write_capability, self._handle_write_file)
        
        # List directory capability
        list_capability = ToolCapability(
            name="list_directory",
            description="List files and directories in a path",
            parameters=[
                Parameter("path", ParameterType.FILE_PATH, "Directory path to list", required=False, default=".")
            ],
            returns="List of files and directories",
            safety_level=SafetyLevel.LOW,
            examples=[
                {"path": "."},
                {"path": "output"}
            ]
        )
        self.add_capability(list_capability, self._handle_list_directory)
    
    def _validate_path(self, path: str) -> bool:
        abs_path = os.path.abspath(os.path.normpath(path))
        
        for root in self.allowed_roots:
            try:
                abs_root = os.path.abspath(root)
                common = os.path.commonpath([abs_path, abs_root])
                if common == abs_root:
                    return True
            except ValueError as e:
                # Handle the case where paths are on different drives in Windows
                continue
        
        return False
    
    def _handle_read_file(self, path: str) -> str:
        """Handle read file capability."""
        if not self._validate_path(path):
            raise ValueError(f"Path '{path}' is outside allowed roots: {self.allowed_roots}")

        if not os.path.exists(path):
            raise FileNotFoundError(f"File '{path}' not found")

        # Check file permissions
        if not os.access(path, os.R_OK):
            raise PermissionError(f"Permission denied to read file: {path}")

        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def _handle_write_file(self, path: str, content: str) -> str:
        """Handle write file capability."""
        if not self._validate_path(path):
            raise ValueError(f"Path '{path}' is outside allowed roots: {self.allowed_roots}")

        # Check and create directory with write permissions
        dirpath = os.path.dirname(path)
        if dirpath and dirpath != '.':
            abs_dirpath = os.path.abspath(dirpath)
            try:
                if not os.access(abs_dirpath, os.W_OK):
                    raise PermissionError(f"Directory '{dirpath}' does not have write permissions")
                os.makedirs(dirpath, exist_ok=True)
            except OSError as e:
                raise IOError(f"Failed to create directory '{dirpath}': {e}")

        # Check file write permissions
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path) and not os.access(abs_path, os.W_OK):
            raise PermissionError(f"File '{path}' does not have write permissions")

        # Write content to file with error handling
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            raise IOError(f"Error writing to file '{path}': {e}")

        return f"Content written successfully to {path}"
    
    def _handle_list_directory(self, path: str = ".") -> List[str]:
        """Handle list directory capability."""
        if not self._validate_path(path):
            raise ValueError(f"Path '{path}' is outside allowed roots: {self.allowed_roots}")

        try:
            with os.scandir(path) as entries:
                items = [entry.name + "/" if entry.is_dir() else entry.name for entry in entries]
        except FileNotFoundError:
            raise FileNotFoundError(f"Directory '{path}' not found") from None
        except PermissionError:
            raise PermissionError(f"Permission denied to access directory '{path}'") from None
        except OSError as e:
            raise OSError(f"An error occurred while accessing directory '{path}': {e}") from None

        # Sort items by name, directories first
        items.sort(key=lambda x: (not x.endswith('/'), x))

        return items
    
    def execute(self, operation: str, parameters: Dict[str, Any]):
        """Execute a registered capability."""
        try:
            if operation in self._capabilities:
                return self.execute_capability(operation, **parameters)
            else:
                return ToolResult(
                    tool_name=self.__class__.__name__,
                    capability_name=operation,
                    status=ResultStatus.FAILURE,
                    error_message=f"Operation '{operation}' not supported"
                )
        except Exception as e:
            return ToolResult(
                tool_name=self.__class__.__name__,
                capability_name=operation,
                status=ResultStatus.ERROR,
                error_message=str(e)
            )