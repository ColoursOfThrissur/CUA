"""
Pending Tools API Endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import inspect
import asyncio

router = APIRouter(prefix="/pending-tools", tags=["pending-tools"])

# Global instances (set from server)
pending_tools_manager = None
tool_registrar = None
registry_manager = None
approve_lock = asyncio.Lock()

def set_pending_tools_manager(ptm):
    global pending_tools_manager
    pending_tools_manager = ptm

def set_tool_registrar(tr):
    global tool_registrar
    tool_registrar = tr

def set_registry_manager_for_pending(manager):
    global registry_manager
    registry_manager = manager

class RejectRequest(BaseModel):
    reason: Optional[str] = ""


def _post_register_contract_check(tool_name: str):
    """Run non-invasive runtime contract checks after registration."""
    tool_instance = getattr(tool_registrar, "registered_tools", {}).get(tool_name)
    if not tool_instance:
        return False, "Registered tool instance not found"

    try:
        sig = inspect.signature(tool_instance.execute)
        params = list(sig.parameters.values())
    except Exception as e:
        return False, f"Unable to inspect execute() signature: {e}"

    # Bound methods expose either:
    # - execute(operation, parameters)
    # - execute(operation, **kwargs)
    if not params:
        return False, "execute() must accept at least operation"
    has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params)
    supports_param_dict = len(params) >= 2
    if not has_kwargs and not supports_param_dict:
        return False, "execute() must support parameters dict or **kwargs"

    try:
        capabilities = tool_instance.get_capabilities()
    except Exception as e:
        return False, f"get_capabilities() failed: {e}"
    if not capabilities:
        return False, "No capabilities registered"

    for cap_name in capabilities.keys():
        capability = capabilities.get(cap_name)
        for param in getattr(capability, "parameters", []) or []:
            if getattr(param, "required", True) and getattr(param, "default", None) is not None:
                return False, (
                    f"Capability '{cap_name}' has parameter '{param.name}' with "
                    "required=True and a default value"
                )
        handler_name = f"_handle_{cap_name}"
        handler = getattr(tool_instance, handler_name, None)
        if not callable(handler):
            return False, f"Missing capability handler: {handler_name}"
    return True, ""

@router.get("/list")
async def get_pending_tools():
    """Get all pending tools awaiting approval"""
    if not pending_tools_manager:
        return {"pending_tools": []}
    
    return {"pending_tools": pending_tools_manager.get_pending_list()}

@router.get("/{tool_id}")
async def get_tool_details(tool_id: str):
    """Get detailed info about pending tool"""
    if not pending_tools_manager:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    
    tool = pending_tools_manager.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    return tool

@router.post("/{tool_id}/approve")
async def approve_tool(tool_id: str):
    """Approve and activate tool"""
    if not pending_tools_manager or not tool_registrar:
        raise HTTPException(status_code=503, detail="System not initialized")

    async with approve_lock:
        # Get tool metadata
        tool = pending_tools_manager.get_tool(tool_id)
        if not tool:
            raise HTTPException(status_code=404, detail="Tool not found")
        
        # Register tool dynamically
        tool_file = tool.get('tool_file')
        if not tool_file:
            raise HTTPException(status_code=400, detail="No tool file specified")

        valid, contract_error = pending_tools_manager.validate_tool_file_contract(tool_file)
        if not valid:
            raise HTTPException(status_code=400, detail=f"Tool contract validation failed: {contract_error}")

        try:
            from tools.capability_extractor import CapabilityExtractor
            extracted = CapabilityExtractor().extract_from_file(tool_file)
            if not extracted or not extracted.get("operations"):
                raise HTTPException(status_code=400, detail="Tool has no extractable capabilities")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Capability extraction failed: {str(e)}")
        
        reg_result = tool_registrar.register_new_tool(tool_file)
        
        if not reg_result['success']:
            raise HTTPException(status_code=400, detail=f"Registration failed: {reg_result['error']}")

        smoke_ok, smoke_error = _post_register_contract_check(reg_result['tool_name'])
        if not smoke_ok:
            try:
                tool_registrar.unregister_tool(reg_result['tool_name'])
            except Exception:
                pass
            raise HTTPException(status_code=400, detail=f"Post-registration validation failed: {smoke_error}")
        
        # Mark as approved
        pending_tools_manager.approve_tool(tool_id)

        # Keep tool registry view in sync when possible.
        try:
            if registry_manager and extracted:
                extracted["source_file"] = str(tool_file).replace("\\", "/")
                registry_manager.update_tool(extracted)
        except Exception:
            # Registry sync should not block activation after successful runtime registration.
            pass

        skill_update_results = []
        try:
            from application.services.skill_updater import SkillUpdater

            skill_update_results = SkillUpdater().apply_update_plans(tool.get("skill_updates") or [])
        except Exception:
            skill_update_results = []
        
        return {
            "success": True,
            "tool_name": reg_result['tool_name'],
            "capabilities": reg_result['capabilities'],
            "skill_updates": skill_update_results,
            "message": f"Tool '{reg_result['tool_name']}' activated successfully"
        }

@router.post("/{tool_id}/test")
async def test_tool(tool_id: str):
    """Run LLM-generated tests on pending tool"""
    if not pending_tools_manager or not tool_registrar:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    tool = pending_tools_manager.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    tool_file = tool.get('tool_file')
    if not tool_file:
        raise HTTPException(status_code=400, detail="No tool file specified")
    
    try:
        from infrastructure.testing.llm_test_orchestrator import LLMTestOrchestrator
        from planner.llm_client import LLMClient
        from tools.capability_extractor import CapabilityExtractor
        from tools.capability_registry import CapabilityRegistry
        import importlib.util
        from pathlib import Path
        
        # Load tool temporarily
        tool_path = Path(tool_file)
        spec = importlib.util.spec_from_file_location("temp_tool", tool_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Get tool class
        tool_name = tool_path.stem
        class_name = ''.join(p[:1].upper() + p[1:] for p in tool_name.split('_') if p)
        tool_class = getattr(module, class_name)
        
        # Create registry and instantiate
        from application.use_cases.tool_lifecycle.tool_orchestrator import ToolOrchestrator
        registry = CapabilityRegistry()
        orchestrator = ToolOrchestrator(registry=registry)
        tool_instance = tool_class(orchestrator=orchestrator)
        
        # Register temporarily
        registry.register_tool(tool_instance)
        
        # Get capabilities
        capabilities = tool_instance.get_capabilities()
        if not capabilities:
            raise HTTPException(status_code=400, detail="Tool has no capabilities")
        
        # Run LLM tests for each capability
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
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test execution failed: {str(e)}")

@router.post("/{tool_id}/reject")
async def reject_tool(tool_id: str, request: RejectRequest):
    """Reject and remove pending tool"""
    if not pending_tools_manager:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    
    result = pending_tools_manager.reject_tool(tool_id, request.reason)
    
    if not result['success']:
        raise HTTPException(status_code=404, detail=result['error'])
    
    return {"success": True, "message": "Tool rejected and removed"}

@router.get("/active/list")
async def get_active_tools():
    """Get list of currently active tools"""
    if not tool_registrar:
        return {"active_tools": []}
    
    return {"active_tools": tool_registrar.get_active_tools()}
