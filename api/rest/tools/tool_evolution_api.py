"""API for tool evolution."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict

router = APIRouter()

_evolution_orchestrator = None
_pending_manager = None


def set_evolution_dependencies(orchestrator, pending_manager):
    """Set dependencies."""
    global _evolution_orchestrator, _pending_manager
    _evolution_orchestrator = orchestrator
    _pending_manager = pending_manager


class EvolveToolRequest(BaseModel):
    tool_name: str
    user_prompt: Optional[str] = None


@router.post("/evolution/evolve")
async def evolve_tool(request: EvolveToolRequest):
    """Start tool evolution process."""
    if not _evolution_orchestrator:
        raise HTTPException(status_code=500, detail="Evolution system not initialized")
    
    success, message = _evolution_orchestrator.evolve_tool(
        request.tool_name,
        request.user_prompt
    )
    
    conversation_log = _evolution_orchestrator.get_conversation_log()
    
    return {
        "success": success,
        "message": message,
        "conversation_log": conversation_log,
        "skill_updates": getattr(_evolution_orchestrator, "last_skill_updates", []),
    }


@router.get("/evolution/pending")
async def get_pending_evolutions():
    """Get all pending evolutions."""
    if not _pending_manager:
        raise HTTPException(status_code=500, detail="Pending manager not initialized")
    
    pending = _pending_manager.get_all_pending()
    
    return {"pending_evolutions": pending}


@router.post("/evolution/approve/{tool_name}")
async def approve_evolution(tool_name: str):
    """Approve pending evolution."""
    if not _pending_manager:
        raise HTTPException(status_code=500, detail="Pending manager not initialized")
    
    evolution = _pending_manager.get_pending_evolution(tool_name)
    if not evolution:
        raise HTTPException(status_code=404, detail="Evolution not found")
    
    # Re-check dependencies before approval
    from infrastructure.analysis.dependency_checker import DependencyChecker
    checker = DependencyChecker()
    improved_code = evolution.get("improved_code", "")
    report = checker.check_code(improved_code)
    
    # Update dependencies in proposal
    if "proposal" not in evolution:
        evolution["proposal"] = {}
    evolution["proposal"]["dependencies"] = {
        "missing_libraries": report.missing_libraries,
        "missing_services": report.missing_services
    }
    _pending_manager._save(_pending_manager._load())
    
    # Check if dependencies still missing
    if report.has_missing():
        return {
            "success": False,
            "needs_dependencies": True,
            "dependencies": {
                "missing_libraries": report.missing_libraries,
                "missing_services": report.missing_services
            },
            "message": "Please resolve dependencies first"
        }
    
    success = _pending_manager.approve_evolution(tool_name)
    
    if not success:
        raise HTTPException(status_code=404, detail="Evolution not found")
    
    # Sync registry with the newly written tool file
    try:
        from tools.capability_extractor import CapabilityExtractor
        from application.use_cases.tool_lifecycle.tool_registry_manager import ToolRegistryManager
        tool_path = evolution.get("tool_path")
        if tool_path:
            extracted = CapabilityExtractor().extract_from_file(tool_path)
            if extracted:
                extracted["source_file"] = str(tool_path).replace("\\", "/")
                ToolRegistryManager().update_tool(extracted)
    except Exception:
        pass  # Registry sync must not block approval
    
    return {"success": True, "message": f"Evolution approved: {tool_name}"}

@router.post("/evolution/test/{tool_name}")
async def test_evolution(tool_name: str):
    """Run LLM-generated tests on evolved tool."""
    if not _pending_manager:
        raise HTTPException(status_code=500, detail="Pending manager not initialized")
    
    evolution = _pending_manager.get_pending_evolution(tool_name)
    if not evolution:
        raise HTTPException(status_code=404, detail="Evolution not found")
    
    improved_code = evolution.get("improved_code", "")
    if not improved_code:
        raise HTTPException(status_code=400, detail="No improved code found")
    
    try:
        from infrastructure.testing.llm_test_orchestrator import LLMTestOrchestrator
        from planner.llm_client import LLMClient
        from tools.capability_registry import CapabilityRegistry
        from application.use_cases.tool_lifecycle.tool_orchestrator import ToolOrchestrator
        import tempfile
        import importlib.util
        from pathlib import Path
        
        # Write improved code to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(improved_code)
            temp_path = f.name
        
        try:
            # Load tool
            spec = importlib.util.spec_from_file_location("temp_evolved_tool", temp_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Get tool class
            class_name = ''.join(p[:1].upper() + p[1:] for p in tool_name.split('_') if p)
            tool_class = getattr(module, class_name)
            
            # Create registry and instantiate
            registry = CapabilityRegistry()
            orchestrator = ToolOrchestrator(registry=registry)
            tool_instance = tool_class(orchestrator=orchestrator)
            
            # Register temporarily
            registry.register_tool(tool_instance)
            
            # Get capabilities
            capabilities = tool_instance.get_capabilities()
            if not capabilities:
                raise HTTPException(status_code=400, detail="Tool has no capabilities")
            
            # Run LLM tests
            llm_client = LLMClient()
            test_orchestrator = LLMTestOrchestrator(llm_client, registry)
            
            all_results = []
            for cap_name, capability in capabilities.items():
                cap_dict = {
                    'name': cap_name,
                    'description': getattr(capability, 'description', ''),
                    'parameters': [{
                        'name': p.name,
                        'type': p.type.value if hasattr(p.type, 'value') else str(p.type),
                        'description': getattr(p, 'description', ''),
                        'required': getattr(p, 'required', True)
                    } for p in getattr(capability, 'parameters', [])],
                    'returns': getattr(capability, 'returns', 'Result')
                }
                
                test_cases = test_orchestrator.generate_test_cases(tool_name, cap_dict)
                result = test_orchestrator.execute_test_suite(tool_name, cap_name, test_cases)
                
                all_results.append({
                    'capability': cap_name,
                    'total_tests': result.total_tests,
                    'passed': result.passed_tests,
                    'failed': result.failed_tests,
                    'quality_score': result.overall_quality_score,
                    'test_results': [{
                        'test_name': tr.test_name,
                        'passed': tr.passed,
                        'execution_time_ms': tr.execution_time_ms,
                        'error': tr.error,
                        'quality_score': tr.quality_score
                    } for tr in result.test_results]
                })
            
            overall_passed = sum(r['passed'] for r in all_results)
            overall_total = sum(r['total_tests'] for r in all_results)
            overall_quality = sum(r['quality_score'] for r in all_results) / len(all_results) if all_results else 0
            
            return {
                'success': True,
                'tool_name': tool_name,
                'overall_quality_score': int(overall_quality),
                'total_tests': overall_total,
                'passed_tests': overall_passed,
                'failed_tests': overall_total - overall_passed,
                'results_by_capability': all_results
            }
        finally:
            Path(temp_path).unlink(missing_ok=True)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test execution failed: {str(e)}")


@router.post("/evolution/reject/{tool_name}")
async def reject_evolution(tool_name: str):
    """Reject pending evolution."""
    if not _pending_manager:
        raise HTTPException(status_code=500, detail="Pending manager not initialized")
    
    success = _pending_manager.reject_evolution(tool_name)
    
    if not success:
        raise HTTPException(status_code=404, detail="Evolution not found")
    
    return {"success": True, "message": f"Evolution rejected: {tool_name}"}


@router.get("/evolution/conversation/{tool_name}")
async def get_evolution_conversation(tool_name: str):
    """Get conversation log for evolution."""
    if not _pending_manager:
        raise HTTPException(status_code=500, detail="Pending manager not initialized")
    
    evolution = _pending_manager.get_pending_evolution(tool_name)
    
    if not evolution:
        raise HTTPException(status_code=404, detail="Evolution not found")
    
    return {
        "tool_name": tool_name,
        "conversation_log": evolution.get("conversation_log", []),
        "proposal": evolution.get("proposal", {}),
        "health_before": evolution.get("health_before", 0),
        "dependencies": evolution.get("proposal", {}).get("dependencies"),
        "skill_updates": evolution.get("skill_updates", []),
    }


@router.post("/evolution/resolve-dependencies/{tool_name}")
async def resolve_dependencies(tool_name: str, action: str, items: List[str]):
    """Resolve missing dependencies.
    
    action: 'install' for libraries, 'generate' for services, 'skip' to ignore
    items: list of library/service names to resolve
    """
    if not _pending_manager:
        raise HTTPException(status_code=500, detail="Pending manager not initialized")
    
    evolution = _pending_manager.get_pending_evolution(tool_name)
    if not evolution:
        raise HTTPException(status_code=404, detail="Evolution not found")
    
    from infrastructure.analysis.dependency_resolver import DependencyResolver
    resolver = DependencyResolver(llm_client=None)  # TODO: inject LLM client
    
    results = []
    
    if action == "install":
        for lib in items:
            success, msg = resolver.install_library(lib)
            results.append({"item": lib, "success": success, "message": msg})
    
    elif action == "generate":
        for service in items:
            success, code = resolver.generate_service(service)
            results.append({"item": service, "success": success, "code": code if success else None})
    
    elif action == "skip":
        # Remove dependencies from proposal
        if "dependencies" in evolution.get("proposal", {}):
            deps = evolution["proposal"]["dependencies"]
            deps["missing_libraries"] = [l for l in deps.get("missing_libraries", []) if l not in items]
            deps["missing_services"] = [s for s in deps.get("missing_services", []) if s not in items]
            _pending_manager._save(_pending_manager._load())
        results.append({"action": "skipped", "items": items})
    
    return {"success": True, "results": results}
