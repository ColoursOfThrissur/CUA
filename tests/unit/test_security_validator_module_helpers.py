from infrastructure.validation.ast.security_validator import EnhancedCodeValidator


def test_security_validator_allows_module_level_helper_function_calls():
    code = """
from tools.tool_interface import BaseTool


def _normalize_period(period: str, default: str = "3mo") -> str:
    return default if not period else period


class FinancialAnalysisTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        pass

    def execute(self, operation: str, **kwargs):
        return self._handle_get_advisor_insight(**kwargs)

    def _handle_get_advisor_insight(self, **kwargs):
        period = _normalize_period(kwargs.get("period", "3mo"), default="3mo")
        return {"success": True, "period": period}
""".strip()

    validator = EnhancedCodeValidator()
    is_valid, error = validator.validate(code, "FinancialAnalysisTool")

    assert is_valid is True, error
