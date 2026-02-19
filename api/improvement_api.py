"""
Self-Improvement Loop API Endpoints
"""
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/improvement", tags=["self-improvement"])

# Global loop instance (initialized in main server)
loop_instance = None

def set_loop_instance(loop):
    global loop_instance
    loop_instance = loop
    print(f"[DEBUG] Loop instance set: {loop is not None}")

class StartLoopRequest(BaseModel):
    max_iterations: Optional[int] = 1
    custom_prompt: Optional[str] = None
    dry_run: Optional[bool] = False

class StopLoopRequest(BaseModel):
    mode: str = "graceful"

class ApprovalRequest(BaseModel):
    proposal_id: str
    approved: bool

class ImportPlanRequest(BaseModel):
    data: dict

class CreateToolRequest(BaseModel):
    description: str
    tool_name: Optional[str] = None

@router.post("/start")
async def start_loop(request: StartLoopRequest):
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    if request.max_iterations and request.max_iterations > 0:
        loop_instance.controller.max_iterations = request.max_iterations
    loop_instance.custom_focus = request.custom_prompt if request.custom_prompt else None
    loop_instance.dry_run = request.dry_run if request.dry_run else False
    loop_instance.continuous_mode = False  # Single run
    
    result = await loop_instance.start_loop()
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@router.post("/start-continuous")
async def start_continuous():
    """Start continuous improvement mode - runs until stopped"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    if loop_instance.state.status.value == "running":
        raise HTTPException(status_code=409, detail="Loop already running")
    
    loop_instance.continuous_mode = True
    result = await loop_instance.start_loop()
    
    return {"success": True, "mode": "continuous", "message": "Continuous mode started"}

@router.post("/stop")
async def stop_loop(request: StopLoopRequest):
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    # Check if in critical section
    if request.mode == "immediate" and hasattr(loop_instance, 'in_critical_section'):
        if loop_instance.in_critical_section:
            return {"success": False, "message": "In critical section, waiting for safe stop point"}
    
    result = await loop_instance.stop_loop(request.mode)
    return result

@router.post("/approve")
async def approve_proposal(request: ApprovalRequest):
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    # Use lock to prevent concurrent approval conflicts
    async with loop_instance.approval_lock:
        if request.approved:
            success = loop_instance.approve_proposal(request.proposal_id)
        else:
            success = loop_instance.reject_proposal(request.proposal_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Proposal not found or already processed")
    
    return {"success": True, "proposal_id": request.proposal_id, "approved": request.approved}

@router.get("/status")
async def get_status():
    """Get current loop status - returns default if not initialized"""
    if not loop_instance:
        return {
            "status": "not_initialized",
            "running": False,
            "iteration": 0,
            "maxIterations": 10,
            "logs": [],
            "dry_run": False,
            "preview_count": 0,
            "pending_approvals": {},
            "evolution_mode": False,
            "message": "Self-improvement loop not initialized. Check server logs."
        }
    
    # Non-blocking status retrieval
    try:
        status = loop_instance.get_status()
        status['pending_approvals'] = loop_instance.pending_approvals
        status['evolution_mode'] = loop_instance.evolution_bridge.should_use_evolution()
        return status
    except Exception as e:
        return {
            "status": "error",
            "running": False,
            "iteration": 0,
            "maxIterations": 10,
            "logs": [],
            "error": str(e)
        }

@router.post("/clear-logs")
async def clear_logs():
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    loop_instance.logs = []
    return {"success": True}

@router.get("/previews")
async def get_previews():
    if not loop_instance:
        return {"previews": []}
    return {"previews": loop_instance.preview_proposals}

@router.get("/history")
async def get_history(limit: int = 50):
    if not loop_instance:
        return {"history": []}
    history = loop_instance.plan_history.get_history(limit)
    return {"history": history}

@router.get("/analytics")
async def get_analytics(days: int = 30):
    if not loop_instance:
        return {
            "total_attempts": 0,
            "successful_attempts": 0,
            "success_rate": 0,
            "avg_duration_seconds": 0,
            "risk_distribution": {},
            "common_errors": [],
            "daily_trend": []
        }
    stats = loop_instance.analytics.get_stats(days)
    return stats

@router.get("/logs")
async def get_logs():
    if not loop_instance:
        return {"logs": []}
    return {"logs": loop_instance.logs}

@router.get("/debug/llm-test")
async def test_llm():
    """Test if LLM is responding"""
    if not loop_instance:
        return {"error": "Loop not initialized"}
    
    try:
        from core.logging_system import get_logger
        logger = get_logger("debug")
        
        # Test simple call
        logger.info(f"Testing LLM: {loop_instance.llm_client.model}")
        response = loop_instance.llm_client._call_llm("Say 'test'", temperature=0.1, expect_json=False)
        
        if response:
            return {
                "success": True,
                "model": loop_instance.llm_client.model,
                "response_length": len(response),
                "response_preview": response[:200]
            }
        else:
            return {
                "success": False,
                "model": loop_instance.llm_client.model,
                "error": "No response from LLM"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@router.post("/export/{proposal_id}")
async def export_proposal(proposal_id: str):
    """Export proposal as JSON for sharing"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    proposal = None
    for preview in loop_instance.preview_proposals:
        if f"proposal_{preview['iteration']:03d}" == proposal_id:
            proposal = preview
            break
    
    if not proposal and proposal_id in loop_instance.pending_approvals:
        proposal = loop_instance.pending_approvals[proposal_id]
    
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    
    return {
        "proposal_id": proposal_id,
        "exported_at": datetime.now().isoformat(),
        "data": proposal
    }

