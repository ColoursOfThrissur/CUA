"""Replan Steps Use Case - Replans remaining steps after failure."""
import logging
from typing import List, Dict, Optional
from domain.entities.task import TaskStep
from domain.repositories.repositories import ToolRepository
from infrastructure.llm.llm_gateway import LLMGateway
from infrastructure.llm.prompt_builder import PlanningPromptBuilder
from infrastructure.validation.plan_validator import PlanValidator

logger = logging.getLogger(__name__)


class ReplanStepsUseCase:
    """Use case for replanning remaining steps."""
    
    def __init__(
        self,
        llm_gateway: LLMGateway,
        tool_repo: ToolRepository,
        prompt_builder: PlanningPromptBuilder,
        plan_validator: PlanValidator
    ):
        self._llm = llm_gateway
        self._tools = tool_repo
        self._prompts = prompt_builder
        self._validator = plan_validator
    
    def execute(
        self,
        original_goal: str,
        remaining_steps: List[TaskStep],
        replan_context: Dict,
        context: Optional[Dict] = None
    ) -> List[TaskStep]:
        """Replan remaining steps given failures."""
        logger.info(f"[PLANNER] Replanning {len(remaining_steps)} remaining steps")
        
        # Get available tools
        skill_preferred = set((context or {}).get("skill_context", {}).get("preferred_tools", []))
        available_tools = self._tools.get_capabilities(preferred_tools=skill_preferred or None)
        
        # Extract replan context
        completed_summary = replan_context.get("completed_summary", {})
        completed_artifacts = replan_context.get("completed_artifacts", {})
        failed_errors = replan_context.get("failed_errors", {})
        
        # Build replan prompt
        prompt = self._prompts.build_replan_prompt(
            original_goal=original_goal,
            remaining_steps=remaining_steps,
            completed_summary=completed_summary,
            completed_artifacts=completed_artifacts,
            failed_errors=failed_errors,
            available_tools=available_tools
        )
        
        try:
            # Get LLM response
            response = self._llm.generate_plan(prompt, temperature=0.3)
            
            if not response:
                raise RuntimeError("LLM returned no response during replan")
            
            # Parse response
            response = response.strip()
            if "```json" in response:
                response = response[response.find("```json") + 7:response.rfind("```")].strip()
            elif "```" in response:
                response = response[response.find("```") + 3:response.rfind("```")].strip()
            
            steps_data = self._validator.parse_llm_response(f'{{"steps": {response} }}')
            if isinstance(steps_data, dict):
                steps_data = steps_data.get("steps", steps_data)
            if not isinstance(steps_data, list):
                raise ValueError("Expected JSON array")
            
            # Build new steps
            current_tools = self._validator._build_tool_index()
            new_steps = []
            
            for sd in steps_data:
                tool_name = sd.get("tool_name")
                operation = sd.get("operation")
                
                if tool_name not in current_tools:
                    logger.warning(f"Replan: unknown tool {tool_name}, skipping")
                    continue
                
                tool = current_tools[tool_name]
                caps = tool.get_capabilities() or {}
                
                # Remap operation
                if operation not in caps:
                    remapped = self._validator._OP_ALIASES.get(operation)
                    if remapped and remapped in caps:
                        operation = remapped
                    else:
                        logger.warning(f"Replan: unknown op {operation}, skipping")
                        continue
                
                capability = caps[operation]
                params = sd.get("parameters", {})
                params = self._validator._normalize_params(params, capability)
                
                new_steps.append(TaskStep(
                    step_id=sd["step_id"],
                    description=sd["description"],
                    tool_name=tool_name,
                    operation=operation,
                    parameters=params,
                    dependencies=sd.get("dependencies", []),
                    expected_output=sd.get("expected_output", ""),
                    domain=sd.get("domain", "general"),
                    retry_on_failure=sd.get("retry_on_failure", True),
                    max_retries=sd.get("max_retries", 3),
                    preconditions=sd.get("preconditions", []),
                    postconditions=sd.get("postconditions", []),
                    checkpoint_policy=sd.get("checkpoint_policy", "on_failure"),
                    retry_policy=sd.get("retry_policy", {}),
                ))
            
            if new_steps:
                logger.info(f"[PLANNER] Replan produced {len(new_steps)} replacement steps")
                try:
                    self._validator._validate_dependencies(new_steps)
                except ValueError as e:
                    logger.warning(f"Replan dependency validation failed: {e}, returning original")
                    return remaining_steps
                return new_steps
        
        except Exception as e:
            logger.error(f"Replan failed: {e}")
        
        # Fallback
        return remaining_steps
