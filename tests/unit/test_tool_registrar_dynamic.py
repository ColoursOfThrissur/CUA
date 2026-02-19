from core.tool_registrar import ToolRegistrar
from tools.capability_registry import CapabilityRegistry


def test_register_new_tool_resolves_non_filename_class():
    registry = CapabilityRegistry()
    registrar = ToolRegistrar(registry)

    result = registrar.register_new_tool("tools/experimental/SyntaxGuardRetryAfterSanitization.py")

    assert result["success"] is True
    assert result["tool_name"] == "SyntaxGuardRetryAfterSanitization"
    assert "sanitize_and_validate" in result["capabilities"]