@router.post("/import")
async def import_plan(request: ImportPlanRequest):
    """Import and validate exported plan"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    try:
        if 'proposal' not in request.data:
            raise HTTPException(status_code=400, detail="Invalid plan format")
        
        proposal = request.data['proposal']
        required = ['description', 'files_changed', 'patch']
        
        for field in required:
            if field not in proposal:
                raise HTTPException(status_code=400, detail=f"Missing {field}")
        
        # Validate files against protected files
        from core.immutable_brain_stem import BrainStem
        for file_path in proposal['files_changed']:
            result = BrainStem.validate_path(file_path)
            if not result.is_valid:
                raise HTTPException(status_code=400, detail=f"Invalid file path: {result.reason}")
        
        # Validate patch format
        patch = proposal.get('patch', '')
        if not patch or not (
            patch.startswith('FILE_REPLACE:') or
            '---' in patch or
            '+++' in patch
        ):
            raise HTTPException(status_code=400, detail="Invalid patch format")
        
        proposal_id = f"imported_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        loop_instance.pending_approvals[proposal_id] = {
            "proposal": proposal,
            "risk_score": request.data.get('risk_score'),
            "approved": None
        }
        
        loop_instance.add_log("info", f"Plan imported: {proposal['description']}", proposal_id)
        
        return {
            "success": True,
            "proposal_id": proposal_id,
            "message": "Plan imported. Review and approve to execute."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/history/{plan_id}")
async def get_plan_details(plan_id: str):
    """Get detailed plan information"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    plan = loop_instance.plan_history.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    return plan

