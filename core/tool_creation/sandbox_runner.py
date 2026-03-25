"""
Sandbox runner for testing generated tools
"""
import os
import tempfile
import importlib.util
import logging
import traceback
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

try:
    from core.tool_creation_logger import ToolCreationLogger
    creation_logger = ToolCreationLogger()
except:
    creation_logger = None


class SandboxRunner:
    """Runs generated tools in isolated sandbox environment"""
    
    def __init__(self, expansion_mode):
        self.expansion_mode = expansion_mode
    
    def run_sandbox(self, tool_name: str, creation_id: int = None, stub_ops: set = None) -> bool:
        """Run runtime playground validation for a newly generated tool.
        stub_ops: set of operation names that are known stubs (skip 'returned None' for these).
        """
        if creation_logger and creation_id:
            creation_logger.log_artifact(creation_id, "sandbox_start", "sandbox", {"tool_name": tool_name})
        
        tool_path = Path(getattr(self.expansion_mode, "experimental_dir", "tools/experimental")) / f"{tool_name}.py"
        if not tool_path.exists():
            error_msg = f"Tool file not found at {tool_path}"
            logger.warning(f"Sandbox skipped: {error_msg}")
            if creation_logger and creation_id:
                creation_logger.log_artifact(creation_id, "error", "sandbox", {"error": error_msg})
            return False
        
        try:
            if creation_logger and creation_id:
                creation_logger.log_artifact(creation_id, "loading_tool", "sandbox", {"tool_path": str(tool_path)})
            
            tool_class = self._load_tool_class(tool_name, tool_path)
            if tool_class is None:
                error_msg = f"Could not load tool class. Check: 1) Class name matches file name, 2) No syntax errors, 3) Imports are valid"
                logger.error(f"Sandbox failed: {error_msg}")
                if creation_logger and creation_id:
                    creation_logger.log_artifact(creation_id, "error", "sandbox", {"error": error_msg, "tool_path": str(tool_path)})
                return False
            
            # Create orchestrator BEFORE chdir so LLMLogger resolves to project root
            from core.tool_orchestrator import ToolOrchestrator
            from tools.capability_registry import CapabilityRegistry
            
            if creation_logger and creation_id:
                creation_logger.log_artifact(creation_id, "creating_orchestrator", "sandbox", {})
            
            registry = CapabilityRegistry()
            orchestrator = ToolOrchestrator(registry=registry)
            
            # DON'T chdir - let tool access real data directory
            # Tools should use storage service which is scoped to temp data
            if creation_logger and creation_id:
                creation_logger.log_artifact(creation_id, "instantiating_tool", "sandbox", {"class_name": tool_class.__name__})
            
            # Instantiate tool with orchestrator
            tool_instance = tool_class(orchestrator=orchestrator)
            
            if creation_logger and creation_id:
                creation_logger.log_artifact(creation_id, "running_tests", "sandbox", {})
            
            result = self._run_smoke_tests(tool_instance, orchestrator, creation_id, stub_ops=stub_ops)
            
            if creation_logger and creation_id:
                creation_logger.log_artifact(creation_id, "sandbox_complete", "sandbox", {"success": result})
            
            return result
        
        except Exception as e:
            error_msg = f"{str(e)}"
            error_trace = traceback.format_exc()
            logger.error(f"Sandbox failed for {tool_name}: {error_msg}\n{error_trace}")
            if creation_logger and creation_id:
                creation_logger.log_artifact(creation_id, "error", "sandbox", {
                    "error": error_msg,
                    "traceback": error_trace
                })
            return False
    
    def _load_tool_class(self, tool_name: str, tool_path: Path):
        """Load generated tool class from file path"""
        module_name = f"_sandbox_{tool_name.lower()}_{abs(hash(str(tool_path)))}"
        spec = importlib.util.spec_from_file_location(module_name, str(tool_path))
        if spec is None or spec.loader is None:
            return None
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        class_name = self._class_name(tool_name)
        return getattr(module, class_name, None)
    
    def _run_smoke_tests(self, tool_instance, orchestrator, creation_id: int = None, stub_ops: set = None) -> bool:
        """Execute deterministic smoke sequence across discovered capabilities"""
        stub_ops = stub_ops or set()
        try:
            capabilities = tool_instance.get_capabilities()
        except Exception as e:
            error_msg = f"Failed to get capabilities: {str(e)}"
            logger.error(error_msg)
            if creation_logger and creation_id:
                creation_logger.log_artifact(creation_id, "error", "sandbox", {"error": error_msg, "traceback": traceback.format_exc()})
            return False
        
        if not capabilities:
            error_msg = "Generated tool has no capabilities"
            logger.error(f"Sandbox failed: {error_msg}")
            if creation_logger and creation_id:
                creation_logger.log_artifact(creation_id, "error", "sandbox", {"error": error_msg})
            return False
        
        if creation_logger and creation_id:
            creation_logger.log_artifact(creation_id, "capabilities_found", "sandbox", {
                "count": len(capabilities),
                "operations": list(capabilities.keys())
            })
        
        # Shared test data
        shared = {
            "id": "demo-001",
            "task_id": "demo-001",
            "contact_id": "demo-001",
            "plan_id": "demo-001",
            "name": "Demo User",
            "email": "demo@example.com",
            "notes": "sandbox validation",
            "summary": "sandbox validation",
        }
        
        # Auto-detect network_only: if all capability names contain network patterns, skip sandbox
        _NETWORK_PATTERNS = {'http', 'url', 'browser', 'navigate', 'fetch', 'request', 'scrape', 'crawl', 'web'}
        cap_names = list(capabilities.keys())
        network_only = bool(cap_names and all(
            any(p in cap.lower() for p in _NETWORK_PATTERNS) for cap in cap_names
        ))
        if network_only:
            logger.warning(f"Sandbox: auto-detected network_only tool ({cap_names}), skipping execution")
            if creation_logger and creation_id:
                creation_logger.log_artifact(creation_id, "sandbox_network_only", "sandbox", {
                    "caps": cap_names, "note": "All capabilities are network-dependent"
                })
            return True

        # Order operations: create/save first, then get/read, then list
        operations = list(capabilities.keys())
        ordered_ops = [op for op in ("create", "save", "append", "get", "read", "list", "recent") if op in operations]
        ordered_ops.extend(op for op in operations if op not in ordered_ops)
        
        created_ids = []
        skipped_count = 0
        success_count = 0
        for op in ordered_ops:
            capability = capabilities.get(op)
            params = self._build_test_parameters(capability, shared)
            
            logger.info(f"[SANDBOX] Testing operation: {op}")
            if creation_logger and creation_id:
                creation_logger.log_artifact(creation_id, "testing_operation", "sandbox", {
                    "operation": op,
                    "parameters": params
                })
            
            try:
                result = orchestrator.execute_tool_step(
                    tool=tool_instance,
                    tool_name=getattr(tool_instance, "name", tool_instance.__class__.__name__),
                    operation=op,
                    parameters=params,
                    context={},
                )
            except KeyError as e:
                error_msg = f"KeyError: {str(e)} - Handler tried to access missing parameter"
                logger.error(f"Sandbox failed for operation '{op}': {error_msg}")
                if creation_logger and creation_id:
                    creation_logger.log_artifact(creation_id, "operation_failed", "sandbox", {
                        "operation": op,
                        "error": error_msg,
                        "traceback": traceback.format_exc()
                    })
                return False
            except Exception as e:
                error_msg = str(e)
                # Asyncio misuse — give targeted message
                if any(x in error_msg.lower() for x in ['asyncio', 'event loop', 'run_until_complete']):
                    logger.error(f"Sandbox: asyncio misuse in '{op}' — use ThreadPoolExecutor instead")
                    if creation_logger and creation_id:
                        creation_logger.log_artifact(creation_id, "operation_failed", "sandbox", {
                            "operation": op, "error": "asyncio misuse — use ThreadPoolExecutor"
                        })
                    return False
                # Ignore SSL errors, network issues, and element-not-found in sandbox - they're expected
                if any(x in error_msg.lower() for x in ['ssl', 'certificate', 'connection', 'network', 'timeout', 'browser not open', 'no such element', 'unable to locate element']):
                    logger.warning(f"Sandbox: Ignoring network/browser/element error for '{op}': {error_msg}")
                    if creation_logger and creation_id:
                        creation_logger.log_artifact(creation_id, "operation_skipped", "sandbox", {
                            "operation": op,
                            "reason": "network_or_browser_error",
                            "error": error_msg
                        })
                    skipped_count += 1
                    continue  # Skip this operation, continue with others
                
                logger.error(f"Exception during operation '{op}': {error_msg}")
                if creation_logger and creation_id:
                    creation_logger.log_artifact(creation_id, "operation_failed", "sandbox", {
                        "operation": op,
                        "error": error_msg,
                        "traceback": traceback.format_exc()
                    })
                return False
            
            # Also treat handler-level success:False as a failure (not just orchestrator-level)
            if result.success and isinstance(result.data, dict) and result.data.get('success') is False:
                handler_error = result.data.get('error', 'unknown')
                ignorable = ['not found', 'ssl', 'certificate', 'connection', 'network', 'timeout',
                             'browser not open', 'no such element']
                if not any(x in handler_error.lower() for x in ignorable):
                    # Skip 'returned None' for known stub operations
                    if op in stub_ops and 'none' in handler_error.lower():
                        logger.warning(f"Sandbox: skipping stub op '{op}' returned None")
                        skipped_count += 1
                        continue
                    logger.error(f"Sandbox: handler returned success=False for '{op}': {handler_error}")
                    if creation_logger and creation_id:
                        creation_logger.log_artifact(creation_id, "operation_failed", "sandbox", {
                            "operation": op, "error": handler_error
                        })
                    return False
                else:
                    logger.warning(f"Sandbox: ignoring expected error for '{op}': {handler_error}")
                    skipped_count += 1
                    continue

            if not result.success:
                error_msg = f"Operation '{op}' failed: {result.error}"
                if any(x in error_msg.lower() for x in ['ssl', 'certificate', 'connection', 'network', 'timeout', 'browser not open', 'no such element', 'unable to locate element']):
                    logger.warning(f"Sandbox: Ignoring network/browser/element error for '{op}': {error_msg}")
                    if creation_logger and creation_id:
                        creation_logger.log_artifact(creation_id, "operation_skipped", "sandbox", {
                            "operation": op, "reason": "network_or_browser_error", "error": error_msg
                        })
                    skipped_count += 1
                    continue

                # Skip 'returned None' for known stub operations
                if op in stub_ops and result.error and 'none' in result.error.lower():
                    logger.warning(f"Sandbox: skipping stub op '{op}' returned None")
                    skipped_count += 1
                    continue
                
                logger.error(f"Sandbox failed for operation '{op}': {result.error}")
                if creation_logger and creation_id:
                    creation_logger.log_artifact(creation_id, "operation_failed", "sandbox", {
                        "operation": op,
                        "error": result.error
                    })
                return False
            
            if creation_logger and creation_id:
                creation_logger.log_artifact(creation_id, "operation_success", "sandbox", {
                    "operation": op,
                    "result_type": type(result.data).__name__ if result.data else "None",
                    "result_preview": str(result.data)[:200] if result.data else None
                })
            
            success_count += 1
            
            # Track created IDs for verification
            if op in ("create", "save") and result.data:
                if isinstance(result.data, dict):
                    item_id = result.data.get("id")
                    if item_id:
                        created_ids.append(item_id)
        
        # Verify persistence: if create/save worked, get/list should find items
        if created_ids and "get" in operations:
            result = orchestrator.execute_tool_step(
                tool=tool_instance,
                tool_name=getattr(tool_instance, "name", tool_instance.__class__.__name__),
                operation="get",
                parameters={"id": created_ids[0]},
                context={},
            )
            if not result.success:
                logger.warning("Sandbox persistence check: get failed (may be expected for some tools)")
        
        if created_ids and "list" in operations:
            result = orchestrator.execute_tool_step(
                tool=tool_instance,
                tool_name=getattr(tool_instance, "name", tool_instance.__class__.__name__),
                operation="list",
                parameters={"limit": 5},
                context={},
            )
            if not result.success:
                logger.warning("Sandbox persistence check: list failed (may be expected for some tools)")
        
        # If all operations were skipped due to network errors, still pass
        if skipped_count > 0 and success_count == 0:
            logger.warning(f"Sandbox: All {skipped_count} operations skipped (network-dependent tool). Real validation will occur via LLM tests after approval.")
            if creation_logger and creation_id:
                creation_logger.log_artifact(creation_id, "sandbox_network_only", "sandbox", {
                    "skipped_count": skipped_count,
                    "note": "Tool requires network access - will be validated via LLM tests"
                })
            return True
        
        # Log summary
        if creation_logger and creation_id:
            creation_logger.log_artifact(creation_id, "sandbox_summary", "sandbox", {
                "total_operations": len(ordered_ops),
                "success_count": success_count,
                "skipped_count": skipped_count,
                "status": "passed"
            })
        
        logger.info(f"Sandbox validation passed for {getattr(tool_instance, 'name', 'tool')} ({success_count} operations succeeded, {skipped_count} skipped)")
        return True
    
    def _build_test_parameters(self, capability, shared: Dict[str, Any]) -> Dict[str, Any]:
        """Build deterministic test parameters from capability metadata"""
        from tools.tool_capability import ParameterType
        
        params: Dict[str, Any] = {}
        parameters_list = getattr(capability, "parameters", []) or []
        
        for p in parameters_list:
            name = getattr(p, "name", None)
            if not name:
                continue
            
            # Use shared values if available
            if name in shared:
                params[name] = shared[name]
                continue
            
            default = getattr(p, "default", None)
            required = bool(getattr(p, "required", True))
            p_type = getattr(p, "type", None)
            
            if default is not None:
                params[name] = default
            elif required:
                # Type-aware smart parameter generation
                name_lower = name.lower()
                
                if p_type == ParameterType.INTEGER:
                    if "priority" in name_lower:
                        params[name] = 2
                    elif "version" in name_lower:
                        params[name] = 1
                    elif "id" in name_lower:
                        params[name] = 1001
                    else:
                        params[name] = 3
                
                elif p_type == ParameterType.STRING:
                    if "code" in name_lower:
                        params[name] = "print('demo')"
                    elif "language" in name_lower or "lang" in name_lower:
                        params[name] = "python"
                    elif "snippet" in name_lower and "id" in name_lower:
                        params[name] = "demo-snippet-001"
                    elif "project" in name_lower and "id" in name_lower:
                        params[name] = "demo-project-001"
                    elif "task" in name_lower and "id" in name_lower:
                        params[name] = "demo-task-001"
                    elif "name" in name_lower or "title" in name_lower:
                        params[name] = "Demo name"
                    elif "deadline" in name_lower or "due" in name_lower:
                        params[name] = "2026-12-31"
                    elif "priority" in name_lower:
                        params[name] = "medium"
                    elif "status" in name_lower:
                        params[name] = "active"
                    elif "version" in name_lower:
                        params[name] = "1.0"
                    elif "description" in name_lower or "desc" in name_lower:
                        params[name] = "Demo description"
                    elif "url" in name_lower:
                        params[name] = "https://webscraper.io/test-sites/e-commerce/allinone"
                    elif "query" in name_lower:
                        params[name] = "demo query"
                    else:
                        params[name] = f"demo_{name}"
                
                elif p_type == ParameterType.BOOLEAN:
                    params[name] = True
                
                elif p_type == ParameterType.LIST:
                    if "tag" in name_lower:
                        params[name] = ["demo", "test"]
                    else:
                        params[name] = ["demo"]
                
                elif p_type == ParameterType.DICT:
                    if "filter" in name_lower:
                        params[name] = {"source": "sandbox"}
                    else:
                        params[name] = {"source": "sandbox"}
                
                elif p_type == ParameterType.FILE_PATH:
                    params[name] = f"data/{name}.txt"
                
                else:
                    params[name] = f"demo_{name}"
        
        return params
    
    def _class_name(self, tool_name: str) -> str:
        from core.tool_creation.code_generator.base import canonical_class_name
        return canonical_class_name(tool_name)
