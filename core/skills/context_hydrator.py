"""
Skill Context Hydrator - Builds SkillExecutionContext from SkillDefinition.

Takes a selected skill and creates a rich execution context with:
- Tool selection guidance (preferred_tools, fallback strategies)
- Validation rules (verification_mode, expected I/O types)
- Recovery settings (max_retries, degraded_mode based on risk_level)
"""

from typing import Optional
from core.skills.models import SkillDefinition, SkillSelection
from core.skills.execution_context import SkillExecutionContext


class SkillContextHydrator:
    """Builds execution context from skill definition."""
    
    @staticmethod
    def build_context(
        skill_selection: SkillSelection,
        skill_definition: SkillDefinition,
        user_request: str
    ) -> SkillExecutionContext:
        """
        Build execution context from skill selection and definition.
        
        Args:
            skill_selection: Result from SkillSelector
            skill_definition: Full skill definition from registry
            user_request: Original user request for tracing
            
        Returns:
            SkillExecutionContext with all guidance populated
        """
        
        # Derive risk level from skill definition (not just metadata)
        risk_level = skill_definition.risk_level or skill_definition.metadata.get("risk_level", "medium")
        
        # Derive recovery settings from risk level
        max_retries = {
            "low": 5,      # Low risk = aggressive retries
            "medium": 3,   # Medium risk = moderate retries
            "high": 1      # High risk = minimal retries
        }.get(risk_level, 3)
        
        degraded_mode_enabled = (risk_level == "low")  # Only low-risk skills can degrade
        
        # Build context with ALL skill fields extracted
        context = SkillExecutionContext(
            skill_name=skill_selection.skill_name,
            category=skill_selection.category,
            skill_definition=skill_definition,
            
            # Execution guidance from skill (ALL fields now extracted)
            verification_mode=skill_definition.verification_mode,
            risk_level=risk_level,
            fallback_strategy=skill_definition.fallback_strategy,
            
            # Tool selection guidance (ALL fields now extracted)
            preferred_tools=skill_definition.preferred_tools.copy(),
            expected_input_types=skill_definition.expected_input_types.copy(),
            expected_output_types=skill_definition.expected_output_types.copy(),
            
            # Recovery settings
            max_retries=max_retries,
            retry_backoff=1.0,
            degraded_mode_enabled=degraded_mode_enabled,
        )
        
        # Add skill constraints for LLM guidance
        context.validation_rules = {
            "required_tools": skill_definition.required_tools,
            "preferred_connectors": skill_definition.preferred_connectors,
            "trigger_examples": skill_definition.trigger_examples,
            "ui_renderer": skill_definition.ui_renderer,
            "instructions_path": skill_definition.instructions_path,
        }
        
        return context
    
    @staticmethod
    def update_with_tool_selection(
        context: SkillExecutionContext,
        selected_tool: str,
        available_tools: dict,
        fallback_tools: list,
        reasoning: str
    ) -> SkillExecutionContext:
        """
        Update context after tool selection phase.
        
        Args:
            context: Existing context
            selected_tool: Primary tool selected
            available_tools: Dict of tool_name -> ToolVersion
            fallback_tools: List of fallback tool names
            reasoning: Why this tool was selected
            
        Returns:
            Updated context
        """
        context.selected_tool = selected_tool
        context.available_tools = available_tools
        context.fallback_tools = fallback_tools
        context.tool_selection_reasoning = reasoning
        
        return context
