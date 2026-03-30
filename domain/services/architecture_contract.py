"""
Architecture Contract - Defines and validates tool architecture contracts
"""

from typing import Dict, Any, Optional, List


def derive_skill_contract_for_tool(tool_name: str, tool_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Derive an architecture contract for a tool based on its specification."""
    return {
        "tool_name": tool_name,
        "capabilities": tool_spec.get("capabilities", []),
        "required_services": tool_spec.get("services", []),
        "input_schema": tool_spec.get("input_schema", {}),
        "output_schema": tool_spec.get("output_schema", {}),
        "constraints": tool_spec.get("constraints", [])
    }


def enrich_contract_from_skill_context(contract: Dict[str, Any], skill_context: Any) -> Dict[str, Any]:
    """Enrich a contract with information from skill context."""
    enriched = contract.copy()
    
    if hasattr(skill_context, 'skill_name'):
        enriched['skill_name'] = skill_context.skill_name
    
    if hasattr(skill_context, 'preferred_tools'):
        enriched['related_tools'] = skill_context.preferred_tools
    
    return enriched


def validate_architecture_contract(contract: Dict[str, Any], code: str) -> Dict[str, Any]:
    """Validate that code adheres to an architecture contract."""
    violations = []
    
    # Basic validation
    if not contract.get("tool_name"):
        violations.append("Contract missing tool_name")
    
    if not contract.get("capabilities"):
        violations.append("Contract missing capabilities")
    
    # Check if code contains required patterns
    required_services = contract.get("required_services", [])
    for service in required_services:
        if f"self.services.{service}" not in code:
            violations.append(f"Code does not use required service: {service}")
    
    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "contract": contract
    }
