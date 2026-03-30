"""
Skills API - Manage pending skill approvals
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import json

router = APIRouter(prefix="/api/skills", tags=["skills"])

# Global instances (set by server.py)
_pending_skills_manager = None
_skills_registry = None

def set_skills_dependencies(pending_manager, registry):
    global _pending_skills_manager, _skills_registry
    _pending_skills_manager = pending_manager
    _skills_registry = registry

class ApproveSkillRequest(BaseModel):
    reason: Optional[str] = None

class RejectSkillRequest(BaseModel):
    reason: str

@router.get("/pending")
async def get_pending_skills():
    """Get all pending skill approvals"""
    if not _pending_skills_manager:
        raise HTTPException(status_code=503, detail="Skills manager not initialized")
    
    pending = _pending_skills_manager.get_pending_skills()
    return {"success": True, "pending_skills": pending}

@router.get("/pending/{skill_id}")
async def get_skill_details(skill_id: str):
    """Get details of a pending skill"""
    if not _pending_skills_manager:
        raise HTTPException(status_code=503, detail="Skills manager not initialized")
    
    skill = _pending_skills_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return {"success": True, "skill": skill}

@router.post("/pending/{skill_id}/approve")
async def approve_skill(skill_id: str, request: ApproveSkillRequest):
    """Approve and create a pending skill"""
    if not _pending_skills_manager:
        raise HTTPException(status_code=503, detail="Skills manager not initialized")
    
    skill = _pending_skills_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    # Create skill directory and files
    skill_name = skill["skill_name"]
    skill_dir = Path("skills") / skill_name
    
    try:
        skill_dir.mkdir(parents=True, exist_ok=True)
        
        # Write skill.json
        skill_json_path = skill_dir / "skill.json"
        skill_json_path.write_text(json.dumps(skill["skill_definition"], indent=2))
        
        # Write SKILL.md
        skill_md_path = skill_dir / "SKILL.md"
        instructions = skill.get("instructions", f"# {skill_name}\n\nSkill instructions go here.")
        skill_md_path.write_text(instructions)
        
        # Mark as approved
        _pending_skills_manager.approve_skill(skill_id)
        
        # Reload skills registry if available
        if _skills_registry:
            from application.services.skill_loader import load_skills
            load_skills(_skills_registry, "skills")
        
        return {
            "success": True,
            "message": f"Skill {skill_name} approved and created",
            "skill_path": str(skill_dir)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create skill: {str(e)}")

@router.post("/pending/{skill_id}/reject")
async def reject_skill(skill_id: str, request: RejectSkillRequest):
    """Reject a pending skill"""
    if not _pending_skills_manager:
        raise HTTPException(status_code=503, detail="Skills manager not initialized")
    
    success = _pending_skills_manager.reject_skill(skill_id, request.reason)
    if not success:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return {"success": True, "message": "Skill rejected"}
