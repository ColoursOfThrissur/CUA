"""Validation service - auto-validates parameters from ToolCapability specs."""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str]
    sanitized: Dict[str, Any]


class ValidationService:
    """Validates handler parameters against ToolCapability specs."""
    
    @staticmethod
    def validate(capability, parameters: Dict[str, Any]) -> ValidationResult:
        """Validate parameters against capability spec."""
        from tools.tool_capability import ParameterType
        
        errors = []
        sanitized = {}
        
        if not hasattr(capability, 'parameters'):
            return ValidationResult(valid=True, errors=[], sanitized=parameters)
        
        # Check required parameters
        for param in capability.parameters:
            name = param.name
            required = getattr(param, 'required', True)
            default = getattr(param, 'default', None)
            param_type = param.type
            
            value = parameters.get(name)
            
            # Handle missing required
            if value is None or value == "":
                if required and default is None:
                    errors.append(f"Missing required parameter: {name}")
                    continue
                elif default is not None:
                    value = default
                else:
                    continue
            
            # Type validation
            if param_type == ParameterType.STRING:
                if not isinstance(value, str):
                    errors.append(f"{name} must be string, got {type(value).__name__}")
                else:
                    sanitized[name] = value
            elif param_type == ParameterType.INTEGER:
                if not isinstance(value, int):
                    try:
                        sanitized[name] = int(value)
                    except (ValueError, TypeError):
                        errors.append(f"{name} must be integer, got {type(value).__name__}")
                else:
                    sanitized[name] = value
            elif param_type == ParameterType.BOOLEAN:
                if not isinstance(value, bool):
                    if isinstance(value, str):
                        sanitized[name] = value.lower() in ('true', '1', 'yes')
                    else:
                        sanitized[name] = bool(value)
                else:
                    sanitized[name] = value
            elif param_type == ParameterType.LIST:
                if not isinstance(value, list):
                    errors.append(f"{name} must be list, got {type(value).__name__}")
                else:
                    sanitized[name] = value
            elif param_type == ParameterType.DICT:
                if not isinstance(value, dict):
                    errors.append(f"{name} must be dict, got {type(value).__name__}")
                else:
                    sanitized[name] = value
            elif param_type == ParameterType.FILE_PATH:
                if not isinstance(value, str):
                    errors.append(f"{name} must be string path, got {type(value).__name__}")
                else:
                    sanitized[name] = value
            else:
                sanitized[name] = value
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            sanitized=sanitized
        )
