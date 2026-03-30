"""
Auto-Skill Detection - Fallback logic when skill confidence is below threshold.

Provides:
- Fallback when SkillSelector confidence < threshold
- Manual skill entry when auto-detection fails
- Graceful degradation to direct tool routing
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from domain.entities.skill_models import SkillSelection, SkillDefinition


class DetectionMode(Enum):
    AUTO = "auto"
    MANUAL = "manual"
    DIRECT_ROUTING = "direct_routing"


@dataclass
class AutoDetectionResult:
    """Result of auto-skill detection process."""
    mode: DetectionMode
    skill_name: Optional[str]
    confidence: float
    reason: str
    manual_options: List[str]  # Available skills for manual selection
    fallback_used: bool


class AutoSkillDetector:
    """Handles auto-skill detection with fallback strategies."""
    
    def __init__(self, confidence_threshold: float = 0.35):
        self.confidence_threshold = confidence_threshold
    
    def detect_with_fallback(
        self,
        user_message: str,
        skill_registry,
        skill_selector,
        llm_client,
        allow_manual: bool = True
    ) -> AutoDetectionResult:
        """
        Detect skill with fallback strategies.
        
        Args:
            user_message: User's request
            skill_registry: Registry of available skills
            skill_selector: Primary skill selector
            llm_client: LLM client for fallback detection
            allow_manual: Whether to offer manual selection
            
        Returns:
            AutoDetectionResult with detection outcome
        """
        # Try primary skill selection
        primary_selection = skill_selector.select_skill(user_message, skill_registry, llm_client)
        
        if primary_selection.matched and primary_selection.confidence >= self.confidence_threshold:
            # Primary selection succeeded
            return AutoDetectionResult(
                mode=DetectionMode.AUTO,
                skill_name=primary_selection.skill_name,
                confidence=primary_selection.confidence,
                reason=f"Auto-detected with confidence {primary_selection.confidence:.2f}",
                manual_options=[],
                fallback_used=False
            )
        
        # Primary selection failed or low confidence - try enhanced detection
        enhanced_result = self._enhanced_skill_detection(
            user_message, skill_registry, llm_client
        )
        
        if enhanced_result.confidence >= self.confidence_threshold:
            return AutoDetectionResult(
                mode=DetectionMode.AUTO,
                skill_name=enhanced_result.skill_name,
                confidence=enhanced_result.confidence,
                reason=f"Enhanced detection with confidence {enhanced_result.confidence:.2f}",
                manual_options=[],
                fallback_used=True
            )
        
        # Enhanced detection also failed
        available_skills = [skill.name for skill in skill_registry.list_all()]
        
        if allow_manual and available_skills:
            # Offer manual selection
            return AutoDetectionResult(
                mode=DetectionMode.MANUAL,
                skill_name=None,
                confidence=0.0,
                reason=f"Auto-detection confidence too low ({enhanced_result.confidence:.2f})",
                manual_options=available_skills,
                fallback_used=True
            )
        
        # Fall back to direct tool routing
        return AutoDetectionResult(
            mode=DetectionMode.DIRECT_ROUTING,
            skill_name=None,
            confidence=0.0,
            reason="No confident skill match found, using direct tool routing",
            manual_options=[],
            fallback_used=True
        )
    
    def _enhanced_skill_detection(
        self,
        user_message: str,
        skill_registry,
        llm_client
    ) -> SkillSelection:
        """
        Enhanced skill detection using more sophisticated LLM analysis.
        
        Args:
            user_message: User's request
            skill_registry: Registry of available skills
            llm_client: LLM client
            
        Returns:
            SkillSelection with enhanced analysis
        """
        # Get all available skills with detailed context
        skills_context = []
        for skill in skill_registry.list_all():
            skills_context.append({
                "name": skill.name,
                "category": skill.category,
                "description": skill.description,
                "trigger_examples": skill.trigger_examples[:3],  # Limit for prompt size
                "input_types": skill.input_types,
                "output_types": skill.output_types,
                "preferred_tools": skill.preferred_tools
            })
        
        # Enhanced prompt with more context
        prompt = f"""Analyze this user request and select the most appropriate skill.

