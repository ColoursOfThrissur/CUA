"""Shared orchestration layer for tool invocation and result normalization."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import inspect
import time

from core.parameter_resolution import resolve_tool_parameters
from core.storage_broker import get_storage_broker
from core.tool_services import ToolServices
from core.validation_service import ValidationService
from core.tool_execution_logger import get_execution_logger


@dataclass
class OrchestratedToolResult:
    success: bool
    data: Any
    error: Optional[str]
    raw_result: Any
    tool_name: str
    operation: str
    resolved_parameters: Dict[str, Any]
    missing_required: List[str]
    artifacts: List[Dict[str, Any]]
    meta: Dict[str, Any]


class ToolOrchestrator:
    """Central orchestrator used by executors to run tools consistently."""
    
    def __init__(self, llm_client=None, registry=None):
        self._services_cache: Dict[str, ToolServices] = {}
        self._llm_client = llm_client
        self._registry = registry
        self._execution_logger = get_execution_logger()
    
    def get_services(self, tool_name: str) -> ToolServices:
        """Get service facade for a tool (cached per tool name)."""
        if tool_name not in self._services_cache:
            storage_broker = get_storage_broker(tool_name)
            # Lazy load LLM client if not provided
            if self._llm_client is None:
                from planner.llm_client import get_llm_client
                self._llm_client = get_llm_client()
            self._services_cache[tool_name] = ToolServices(
                tool_name, 
                storage_broker, 
                self._llm_client,
                orchestrator=self,
                registry=self._registry
            )
        return self._services_cache[tool_name]

    def execute_tool_step(
        self,
        tool,
        tool_name: str,
        operation: str,
        parameters: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> OrchestratedToolResult:
        start_time = time.time()
        resolution = resolve_tool_parameters(tool, operation, parameters, context=context)
        if resolution.missing_required:
            missing = ", ".join(resolution.missing_required)
            return OrchestratedToolResult(
                success=False,
                data=None,
                error=(
                    f"Missing required parameters for {tool_name}.{operation}: {missing}. "
                    f"Ask user to provide missing values."
                ),
                raw_result=None,
                tool_name=tool_name,
                operation=operation,
                resolved_parameters=resolution.resolved_parameters,
                missing_required=resolution.missing_required,
                artifacts=[],
                meta={"auto_filled": resolution.auto_filled},
            )

        # Auto-validate from ToolCapability spec
        capabilities = tool.get_capabilities() if hasattr(tool, 'get_capabilities') else {}
        capability = capabilities.get(operation)
        if capability:
            validation = ValidationService.validate(capability, resolution.resolved_parameters)
            if not validation.valid:
                return OrchestratedToolResult(
                    success=False,
                    data=None,
                    error=f"Validation failed: {'; '.join(validation.errors)}",
                    raw_result=None,
                    tool_name=tool_name,
                    operation=operation,
                    resolved_parameters=resolution.resolved_parameters,
                    missing_required=[],
                    artifacts=[],
                    meta={"auto_filled": resolution.auto_filled, "validation_errors": validation.errors},
                )
            # Use sanitized parameters
            resolution.resolved_parameters.update(validation.sanitized)

        try:
            raw_result = self._execute_tool_compat(tool, operation, resolution.resolved_parameters)
        except Exception as e:
            # Log failed execution
            execution_time_ms = (time.time() - start_time) * 1000
            self._execution_logger.log_execution(
                tool_name=tool_name,
                operation=operation,
                success=False,
                error=str(e),
                execution_time_ms=execution_time_ms,
                parameters=resolution.resolved_parameters,
                output_data=None
            )
            # Thin tools raise exceptions for errors - wrap them
            from tools.tool_result import ToolResult, ResultStatus
            return OrchestratedToolResult(
                success=False,
                data=None,
                error=str(e),
                raw_result=None,
                tool_name=tool_name,
                operation=operation,
                resolved_parameters=resolution.resolved_parameters,
                missing_required=[],
                artifacts=[],
                meta={"auto_filled": resolution.auto_filled, "exception": type(e).__name__},
            )
        
        # Handle thin tools that return plain dicts or raise exceptions
        if isinstance(raw_result, dict) and "status" not in raw_result and "success" not in raw_result:
            # This is a thin tool returning business data - wrap it
            from tools.tool_result import ToolResult, ResultStatus
            raw_result = ToolResult(
                tool_name=tool_name,
                capability_name=operation,
                status=ResultStatus.SUCCESS,
                data=raw_result,
                error_message=None
            )
        
        success, data, error = self._normalize_result(raw_result)
        artifacts = self._extract_artifacts(data)
        
        # Log successful execution
        execution_time_ms = (time.time() - start_time) * 1000
        self._execution_logger.log_execution(
            tool_name=tool_name,
            operation=operation,
            success=success,
            error=error,
            execution_time_ms=execution_time_ms,
            parameters=resolution.resolved_parameters,
            output_data=data
        )
        
        return OrchestratedToolResult(
            success=success,
            data=data,
            error=error,
            raw_result=raw_result,
            tool_name=tool_name,
            operation=operation,
            resolved_parameters=resolution.resolved_parameters,
            missing_required=[],
            artifacts=artifacts,
            meta={"auto_filled": resolution.auto_filled},
        )

    def _execute_tool_compat(self, tool, operation: str, parameters: Dict[str, Any]):
        """Execute tool with compatibility across execute signatures."""
        params = parameters or {}
        print(f"[ORCHESTRATOR] Executing {tool.__class__.__name__}.{operation} with params: {params}")
        print(f"[ORCHESTRATOR] Tool has services: {hasattr(tool, 'services') and tool.services is not None}")
        
        if not hasattr(tool, "execute") and hasattr(tool, "execute_capability"):
            try:
                return tool.execute_capability(operation, **params)
            except Exception:
                pass
        supports_kwargs = False
        supports_dict = True
        try:
            sig = inspect.signature(tool.execute)
            param_count = len(sig.parameters)
            supports_kwargs = any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            )
            supports_dict = param_count >= 2
        except Exception:
            # If signature inspection fails, keep conservative defaults.
            supports_kwargs = False
            supports_dict = True

        if supports_kwargs:
            return tool.execute(operation, **params)

        try:
            return tool.execute(operation, params)
        except TypeError:
            # Only fallback when execute() explicitly supports **kwargs.
            if supports_dict and not supports_kwargs:
                raise
            return tool.execute(operation, **params)

    def _normalize_result(self, result: Any) -> tuple[bool, Any, Optional[str]]:
        if result is None:
            return False, None, "Tool returned no result"

        if hasattr(result, "is_success"):
            success = result.is_success()
            data = getattr(result, "data", None)
            error = getattr(result, "error_message", None)
            if success:
                error = None
            return success, data, error

        if hasattr(result, "status"):
            status = getattr(result, "status", None)
            status_value = getattr(status, "value", str(status)).lower() if status is not None else "failure"
            success = status_value == "success"
            data = getattr(result, "data", None)
            error = getattr(result, "error_message", None)
            if success:
                error = None
            return success, data, error

        if isinstance(result, dict):
            if "success" in result:
                success = bool(result.get("success"))
                data = result.get("data")
                error = result.get("error") or result.get("error_message")
                if success:
                    error = None
                return success, data, error
            # Treat plain dict output as successful payload.
            return True, result, None

        return True, result, None

    def _extract_artifacts(self, data: Any) -> List[Dict[str, Any]]:
        artifacts: List[Dict[str, Any]] = []
        if not isinstance(data, dict):
            return artifacts
        for key in ("path", "file", "file_path", "output_path"):
            value = data.get(key)
            if isinstance(value, str):
                artifacts.append({"type": "file_ref", "key": key, "path": value})
        files = data.get("files")
        if isinstance(files, list):
            for item in files:
                if isinstance(item, str):
                    artifacts.append({"type": "file_ref", "key": "files", "path": item})
        return artifacts
