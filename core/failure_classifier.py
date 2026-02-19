"""
Failure Classifier - Classify failures and determine action
"""
from enum import Enum
from typing import Tuple

class FailureType(Enum):
    BASELINE_FAILURE = "baseline_failure"  # Fatal - stop loop
    SYNTAX_ERROR = "syntax_error"  # Regenerate
    INTEGRATION_ERROR = "integration_error"  # Retry merge
    TEST_REGRESSION = "test_regression"  # Reject proposal
    ENVIRONMENT_ERROR = "environment_error"  # Retry once
    UNKNOWN = "unknown"

class FailureAction(Enum):
    STOP_LOOP = "stop_loop"
    REGENERATE = "regenerate"
    RETRY_MERGE = "retry_merge"
    REJECT = "reject"
    RETRY_ONCE = "retry_once"

class FailureClassifier:
    @staticmethod
    def classify(error_message: str, context: dict) -> Tuple[FailureType, FailureAction]:
        """Classify failure and determine action"""
        error_lower = error_message.lower()
        
        # Baseline failure - FATAL
        if "baseline" in error_lower and "fail" in error_lower:
            return FailureType.BASELINE_FAILURE, FailureAction.STOP_LOOP
        
        # Syntax errors
        if any(x in error_lower for x in ["syntaxerror", "indentationerror", "unexpected indent"]):
            return FailureType.SYNTAX_ERROR, FailureAction.REGENERATE
        
        # Integration errors
        if any(x in error_lower for x in ["cannot merge", "integration failed", "duplicate class"]):
            return FailureType.INTEGRATION_ERROR, FailureAction.RETRY_MERGE
        
        # Test regression
        baseline_passed = context.get('baseline_passed', 0)
        tests_passed = context.get('tests_passed', 0)
        if baseline_passed > 0 and tests_passed < baseline_passed:
            return FailureType.TEST_REGRESSION, FailureAction.REJECT
        
        # Environment errors
        if any(x in error_lower for x in ["timeout", "connection", "network", "pytest not"]):
            return FailureType.ENVIRONMENT_ERROR, FailureAction.RETRY_ONCE
        
        return FailureType.UNKNOWN, FailureAction.REJECT
