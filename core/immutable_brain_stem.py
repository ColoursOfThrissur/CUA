"""
Immutable BrainStem with signature verification
Prevents runtime modification and validates integrity
"""

import hashlib
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

class RiskLevel(Enum):
    SAFE = "safe"
    LOW = "low" 
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"

@dataclass
class ValidationResult:
    is_valid: bool
    risk_level: RiskLevel
    reason: str
    allowed_path: Optional[str] = None

class ImmutableBrainStem:
    """
    Immutable safety validation - CANNOT be modified at runtime
    Checksum verified on initialization
    """
    
    # SAFETY RULES - Loaded from config
    @staticmethod
    def _get_allowed_roots():
        from core.config_manager import get_config
        return tuple(get_config().security.allowed_roots)
    
    @staticmethod
    def _get_blocked_paths():
        from core.config_manager import get_config
        return tuple(get_config().security.blocked_paths)
    
    @staticmethod
    def _get_blocked_extensions():
        from core.config_manager import get_config
        return tuple(get_config().security.blocked_extensions)
    _SAFE_OPERATIONS = ("read_file", "list_directory")
    _RISKY_OPERATIONS = ("write_file", "delete_file", "execute_command")
    
    # CRITICAL: Precomputed checksum - MUST be set before deployment
    # Generate with: python -c "import hashlib; print(hashlib.sha256(open('core/immutable_brain_stem.py','rb').read()).hexdigest())"
    _EXPECTED_CHECKSUM = "2a07461577987de48d8214230f87b17c564ae68558688b478792106480fea57a"
    
    def __init__(self):
        """Verify integrity on initialization"""
        if not self._verify_integrity():
            raise RuntimeError("CRITICAL: BrainStem integrity check FAILED - possible tampering detected")
        
        # Make attributes immutable
        object.__setattr__(self, '_initialized', True)
    
    def __setattr__(self, name, value):
        """Prevent any attribute modification"""
        if hasattr(self, '_initialized'):
            raise RuntimeError("BrainStem is immutable - cannot modify attributes")
        object.__setattr__(self, name, value)
    
    @classmethod
    def _verify_integrity(cls) -> bool:
        """Verify file hasn't been tampered with (excluding checksum line)"""
        try:
            # Calculate checksum of this file, excluding the checksum line itself
            current_file = __file__
            with open(current_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # Exclude the line containing _EXPECTED_CHECKSUM
                filtered_lines = [line for line in lines if '_EXPECTED_CHECKSUM' not in line]
                content = ''.join(filtered_lines).encode('utf-8')
                checksum = hashlib.sha256(content).hexdigest()
            
            # CRITICAL: Fail if checksum not set
            if cls._EXPECTED_CHECKSUM == "REPLACE_WITH_ACTUAL_CHECKSUM_BEFORE_PRODUCTION":
                raise RuntimeError("CRITICAL: BrainStem checksum not provisioned - cannot run in production")
            
            # Verify checksum matches
            if checksum != cls._EXPECTED_CHECKSUM:
                raise RuntimeError(f"CRITICAL: BrainStem integrity violation! Expected: {cls._EXPECTED_CHECKSUM}, Got: {checksum}")
            
            return True
            
        except Exception as e:
            print(f"CRITICAL: Integrity check failed: {e}")
            return False
    
    @staticmethod
    def validate_path(path: str) -> ValidationResult:
        """Validate file path with hardened checks"""
        
        # Normalize path
        abs_path = os.path.abspath(os.path.normpath(path))
        
        # Check blocked paths using commonpath (prevents traversal)
        for blocked in ImmutableBrainStem._get_blocked_paths():
            try:
                blocked_abs = os.path.abspath(blocked)
                common = os.path.commonpath([abs_path, blocked_abs])
                if common == blocked_abs:
                    return ValidationResult(
                        is_valid=False,
                        risk_level=RiskLevel.BLOCKED,
                        reason=f"Path blocked: {blocked}"
                    )
            except ValueError:
                # Different drives on Windows - safe
                continue
        
        # Check allowed roots using commonpath
        allowed = False
        for root in ImmutableBrainStem._get_allowed_roots():
            try:
                root_abs = os.path.abspath(root)
                common = os.path.commonpath([abs_path, root_abs])
                if common == root_abs:
                    allowed = True
                    break
            except ValueError:
                continue
        
        if not allowed:
            return ValidationResult(
                is_valid=False,
                risk_level=RiskLevel.HIGH,
                reason="Path outside allowed roots"
            )
        
        # Check file extension
        _, ext = os.path.splitext(path)
        if ext.lower() in ImmutableBrainStem._get_blocked_extensions():
            return ValidationResult(
                is_valid=False,
                risk_level=RiskLevel.BLOCKED,
                reason=f"Blocked file extension: {ext}"
            )
        
        return ValidationResult(
            is_valid=True,
            risk_level=RiskLevel.SAFE,
            reason="Path validated",
            allowed_path=abs_path
        )
    
    @staticmethod
    def validate_operation(operation: str, parameters: Dict[str, Any]) -> ValidationResult:
        """Validate operation against safety rules"""
        
        # Check operation type
        if operation in ImmutableBrainStem._SAFE_OPERATIONS:
            risk_level = RiskLevel.SAFE
        elif operation in ImmutableBrainStem._RISKY_OPERATIONS:
            risk_level = RiskLevel.MEDIUM
        else:
            return ValidationResult(
                is_valid=False,
                risk_level=RiskLevel.HIGH,
                reason=f"Unknown operation: {operation}"
            )
        
        # Validate paths in parameters
        for key, value in parameters.items():
            if key in ["path", "file_path", "directory"]:
                path_result = ImmutableBrainStem.validate_path(str(value))
                if not path_result.is_valid:
                    return path_result
        
        return ValidationResult(
            is_valid=True,
            risk_level=risk_level,
            reason="Operation validated"
        )
    
    @staticmethod
    def validate_plan_step(tool: str, operation: str, parameters: Dict[str, Any]) -> ValidationResult:
        """Validate complete plan step"""
        
        # Validate operation first
        op_result = ImmutableBrainStem.validate_operation(operation, parameters)
        if not op_result.is_valid:
            return op_result
        
        # Additional tool-specific validation
        if tool == "filesystem_tool":
            if operation == "write_file" and "content" in parameters:
                from core.config_manager import get_config
                content = str(parameters["content"])
                max_size = get_config().security.max_file_size_mb * 1024 * 1024
                if len(content) > max_size:
                    return ValidationResult(
                        is_valid=False,
                        risk_level=RiskLevel.HIGH,
                        reason=f"File content exceeds {get_config().security.max_file_size_mb}MB limit"
                    )
        
        return ValidationResult(
            is_valid=True,
            risk_level=op_result.risk_level,
            reason="Plan step validated"
        )

# Create singleton instance
BrainStem = ImmutableBrainStem()
