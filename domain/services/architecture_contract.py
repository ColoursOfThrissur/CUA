"""Helpers for thin tool-architecture contracts.

This module is intentionally separate from the skill-aware architecture helpers in
`infrastructure.validation.ast.architecture_validator`. The functions here operate
on an explicit tool contract object plus source code.
"""

from typing import Any, Dict


def build_tool_architecture_contract(tool_name: str, tool_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a thin architecture contract from an explicit tool specification."""
    return {
        "tool_name": tool_name,
        "capabilities": tool_spec.get("capabilities", []),
        "required_services": tool_spec.get("services", []),
        "input_schema": tool_spec.get("input_schema", {}),
        "output_schema": tool_spec.get("output_schema", {}),
        "constraints": tool_spec.get("constraints", []),
    }


def enrich_tool_architecture_contract(contract: Dict[str, Any], skill_context: Any) -> Dict[str, Any]:
    """Enrich a thin contract with lightweight skill metadata for reporting."""
    enriched = contract.copy()

    if hasattr(skill_context, "skill_name"):
        enriched["skill_name"] = skill_context.skill_name

    if hasattr(skill_context, "preferred_tools"):
        enriched["related_tools"] = skill_context.preferred_tools

    return enriched


def validate_tool_architecture_contract(contract: Dict[str, Any], code: str) -> Dict[str, Any]:
    """Validate that source code adheres to an explicit tool contract."""
    violations = []

    if not contract.get("tool_name"):
        violations.append("Contract missing tool_name")

    if not contract.get("capabilities"):
        violations.append("Contract missing capabilities")

    required_services = contract.get("required_services", [])
    for service in required_services:
        if f"self.services.{service}" not in code:
            violations.append(f"Code does not use required service: {service}")

    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "contract": contract,
    }
