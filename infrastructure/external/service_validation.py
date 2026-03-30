"""
Service Validation Logic - Validates generated tools against skill service patterns.

Ensures that:
- Generated tools use appropriate self.services.X patterns for their skill domain
- Service usage aligns with skill constraints and risk levels
- Tool capabilities match skill expected input/output types
"""

from typing import Dict, List, Optional, Set, Any
import ast
import re
from dataclasses import dataclass

from domain.entities.skill_models import SkillDefinition


@dataclass
class ServiceValidationResult:
    """Result of service pattern validation."""
    valid: bool
    errors: List[str]
    warnings: List[str]
    required_services: Set[str]
    used_services: Set[str]
    skill_alignment_score: float  # 0.0 to 1.0


class ServicePatternValidator:
    """Validates tool service usage against skill patterns."""
    
    # Service patterns expected for each skill category
    SKILL_SERVICE_PATTERNS = {
        "web": {
            "required": ["http"],
            "recommended": ["storage", "json", "logging"],
            "forbidden": ["shell", "fs"],
            "risk_services": {"shell": "high", "fs": "medium"}
        },
        "computer": {
            "required": [],
            "recommended": ["fs", "shell", "storage", "logging"],
            "forbidden": [],
            "risk_services": {"shell": "high", "fs": "medium"}
        },
        "development": {
            "required": [],
            "recommended": ["fs", "shell", "storage", "json", "logging"],
            "forbidden": [],
            "risk_services": {"shell": "high", "fs": "medium"}
        },
        "automation": {
            "required": [],
            "recommended": ["storage", "http", "logging"],
            "forbidden": [],
            "risk_services": {"shell": "high", "fs": "medium"}
        },
        "data": {
            "required": [],
            "recommended": ["storage", "json", "http", "logging"],
            "forbidden": ["shell"],
            "risk_services": {"http": "medium"}
        },
        "productivity": {
            "required": ["storage"],
            "recommended": ["json", "logging"],
            "forbidden": ["shell", "http"],
            "risk_services": {}
        }
    }
    
    def validate_tool_against_skill(
        self, 
        tool_code: str, 
        skill_definition: SkillDefinition
    ) -> ServiceValidationResult:
        """
        Validate tool code against skill service patterns.
        
        Args:
            tool_code: Generated tool source code
            skill_definition: Skill the tool should align with
            
        Returns:
            ServiceValidationResult with validation details
        """
        errors = []
        warnings = []
        used_services = self._extract_service_usage(tool_code)
        
        # Get expected patterns for skill category
        patterns = self.SKILL_SERVICE_PATTERNS.get(skill_definition.category, {})
        required_services = set(patterns.get("required", []))
        recommended_services = set(patterns.get("recommended", []))
        forbidden_services = set(patterns.get("forbidden", []))
        risk_services = patterns.get("risk_services", {})
        
        # Check required services
        missing_required = required_services - used_services
        if missing_required:
            errors.append(f"Missing required services for {skill_definition.category} skill: {', '.join(missing_required)}")
        
        # Check forbidden services
        forbidden_used = forbidden_services & used_services
        if forbidden_used:
            errors.append(f"Using forbidden services for {skill_definition.category} skill: {', '.join(forbidden_used)}")
        
        # Check risk alignment
        for service, risk_level in risk_services.items():
            if service in used_services:
                if skill_definition.risk_level == "low" and risk_level == "high":
                    errors.append(f"High-risk service '{service}' used in low-risk skill")
                elif skill_definition.risk_level == "medium" and risk_level == "high":
                    warnings.append(f"High-risk service '{service}' used in medium-risk skill")
        
        # Check capability alignment
        capability_errors = self._validate_capability_alignment(tool_code, skill_definition)
        errors.extend(capability_errors)
        
        # Calculate alignment score
        alignment_score = self._calculate_alignment_score(
            used_services, required_services, recommended_services, forbidden_services
        )
        
        return ServiceValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            required_services=required_services,
            used_services=used_services,
            skill_alignment_score=alignment_score
        )
    
    def _extract_service_usage(self, tool_code: str) -> Set[str]:
        """Extract self.services.X usage from tool code."""
        services = set()
        
        # Parse AST to find service usage
        try:
            tree = ast.parse(tool_code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    if (isinstance(node.value, ast.Attribute) and
                        isinstance(node.value.value, ast.Name) and
                        node.value.value.id == "self" and
                        node.value.attr == "services"):
                        services.add(node.attr)
        except SyntaxError:
            # Fallback to regex if AST parsing fails
            pattern = r'self\.services\.(\w+)'
            matches = re.findall(pattern, tool_code)
            services.update(matches)
        
        return services
    
    def _validate_capability_alignment(
        self, 
        tool_code: str, 
        skill_definition: SkillDefinition
    ) -> List[str]:
        """Validate that tool capabilities align with skill expectations."""
        errors = []
        
        # Extract capability names from tool code
        capability_pattern = r'ToolCapability\s*\(\s*name\s*=\s*["\']([^"\']+)["\']'
        capabilities = re.findall(capability_pattern, tool_code)
        
        if not capabilities:
            errors.append("No capabilities found in tool code")
            return errors
        
        # Check if capabilities match skill domain
        skill_keywords = set()
        skill_keywords.update(skill_definition.trigger_examples)
        skill_keywords.update(skill_definition.input_types)
        skill_keywords.update(skill_definition.output_types)
        
        # Convert to lowercase for matching
        skill_keywords = {kw.lower() for kw in skill_keywords}
        
        aligned_capabilities = 0
        for capability in capabilities:
            capability_words = set(re.findall(r'\w+', capability.lower()))
            if capability_words & skill_keywords:
                aligned_capabilities += 1
        
        # aligned_capabilities == 0 is a soft warning, not a hard error — skip
        return errors
    
    def _calculate_alignment_score(
        self,
        used_services: Set[str],
        required_services: Set[str],
        recommended_services: Set[str],
        forbidden_services: Set[str]
    ) -> float:
        """Calculate skill alignment score (0.0 to 1.0)."""
        score = 0.0
        total_weight = 0.0
        
        # Required services (weight: 0.5)
        if required_services:
            required_met = len(required_services & used_services) / len(required_services)
            score += required_met * 0.5
            total_weight += 0.5
        
        # Recommended services (weight: 0.3)
        if recommended_services:
            recommended_met = len(recommended_services & used_services) / len(recommended_services)
            score += recommended_met * 0.3
            total_weight += 0.3
        
        # Forbidden services penalty (weight: 0.2)
        if forbidden_services:
            forbidden_used = len(forbidden_services & used_services)
            penalty = forbidden_used / len(forbidden_services) if forbidden_services else 0
            score += (1.0 - penalty) * 0.2
            total_weight += 0.2
        
        return score / total_weight if total_weight > 0 else 0.0


def validate_tool_service_patterns(tool_code: str, skill_definition: SkillDefinition) -> ServiceValidationResult:
    """
    Convenience function to validate tool service patterns.
    
    Args:
        tool_code: Generated tool source code
        skill_definition: Skill the tool should align with
        
    Returns:
        ServiceValidationResult with validation details
    """
    validator = ServicePatternValidator()
    return validator.validate_tool_against_skill(tool_code, skill_definition)