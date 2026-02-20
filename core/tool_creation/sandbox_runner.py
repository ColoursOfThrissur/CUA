"""
Sandbox runner for testing generated tools
"""
import os
import tempfile
import importlib.util
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SandboxRunner:
    """Runs generated tools in isolated sandbox environment"""
    
    def __init__(self, expansion_mode):
        self.expansion_mode = expansion_mode
    
    def run_sandbox(self, tool_name: str) -> bool:
        """Run runtime playground validation for a newly generated tool"""
        tool_path = Path(getattr(self.expansion_mode, "experimental_dir", "tools/experimental")) / f"{tool_name}.py"
        if not tool_path.exists():
            logger.warning(f"Sandbox skipped: tool file not found at {tool_path}")
            return False
        
        try:
            tool_class = self._load_tool_class(tool_name, tool_path)
            if tool_class is None:
                logger.error(f"Sandbox failed: could not resolve tool class for {tool_name}")
                return False
            
            # Create orchestrator BEFORE chdir so LLMLogger resolves to project root
            from core.tool_orchestrator import ToolOrchestrator
            from tools.capability_registry import CapabilityRegistry
            registry = CapabilityRegistry()
            orchestrator = ToolOrchestrator(registry=registry)
            
            original_cwd = Path.cwd()
            with tempfile.TemporaryDirectory(prefix=f"tool_sandbox_{tool_name}_") as temp_dir:
                os.chdir(temp_dir)
                try:
                    os.makedirs("data", exist_ok=True)
                    
                    # Instantiate tool with orchestrator
                    tool_instance = tool_class(orchestrator=orchestrator)
                    
                    return self._run_smoke_tests(tool_instance, orchestrator)
                finally:
                    os.chdir(original_cwd)
        
        except Exception as e:
            logger.error(f"Sandbox failed for {tool_name}: {e}")
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
    
    def _run_smoke_tests(self, tool_instance, orchestrator) -> bool:
        """Execute deterministic smoke sequence across discovered capabilities"""
        capabilities = tool_instance.get_capabilities()
        if not capabilities:
            logger.error("Sandbox failed: generated tool has no capabilities")
            return False
        
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
        
        # Order operations: create/save first, then get/read, then list
        operations = list(capabilities.keys())
        ordered_ops = [op for op in ("create", "save", "append", "get", "read", "list", "recent") if op in operations]
        ordered_ops.extend(op for op in operations if op not in ordered_ops)
        
        created_ids = []
        for op in ordered_ops:
            capability = capabilities.get(op)
            params = self._build_test_parameters(capability, shared)
            
            logger.info(f"[SANDBOX] Testing operation: {op}")
            result = orchestrator.execute_tool_step(
                tool=tool_instance,
                tool_name=getattr(tool_instance, "name", tool_instance.__class__.__name__),
                operation=op,
                parameters=params,
                context={},
            )
            
            if not result.success:
                logger.error(f"Sandbox failed for operation '{op}': {result.error}")
                return False
            
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
        
        logger.info(f"Sandbox validation passed for {getattr(tool_instance, 'name', 'tool')}")
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
                        params[name] = "https://example.com"
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
        """Convert tool_name to ClassName"""
        return ''.join((part[:1].upper() + part[1:]) for part in tool_name.split('_') if part)