@router.post("/rollback/{plan_id}")
async def rollback_plan(plan_id: str):
    """Rollback to state before plan was applied"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    # Check if loop is running
    if loop_instance.state.status.value == "running":
        raise HTTPException(status_code=409, detail="Cannot rollback while loop is running. Stop the loop first.")
    
    plan = loop_instance.plan_history.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    backup_id = plan.get('backup_id', '')
    if not backup_id:
        raise HTTPException(status_code=400, detail="No backup available for this plan")
    
    try:
        from updater.atomic_applier import AtomicApplier
        applier = AtomicApplier(repo_path=".")
        
        if backup_id.startswith('manual_backup_'):
            # Manual backup - find .bak file
            update_id = backup_id.replace('manual_backup_', '')
            from pathlib import Path
            backup_dir = Path("backups")
            
            # Find matching backup file
            backup_files = list(backup_dir.glob(f"*.{update_id}.bak"))
            if not backup_files:
                raise HTTPException(status_code=404, detail="Backup file not found")
            
            success = applier.rollback_manual_backup(backup_files[0].name)
        else:
            # Git-based backup
            update_id = backup_id.replace('backup_', '')
            success = applier.rollback(update_id)
        
        if success:
            loop_instance.add_log("info", f"Rolled back plan {plan_id}")
            return {"success": True, "message": f"Rolled back to {backup_id}"}
        else:
            raise HTTPException(status_code=500, detail="Rollback failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rollback error: {str(e)}")

@router.post("/evolution/enable")
async def enable_evolution():
    """Enable evolution mode"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    loop_instance.set_evolution_mode(True)
    return {"status": "enabled"}

@router.post("/evolution/disable")
async def disable_evolution():
    """Disable evolution mode"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    loop_instance.set_evolution_mode(False)
    return {"status": "disabled"}

@router.get("/evolution/insights")
async def get_insights():
    """Get self-reflection insights"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    insights = loop_instance.evolution_bridge.get_self_reflection()
    return {"insights": [
        {
            "category": i.category,
            "severity": i.severity,
            "description": i.description,
            "affected_files": i.affected_files,
            "suggested_action": i.suggested_action
        }
        for i in insights[:10]
    ]}

@router.get("/evolution/budget")
async def get_budget():
    """Get growth budget status"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    budget = loop_instance.evolution_bridge.get_growth_budget()
    return {
        "current_cycle": budget.current_cycle,
        "new_tools_created": budget.new_tools_created,
        "structural_changes_made": budget.structural_changes_made,
        "can_create_tool": budget.can_create_tool(),
        "can_structural_change": budget.can_structural_change()
    }

@router.get("/evolution/capability-gaps")
async def get_capability_gaps():
    """Get detected capability gaps"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    # Build capability graph
    from core.capability_mapper import CapabilityMapper
    from core.gap_tracker import GapTracker
    
    mapper = CapabilityMapper()
    mapper.build_capability_graph()
    
    tracker = GapTracker()
    summary = tracker.get_summary()
    
    return {
        "total_capabilities": len(mapper.capability_graph),
        "capability_graph": mapper.capability_graph,
        "gaps": summary
    }

@router.post("/evolution/detect-gap")
async def detect_gap(task: str, error: str = ""):
    """Manually trigger gap detection for a task"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    
    from core.capability_mapper import CapabilityMapper
    from core.gap_detector import GapDetector
    from core.gap_tracker import GapTracker
    
    mapper = CapabilityMapper()
    mapper.build_capability_graph()
    
    detector = GapDetector(mapper)
    gap = detector.analyze_failed_task(task, error)
    
    if gap:
        tracker = GapTracker()
        tracker.record_gap(gap)
        
        return {
            "gap_detected": True,
            "capability": gap.capability,
            "confidence": gap.confidence,
            "reason": gap.reason,
            "suggested_library": gap.suggested_library,
            "domain": gap.domain
        }
    
    return {"gap_detected": False}

@router.post("/evolution/promote/{tool_name}")
async def promote_tool(tool_name: str):
    """Promote experimental tool to stable"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")
    success, msg = loop_instance.evolution_bridge.promote_experimental_tool(tool_name)
    return {"success": success, "message": msg}

