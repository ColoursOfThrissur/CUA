"""Shared orchestration layer for tool invocation and result normalization."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import inspect
import time

logger = logging.getLogger(__name__)

from core.parameter_resolution import resolve_tool_parameters
from core.storage_broker import get_storage_broker
from core.tool_services import ToolServices
from core.validation_service import ValidationService
from core.tool_execution_logger import get_execution_logger
from core.circuit_breaker import get_circuit_breaker, CircuitBreakerError
from core.verification_engine import get_verification_engine, VERDICT_RETRY, VERDICT_FALLBACK, VERDICT_ESCALATE


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
        self._circuit_breaker = get_circuit_breaker()
        self._verifier = get_verification_engine(llm_client)
    
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

    def invalidate_cache(self, tool_name: str) -> None:
        """Evict a tool's cached ToolServices — call after tool reload or evolution apply."""
        self._services_cache.pop(tool_name, None)
        logger.debug(f"[ORCHESTRATOR] Services cache invalidated for {tool_name}")

    def execute_tool_step(
        self,
        tool,
        tool_name: str,
        operation: str,
        parameters: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        execution_context: Optional[Any] = None,
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
            # Wrap execution with circuit breaker
            raw_result = self._circuit_breaker.call(
                tool_name,
                self._execute_tool_compat,
                tool, operation, resolution.resolved_parameters
            )
        except CircuitBreakerError as e:
            # Circuit is open - tool is quarantined
            execution_time_ms = (time.time() - start_time) * 1000
            self._execution_logger.log_execution(
                tool_name=tool_name,
                operation=operation,
                success=False,
                error=f"Circuit breaker OPEN: {str(e)}",
                execution_time_ms=execution_time_ms,
                parameters=resolution.resolved_parameters,
                output_data=None
            )
            
            # Update execution context if provided
            if execution_context:
                execution_context.add_error(tool_name, f"Circuit breaker OPEN: {str(e)}", 0)
                if execution_context.should_fallback():
                    execution_context.warnings.append(f"Circuit breaker open for {tool_name}, fallback available")

            error_msg = f"Tool quarantined due to repeated failures. {str(e)}"
            self._verify_error_result(error_msg, tool_name, operation, execution_context)
            return OrchestratedToolResult(
                success=False,
                data=None,
                error=error_msg,
                raw_result=None,
                tool_name=tool_name,
                operation=operation,
                resolved_parameters=resolution.resolved_parameters,
                missing_required=[],
                artifacts=[],
                meta={"auto_filled": resolution.auto_filled, "circuit_breaker": "open"},
            )
        except Exception as e:
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
            if execution_context:
                execution_context.add_error(tool_name, str(e), execution_context.retry_count)
            self._verify_error_result(str(e), tool_name, operation, execution_context)
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

        # Multi-layer verification (ALL paths — success and error)
        verification = self._verifier.verify(
            data=data,
            tool_name=tool_name,
            operation=operation,
            skill_context=execution_context,
        )
        if not verification.passed:
            logger.warning(
                f"[VERIFY] {tool_name}.{operation} → {verification.verdict} "
                f"(confidence={verification.confidence:.2f}): {verification.notes}"
            )
            if execution_context:
                for issue in verification.issues:
                    if issue.severity == "error":
                        execution_context.add_error(tool_name, issue.message, getattr(execution_context, 'retry_count', 0))

            if verification.verdict == VERDICT_RETRY:
                success = False
                error = f"Verification failed (retry): {verification.notes}"
            elif verification.verdict == VERDICT_FALLBACK:
                success = False
                error = f"Verification failed (fallback): {verification.notes}"
                if execution_context and hasattr(execution_context, 'fallback_tools') and execution_context.fallback_tools:
                    execution_context.selected_tool = execution_context.fallback_tools[0]
                    execution_context.warnings.append(f"Switched to fallback due to verification: {verification.notes}")
            elif verification.verdict == VERDICT_ESCALATE:
                success = False
                error = f"Verification escalated (cross-source disagreement): {verification.notes}"
        else:
            # Warn but don't fail on warnings-only
            for issue in verification.issues:
                if execution_context:
                    execution_context.warnings.append(f"[VERIFY] {issue.message}")
        
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
        
        # Update execution context if provided
        if execution_context:
            execution_context.add_step(
                tool=tool_name,
                operation=operation,
                status="success" if success else "failure",
                duration=execution_time_ms / 1000.0,
                result=data
            )
            if success:
                execution_context.partial_results.append(data)
        
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
        logger.debug(f"[ORCHESTRATOR] Executing {tool.__class__.__name__}.{operation} with params: {params}")
        logger.debug(f"[ORCHESTRATOR] Tool has services: {hasattr(tool, 'services') and tool.services is not None}")
        
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
                # If success=True but no nested "data" key, use the whole dict as data
                if success and data is None:
                    data = {k: v for k, v in result.items() if k not in ("success", "error", "error_message")}
                error = result.get("error") or result.get("error_message")
                if success:
                    error = None
                return success, data, error
            # Plain dict with an "error" key but no "success" key — treat as failure.
            if "error" in result or "error_message" in result:
                error_msg = result.get("error") or result.get("error_message")
                return False, None, str(error_msg)
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
    
    def _verify_error_result(
        self, error: str, tool_name: str, operation: str, execution_context: Optional[Any]
    ) -> None:
        """Run verification on error/fallback paths so issues are logged consistently."""
        verification = self._verifier.verify(
            data=None,
            tool_name=tool_name,
            operation=operation,
            skill_context=execution_context,
        )
        if execution_context and verification.issues:
            for issue in verification.issues:
                execution_context.warnings.append(f"[VERIFY:{issue.layer}] {issue.message}")
