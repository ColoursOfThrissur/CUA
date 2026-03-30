"""Use case for approving and activating a pending tool."""

from __future__ import annotations

from typing import Any, Dict, Optional


class ActivateToolUseCase:
    """Application-facing approval flow for pending tools.

    This mirrors the runtime behavior used by the pending-tools API, but keeps
    the orchestration in the application layer so imports into this module are
    no longer dead ends.
    """

    def __init__(self, pending_tools_manager, tool_registrar, registry_manager=None):
        self.pending_tools_manager = pending_tools_manager
        self.tool_registrar = tool_registrar
        self.registry_manager = registry_manager

    def execute(self, tool_id: str) -> Dict[str, Any]:
        tool = self.pending_tools_manager.get_tool(tool_id)
        if not tool:
            return {"success": False, "error": "Tool not found"}

        tool_file = tool.get("tool_file")
        if not tool_file:
            return {"success": False, "error": "No tool file specified"}

        valid, contract_error = self.pending_tools_manager.validate_tool_file_contract(tool_file)
        if not valid:
            return {"success": False, "error": f"Tool contract validation failed: {contract_error}"}

        try:
            from tools.capability_extractor import CapabilityExtractor

            extracted = CapabilityExtractor().extract_from_file(tool_file)
            if not extracted or not extracted.get("operations"):
                return {"success": False, "error": "Tool has no extractable capabilities"}
        except Exception as exc:
            return {"success": False, "error": f"Capability extraction failed: {exc}"}

        reg_result = self.tool_registrar.register_new_tool(tool_file)
        if not reg_result.get("success"):
            return {"success": False, "error": f"Registration failed: {reg_result.get('error', 'unknown error')}"}

        smoke_ok, smoke_error = self._post_register_contract_check(reg_result["tool_name"])
        if not smoke_ok:
            try:
                self.tool_registrar.unregister_tool(reg_result["tool_name"])
            except Exception:
                pass
            return {"success": False, "error": f"Post-registration validation failed: {smoke_error}"}

        approval_result = self.pending_tools_manager.approve_tool(tool_id)
        if not approval_result.get("success"):
            return approval_result

        try:
            if self.registry_manager and extracted:
                extracted["source_file"] = str(tool_file).replace("\\", "/")
                self.registry_manager.update_tool(extracted)
        except Exception:
            pass

        skill_update_results = []
        try:
            from application.services.skill_updater import SkillUpdater

            skill_update_results = SkillUpdater().apply_update_plans(tool.get("skill_updates") or [])
        except Exception:
            skill_update_results = []

        return {
            "success": True,
            "tool_name": reg_result["tool_name"],
            "capabilities": reg_result.get("capabilities", []),
            "skill_updates": skill_update_results,
            "message": f"Tool '{reg_result['tool_name']}' activated successfully",
        }

    def _post_register_contract_check(self, tool_name: str) -> tuple[bool, str]:
        tool_instance = getattr(self.tool_registrar, "registered_tools", {}).get(tool_name)
        if not tool_instance:
            return False, "Registered tool instance not found"

        try:
            import inspect

            sig = inspect.signature(tool_instance.execute)
            params = list(sig.parameters.values())
        except Exception as exc:
            return False, f"Unable to inspect execute() signature: {exc}"

        has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params)
        supports_param_dict = len(params) >= 2
        if not params or (not has_kwargs and not supports_param_dict):
            return False, "execute() must support parameters dict or **kwargs"

        try:
            capabilities = tool_instance.get_capabilities()
        except Exception as exc:
            return False, f"get_capabilities() failed: {exc}"

        if not capabilities:
            return False, "No capabilities registered"

        for cap_name, capability in capabilities.items():
            for param in getattr(capability, "parameters", []) or []:
                if getattr(param, "required", True) and getattr(param, "default", None) is not None:
                    return False, (
                        f"Capability '{cap_name}' has parameter '{param.name}' with "
                        "required=True and a default value"
                    )
            handler_name = f"_handle_{cap_name}"
            handler = getattr(tool_instance, handler_name, None)
            if not callable(handler):
                return False, f"Missing capability handler: {handler_name}"

        return True, ""


def activate_tool(
    tool_id: str,
    pending_tools_manager,
    tool_registrar,
    registry_manager: Optional[Any] = None,
) -> Dict[str, Any]:
    """Compatibility helper for older callers expecting a function API."""

    return ActivateToolUseCase(
        pending_tools_manager=pending_tools_manager,
        tool_registrar=tool_registrar,
        registry_manager=registry_manager,
    ).execute(tool_id)


__all__ = ["ActivateToolUseCase", "activate_tool"]