User Request: "{user_message}"

Available Skills:
{self._format_skills_for_prompt(skills_context)}

Consider:
1. What is the user trying to accomplish?
2. What domain does this task belong to?
3. What tools would be needed?
4. What type of output is expected?

Respond with JSON only:
{{
    "skill_name": "exact_skill_name_or_empty_string",
    "confidence": 0.0_to_1.0,
    "reasoning": "detailed_explanation",
    "task_analysis": "what_user_wants_to_accomplish",
    "domain_match": "why_this_skill_fits"
}}"""
        
        try:
            response = llm_client._call_llm(prompt, temperature=0.1, max_tokens=400, expect_json=True)
            parsed = llm_client._extract_json(response) if response else None
            
            if not isinstance(parsed, dict):
                return self._create_failed_selection("LLM response not valid JSON")
            
            skill_name = str(parsed.get("skill_name", "")).strip()
            confidence = float(parsed.get("confidence", 0.0))
            reasoning = str(parsed.get("reasoning", "enhanced_detection"))
            
            # Validate skill exists
            skill = skill_registry.get(skill_name) if skill_name else None
            if not skill:
                return self._create_failed_selection("Selected skill not found in registry")
            
            return SkillSelection(
                matched=True,
                skill_name=skill.name,
                category=skill.category,
                confidence=confidence,
                reason=f"enhanced_llm:{reasoning}",
                fallback_mode=skill.fallback_strategy,
                candidate_skills=[skill.name]
            )
            
        except Exception as e:
            return self._create_failed_selection(f"Enhanced detection failed: {str(e)}")
    
    def _format_skills_for_prompt(self, skills_context: List[Dict[str, Any]]) -> str:
        """Format skills context for LLM prompt."""
        lines = []
        for skill in skills_context:
            lines.append(f"- {skill['name']} ({skill['category']}): {skill['description']}")
            lines.append(f"  Examples: {', '.join(skill['trigger_examples'])}")
            lines.append(f"  Tools: {', '.join(skill['preferred_tools'])}")
            lines.append(f"  Outputs: {', '.join(skill['output_types'])}")
            lines.append("")
        return "\n".join(lines)
    
    def _create_failed_selection(self, reason: str) -> SkillSelection:
        """Create a failed skill selection."""
        return SkillSelection(
            matched=False,
            skill_name=None,
            category=None,
            confidence=0.0,
            reason=reason,
            fallback_mode="direct_tool_routing",
            candidate_skills=[]
        )
    
    def handle_manual_selection(
        self,
        selected_skill_name: str,
        skill_registry
    ) -> AutoDetectionResult:
        """
        Handle manual skill selection by user.
        
        Args:
            selected_skill_name: Skill name selected by user
            skill_registry: Registry of available skills
            
        Returns:
            AutoDetectionResult with manual selection
        """
        skill = skill_registry.get(selected_skill_name)
        if not skill:
            return AutoDetectionResult(
                mode=DetectionMode.DIRECT_ROUTING,
                skill_name=None,
                confidence=0.0,
                reason=f"Invalid skill selection: {selected_skill_name}",
                manual_options=[],
                fallback_used=True
            )
        
        return AutoDetectionResult(
            mode=DetectionMode.MANUAL,
            skill_name=skill.name,
            confidence=1.0,  # Manual selection is 100% confident
            reason=f"Manually selected by user",
            manual_options=[],
            fallback_used=True
        )


def detect_skill_with_fallback(
    user_message: str,
    skill_registry,
    skill_selector,
    llm_client,
    confidence_threshold: float = 0.35,
    allow_manual: bool = True
) -> AutoDetectionResult:
    """
    Convenience function for auto-skill detection with fallback.
    
    Args:
        user_message: User's request
        skill_registry: Registry of available skills
        skill_selector: Primary skill selector
        llm_client: LLM client
        confidence_threshold: Minimum confidence for auto-detection
        allow_manual: Whether to offer manual selection
        
    Returns:
        AutoDetectionResult with detection outcome
    """
    detector = AutoSkillDetector(confidence_threshold)
    return detector.detect_with_fallback(
        user_message, skill_registry, skill_selector, llm_client, allow_manual
    )