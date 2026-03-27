"""Circuit Breaker for tool execution - prevents repeated calls to broken tools."""
import time
import logging
from collections import deque
from threading import Lock
from typing import Dict, Optional
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitStats:
    """Per-tool circuit state with sliding window failure tracking."""
    state: CircuitState = CircuitState.CLOSED
    opened_at: float = 0
    last_failure_time: float = 0
    last_success_time: float = 0
    # Sliding window: True=success, False=failure, maxlen=50
    window: deque = field(default_factory=lambda: deque(maxlen=50))
    # Half-open probe counter
    half_open_successes: int = 0
    lock: Lock = field(default_factory=Lock, compare=False, repr=False)

    def failure_rate(self) -> float:
        if not self.window:
            return 0.0
        return self.window.count(False) / len(self.window)

    def total_calls(self) -> int:
        return len(self.window)

    def failure_count(self) -> int:
        return self.window.count(False)

    def success_count(self) -> int:
        return self.window.count(True)


class CircuitBreaker:
    """Circuit breaker with sliding window — thread-safe per-tool locking.

    Thresholds (configurable):
      OPEN  when failure_rate > open_threshold  (default 40%) with min 5 calls
      CLOSE when failure_rate < close_threshold (default 20%) after recovery
    """

    def __init__(
        self,
        failure_threshold: int = 5,       # kept for API compat, unused
        success_threshold: int = 2,
        timeout: int = 60,
        half_open_timeout: int = 30,
        open_threshold: float = 0.40,     # open  if rate > 40%
        close_threshold: float = 0.20,    # close if rate < 20%
        min_calls: int = 5,               # need at least N calls before tripping
    ):
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.open_threshold = open_threshold
        self.close_threshold = close_threshold
        self.min_calls = min_calls
        self.circuits: Dict[str, CircuitStats] = {}
        self._registry_lock = Lock()

    def call(self, tool_name: str, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        circuit = self._get_circuit(tool_name)

        with circuit.lock:
            if circuit.state == CircuitState.OPEN:
                if time.time() - circuit.opened_at > self.timeout:
                    logger.info(f"Circuit {tool_name}: OPEN -> HALF_OPEN (timeout expired)")
                    circuit.state = CircuitState.HALF_OPEN
                    circuit.half_open_successes = 0
                else:
                    raise CircuitBreakerError(f"Circuit breaker OPEN for {tool_name}")

        try:
            result = func(*args, **kwargs)
            self._on_success(tool_name)
            return result
        except Exception as e:
            self._on_failure(tool_name)
            raise e

    def _get_circuit(self, tool_name: str) -> CircuitStats:
        with self._registry_lock:
            if tool_name not in self.circuits:
                self.circuits[tool_name] = CircuitStats()
            return self.circuits[tool_name]

    def _on_success(self, tool_name: str):
        circuit = self._get_circuit(tool_name)
        with circuit.lock:
            circuit.window.append(True)
            circuit.last_success_time = time.time()

            if circuit.state == CircuitState.HALF_OPEN:
                circuit.half_open_successes += 1
                if circuit.half_open_successes >= self.success_threshold:
                    logger.info(f"Circuit {tool_name}: HALF_OPEN -> CLOSED (recovered, rate={circuit.failure_rate():.0%})")
                    circuit.state = CircuitState.CLOSED
            elif circuit.state == CircuitState.CLOSED:
                # Auto-recover: if rate drops below close_threshold, stay closed
                rate = circuit.failure_rate()
                if rate < self.close_threshold and len(circuit.window) >= self.min_calls:
                    pass  # already closed, nothing to do

    def _on_failure(self, tool_name: str):
        circuit = self._get_circuit(tool_name)
        with circuit.lock:
            circuit.window.append(False)
            circuit.last_failure_time = time.time()
            rate = circuit.failure_rate()

            if circuit.state == CircuitState.HALF_OPEN:
                logger.warning(f"Circuit {tool_name}: HALF_OPEN -> OPEN (still failing, rate={rate:.0%})")
                circuit.state = CircuitState.OPEN
                circuit.opened_at = time.time()
                circuit.half_open_successes = 0
            elif circuit.state == CircuitState.CLOSED:
                if len(circuit.window) >= self.min_calls and rate > self.open_threshold:
                    logger.error(f"Circuit {tool_name}: CLOSED -> OPEN (rate={rate:.0%} > {self.open_threshold:.0%}, window={len(circuit.window)})")
                    circuit.state = CircuitState.OPEN
                    circuit.opened_at = time.time()

    def get_state(self, tool_name: str) -> CircuitState:
        circuit = self._get_circuit(tool_name)
        with circuit.lock:
            return circuit.state

    def get_stats(self, tool_name: str) -> Dict:
        circuit = self._get_circuit(tool_name)
        with circuit.lock:
            return {
                "state": circuit.state.value,
                "failure_rate": round(circuit.failure_rate(), 3),
                "failure_count": circuit.failure_count(),
                "success_count": circuit.success_count(),
                "window_size": circuit.total_calls(),
                "last_failure": circuit.last_failure_time,
                "last_success": circuit.last_success_time,
            }

    def reset(self, tool_name: str):
        circuit = self._get_circuit(tool_name)
        with circuit.lock:
            logger.info(f"Circuit {tool_name}: Manual reset")
            circuit.window.clear()
            circuit.state = CircuitState.CLOSED
            circuit.opened_at = 0
            circuit.half_open_successes = 0

    def get_all_open_circuits(self) -> list:
        """Get list of all open circuits."""
        with self._registry_lock:
            names = list(self.circuits.keys())
        return [
            name for name in names
            if self.get_state(name) == CircuitState.OPEN
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
