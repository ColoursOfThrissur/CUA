"""
Context Builder - Builds the execution context for auto-evolutions.
"""
from typing import Optional
from infrastructure.persistence.sqlite.logging import SQLiteLogger
from application.use_cases.evolution.evolution_queue import QueuedEvolution
from domain.value_objects.execution_context import SkillExecutionContext
from infrastructure.validation.ast.architecture_validator import infer_skill_contract_for_tool
from application.services.skill_registry import SkillRegistry

class ContextBuilder:
    def __init__(self, logger: SQLiteLogger):
        self.logger = logger

    def build_context(self, tool_name: str, evolution: QueuedEvolution) -> Optional[SkillExecutionContext]:
        """Build SkillExecutionContext for auto-triggered tool evolutions."""
        try:
            # Step 1: Infer skill from tool name
            skill_contract = infer_skill_contract_for_tool(tool_name)
            
            if not skill_contract:
                self.logger.debug(f"No skill contract found for {tool_name}, using defaults")
                return SkillExecutionContext(
                    skill_name="general",
                    category="general",
                    verification_mode="output_validation",
                    risk_level="medium",
                    fallback_strategy="fail_fast",
                    expected_output_types=[],
                    max_retries=3,
                )
            
            # Step 2: Load skill definition for full context
            skill_registry = SkillRegistry()
            skill_registry.load_all()
            skill_name = skill_contract.get("target_skill")
            skill_definition = skill_registry.get(skill_name) if skill_name else None
            
            # Step 3: Create execution context with skill guidance
            execution_context = SkillExecutionContext(
                skill_name=skill_name or "general",
                category=skill_contract.get("target_category", "general"),
                skill_definition=skill_definition,
                verification_mode=skill_contract.get("verification_mode", "output_validation"),
                risk_level=skill_definition.risk_level if skill_definition else "medium",
                fallback_strategy=skill_definition.fallback_strategy if skill_definition else "fail_fast",
                preferred_tools=skill_definition.preferred_tools if skill_definition else [],
                expected_output_types=skill_contract.get("output_types", []),
            )
            
            # Step 4: Add evolution metadata for improved reasoning
            evolution_reason = evolution.reason or ""
            evolution_metadata = evolution.metadata or {}
            
            context_hints = []
            if evolution_metadata.get("category") == "WEAK":
                context_hints.append("Tool has critical issues that need fixing")
            elif evolution_metadata.get("category") == "NEEDS_IMPROVEMENT":
                context_hints.append("Tool needs improvements to be more reliable")
            elif evolution_metadata.get("is_enhancement"):
                context_hints.append("Tool is healthy but has enhancement opportunities")
            
            if evolution_metadata.get("issues_count", 0) > 0:
                context_hints.append(f"LLM identified {evolution_metadata['issues_count']} issues")
            
            if context_hints:
                execution_context.add_step(
                    tool=tool_name,
                    operation="auto_evolution_context",
                    status="prepared",
                    duration=0.0,
                    result={"reason": evolution_reason, "context": context_hints}
                )
            
            self.logger.info(
                f"Built execution context for {tool_name}: skill={skill_name}, "
                f"category={skill_contract.get('target_category')}, "
                f"verification_mode={execution_context.verification_mode}"
            )
            
            return execution_context
            
        except Exception as e:
            self.logger.error(f"Failed to build execution context for {tool_name}: {e}")
            return None
