"""
Error Recovery System - Retry logic with exponential backoff
"""

import time
from typing import Callable, Any, Optional
from dataclasses import dataclass
from enum import Enum

class RecoveryStrategy(Enum):
    RETRY = "retry"
    SKIP = "skip"
    ABORT = "abort"
    FALLBACK = "fallback"

@dataclass
class RecoveryConfig:
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    strategy: RecoveryStrategy = RecoveryStrategy.RETRY

class ErrorRecovery:
    """Handles error recovery with configurable strategies"""
    
    def __init__(self, config: RecoveryConfig = None):
        self.config = config or RecoveryConfig()
    
    def execute_with_retry(self, func: Callable, *args, **kwargs) -> tuple[bool, Any, Optional[str]]:
        """Execute function with retry logic"""
        
        delay = self.config.initial_delay
        last_error = None
        
        for attempt in range(self.config.max_retries):
            try:
                result = func(*args, **kwargs)
                return True, result, None
                
            except Exception as e:
                last_error = str(e)
                
                if attempt < self.config.max_retries - 1:
                    time.sleep(delay)
                    delay = min(delay * self.config.backoff_factor, self.config.max_delay)
        
        return False, None, last_error
    
    def recover_step(self, step_func: Callable, fallback_func: Optional[Callable] = None) -> tuple[bool, Any, Optional[str]]:
        """Recover from step failure using configured strategy"""
        
        if self.config.strategy == RecoveryStrategy.RETRY:
            return self.execute_with_retry(step_func)
        
        elif self.config.strategy == RecoveryStrategy.FALLBACK and fallback_func:
            success, result, error = self.execute_with_retry(step_func)
            if not success:
                return self.execute_with_retry(fallback_func)
            return success, result, error
        
        elif self.config.strategy == RecoveryStrategy.SKIP:
            try:
                result = step_func()
                return True, result, None
            except Exception as e:
                return True, None, f"Skipped: {str(e)}"
        
        else:  # ABORT
            try:
                result = step_func()
                return True, result, None
            except Exception as e:
                return False, None, str(e)