@router.post("/tools/create")
async def create_tool_from_description(
    payload: Optional[CreateToolRequest] = Body(default=None),
    description: Optional[str] = None,
    tool_name: Optional[str] = None
):
    """Create new tool from user description - LLM generates code"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")

    effective_description = payload.description if payload else description
    effective_tool_name = payload.tool_name if payload and payload.tool_name else tool_name
    if not effective_description:
        raise HTTPException(status_code=422, detail="description is required")
    
    from core.tool_creation_flow import ToolCreationFlow
    from core.capability_graph import CapabilityGraph
    from core.expansion_mode import ExpansionMode
    from core.growth_budget import GrowthBudget
    
    # Check growth budget (soft check for user-triggered create endpoint)
    budget = GrowthBudget()
    budget_exhausted = not budget.can_create_tool()
    
    # Initialize components
    capability_graph = CapabilityGraph()
    # Tool creation endpoint is explicitly for experimental tool scaffolding.
    expansion_mode = ExpansionMode(enabled=True)
    tool_creation = ToolCreationFlow(capability_graph, expansion_mode, budget)
    
    # Create tool
    try:
        success, msg = tool_creation.create_new_tool(
            effective_description,
            loop_instance.llm_client,
            bypass_budget=True,
            preferred_tool_name=effective_tool_name,
        )
        
        if success:
            import re
            from pathlib import Path

            # Expected message format: "Experimental tool created: ToolName"
            parsed_name = None
            name_match = re.search(r"Experimental tool created:\s*([A-Za-z0-9_]+)", msg or "")
            if name_match:
                parsed_name = name_match.group(1)

            resolved_tool_name = parsed_name or (effective_tool_name.strip() if effective_tool_name else None)
            tool_file = f"tools/experimental/{resolved_tool_name}.py" if resolved_tool_name else None
            test_file = f"tests/experimental/test_{resolved_tool_name}.py" if resolved_tool_name else None

            pending_id = None
            pending_manager = getattr(loop_instance, "pending_tools_manager", None)
            if pending_manager and tool_file and Path(tool_file).exists():
                valid, contract_error = pending_manager.validate_tool_file_contract(tool_file)
                if not valid:
                    # Clean up malformed generated artifacts instead of queueing broken tools.
                    try:
                        Path(tool_file).unlink(missing_ok=True)
                        if test_file:
                            Path(test_file).unlink(missing_ok=True)
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=400,
                        detail=f"Generated tool failed contract validation: {contract_error}",
                    )

                # Ensure capability metadata can be extracted before queueing.
                try:
                    from tools.capability_extractor import CapabilityExtractor
                    extracted = CapabilityExtractor().extract_from_file(tool_file)
                    if not extracted or not extracted.get("operations"):
                        try:
                            Path(tool_file).unlink(missing_ok=True)
                            if test_file:
                                Path(test_file).unlink(missing_ok=True)
                        except Exception:
                            pass
                        raise HTTPException(
                            status_code=400,
                            detail="Generated tool failed capability extraction validation",
                        )
                except Exception as e:
                    try:
                        Path(tool_file).unlink(missing_ok=True)
                        if test_file:
                            Path(test_file).unlink(missing_ok=True)
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=400,
                        detail=f"Generated tool failed capability extraction validation: {e}",
                    )

                pending_id = pending_manager.add_pending_tool({
                    "tool_file": tool_file.replace("\\", "/"),
                    "test_file": test_file.replace("\\", "/") if test_file else None,
                    "description": effective_description,
                    "risk_score": "low",
                    "is_new_tool": True,
                })

            return {
                "success": True,
                "message": msg,
                "tool_name": resolved_tool_name,
                "file_path": tool_file.replace("\\", "/") if tool_file else None,
                "status": "pending_approval" if pending_id else "experimental",
                "pending_tool_id": pending_id,
                "note": "Tool created in experimental namespace and queued for approval." if pending_id else "Tool created in experimental namespace. Pending manager unavailable.",
                "budget_warning": "Growth budget exhausted; user-initiated create allowed by override." if budget_exhausted else None
            }
        else:
            raise HTTPException(status_code=400, detail=msg)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tool creation failed: {str(e)}")
