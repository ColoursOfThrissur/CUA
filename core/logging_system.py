"""
Production Logging System - Structured JSON logs with levels
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from enum import Enum

class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class StructuredLogger:
    """JSON structured logger for production"""
    
    def __init__(self, log_dir: str = "./logs", service_name: str = "cua"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.service_name = service_name
        
        # Setup file handler
        log_file = self.log_dir / f"{service_name}.log"
        self.file_handler = logging.FileHandler(log_file)
        self.file_handler.setLevel(logging.DEBUG)
        
        # Setup logger
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.file_handler)
    
    def _log(self, level: LogLevel, message: str, **context):
        """Write structured log entry"""
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": self.service_name,
            "level": level.value,
            "message": message,
            **context
        }
        
        log_line = json.dumps(log_entry)
        
        if level == LogLevel.DEBUG:
            self.logger.debug(log_line)
        elif level == LogLevel.INFO:
            self.logger.info(log_line)
        elif level == LogLevel.WARNING:
            self.logger.warning(log_line)
        elif level == LogLevel.ERROR:
            self.logger.error(log_line)
        elif level == LogLevel.CRITICAL:
            self.logger.critical(log_line)
    
    def debug(self, message: str, **context):
        self._log(LogLevel.DEBUG, message, **context)
    
    def info(self, message: str, **context):
        self._log(LogLevel.INFO, message, **context)
    
    def warning(self, message: str, **context):
        self._log(LogLevel.WARNING, message, **context)
    
    def error(self, message: str, **context):
        self._log(LogLevel.ERROR, message, **context)
    
    def critical(self, message: str, **context):
        self._log(LogLevel.CRITICAL, message, **context)
    
    def log_request(self, session_id: str, user_message: str, **context):
        """Log user request"""
        self.info("user_request", session_id=session_id, user_message=user_message, **context)
    
    def log_plan_generation(self, plan_id: str, steps: int, confidence: float):
        """Log plan generation"""
        self.info("plan_generated", plan_id=plan_id, steps=steps, confidence=confidence)
    
    def log_execution(self, execution_id: str, status: str, steps_completed: int, steps_total: int):
        """Log execution progress"""
        self.info("execution_progress", execution_id=execution_id, status=status, 
                 steps_completed=steps_completed, steps_total=steps_total)
    
    def log_error(self, error_type: str, error_message: str, **context):
        """Log error with context"""
        self.error("error_occurred", error_type=error_type, error_message=error_message, **context)

# Global logger instance
_logger: Optional[StructuredLogger] = None

def get_logger(service_name: str = "cua") -> StructuredLogger:
    """Get or create global logger"""
    global _logger
    if _logger is None:
        _logger = StructuredLogger(service_name=service_name)
    return _logger
