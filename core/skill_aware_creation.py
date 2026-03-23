"""
Skill-Aware Tool Creation Enhancement - Ensures tool creation LLM receives full skill constraints.

Provides:
- Full skill constraint extraction for LLM prompts
- Domain-specific tool generation guidance
- Service pattern alignment with skill requirements
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from core.skills.models import SkillDefinition


@dataclass
class SkillConstraints:
    """Extracted skill constraints for tool creation."""
    skill_name: str
    category: str
    description: str
    
    # Tool guidance
    preferred_tools: List[str]
    required_tools: List[str]
    forbidden_tools: List[str]
    
    # I/O expectations
    input_types: List[str]
    output_types: List[str]
    
    # Execution constraints
    verification_mode: str
    risk_level: str
    
    # Domain patterns
    trigger_examples: List[str]
    service_patterns: Dict[str, Any]
    ui_renderer: str
    
    # Instructions
    instructions_summary: str


class SkillAwareCreationEnhancer:
    """Enhances tool creation with full skill constraints."""
    
    def __init__(self):
        # Service patterns expected for each skill category
        self.service_patterns = {
            "web": {
                "required": ["http", "logging"],
                "recommended": ["storage", "json"],
                "forbidden": ["shell", "fs"],
                "examples": [
                    "self.services.http.get(url)",
                    "self.services.json.parse(response)",
                    "self.services.storage.save(id, data)"
                ]
            },
            "computer": {
                "required": ["fs", "logging"],
                "recommended": ["shell", "storage"],
                "forbidden": [],
                "examples": [
                    "self.services.fs.read(path)",
                    "self.services.shell.execute(command)",
                    "self.services.storage.save(id, data)"
                ]
            },
            "development": {
                "required": ["fs", "logging"],
                "recommended": ["shell", "storage", "json"],
                "forbidden": [],
                "examples": [
                    "self.services.fs.write(path, content)",
                    "self.services.shell.execute(command)",
                    "self.services.json.parse(data)"
                ]
            },
            "automation": {
                "required": ["logging"],
                "recommended": ["storage", "http"],
                "forbidden": [],
                "examples": [
                    "self.services.storage.save(id, data)",
                    "self.services.http.post(url, data)",
                    "self.services.logging.info(message)"
                ]
            },
            "data": {
                "required": ["http", "json", "logging"],
                "recommended": ["storage"],
                "forbidden": ["shell", "fs"],
                "examples": [
                    "self.services.http.get(api_url)",
                    "self.services.json.parse(response)",
                    "self.services.storage.save(id, processed_data)"
                ]
            },
            "productivity": {
                "required": ["storage", "logging"],
                "recommended": ["json"],
                "forbidden": ["shell", "http"],
                "examples": [
                    "self.services.storage.save(id, data)",
                    "self.services.storage.list()",
                    "self.services.json.stringify(data)"
                ]
            }
        }
    
    def extract_skill_constraints(
        self, 
        skill_definition: SkillDefinition,
        skill_instructions: Optional[str] = None
    ) -> SkillConstraints:
        """
        Extract comprehensive skill constraints for tool creation.
        
        Args:
            skill_definition: Full skill definition
            skill_instructions: Optional skill instructions content
            
        Returns:
            SkillConstraints with all extracted information
        """
        # Get service patterns for this skill category
        service_patterns = self.service_patterns.get(skill_definition.category, {})
        
        # Extract forbidden tools (tools not in preferred/required)
        all_tools = set()
        for other_skill_patterns in self.service_patterns.values():
            all_tools.update(other_skill_patterns.get("required", []))
            all_tools.update(other_skill_patterns.get("recommended", []))
        
        skill_tools = set(skill_definition.preferred_tools + skill_definition.required_tools)
        forbidden_tools = list(service_patterns.get("forbidden", []))
        
        return SkillConstraints(
            skill_name=skill_definition.name,
            category=skill_definition.category,
            description=skill_definition.description,
            
            preferred_tools=skill_definition.preferred_tools,
            required_tools=skill_definition.required_tools,
            forbidden_tools=forbidden_tools,
            
            input_types=skill_definition.input_types,
            output_types=skill_definition.output_types,
            
            verification_mode=skill_definition.verification_mode,
            risk_level=skill_definition.risk_level,
            
            trigger_examples=skill_definition.trigger_examples,
            service_patterns=service_patterns,
            ui_renderer=skill_definition.ui_renderer,
            
            instructions_summary=skill_instructions or skill_definition.description
        )
    
    def enhance_tool_spec_prompt(
        self, 
        base_prompt: str,
        skill_constraints: SkillConstraints,
        gap_description: str
    ) -> str:
        """
        Enhance tool specification prompt with skill constraints.
        
        Args:
            base_prompt: Base tool creation prompt
            skill_constraints: Extracted skill constraints
            gap_description: Original capability gap description
            
        Returns:
            Enhanced prompt with skill guidance
        """
        skill_guidance = f"""
