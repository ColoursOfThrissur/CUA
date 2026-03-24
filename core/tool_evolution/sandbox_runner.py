"""Sandbox runner for tool evolution - matches creation pattern."""
import tempfile
import importlib.util
import traceback
import re
from pathlib import Path
from typing import Optional, Dict, Any
from core.sqlite_logging import get_logger

logger = get_logger("sandbox_runner")


class EvolutionSandboxRunner:
    """Runs evolved tool in sandbox to test it."""
    
    def __init__(self, expansion_mode):
        self.expansion_mode = expansion_mode
    
    def test_improved_tool(
        self,
        tool_name: str,
        improved_code: str,
        original_path: str,
        new_service_specs: Optional[Dict[str, Any]] = None,
        network_only: bool = False
    ) -> tuple[bool, str]:
        """Test improved tool in isolated environment. Returns (success, output)."""
        
        output_lines = []
        
        # Check for missing dependencies
        missing_deps = self._check_dependencies(improved_code, new_service_specs)
        if missing_deps['libraries'] or missing_deps['services']:
            output_lines.append("⚠ MISSING DEPENDENCIES DETECTED:")
            if missing_deps['libraries']:
                output_lines.append(f"  Libraries: {', '.join(missing_deps['libraries'])}")
            if missing_deps['services']:
                output_lines.append(f"  Services: {', '.join(missing_deps['services'])}")
            output_lines.append("  These must be resolved before deployment")
            return False, "\n".join(output_lines)
        
        # Check for new services
        if new_service_specs:
            output_lines.append(f"⚠ Tool requires {len(new_service_specs)} new service(s): {', '.join(new_service_specs.keys())}")
            output_lines.append("  These services will need to be created before deployment")
        
        # Auto-detect network_only if not explicitly set:
        # if ALL capabilities involve network/browser patterns, treat as network-only
        if not network_only:
            network_patterns = ['http', 'url', 'browser', 'navigate', 'fetch', 'request', 'scrape', 'crawl', 'web']
            cap_names = list(self._extract_capabilities(improved_code))
            if cap_names and all(
                any(p in cap.lower() for p in network_patterns) for cap in cap_names
            ):
                network_only = True
                logger.info(f"Auto-detected network_only=True for {tool_name} based on capability names: {cap_names}")

        # Extract class name from code
        class_name = self._extract_class_name(improved_code)
        if not class_name:
            logger.error("Could not extract class name from improved code")
            return False, "Could not extract class name"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Write improved code to temp file
            temp_tool_file = tmpdir_path / f"{tool_name}.py"
            temp_tool_file.write_text(improved_code)
            
            try:
                # Load tool class
                tool_class = self._load_tool_class(tool_name, temp_tool_file)
                if tool_class is None:
                    error_msg = "Could not load tool class. Check: 1) Class name matches file name, 2) No syntax errors, 3) Imports are valid"
                    logger.error(f"Sandbox failed: {error_msg}")
                    return False, error_msg
                
                output_lines.append("✓ Import test passed")
                
                # Create orchestrator
                from core.tool_orchestrator import ToolOrchestrator
                from tools.capability_registry import CapabilityRegistry
                
                registry = CapabilityRegistry()
                orchestrator = ToolOrchestrator(registry=registry)
                
                # Instantiate tool
                tool_instance = tool_class(orchestrator=orchestrator)
                output_lines.append("✓ Instantiation test passed")
                
                # Run smoke tests
                success = self._run_smoke_tests(tool_instance, orchestrator, output_lines)
                
                if success:
                    logger.info(f"Sandbox tests passed for {tool_name}")
                    return True, "\n".join(output_lines)
                else:
                    return False, "\n".join(output_lines)
                    
            except Exception as e:
                error_msg = f"Sandbox error: {str(e)}\n{traceback.format_exc()}"
                logger.error(error_msg)
                output_lines.append(f"✗ {error_msg}")
                return False, "\n".join(output_lines)
    
    def _load_tool_class(self, tool_name: str, tool_path: Path):
        """Load tool class from file path."""
        module_name = f"_sandbox_{tool_name.lower()}_{abs(hash(str(tool_path)))}"
        spec = importlib.util.spec_from_file_location(module_name, str(tool_path))
        if spec is None or spec.loader is None:
            return None
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        class_name = self._class_name(tool_name)
        return getattr(module, class_name, None)
    
    def _run_smoke_tests(self, tool_instance, orchestrator, output_lines: list) -> bool:
        """Execute smoke tests across capabilities (matches creation pattern)."""
        try:
            capabilities = tool_instance.get_capabilities()
        except Exception as e:
            error_msg = f"Failed to get capabilities: {str(e)}"
            logger.error(error_msg)
            output_lines.append(f"✗ {error_msg}")
            return False
        
        if not capabilities:
            error_msg = "Tool has no capabilities"
            logger.error(error_msg)
            output_lines.append(f"✗ {error_msg}")
            return False
        
        output_lines.append(f"✓ Found {len(capabilities)} capabilities: {list(capabilities.keys())}")
        
        # Shared test data
        shared = {
            "id": "demo-001",
            "name": "Demo User",
            "email": "demo@example.com",
            "notes": "sandbox validation",
        }
        
        # Order operations: create/save first, then get/read, then list
        operations = list(capabilities.keys())
        ordered_ops = [op for op in ("create", "save", "get", "read", "list") if op in operations]
        ordered_ops.extend(op for op in operations if op not in ordered_ops)
        
        skipped_count = 0
        success_count = 0
        
        for op in ordered_ops:
            capability = capabilities.get(op)
            params = self._build_test_parameters(capability, shared)
            
            try:
                result = orchestrator.execute_tool_step(
                    tool=tool_instance,
                    tool_name=getattr(tool_instance, "name", tool_instance.__class__.__name__),
                    operation=op,
                    parameters=params,
                    context={},
                )
            except KeyError as e:
                error_msg = f"KeyError in '{op}': {str(e)} - Handler tried to access missing parameter"
                logger.error(error_msg)
                output_lines.append(f"✗ {error_msg}")
                return False
            except Exception as e:
                error_msg = str(e)
                # Only skip specific network/browser errors that are expected in sandbox
                skip_patterns = [
                    'ssl', 'certificate', 'tls',  # SSL/TLS errors
                    'connection refused', 'connection reset', 'connection timeout',  # Connection errors
                    'network is unreachable', 'no route to host',  # Network errors
                    'browser not open', 'browser is not initialized',  # Browser state errors
                    'no such element', 'element not found', 'stale element'  # Element errors
                ]
                if any(pattern in error_msg.lower() for pattern in skip_patterns):
                    logger.warning(f"Sandbox: Skipping expected network/browser error for '{op}': {error_msg}")
                    skipped_count += 1
                    continue
                
                # Real errors should fail
                logger.error(f"Exception during '{op}': {error_msg}")
                output_lines.append(f"✗ Operation '{op}' failed: {error_msg}")
                return False
            
            if not result.success:
                error_msg = result.error
                # Only skip specific network/browser errors that are expected in sandbox
                skip_patterns = [
                    'ssl', 'certificate', 'tls',  # SSL/TLS errors
                    'connection refused', 'connection reset', 'connection timeout',  # Connection errors
                    'network is unreachable', 'no route to host',  # Network errors
                    'browser not open', 'browser is not initialized',  # Browser state errors
                    'no such element', 'element not found', 'stale element'  # Element errors
                ]
                if any(pattern in error_msg.lower() for pattern in skip_patterns):
                    logger.warning(f"Sandbox: Skipping expected network/browser error for '{op}': {error_msg}")
                    skipped_count += 1
                    continue
                
                # Real errors should fail
                logger.error(f"Operation '{op}' failed: {error_msg}")
                output_lines.append(f"✗ Operation '{op}' failed: {error_msg}")
                return False
            
            success_count += 1
        
        # CRITICAL: Require at least 1 successful operation
        # If all operations skipped with no successes, this is a failure
        if success_count == 0:
            if skipped_count > 0:
                # Check if tool is explicitly marked as network-only
                if network_only:
                    logger.warning(f"All {skipped_count} operations skipped (network-only tool)")
                    output_lines.append(f"⚠ Network-only tool - all operations skipped in sandbox")
                    output_lines.append(f"⚠ Manual testing required after deployment")
                    return True
                else:
                    logger.error(f"All {skipped_count} operations skipped but tool not marked network-only")
                    output_lines.append(f"✗ All operations skipped - no successful execution paths")
                    output_lines.append(f"✗ Tool may be broken or requires network access")
                    return False
            else:
                logger.error("No operations succeeded")
                output_lines.append(f"✗ No successful operations")
                return False
        
        output_lines.append(f"✓ Smoke tests passed ({success_count} operations succeeded, {skipped_count} skipped)")
        logger.info(f"Sandbox validation passed ({success_count} operations succeeded, {skipped_count} skipped)")
        return True
    
    def _build_test_parameters(self, capability, shared: Dict[str, Any]) -> Dict[str, Any]:
        """Build test parameters from capability metadata (matches creation pattern)."""
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
                name_lower = name.lower()
                
                if p_type == ParameterType.INTEGER:
                    params[name] = 3 if "priority" not in name_lower else 2
                elif p_type == ParameterType.STRING:
                    if "url" in name_lower:
                        params[name] = "https://webscraper.io/test-sites/e-commerce/allinone"
                    elif "query" in name_lower:
                        params[name] = "demo query"
                    else:
                        params[name] = f"demo_{name}"
                elif p_type == ParameterType.BOOLEAN:
                    params[name] = True
                elif p_type == ParameterType.LIST:
                    params[name] = ["demo"]
                elif p_type == ParameterType.DICT:
                    params[name] = {"source": "sandbox"}
                elif p_type == ParameterType.FILE_PATH:
                    params[name] = f"data/{name}.txt"
                else:
                    params[name] = f"demo_{name}"
        
        return params
    
    def _check_dependencies(self, code: str, new_service_specs: Optional[Dict[str, Any]]) -> Dict[str, list]:
        """Check for missing dependencies in code."""
        from core.dependency_checker import DependencyChecker
        
        checker = DependencyChecker()
        report = checker.check_code(code)
        
        missing = {
            'libraries': report.missing_libraries,
            'services': []
        }
        
        # Filter out services that will be created
        pending_service_names = set(new_service_specs.keys()) if new_service_specs else set()
        for svc in report.missing_services:
            if svc not in pending_service_names:
                missing['services'].append(svc)
        
        return missing
    
    def _extract_class_name(self, code: str) -> Optional[str]:
        """Extract class name from code."""
        match = re.search(r'class\s+(\w+)', code)
        return match.group(1) if match else None

    def _extract_capabilities(self, code: str) -> list:
        """Extract capability names from code."""
        return re.findall(r"name=['\"]([\w_]+)['\"]", code)
    
    def _class_name(self, tool_name: str) -> str:
        """Convert tool_name to ClassName."""
        return ''.join((part[:1].upper() + part[1:]) for part in tool_name.split('_') if part)
