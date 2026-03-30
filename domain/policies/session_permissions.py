"""
Per-Session Permission Gate
Each session has isolated permission tracking
"""

from typing import Dict, Any
from dataclasses import dataclass
from enum import Enum
from domain.policies.immutable_brain_stem import BrainStem, ValidationResult, RiskLevel

class PermissionLevel(Enum):
    DENIED = 0
    READ_ONLY = 1
    LIMITED_WRITE = 2
    FULL_ACCESS = 3

@dataclass
class Permission:
    tool: str
    operation: str
    level: PermissionLevel
    conditions: Dict[str, Any]

class SessionPermissions:
    """Per-session permission tracking"""
    
    def __init__(self, session_id: str, max_file_writes: int = None, max_file_size: int = None):
        from shared.config.config_manager import get_config
        config = get_config()
        self.session_id = session_id
        self.max_file_writes = max_file_writes or config.security.max_file_writes
        self.max_file_size = max_file_size or (config.security.max_file_size_mb * 1024 * 1024)
        self.files_written = 0
        self.operations_log = []
    
    def record_operation(self, tool: str, operation: str, success: bool):
        """Record operation for this session"""
        if operation == "write_file" and success:
            self.files_written += 1
        
        self.operations_log.append({
            "tool": tool,
            "operation": operation,
            "success": success
        })
    
    def can_write_file(self, content_size: int = 0) -> tuple[bool, str]:
        """Check if session can write file"""
        if self.files_written >= self.max_file_writes:
            return False, f"Session file write limit exceeded ({self.max_file_writes})"
        
        if content_size > self.max_file_size:
            return False, f"File size exceeds limit ({self.max_file_size} bytes)"
        
        return True, "OK"
    
    def reset(self):
        """Reset session limits"""
        self.files_written = 0
        self.operations_log = []

class PermissionGate:
    """Manages permissions with per-session isolation"""
    
    def __init__(self):
        self.sessions: Dict[str, SessionPermissions] = {}
        self.default_permissions = self._init_default_permissions()
    
    def _init_default_permissions(self) -> Dict[str, Permission]:
        """Initialize default permission set"""
        from shared.config.config_manager import get_config
        max_size = get_config().security.max_file_size_mb * 1024 * 1024
        
        return {
            "filesystem_tool.read_file": Permission(
                tool="filesystem_tool",
                operation="read_file", 
                level=PermissionLevel.READ_ONLY,
                conditions={}
            ),
            "filesystem_tool.write_file": Permission(
                tool="filesystem_tool",
                operation="write_file",
                level=PermissionLevel.LIMITED_WRITE,
                conditions={"max_size": max_size}
            ),
            "filesystem_tool.list_directory": Permission(
                tool="filesystem_tool",
                operation="list_directory",
                level=PermissionLevel.READ_ONLY,
                conditions={}
            )
        }
    
    def get_session(self, session_id: str) -> SessionPermissions:
        """Get or create session permissions"""
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionPermissions(session_id)
        return self.sessions[session_id]
    
    def check_permission(self, session_id: str, tool: str, operation: str, 
                        parameters: Dict[str, Any]) -> ValidationResult:
        """Check if operation is permitted for this session"""
        
        # First check brain stem validation
        brain_result = BrainStem.validate_plan_step(tool, operation, parameters)
        if not brain_result.is_valid:
            return brain_result
        
        # Check permission exists
        perm_key = f"{tool}.{operation}"
        if perm_key not in self.default_permissions:
            return ValidationResult(
                is_valid=False,
                risk_level=RiskLevel.HIGH,
                reason=f"No permission defined for {perm_key}"
            )
        
        permission = self.default_permissions[perm_key]
        
        # Check permission level
        if permission.level == PermissionLevel.DENIED:
            return ValidationResult(
                is_valid=False,
                risk_level=RiskLevel.BLOCKED,
                reason="Operation denied by permission policy"
            )
        
        # Get session
        session = self.get_session(session_id)
        
        # Check session-specific limits
        if operation == "write_file":
            content_size = len(str(parameters.get("content", "")))
            can_write, reason = session.can_write_file(content_size)
            
            if not can_write:
                return ValidationResult(
                    is_valid=False,
                    risk_level=RiskLevel.HIGH,
                    reason=reason
                )
        
        return ValidationResult(
            is_valid=True,
            risk_level=RiskLevel.SAFE,
            reason="Permission granted"
        )
    
    def record_operation(self, session_id: str, tool: str, operation: str, success: bool):
        """Record completed operation for session"""
        session = self.get_session(session_id)
        session.record_operation(tool, operation, success)
    
    def reset_session(self, session_id: str):
        """Reset session limits"""
        if session_id in self.sessions:
            self.sessions[session_id].reset()
    
    def delete_session(self, session_id: str):
        """Delete session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