SKILL CONTEXT:
Target Skill: {skill_constraints.skill_name} ({skill_constraints.category})
Description: {skill_constraints.description}

DOMAIN REQUIREMENTS:
- Input Types: {', '.join(skill_constraints.input_types)}
- Output Types: {', '.join(skill_constraints.output_types)}
- Verification Mode: {skill_constraints.verification_mode}
- Risk Level: {skill_constraints.risk_level}

SERVICE PATTERNS (REQUIRED):
Use these service patterns for {skill_constraints.category} domain:
{self._format_service_examples(skill_constraints.service_patterns)}

TOOL ALIGNMENT:
- Must align with existing tools: {', '.join(skill_constraints.preferred_tools)}
- Must NOT conflict with: {', '.join(skill_constraints.forbidden_tools)}

EXAMPLE TASKS:
{self._format_trigger_examples(skill_constraints.trigger_examples)}

VERIFICATION REQUIREMENTS:
{self._format_verification_requirements(skill_constraints.verification_mode)}

"""
        
        return base_prompt + skill_guidance
    
    def enhance_code_generation_prompt(
        self,
        base_prompt: str,
        skill_constraints: SkillConstraints,
        tool_spec: Dict[str, Any]
    ) -> str:
        """
        Enhance code generation prompt with skill constraints.
        
        Args:
            base_prompt: Base code generation prompt
            skill_constraints: Extracted skill constraints
            tool_spec: Tool specification
            
        Returns:
            Enhanced prompt with implementation guidance
        """
        implementation_guidance = f"""
IMPLEMENTATION REQUIREMENTS FOR {skill_constraints.skill_name.upper()} SKILL:

SERVICE USAGE (MANDATORY):
{self._format_service_requirements(skill_constraints.service_patterns)}

OUTPUT FORMAT:
- Must return data compatible with {skill_constraints.verification_mode} verification
- Expected output types: {', '.join(skill_constraints.output_types)}
{self._format_output_requirements(skill_constraints.verification_mode, skill_constraints.output_types)}

RISK LEVEL: {skill_constraints.risk_level}
{self._format_risk_requirements(skill_constraints.risk_level)}

DOMAIN PATTERNS:
Follow these patterns for {skill_constraints.category} domain tools:
{self._format_domain_patterns(skill_constraints.category)}

