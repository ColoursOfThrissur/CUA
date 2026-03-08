"""Circuit Breaker for tool execution - prevents repeated calls to broken tools."""
import time
import logging
from typing import Dict, Optional
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Circuit broken, reject calls
    HALF_OPEN = "half_open"  # Testing if tool recovered


@dataclass
class CircuitStats:
    """Statistics for a circuit"""
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0
    last_success_time: float = 0
    state: CircuitState = CircuitState.CLOSED
    opened_at: float = 0


class CircuitBreaker:
    """Circuit breaker pattern for tool execution"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: int = 60,
        half_open_timeout: int = 30
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.half_open_timeout = half_open_timeout
        
        self.circuits: Dict[str, CircuitStats] = {}
    
    def call(self, tool_name: str, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        circuit = self._get_circuit(tool_name)
        
        # Check if circuit is open
        if circuit.state == CircuitState.OPEN:
            if time.time() - circuit.opened_at > self.timeout:
                logger.info(f"Circuit {tool_name}: OPEN -> HALF_OPEN (timeout expired)")
                circuit.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerError(f"Circuit breaker OPEN for {tool_name}")
        
        # Execute function
        try:
            result = func(*args, **kwargs)
            self._on_success(tool_name)
            return result
        except Exception as e:
            self._on_failure(tool_name)
            raise e
    
    def _get_circuit(self, tool_name: str) -> CircuitStats:
        """Get or create circuit for tool"""
        if tool_name not in self.circuits:
            self.circuits[tool_name] = CircuitStats()
        return self.circuits[tool_name]
    
    def _on_success(self, tool_name: str):
        """Handle successful execution"""
        circuit = self._get_circuit(tool_name)
        circuit.success_count += 1
        circuit.last_success_time = time.time()
        
        if circuit.state == CircuitState.HALF_OPEN:
            if circuit.success_count >= self.success_threshold:
                logger.info(f"Circuit {tool_name}: HALF_OPEN -> CLOSED (recovered)")
                circuit.state = CircuitState.CLOSED
                circuit.failure_count = 0
                circuit.success_count = 0
    
    def _on_failure(self, tool_name: str):
        """Handle failed execution"""
        circuit = self._get_circuit(tool_name)
        circuit.failure_count += 1
        circuit.last_failure_time = time.time()
        
        if circuit.state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit {tool_name}: HALF_OPEN -> OPEN (still failing)")
            circuit.state = CircuitState.OPEN
            circuit.opened_at = time.time()
            circuit.success_count = 0
        elif circuit.failure_count >= self.failure_threshold:
            logger.error(f"Circuit {tool_name}: CLOSED -> OPEN (threshold reached: {circuit.failure_count} failures)")
            circuit.state = CircuitState.OPEN
            circuit.opened_at = time.time()
    
    def get_state(self, tool_name: str) -> CircuitState:
        """Get current circuit state"""
        return self._get_circuit(tool_name).state
    
    def get_stats(self, tool_name: str) -> Dict:
        """Get circuit statistics"""
        circuit = self._get_circuit(tool_name)
        return {
            "state": circuit.state.value,
            "failure_count": circuit.failure_count,
            "success_count": circuit.success_count,
            "last_failure": circuit.last_failure_time,
            "last_success": circuit.last_success_time
        }
    
    def reset(self, tool_name: str):
        """Manually reset circuit"""
        if tool_name in self.circuits:
            logger.info(f"Circuit {tool_name}: Manual reset")
            self.circuits[tool_name] = CircuitStats()
    
    def get_all_open_circuits(self) -> list:
        """Get list of all open circuits"""
        return [
            name for name, circuit in self.circuits.items()
            if circuit.state == CircuitState.OPEN
        ]


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open"""
    pass


# Global circuit breaker instance
_circuit_breaker = None

def get_circuit_breaker() -> CircuitBreaker:
    """Get global circuit breaker instance"""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker
