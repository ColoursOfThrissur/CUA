"""
Skill-aware tool creation orchestrator
Automatically detects/creates/updates skills during tool creation
"""
import logging
import re
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class SkillAwareCreationOrchestrator:
    """Orchestrates skill detection, creation, and updates during tool creation"""
    
    def __init__(self, skill_registry, llm_client):
        self.skill_registry = skill_registry
        self.llm_client = llm_client
    
    def detect_or_create_skill(self, gap_description: str, tool_spec: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Detect target skill from gap description or create new skill if needed.
        Returns skill_context dict for tool creation.
        """
        # Step 1: Try to match existing skill
        from core.skills import SkillSelector
        selector = SkillSelector()
        
        selection = selector.select_skill(gap_description, self.skill_registry, self.llm_client)
        
        if selection.matched and selection.confidence >= 0.4:
            # Found existing skill
            skill = self.skill_registry.get(selection.skill_name)
            return self._build_skill_context(skill, selection, "existing_skill")
        
        # Step 2: No confident match - ask LLM if we need a new skill
        should_create, skill_proposal = self._should_create_new_skill(gap_description, selection)
        
        if should_create and skill_proposal:
            # Create new skill
            created_skill = self._create_skill(skill_proposal)
            if created_skill:
                return self._build_skill_context(created_skill, None, "created_skill", skill_proposal)
        
        # Step 3: Fallback to best candidate or general
        if selection.candidate_skills:
            fallback_skill = self.skill_registry.get(selection.candidate_skills[0])
            if fallback_skill:
                return self._build_skill_context(fallback_skill, selection, "fallback_skill")
        
        # Step 4: No skill context (tool will be general-purpose)
        return {
            "target_skill": None,
            "target_category": "general",
            "skill_name": None,
            "gap_type": "no_matching_skill",
            "suggested_action": "create_tool",
            "reasons": ["No existing skill matches this capability"],
            "example_tasks": [gap_description],
        }
    
    def _should_create_new_skill(self, gap_description: str, selection) -> Tuple[bool, Optional[Dict]]:
        """Ask LLM if we should create a new skill for this gap"""
        existing_skills = self.skill_registry.to_routing_context()
        
        prompt = f"""Analyze if this capability gap requires a NEW SKILL or fits existing skills.

Gap: {gap_description}

Existing skills:
{existing_skills}

Candidate skills from heuristic: {selection.candidate_skills if selection.candidate_skills else "none"}

Return JSON:
{{
  "create_new_skill": boolean,
  "reason": "why new skill is needed OR why existing skill fits",
  "skill_proposal": {{
    "name": "skill_name",
    "category": "category",
    "description": "what this skill does",
    "trigger_examples": ["example1", "example2"],
    "input_types": ["string", "url"],
    "output_types": ["text", "data"],
    "verification_mode": "strict|lenient|source_backed",
    "risk_level": "low|medium|high",
    "ui_renderer": "text|markdown|structured",
    "fallback_strategy": "direct_tool_routing|ask_user"
  }}
}}

ONLY create new skill if:
- Gap represents a distinct domain (e.g., email automation, data analysis)
- No existing skill category covers this domain
- Multiple related tools would benefit from this skill

DO NOT create new skill if:
- Gap is a single tool capability
- Existing skill can be extended with this tool
- Gap is too narrow/specific
"""
        
        try:
            response = self.llm_client._call_llm(prompt, temperature=0.2, expect_json=True)
            parsed = self.llm_client._extract_json(response) if response else None
            
            if not parsed:
                return False, None
            
            create_new = bool(parsed.get("create_new_skill", False))
            skill_proposal = parsed.get("skill_proposal")
            
            if create_new and skill_proposal:
                # Validate proposal has required fields
                required = ["name", "category", "description"]
                if all(skill_proposal.get(k) for k in required):
                    return True, skill_proposal
            
            return False, None
            
        except Exception as e:
            logger.warning(f"Failed to check if new skill needed: {e}")
            return False, None
    
    def _create_skill(self, skill_proposal: Dict) -> Optional[Dict]:
        """Create a new skill and register it in the skill registry"""
        from core.skills import Skill

        # Validate skill proposal
        required_services = skill_proposal.get('required_tools', [])
        for service in required_services:
            if not hasattr(self.skill_registry.services, service):
                logger.error(f"Missing required service: self.services.{service}")
                return None

        # Create and register the skill
        new_skill = Skill(
            name=skill_proposal['name'],
            category=skill_proposal.get('category', 'general'),
            description=skill_proposal.get('description', ''),
            trigger_examples=skill_proposal.get('trigger_examples', []),
            preferred_tools=skill_proposal.get('preferred_tools', []),
            required_tools=required_services,
            workflow_guidance=skill_proposal.get('workflow_guidance', ''),
        )
        self.skill_registry.register(new_skill)
        logger.info(f"Created and registered new skill: {new_skill.name}")
        return new_skill.to_dict()
    
    def _build_skill_context(self, skill, selection=None, source: str = "", proposal: Dict = None) -> Dict[str, Any]:
        """Build enriched skill context dict for tool creation.
        
        PHASE 1.1 ENHANCEMENT: Now includes skill description, trigger examples,
        preferred connectors, and workflow guidance from SKILL.md.
        """
        context = {
            "target_skill": skill.name,
            "target_category": skill.category,
            "skill_name": skill.name,
            "skill_description": skill.description,  # PHASE 1.1 STEP 2
            "trigger_examples": skill.trigger_examples,  # PHASE 1.1 STEP 3
            "preferred_connectors": skill.preferred_connectors,  # PHASE 1.1 STEP 5
            "gap_type": "matched_skill_missing_tool",
            "suggested_action": "create_tool",
            "reasons": [f"Skill '{skill.name}' needs this capability"],
            "example_tasks": skill.trigger_examples[:3],
            "expected_input_types": skill.input_types,
            "expected_output_types": skill.output_types,
            "verification_mode": skill.verification_mode,
            "ui_renderer": skill.ui_renderer,
            "preferred_tools": skill.preferred_tools,
            "required_tools": skill.required_tools,
            "risk_level": skill.risk_level,
            "fallback_strategy": skill.fallback_strategy,
            "source": source,
        }
        
        # PHASE 1.1 STEP 4: Load workflow guidance from SKILL.md
        try:
            workflow_guidance = self._load_workflow_guidance(skill.skill_dir)
            if workflow_guidance:
                context["workflow_guidance"] = workflow_guidance
        except Exception as e:
            logger.warning(f"Failed to load workflow guidance for {skill.name}: {e}")
        
        if selection:
            context["confidence"] = selection.confidence
            context["selection_reason"] = selection.reason
        
        if proposal:
            context["skill_proposal"] = proposal
        
        return context
    
    def _load_workflow_guidance(self, skill_dir: str) -> Optional[str]:
        """Extract workflow guidance from SKILL.md file.
        
        Extracts the Workflow Guidance section to help LLM understand
        proven patterns for tools in this skill domain.
        """
        try:
            import re  # Import here to avoid scope issues
            
            skill_md_path = Path(skill_dir) / "SKILL.md"
            if not skill_md_path.exists():
                return None
            
            content = skill_md_path.read_text(encoding="utf-8")
            
            # Extract Workflow Guidance section
            match = re.search(
                r"## Workflow Guidance\n(.*?)(?=\n## |\Z)",
                content,
                re.DOTALL
            )
            
            if match:
                workflow_text = match.group(1).strip()
                # Limit to reasonable length (max 2000 chars)
                if len(workflow_text) > 2000:
                    workflow_text = workflow_text[:2000] + "... [truncated]"
                return workflow_text
            
            # Fallback: extract Purpose section if Workflow not found
            match = re.search(
                r"## Purpose\n(.*?)(?=\n## |\Z)",
                content,
                re.DOTALL
            )
            if match:
                purpose_text = match.group(1).strip()
                if len(purpose_text) > 2000:
                    purpose_text = purpose_text[:2000] + "... [truncated]"
                return purpose_text
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not load workflow guidance from {skill_dir}: {e}")
            return None
    
    def update_skill_with_tool(self, skill_context: Dict, tool_spec: Dict) -> Dict[str, Any]:
        """Update skill after tool creation"""
        from core.skills import SkillUpdater
        
        updater = SkillUpdater()
        
        skill_name = skill_context.get("target_skill")
        if not skill_name:
            return {"success": False, "error": "No target skill"}
        
        tool_name = tool_spec.get("name")
        if not tool_name:
            return {"success": False, "error": "No tool name"}
        
        # Build update plan
        plan = updater.plan_tool_creation_update(
            skill_name=skill_name,
            tool_name=tool_name,
            operations=[inp.get("operation") for inp in tool_spec.get("inputs", []) if isinstance(inp, dict)],
            output_types=tool_spec.get("outputs", []),
            gap_context={
                "gap_type": skill_context.get("gap_type"),
                "suggested_action": skill_context.get("suggested_action"),
                "reasons": skill_context.get("reasons", []),
                "example_tasks": skill_context.get("example_tasks", []),
                "example_errors": skill_context.get("example_errors", []),
            },
        )
        
        if not plan:
            return {"success": False, "error": "Failed to create update plan"}
        
        # Apply update
        result = updater.apply_update_plan(plan)
        
        if result.get("success"):
            # Reload skill registry
            self.skill_registry.refresh()
            logger.info(f"Updated skill '{skill_name}' with tool '{tool_name}'")
        
        return result