"""
        
        return base_prompt + implementation_guidance
    
    def _format_service_examples(self, service_patterns: Dict[str, Any]) -> str:
        """Format service usage examples."""
        examples = service_patterns.get("examples", [])
        if not examples:
            return "- Use appropriate self.services.X patterns"
        
        lines = []
        for example in examples:
            lines.append(f"- {example}")
        return "\n".join(lines)
    
    def _format_trigger_examples(self, trigger_examples: List[str]) -> str:
        """Format trigger examples."""
        if not trigger_examples:
            return "- General purpose tasks"
        
        lines = []
        for example in trigger_examples[:5]:  # Limit to 5 examples
            lines.append(f"- \"{example}\"")
        return "\n".join(lines)
    
    def _format_verification_requirements(self, verification_mode: str) -> str:
        """Format verification requirements."""
        requirements = {
            "source_backed": "Tool must return 'sources' field with source URLs and 'content' or 'summary' field",
            "side_effect_observed": "Tool must return 'file_path' or 'path' field showing what was modified",
            "output_validation": "Tool must return structured data that can be validated"
        }
        
        return requirements.get(verification_mode, "Tool must return valid structured data")
    
    def _format_service_requirements(self, service_patterns: Dict[str, Any]) -> str:
        """Format service requirements."""
        lines = []
        
        required = service_patterns.get("required", [])
        if required:
            lines.append(f"REQUIRED: {', '.join(f'self.services.{s}' for s in required)}")
        
        recommended = service_patterns.get("recommended", [])
        if recommended:
            lines.append(f"RECOMMENDED: {', '.join(f'self.services.{s}' for s in recommended)}")
        
        forbidden = service_patterns.get("forbidden", [])
        if forbidden:
            lines.append(f"FORBIDDEN: {', '.join(f'self.services.{s}' for s in forbidden)}")
        
        return "\n".join(lines) if lines else "Use appropriate services"
    
    def _format_output_requirements(self, verification_mode: str, output_types: List[str]) -> str:
        """Format output requirements."""
        lines = []
        
        if verification_mode == "source_backed":
            lines.append("- Include 'sources' field with list of source URLs")
            lines.append("- Include 'content' or 'summary' field with extracted information")
        elif verification_mode == "side_effect_observed":
            lines.append("- Include 'file_path' or 'path' field showing modified files")
            lines.append("- Include 'operation' field describing what was done")
        
        if output_types:
            lines.append(f"- Structure output for types: {', '.join(output_types)}")
        
        return "\n".join(lines) if lines else ""
    
    def _format_risk_requirements(self, risk_level: str) -> str:
        """Format risk-specific requirements."""
        requirements = {
            "low": "- Use safe operations only\n- Extensive input validation\n- Detailed error handling",
            "medium": "- Validate inputs carefully\n- Handle errors gracefully\n- Log operations for audit",
            "high": "- Minimal operations only\n- Strict input validation\n- Comprehensive error handling\n- Detailed logging"
        }
        
        return requirements.get(risk_level, "- Handle operations safely")
    
    def _format_domain_patterns(self, category: str) -> str:
        """Format domain-specific patterns."""
        patterns = {
            "web": "- Always validate URLs\n- Handle HTTP errors\n- Parse responses safely\n- Cache when appropriate",
            "computer": "- Validate file paths\n- Check permissions\n- Handle file system errors\n- Use absolute paths",
            "development": "- Validate code syntax\n- Handle compilation errors\n- Use proper file encoding\n- Backup before changes",
            "automation": "- Validate automation steps\n- Handle UI element changes\n- Provide clear feedback\n- Support retry logic",
            "data": "- Validate data schemas\n- Handle API rate limits\n- Parse data safely\n- Transform data consistently",
            "productivity": "- Organize data clearly\n- Support search/filter\n- Handle large datasets\n- Provide data export"
        }
        
        return patterns.get(category, "- Follow best practices for domain")


def enhance_tool_creation_with_skill(
    base_prompt: str,
    skill_definition: SkillDefinition,
    gap_description: str,
    prompt_type: str = "spec"  # "spec" or "code"
) -> str:
    """
    Convenience function to enhance tool creation prompts with skill constraints.
    
    Args:
        base_prompt: Base prompt to enhance
        skill_definition: Skill definition
        gap_description: Capability gap description
        prompt_type: Type of prompt ("spec" or "code")
        
    Returns:
        Enhanced prompt with skill guidance
    """
    enhancer = SkillAwareCreationEnhancer()
    constraints = enhancer.extract_skill_constraints(skill_definition)
    
    if prompt_type == "spec":
        return enhancer.enhance_tool_spec_prompt(base_prompt, constraints, gap_description)
    elif prompt_type == "code":
        return enhancer.enhance_code_generation_prompt(base_prompt, constraints, {})
    else:
        return base_prompt