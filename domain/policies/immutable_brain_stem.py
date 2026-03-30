"""
Immutable BrainStem with signature verification
Prevents runtime modification and validates integrity
"""

import hashlib
import os
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

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
        from shared.config.config_manager import get_config
        return tuple(get_config().security.allowed_roots)
    
    @staticmethod
    def _get_blocked_paths():
        from shared.config.config_manager import get_config
        return tuple(get_config().security.blocked_paths)
    
    @staticmethod
    def _get_blocked_extensions():
        from shared.config.config_manager import get_config
        return tuple(get_config().security.blocked_extensions)
    _SAFE_OPERATIONS = ("read_file", "list_directory", "get", "parse", "validate")
    _RISKY_OPERATIONS = ("write_file", "delete_file", "execute_command", "post", "put", "delete")

    @staticmethod
    def _get_dynamic_operation_safety() -> Dict[str, str]:
        """Load operation->safety_level map from synced registry, if available."""
        registry_file = Path("data/tool_registry.json")
        if not registry_file.exists():
            return {}
        try:
            payload = json.loads(registry_file.read_text(encoding="utf-8"))
            tools = payload.get("tools", {})
            operation_safety: Dict[str, str] = {}
            for tool_data in tools.values():
                for op_name, op_data in (tool_data.get("operations") or {}).items():
                    if not op_name:
                        continue
                    safety = str(op_data.get("safety_level", "")).lower().strip()
                    if safety:
                        operation_safety[op_name] = safety
                    else:
                        operation_safety.setdefault(op_name, "medium")
            return operation_safety
        except Exception:
            return {}
    
    def __init__(self):
        """Verify integrity on initialization using a sidecar checksum file."""
        status = self._evaluate_integrity()
        object.__setattr__(self, "_integrity_status", status)
        if status["enforced"] and not status["valid"]:
            raise RuntimeError(f"CRITICAL: BrainStem integrity check failed: {status['reason']}")

        # Make attributes immutable
        object.__setattr__(self, '_initialized', True)
    
    def __setattr__(self, name, value):
        """Prevent any attribute modification"""
        if hasattr(self, '_initialized'):
            raise RuntimeError("BrainStem is immutable - cannot modify attributes")
        object.__setattr__(self, name, value)
    
    @staticmethod
    def _get_checksum_file() -> Path:
        from shared.config.config_manager import get_config
        return Path(get_config().security.brainstem_checksum_file)

    @classmethod
    def _calculate_checksum(cls, file_path: Optional[str] = None) -> str:
        target = file_path or __file__
        with open(target, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    @classmethod
    def _load_expected_checksum(cls) -> Optional[str]:
        checksum_file = cls._get_checksum_file()
        if not checksum_file.exists():
            return None
        checksum = checksum_file.read_text(encoding="utf-8").strip()
        return checksum or None

    @classmethod
    def _evaluate_integrity(cls) -> Dict[str, Any]:
        """Evaluate integrity against the configured sidecar checksum."""
        try:
            from shared.config.config_manager import get_config

            config = get_config().security
            expected = cls._load_expected_checksum()
            current = cls._calculate_checksum()
            enforced = bool(config.enforce_brainstem_integrity)

            if not expected:
                return {
                    "valid": not enforced,
                    "configured": False,
                    "enforced": enforced,
                    "reason": "Checksum file missing",
                    "expected_checksum": None,
                    "current_checksum": current,
                }

            is_valid = current == expected
            return {
                "valid": is_valid,
                "configured": True,
                "enforced": enforced,
                "reason": "ok" if is_valid else "Checksum mismatch",
                "expected_checksum": expected,
                "current_checksum": current,
            }
        except Exception as e:
            return {
                "valid": False,
                "configured": False,
                "enforced": False,
                "reason": f"Integrity evaluation error: {e}",
                "expected_checksum": None,
                "current_checksum": None,
            }

    @classmethod
    def _verify_integrity(cls) -> bool:
        return bool(cls._evaluate_integrity()["valid"])

    @classmethod
    def get_integrity_status(cls) -> Dict[str, Any]:
        return dict(cls._evaluate_integrity())
    
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
            dynamic_safety = ImmutableBrainStem._get_dynamic_operation_safety()
            if operation not in dynamic_safety:
                return ValidationResult(
                    is_valid=False,
                    risk_level=RiskLevel.HIGH,
                    reason=f"Unknown operation: {operation}"
                )
            safety = dynamic_safety.get(operation, "medium")
            if safety == "low":
                risk_level = RiskLevel.LOW
            elif safety in {"high", "critical"}:
                risk_level = RiskLevel.HIGH
            else:
                risk_level = RiskLevel.MEDIUM
        
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
                from shared.config.config_manager import get_config
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
