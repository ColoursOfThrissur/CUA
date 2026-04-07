from infrastructure.validation.enhanced_code_validator import EnhancedCodeValidator


def _tool_with_missing_email_service() -> str:
    return """
from tools.tool_interface import BaseTool


class ExampleTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        pass

    def execute(self, operation: str, **kwargs):
        return self._handle_send(**kwargs)

    def _handle_send(self, **kwargs):
        return self.services.email.send(kwargs.get("value"))
""".strip()


def test_enhanced_validator_restores_service_registry_and_missing_services():
    validator = EnhancedCodeValidator()

    assert "browser" in validator.service_registry
    assert "navigate" in validator.service_registry["browser"]
    assert "call_tool" in validator.service_registry
    assert validator.service_registry["call_tool"] == []

    result = validator.validate(_tool_with_missing_email_service(), "ExampleTool")

    assert result["valid"] is False
    assert any("service" in error.lower() for error in result["errors"])
    assert validator.get_missing_services()
    assert validator.get_missing_services()[0]["service_name"] == "email"


def test_service_generation_integration_handles_missing_services_without_unpack_error(monkeypatch):
    from infrastructure.external import service_generation_integration as sgi_module

    class FakeGenerator:
        def generate_service_method(self, service_name, method_name, context):
            return {
                "success": True,
                "code": f"def {method_name}(self, value=None):\\n    return value",
                "service_name": service_name,
                "method_name": method_name,
            }

        def generate_full_service(self, service_name, methods, context):
            return {
                "success": True,
                "code": f"class {service_name.capitalize()}Service:\\n    pass",
                "service_name": service_name,
                "methods": methods,
            }

    class FakePendingManager:
        def __init__(self):
            self.pending = []

        def has_pending_service(self, service_name, method_name=None):
            return False

        def add_pending_service(self, service_name, method_name, code, context, requested_by):
            service_id = f"{service_name}_{method_name}_1"
            self.pending.append((service_id, service_name, method_name, code, context, requested_by))
            return service_id

        def add_pending_full_service(self, service_name, code, methods, context, requested_by):
            service_id = f"{service_name}_full_1"
            self.pending.append((service_id, service_name, None, code, context, requested_by))
            return service_id

    monkeypatch.setattr(sgi_module, "ServiceGenerator", FakeGenerator)
    monkeypatch.setattr(sgi_module, "PendingServicesManager", FakePendingManager)

    integration = sgi_module.ServiceGenerationIntegration()
    result = integration.validate_and_generate_services(
        _tool_with_missing_email_service(),
        class_name="ExampleTool",
        context="Need email sending",
        requested_by="tool_evolution",
    )

    assert result["valid"] is False
    assert result["pending_approval"] is True
    assert result["generated_services"]
    assert result["generated_services"][0]["service_name"] == "email"
    assert result["generated_services"][0]["type"] in {"full_service", "method"}
