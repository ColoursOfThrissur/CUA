"""Shared orchestration layer for tool invocation and result normalization."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import inspect
import time

logger = logging.getLogger(__name__)

from application.services.parameter_resolution import resolve_tool_parameters
from infrastructure.persistence.storage_broker import get_storage_broker
from infrastructure.services.tool_services import ToolServices
from infrastructure.services.llm_service import LLMService
from infrastructure.validation.validation_service import ValidationService
from infrastructure.logging.tool_execution_logger import get_execution_logger
from infrastructure.failure_handling.circuit_breaker import get_circuit_breaker, CircuitBreakerError
from infrastructure.validation.verification_engine import get_verification_engine, VERDICT_RETRY, VERDICT_FALLBACK, VERDICT_ESCALATE
from application.use_cases.planning.task_planner_clean import TaskPlanner
from application.use_cases.execution.result_interpreter import ResultInterpreter

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

    # Class-level signature cache: (tool_class, operation) → (supports_kwargs, supports_dict)
    _sig_cache: Dict[tuple, tuple] = {}
    
    def __init__(self, llm_client=None, registry=None, skill_registry=None):
        self._services_cache: Dict[str, ToolServices] = {}
        self._llm_client = llm_client
        self._registry = registry
        self.skill_registry = skill_registry
        self._execution_logger = get_execution_logger()
        self._circuit_breaker = get_circuit_breaker()
        self._verifier = get_verification_engine(llm_client)
        self._result_interpreter = ResultInterpreter()
        self.main_planner = None
        self._refresh_runtime_dependencies()

    def _refresh_runtime_dependencies(self) -> None:
        """Keep planner and verifier aligned with the current live LLM client."""
        self._verifier = get_verification_engine(self._llm_client)
        if self._registry is not None and self._llm_client is not None:
            self.main_planner = TaskPlanner(
                llm_client=self._llm_client,
                tool_registry=self._registry,
                skill_registry=self.skill_registry,
            )

    def set_llm_client(self, llm_client) -> None:
        """Inject the live LLM client after bootstrap initialization."""
        self._llm_client = llm_client
        for services in self._services_cache.values():
            services.llm = LLMService(llm_client) if llm_client else None
        self._refresh_runtime_dependencies()

    def set_execution_engine(self, execution_engine) -> None:
        """Expose the shared execution engine to tools that need main-path execution."""
        self.execution_engine = execution_engine

    def get_tool(self, tool_name: str):
        """Return the current registered tool instance by name."""
        registry = self._registry
        if registry is None:
            return None
        if hasattr(registry, "get_tool_by_name"):
            return registry.get_tool_by_name(tool_name)
        for tool in getattr(registry, "tools", []):
            if tool.__class__.__name__ == tool_name:
                return tool
        return None
    
    def get_services(self, tool_name: str) -> ToolServices:
        """Get service facade for a tool (cached per tool name)."""
        if tool_name not in self._services_cache:
            storage_broker = get_storage_broker(tool_name)
            # Lazy load LLM client if not provided
            if self._llm_client is None:
                from planner.llm_client import get_llm_client
                self._llm_client = get_llm_client()
                self._refresh_runtime_dependencies()
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
        interpretation = self._get_result_interpreter().interpret(
            raw_result=raw_result,
            data=data,
            success=success,
            error=error,
            tool_name=tool_name,
            operation=operation,
        )
        artifacts = interpretation.artifacts
        execution_feedback = interpretation.execution_feedback

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
                execution_feedback["recommended_action"] = "retry"
                execution_feedback["blocking_reason"] = execution_feedback.get("blocking_reason") or "verification_retry"
            elif verification.verdict == VERDICT_FALLBACK:
                success = False
                error = f"Verification failed (fallback): {verification.notes}"
                execution_feedback["recommended_action"] = "fallback_tool"
                execution_feedback["blocking_reason"] = execution_feedback.get("blocking_reason") or "verification_fallback"
                if execution_context and hasattr(execution_context, 'fallback_tools') and execution_context.fallback_tools:
                    execution_context.selected_tool = execution_context.fallback_tools[0]
                    execution_context.warnings.append(f"Switched to fallback due to verification: {verification.notes}")
            elif verification.verdict == VERDICT_ESCALATE:
                success = False
                error = f"Verification escalated (cross-source disagreement): {verification.notes}"
                execution_feedback["recommended_action"] = "replan"
                execution_feedback["blocking_reason"] = execution_feedback.get("blocking_reason") or "verification_escalate"
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
        
        meta = {
            "auto_filled": resolution.auto_filled,
            "resolved_parameters": resolution.resolved_parameters,
            "artifacts": artifacts,
            "execution_feedback": execution_feedback,
            "result_interpretation": interpretation.to_dict(),
        }

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
            meta=meta,
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

        cache_key = (type(tool), operation)
        if cache_key not in ToolOrchestrator._sig_cache:
            supports_kwargs = False
            supports_dict = True
            try:
                sig = inspect.signature(tool.execute)
                supports_kwargs = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                )
                supports_dict = len(sig.parameters) >= 2
            except Exception:
                pass
            ToolOrchestrator._sig_cache[cache_key] = (supports_kwargs, supports_dict)
        supports_kwargs, supports_dict = ToolOrchestrator._sig_cache[cache_key]

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
            if success and isinstance(data, dict) and "success" in data:
                nested_success = bool(data.get("success"))
                if not nested_success:
                    success = False
                    error = (
                        data.get("error")
                        or data.get("message")
                        or data.get("error_message")
                        or "Tool returned unsuccessful payload"
                    )
            if success:
                error = None
            return success, data, error

        if hasattr(result, "status"):
            status = getattr(result, "status", None)
            status_value = getattr(status, "value", str(status)).lower() if status is not None else "failure"
            success = status_value == "success"
            data = getattr(result, "data", None)
            error = getattr(result, "error_message", None)
            if success and isinstance(data, dict) and "success" in data:
                nested_success = bool(data.get("success"))
                if not nested_success:
                    success = False
                    error = (
                        data.get("error")
                        or data.get("message")
                        or data.get("error_message")
                        or "Tool returned unsuccessful payload"
                    )
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
        return self._get_result_interpreter().extract_artifacts(data)

    def _extract_execution_feedback(self, raw_result: Any, data: Any, success: bool) -> Dict[str, Any]:
        return self._get_result_interpreter().extract_execution_feedback(raw_result, data, success)

    def _get_result_interpreter(self) -> ResultInterpreter:
        interpreter = getattr(self, "_result_interpreter", None)
        if interpreter is None:
            interpreter = ResultInterpreter()
            self._result_interpreter = interpreter
        return interpreter
    
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
