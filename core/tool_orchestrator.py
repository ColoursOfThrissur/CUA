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
from core.circuit_breaker import get_circuit_breaker, CircuitBreakerError


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
            
            # Validate output even in error scenarios
            if execution_context and hasattr(execution_context, 'verification_mode'):
                validation_error = self._validate_output(None, execution_context)
                if validation_error:
                    execution_context.add_error(tool_name, f"Output validation failed: {validation_error}", 0)
            
            return OrchestratedToolResult(
                success=False,
                data=None,
                error=f"Tool quarantined due to repeated failures. {str(e)}",
                raw_result=None,
                tool_name=tool_name,
                operation=operation,
                resolved_parameters=resolution.resolved_parameters,
                missing_required=[],
                artifacts=[],
                meta={"auto_filled": resolution.auto_filled, "circuit_breaker": "open"},
            )
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
            
            # Update execution context if provided
            if execution_context:
                execution_context.add_error(tool_name, str(e), execution_context.retry_count)
            
            # Validate output even in error scenarios
            if execution_context and hasattr(execution_context, 'verification_mode'):
                validation_error = self._validate_output(None, execution_context)
                if validation_error:
                    execution_context.add_error(tool_name, f"Output validation failed: {validation_error}", execution_context.retry_count)
            
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
        
        # Validate output against skill context if provided (ALL PATHS)
        if execution_context and hasattr(execution_context, 'verification_mode'):
            validation_error = self._validate_output(data, execution_context)
            if validation_error:
                # Validation failed - trigger recovery logic
                execution_context.add_error(tool_name, f"Output validation failed: {validation_error}", execution_context.retry_count)
                
                # Check if we should retry or fallback
                if execution_context.should_retry():
                    execution_context.retry_count += 1
                    execution_context.warnings.append(f"Retrying due to validation failure (attempt {execution_context.retry_count})")
                    success = False
                    error = f"Output validation failed: {validation_error} (will retry)"
                elif execution_context.should_fallback():
                    fallback_tool = execution_context.fallback_tools[0] if execution_context.fallback_tools else None
                    if fallback_tool:
                        execution_context.warnings.append(f"Switching to {fallback_tool} due to validation failure")
                        execution_context.selected_tool = fallback_tool
                    success = False
                    error = f"Output validation failed: {validation_error} (will fallback)"
                else:
                    # No recovery options - mark as failed
                    success = False
                    error = f"Output validation failed: {validation_error}"
        
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
    
    def _validate_output(self, data: Any, execution_context: Any) -> Optional[str]:
        """Validate output against skill verification_mode (enhanced for all paths)."""
        verification_mode = getattr(execution_context, 'verification_mode', None)
        expected_output_types = getattr(execution_context, 'expected_output_types', [])
        
        if not verification_mode:
            return None
        
        # Handle None/empty data (error scenarios)
        if data is None:
            if verification_mode in ["source_backed", "side_effect_observed"]:
                return f"No output data for {verification_mode} verification mode"
            return None
        
        if not isinstance(data, dict):
            # For non-dict outputs, only validate if strict verification required
            if verification_mode == "source_backed":
                return "Output must be dict with 'sources' field for source_backed verification"
            elif verification_mode == "side_effect_observed":
                return "Output must be dict with 'file_path' or 'path' field for side_effect_observed verification"
            return None
        
        # Validate based on verification mode
        if verification_mode == "source_backed":
            # For source_backed, we need either:
            # 1. Direct sources field, OR
            # 2. URL field (indicating content was fetched from a source)
            has_sources = "sources" in data and data["sources"]
            has_url = "url" in data and data["url"]
            has_content = "summary" in data or "content" in data or "text" in data
            
            if not (has_sources or has_url):
                return "Output missing 'sources' field or 'url' field for source_backed verification"
            if not has_content:
                return "Output missing 'summary', 'content', or 'text' field for source_backed verification"
        
        elif verification_mode == "side_effect_observed":
            if "file_path" not in data and "path" not in data:
                return "Output missing required 'file_path' or 'path' field for side_effect_observed verification"
        
        # Validate expected_output_types if specified
        if expected_output_types:
            output_keys = set(data.keys())
            type_indicators = {
                "research_summary": ["sources", "summary", "content", "text", "url"],
                "page_summary": ["content", "url", "title", "summary", "text"],
                "structured_extraction": ["extracted_data", "findings", "data", "content", "summary"],
                "source_comparison": ["sources", "comparison", "analysis", "content"],
                "file_list": ["files", "paths", "items"],
                "execution_result": ["output", "result", "status"],
                "code_summary": ["code", "analysis", "summary"],
                "change_summary": ["changes", "diff", "modifications"],
                "diff_result": ["diff", "patch", "changes"],
                "validation_result": ["valid", "errors", "warnings"],
                "test_result": ["passed", "failed", "tests", "results"]
            }
            
            matched = False
            for expected_type in expected_output_types:
                indicators = type_indicators.get(expected_type, [])
                if any(ind in output_keys for ind in indicators):
                    matched = True
                    break
            
            if not matched and expected_output_types:
                return f"Output type doesn't match expected types: {expected_output_types}. Found keys: {list(output_keys)}"
        
        return None
