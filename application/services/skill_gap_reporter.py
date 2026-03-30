"""
Skill Gap Reporter - Reports missing skills for manual creation
"""
from typing import Optional
from application.managers.pending_skills_manager import PendingSkillsManager
import logging

logger = logging.getLogger(__name__)

class SkillGapReporter:
    def __init__(self, pending_skills_manager: PendingSkillsManager):
        self.pending_manager = pending_skills_manager
    
    def report_missing_skill(self, gap_data: dict) -> Optional[str]:
        """Report a missing skill gap for manual creation"""
        
        # Extract skill info from gap
        skill_name = gap_data.get("selected_skill") or gap_data.get("selected_category")
        if not skill_name:
            logger.warning("Cannot report skill gap without skill name")
            return None
        
        # Check if already pending
        if self.pending_manager.has_pending_skill(skill_name):
            logger.info(f"Skill {skill_name} already pending approval")
            return None
        
        # Build skill definition from gap context
        category = gap_data.get("selected_category", "general")
        example_tasks = gap_data.get("example_tasks", [])
        
        skill_definition = {
            "name": skill_name,
            "category": category,
            "description": f"Skill for {category} tasks",
            "trigger_examples": example_tasks if isinstance(example_tasks, list) else [example_tasks] if example_tasks else [],
            "preferred_tools": [],
            "required_tools": [],
            "preferred_connectors": [],
            "input_types": ["query", "task"],
            "output_types": ["result"],
            "verification_mode": "basic",
            "risk_level": "medium",
            "ui_renderer": "default",
            "fallback_strategy": "direct_tool_routing"
        }
        
        # Build instructions template
        instructions = f"""# {skill_name}

## Description
This skill handles {category} related tasks.

## Capabilities
- Handle {category} requests
- Route to appropriate tools
- Verify results

## Example Tasks
{chr(10).join(f"- {task}" for task in (example_tasks if isinstance(example_tasks, list) else [example_tasks]) if task)}

## Instructions
Add detailed instructions for this skill here.
"""
        
        # Build context
        context = f"""Gap Type: {gap_data.get('gap_type', 'unknown')}
Reason: {gap_data.get('reasons', ['No reason provided'])[0] if gap_data.get('reasons') else 'No reason provided'}
Confidence: {gap_data.get('confidence_avg', 0.0)}
Example Errors: {', '.join(gap_data.get('example_errors', [])[:3])}
"""
        
        # Add to pending queue
        skill_id = self.pending_manager.add_pending_skill(
            skill_name=skill_name,
            skill_definition=skill_definition,
            instructions=instructions,
            context=context,
            requested_by="gap_detection"
        )
        
        logger.info(f"Reported missing skill '{skill_name}' for approval (ID: {skill_id})")
        return skill_id
    
    def process_capability_gaps(self, capability_gaps: dict) -> list:
        """Process all capability gaps and report missing skills"""
        reported = []
        
        for gap_key, gap_data in capability_gaps.items():
            gap_type = gap_data.get("gap_type")
            suggested_action = gap_data.get("suggested_action")
            
            # Only report skill routing issues
            if gap_type in ["no_matching_skill", "actionable_request_no_tool_call", 
                           "matched_skill_missing_workflow", "matched_skill_execution_failed"]:
                if suggested_action in ["improve_skill_routing", "improve_skill_workflow"]:
                    skill_id = self.report_missing_skill(gap_data)
                    if skill_id:
                        reported.append({
                            "gap_key": gap_key,
                            "skill_id": skill_id,
                            "skill_name": gap_data.get("selected_skill") or gap_data.get("selected_category")
                        })
        
        return reported
