"""
Self-Improvement Loop API Endpoints
"""
import json
import logging
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

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
    target_skill: Optional[str] = None
    target_category: Optional[str] = None
    gap_type: Optional[str] = None
    suggested_action: Optional[str] = None
    reasons: Optional[list[str]] = None
    example_tasks: Optional[list[str]] = None
    example_errors: Optional[list[str]] = None


class ToolSuggestionResponse(BaseModel):
    action: str = "create_tool"  # create_tool | evolve_tool | improve_skill_routing | improve_skill_workflow
    tool_name: str
    description: str
    rationale: str
    source: str  # gap_tracker | llm_fallback
    confidence: float = 0.7
    suggested_library: Optional[str] = None
    capability_gap: Optional[str] = None
    target_tool: Optional[str] = None
    target_skill: Optional[str] = None
    reasons: Optional[list[str]] = None
    example_tasks: Optional[list[str]] = None
    example_errors: Optional[list[str]] = None
    gap_type: Optional[str] = None
    suggested_action: Optional[str] = None
    registry_snapshot_tools: Optional[int] = None

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
    description: Optional[str] = None,
    tool_name: Optional[str] = None,
    target_skill: Optional[str] = None,
    target_category: Optional[str] = None,
    payload: Optional[CreateToolRequest] = Body(default=None)
):
    """Create new tool from user description - LLM generates code"""
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")

    # Prioritize payload, then query params
    effective_description = payload.description if payload else description
    effective_tool_name = payload.tool_name if payload and payload.tool_name else tool_name
    effective_target_skill = payload.target_skill if payload and payload.target_skill else target_skill
    effective_target_category = payload.target_category if payload and payload.target_category else target_category
    effective_gap_type = payload.gap_type if payload and payload.gap_type else None
    effective_suggested_action = payload.suggested_action if payload and payload.suggested_action else None
    effective_reasons = payload.reasons if payload and payload.reasons else []
    effective_example_tasks = payload.example_tasks if payload and payload.example_tasks else []
    effective_example_errors = payload.example_errors if payload and payload.example_errors else []
    if not effective_description:
        raise HTTPException(status_code=422, detail="description is required")

    # Guardrail: if the user explicitly requests a tool name that already exists,
    # do not create a duplicate. Prefer tool evolution.
    if effective_tool_name:
        try:
            from core.tool_registry_manager import ToolRegistryManager

            def _norm(name: str) -> str:
                return "".join(ch for ch in (name or "").lower() if ch.isalnum())

            registry = ToolRegistryManager().get_registry() or {}
            tools = (registry.get("tools") or {}) if isinstance(registry, dict) else {}
            existing_name = None
            for name in tools.keys():
                if _norm(name) == _norm(effective_tool_name):
                    existing_name = name
                    break
            if existing_name:
                return {
                    "success": False,
                    "status": "already_exists",
                    "action": "evolve_tool",
                    "target_tool": existing_name,
                    "message": f"Tool '{existing_name}' already exists; use evolution instead of creating a duplicate.",
                }
        except Exception:
            pass
    
    from core.tool_creation.flow import ToolCreationOrchestrator
    from core.capability_graph import CapabilityGraph
    from core.expansion_mode import ExpansionMode
    from core.skills import SkillRegistry
    
    # Initialize components
    capability_graph = CapabilityGraph()
    expansion_mode = ExpansionMode(enabled=True)
    
    # Initialize skill registry
    skill_registry = SkillRegistry()
    skill_registry.load_all()
    
    # Auto-detect skill if not provided
    if not effective_target_skill:
        try:
            from core.skills import SkillSelector
            selector = SkillSelector()
            selection = selector.select_skill(effective_description, skill_registry, loop_instance.llm_client)
            
            if selection.matched and selection.confidence >= 0.4:
                effective_target_skill = selection.skill_name
                effective_target_category = selection.category
                logger.info(f"[SKILL-AWARE] Auto-detected skill: {effective_target_skill} (confidence: {selection.confidence:.2f})")
        except Exception as e:
            logger.warning(f"[SKILL-AWARE] Skill auto-detection failed: {e}")
    
    # Create orchestrator with skill awareness
    tool_creation = ToolCreationOrchestrator(
        capability_graph, 
        expansion_mode,
        skill_registry=skill_registry,
        llm_client=loop_instance.llm_client
    )
    skill_context = {
        "target_skill": effective_target_skill,
        "target_category": effective_target_category,
        "gap_type": effective_gap_type,
        "suggested_action": effective_suggested_action,
        "reasons": effective_reasons,
        "example_tasks": effective_example_tasks,
        "example_errors": effective_example_errors,
    }
    if effective_target_skill:
        try:
            from core.skills import SkillRegistry

            skill_registry = SkillRegistry()
            skill_registry.load_all()
            skill = skill_registry.get(effective_target_skill)
            if skill:
                skill_context.update(
                    {
                        "output_types": list(skill.output_types),
                        "verification_mode": skill.verification_mode,
                        "ui_renderer": skill.ui_renderer,
                        "preferred_tools": list(skill.preferred_tools),
                        "required_tools": list(skill.required_tools),
                        "input_types": list(skill.input_types),
                        "risk_level": skill.risk_level,
                        "fallback_strategy": skill.fallback_strategy,
                        "skill_constraints": [],  # Can be populated from SKILL.md if needed
                    }
                )
        except Exception:
            pass
    
    # Create tool
    try:
        success, msg = tool_creation.create_tool(
            effective_description,
            loop_instance.llm_client,
            preferred_tool_name=effective_tool_name,
            skill_context=skill_context,
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

                pending_id = pending_manager.add_pending_tool({
                    "tool_file": tool_file.replace("\\", "/"),
                    "test_file": test_file.replace("\\", "/") if test_file else None,
                    "description": effective_description,
                    "target_skill": effective_target_skill,
                    "target_category": effective_target_category,
                    "skill_updates": getattr(tool_creation, "last_skill_updates", []),
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
                "target_skill": effective_target_skill,
                "target_category": effective_target_category,
                "skill_updates": getattr(tool_creation, "last_skill_updates", []),
                "missing_services": tool_creation.last_spec.get('missing_services', []) if hasattr(tool_creation, 'last_spec') else [],
                "note": "Tool created in experimental namespace and queued for approval." if pending_id else "Tool created in experimental namespace. Pending manager unavailable."
            }
        else:
            raise HTTPException(status_code=400, detail=msg)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tool creation failed: {str(e)}")


@router.get("/tools/suggest", response_model=ToolSuggestionResponse)
async def suggest_next_tool(skip: int = 0):
    """
    Suggest the next most important tool for CUA to create (self-directed growth),
    using persistent capability gaps when available, otherwise an LLM-based fallback.

    This endpoint only proposes; actual creation still requires the user to call /tools/create
    and then approve the generated tool in the pending tools workflow.
    """
    if not loop_instance:
        raise HTTPException(status_code=503, detail="Loop not initialized")

    # Capability-aware: prefer evolving/fixing existing incomplete tools before proposing new ones.
    from pathlib import Path

    def _norm(name: str) -> str:
        return "".join(ch for ch in (name or "").lower() if ch.isalnum())

    registry_snapshot = {}
    try:
        from core.tool_registry_manager import ToolRegistryManager
        registry_snapshot = ToolRegistryManager().get_registry() or {}
    except Exception:
        registry_snapshot = {}

    registry_tools = (registry_snapshot or {}).get("tools", {}) or {}
    registry_tool_names = set(registry_tools.keys())
    registry_tool_norms = {_norm(n): n for n in registry_tool_names}

    incomplete_candidates = []
    for tool_name, tool_entry in registry_tools.items():
        source_file = str((tool_entry or {}).get("source_file") or "")
        if not source_file:
            continue

        path = Path(source_file)
        if not path.exists():
            path = Path(source_file.replace("\\", "/"))
        if not path.exists():
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        score = 0
        if "keep sandbox-safe default" in text:
            score += 1
        if "\"status\": \"stub\"" in text or "\"status\":\"stub\"" in text or "'status': 'stub'" in text:
            score += 1
        if "return {\"operation\":" in text and "\"received\"" in text:
            score += 1
        if "(BaseTool)" in text and "from tools.tool_interface import BaseTool" not in text:
            score += 1

        if score:
            incomplete_candidates.append(
                {"tool_name": tool_name, "score": score, "source_file": str(path).replace("\\", "/")}
            )

    incomplete_candidates.sort(key=lambda x: x["score"], reverse=True)
    if incomplete_candidates:
        # Apply skip offset for cycling
        idx = skip % len(incomplete_candidates)
        top = incomplete_candidates[idx]
        tool = top["tool_name"]
        return ToolSuggestionResponse(
            action="evolve_tool",
            target_tool=tool,
            tool_name=tool,
            description=(
                f"Improve the existing tool '{tool}' (currently incomplete/stub). "
                "Fill in handler logic, fix imports/contract issues, and persist results via self.services.storage."
            ),
            rationale=(
                f"'{tool}' already exists in the registry but looks incomplete (stub markers detected in {top['source_file']}). "
                "Evolving/fixing it is higher leverage than creating a duplicate tool."
            ),
            source="registry_scan",
            confidence=0.85,
            registry_snapshot_tools=len(registry_tool_names),
        )

    # Prefer actionable persistent gaps.
    from core.gap_tracker import GapTracker
    tracker = GapTracker()
    actionable = tracker.get_prioritized_gaps()

    def _camel(name: str) -> str:
        parts = [p for p in (name or "").replace("-", "_").split("_") if p]
        return "".join((p[:1].upper() + p[1:]) for p in parts)

    if actionable:
        # Apply skip offset for cycling through suggestions
        total = len(incomplete_candidates) + len(actionable)
        gap_skip = max(0, skip - len(incomplete_candidates))
        idx = gap_skip % len(actionable)
        top = actionable[idx]
        gap_name = top.capability
        suggested_tool_name = f"{_camel(gap_name)}Tool"
        base_description = (
            f"Add a new tool that provides the missing capability '{gap_name}'. "
            f"It should be safe-by-default and use ToolServices for storage/logging/time/ids. "
            f"Observed reasons: {', '.join((top.reasons or [])[:3])}."
        )

        if top.suggested_action in {"improve_skill_routing", "improve_skill_workflow"}:
            target_skill = top.selected_skill or top.selected_category or "unknown"
            return ToolSuggestionResponse(
                action=top.suggested_action,
                tool_name=f"{_camel(target_skill)}SkillRouting",
                description=(
                    f"Improve routing and workflow behavior for skill/category '{target_skill}'. "
                    f"Observed gap type: {top.gap_type}. Reasons: {', '.join((top.reasons or [])[:3])}."
                ),
                rationale=(
                    f"The highest-priority actionable gap is not a missing tool. "
                    f"It indicates weak skill matching or workflow execution for '{target_skill}'."
                ),
                source="gap_tracker",
                confidence=min(0.95, float(top.confidence_avg or 0.75)),
                capability_gap=gap_name,
                target_skill=top.selected_skill,
                reasons=list((top.reasons or [])[:3]),
                example_tasks=list((top.example_tasks or [])[:3]),
                example_errors=list((top.example_errors or [])[:3]),
                gap_type=top.gap_type,
                suggested_action=top.suggested_action,
                registry_snapshot_tools=len(registry_tool_names),
            )

        # Surface cheaper resolution paths before suggesting tool creation
        effective_action = top.resolution_action or top.suggested_action or "create_tool"
        if effective_action in {"reroute", "mcp", "api_wrap"}:
            resolution_target = top.resolution_target or ""
            action_labels = {
                "reroute": "reroute_existing_tool",
                "mcp": "use_mcp_server",
                "api_wrap": "create_api_wrapper",
            }
            return ToolSuggestionResponse(
                action=action_labels.get(effective_action, effective_action),
                target_tool=resolution_target or top.target_tool,
                tool_name=resolution_target or _camel(gap_name) + "Tool",
                description=(
                    f"Resolution for '{gap_name}': {effective_action} via '{resolution_target}'. "
                    f"Notes: {'; '.join((top.resolution_notes or [])[:2])}."
                ),
                rationale=(
                    f"A cheaper path than tool creation was found for '{gap_name}'. "
                    f"Use '{effective_action}' before creating a new tool."
                ),
                source="gap_tracker",
                confidence=min(0.95, float(top.confidence_avg or 0.75)),
                capability_gap=gap_name,
                target_skill=top.selected_skill,
                reasons=list((top.reasons or [])[:3]),
                example_tasks=list((top.example_tasks or [])[:3]),
                example_errors=list((top.example_errors or [])[:3]),
                gap_type=top.gap_type,
                suggested_action=effective_action,
                registry_snapshot_tools=len(registry_tool_names),
            )

        # Let the LLM refine tool name + description into a better creation prompt.
        try:
            prompt = f"""You are helping an autonomous agent system (CUA) decide what tool to create next.

We detected a persistent capability gap:
- capability: {gap_name}
- occurrences: {top.occurrence_count}
- average_confidence: {top.confidence_avg}
- suggested_library: {top.suggested_library}
- reasons: {top.reasons[:5] if top.reasons else []}

Write a tool creation prompt (1-2 paragraphs) that can be sent to the tool creation engine.
Constraints:
- Tool should be a "thin tool" using self.services.* (storage/logging/http/fs/json/shell/time/ids/call_tool etc.).
- Prefer existing services; if a new service is required, name it explicitly as self.services.<name>.<method>.
- Include clear capabilities (operations) and required parameters.
- Keep it safe and deterministic (input validation, no uncontrolled filesystem/network).
Return JSON only:
{{"tool_name": "...", "description": "...", "rationale": "...", "confidence": 0.0}}
"""
            raw = loop_instance.llm_client._call_llm(prompt, temperature=0.2, max_tokens=700, expect_json=True)
            parsed = loop_instance.llm_client._extract_json(raw) if raw else None
            if isinstance(parsed, dict) and parsed.get("description"):
                return ToolSuggestionResponse(
                    action="create_tool",
                    tool_name=str(parsed.get("tool_name") or suggested_tool_name),
                    description=str(parsed.get("description") or base_description),
                    rationale=str(parsed.get("rationale") or f"Persistent capability gap: {gap_name}"),
                    source="gap_tracker",
                    confidence=float(parsed.get("confidence") or 0.75),
                    suggested_library=top.suggested_library,
                    capability_gap=gap_name,
                    target_skill=top.selected_skill,
                    reasons=list((top.reasons or [])[:3]),
                    example_tasks=list((top.example_tasks or [])[:3]),
                    example_errors=list((top.example_errors or [])[:3]),
                    gap_type=top.gap_type,
                    suggested_action=top.suggested_action,
                    registry_snapshot_tools=len(registry_tool_names),
                )
        except Exception:
            pass

        return ToolSuggestionResponse(
            action="create_tool",
            tool_name=suggested_tool_name,
            description=base_description,
            rationale=f"Persistent capability gap: {gap_name} ({top.occurrence_count}x, conf {top.confidence_avg:.2f})",
            source="gap_tracker",
            confidence=min(0.95, float(top.confidence_avg or 0.75)),
            suggested_library=top.suggested_library,
            capability_gap=gap_name,
            target_skill=top.selected_skill,
            reasons=list((top.reasons or [])[:3]),
            example_tasks=list((top.example_tasks or [])[:3]),
            example_errors=list((top.example_errors or [])[:3]),
            gap_type=top.gap_type,
            suggested_action=top.suggested_action,
            registry_snapshot_tools=len(registry_tool_names),
        )

    # Capability-aware LLM fallback when no actionable gaps are recorded yet.
    try:
        existing_caps_text = ""
        try:
            from core.tool_registry_manager import ToolRegistryManager
            existing_caps_text = ToolRegistryManager().get_all_capabilities_text()
        except Exception:
            existing_caps_text = ""
        
        # Load skills to understand domains
        skill_domains = {}
        try:
            from core.skills import SkillRegistry
            skill_reg = SkillRegistry()
            skill_reg.load_all()
            for skill in skill_reg.list_all():
                skill_domains[skill.category] = {
                    "skill_name": skill.name,
                    "preferred_tools": list(skill.preferred_tools),
                    "description": skill.description
                }
        except Exception:
            pass

        skip_hint = f" (suggestion #{skip + 1} — pick a DIFFERENT tool than previous suggestions)" if skip > 0 else ""
        prompt = f"""You are helping CUA (a self-improving agent) decide what tool to create next.{skip_hint}

Goal: improve autonomy/automation with user approval gates.

SKILL DOMAINS (tools MUST serve an existing skill):
{json.dumps(skill_domains, indent=2)}

Current tool registry (names + operations):
{existing_caps_text or "(registry unavailable)"}

Pick ONE high-leverage tool that serves an existing skill domain.
Specify which skill it serves and what domain-specific operations it provides.

If a closely-related tool already exists, set action="evolve_tool" and target_tool to that existing tool name (do NOT propose a new tool).

Constraints:
- Thin tool using self.services.*
- Must have 2-4 clear capabilities (operations)
- Must specify parameters for each operation
- Prefer writing to data/ or output/ via storage service
- Must align with one of the skill domains above

Return JSON only:
{{
  "action": "create_tool|evolve_tool",
  "target_tool": "",
  "target_skill": "web_research|computer_automation|code_workspace",
  "target_category": "web|computer|development",
  "tool_name": "...",
  "description": "...",
  "rationale": "...",
  "confidence": 0.0
}}
"""
        raw = loop_instance.llm_client._call_llm(prompt, temperature=0.3, max_tokens=700, expect_json=True)
        parsed = loop_instance.llm_client._extract_json(raw) if raw else None
        if isinstance(parsed, dict) and parsed.get("description"):
            action = str(parsed.get("action") or "create_tool")
            tool_name = str(parsed.get("tool_name") or "BenchmarkRunnerTool")
            target_tool = str(parsed.get("target_tool") or "").strip() or None
            target_skill = str(parsed.get("target_skill") or "").strip() or None
            target_category = str(parsed.get("target_category") or "").strip() or None

            # Enforce registry-awareness even if the model ignores the instructions.
            if action == "create_tool":
                existing = registry_tool_norms.get(_norm(tool_name))
                if existing:
                    action = "evolve_tool"
                    target_tool = existing
                    tool_name = existing

            return ToolSuggestionResponse(
                action=action if action in {"create_tool", "evolve_tool"} else "create_tool",
                target_tool=target_tool,
                tool_name=tool_name,
                description=str(parsed.get("description")),
                rationale=str(parsed.get("rationale") or "Capability-aware suggestion based on current registry snapshot."),
                source="llm_fallback",
                confidence=float(parsed.get("confidence") or 0.65),
                target_skill=target_skill,
                target_category=target_category,
                registry_snapshot_tools=len(registry_tool_names),
            )
    except Exception:
        pass

    return ToolSuggestionResponse(
        action="create_tool",
        tool_name="BenchmarkRunnerTool",
        description=(
            "Create a tool that runs a small internal benchmark suite for CUA (a list of tasks/prompts), "
            "records results (pass/fail, latency, tools used) using storage, and produces a summary report. "
            "Include capabilities to add/remove benchmark cases and to run the suite."
        ),
        rationale="No capability gaps recorded yet; an evaluation/benchmark tool helps self-improvement become measurable.",
        source="llm_fallback",
        confidence=0.6,
        registry_snapshot_tools=len(registry_tool_names),
    )
