"""
Retry Coordinator - Manages retry logic for code generation and sandbox testing
"""
from typing import Dict, Optional
from dataclasses import dataclass

@dataclass
class RetryState:
    attempt: int
    max_attempts: int
    stage: str  # 'code_generation' or 'sandbox_test'
    error_feedback: str
    
class RetryCoordinator:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.current_state = None
    
    def start_retry_cycle(self, stage: str):
        """Start new retry cycle"""
        self.current_state = RetryState(
            attempt=1,
            max_attempts=self.max_retries,
            stage=stage,
            error_feedback=""
        )
    
    def can_retry(self) -> bool:
        """Check if can retry"""
        if not self.current_state:
            return False
        return self.current_state.attempt < self.current_state.max_attempts
    
    def next_attempt(self, error: str):
        """Move to next attempt with error feedback"""
        if self.current_state:
            self.current_state.attempt += 1
            self.current_state.error_feedback = error
    
    def format_error_for_llm(self, error: str, context: Dict) -> str:
        """Format error message for LLM with specific guidance"""
        if not self.current_state:
            return error
        
        attempt = self.current_state.attempt
        max_attempts = self.current_state.max_attempts
        
        if self.current_state.stage == 'code_generation':
            # Add specific hints based on error type
            hints = []
            if 'indent' in error.lower():
                hints.append("Use exactly 4 spaces per indentation level")
                hints.append("Do NOT mix tabs and spaces")
            if 'unexpected' in error.lower():
                hints.append("Check that all code blocks are properly aligned")
            if 'json' in error.lower():
                hints.append("Output raw Python code, NOT JSON")
            
            hint_text = "\n".join(f"- {h}" for h in hints) if hints else ""
            
            return f"""Your code has validation errors (attempt {attempt}/{max_attempts}):

Error: {error}

{hint_text}

Fix the code to pass validation."""
        
        elif self.current_state.stage == 'sandbox_test':
            baseline = context.get('baseline_passed', 0)
            new_passed = context.get('tests_passed', 0)
            
            # Extract specific error type
            error_type = "Unknown error"
            if 'ImportError' in error or 'ModuleNotFoundError' in error:
                error_type = "Import error - check your imports"
            elif 'SyntaxError' in error:
                error_type = "Syntax error - check indentation and syntax"
            elif 'AttributeError' in error:
                error_type = "Attribute error - check method/variable names"
            elif 'AssertionError' in error:
                error_type = "Test assertion failed - check logic"
            
            return f"""Your code failed sandbox tests (attempt {attempt}/{max_attempts}):

Baseline: {baseline} tests passed
Your code: {new_passed} tests passed

Error type: {error_type}

Full error output:
{error[:3000]}

Fix the code to pass at least {baseline} tests."""
        
        return error
    
    def reset(self):
        """Reset retry state"""
        self.current_state = None
