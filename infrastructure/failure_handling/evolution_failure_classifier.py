"""
EvolutionFailureClassifier — classifies evolution failures into typed categories.

Four failure types, each with its own repair strategy:
  INFRA        — code bugs in the pipeline (file not found, tool not found)
  OVERFLOW     — LLM context overflow on large tools (>8KB, empty code output)
  PATTERN_LOOP — same error repeating across attempts (LLM ignoring feedback)
  DEP_BLOCKED  — dependency that can never be satisfied (pandas, graphviz)
"""
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from infrastructure.persistence.sqlite.logging import get_logger

logger = get_logger("failure_classifier")

# Size threshold above which chunked evolution is used
OVERFLOW_SIZE_BYTES = 8_000


@dataclass
class EvolutionContext:
    failure_type: str           # INFRA | OVERFLOW | PATTERN_LOOP | DEP_BLOCKED | UNKNOWN
    tool_name: str
    tool_size_bytes: int
    prior_attempts: int
    last_error: str
    error_fingerprint: str      # md5[:10] of step:error — used to detect identical retries
    recommended_strategy: str   # InfraRepair | ChunkEvolution | ConstrainedRewrite | DepBlocked | Default


class EvolutionFailureClassifier:
    """Classifies a failure and recommends the appropriate repair strategy."""

    # Libraries that can never be installed in the CUA environment
    _BLOCKED_LIBS = {
        "pandas", "numpy", "graphviz", "matplotlib", "plotly", "scipy",
        "sklearn", "tensorflow", "torch", "PIL", "cv2",
    }

    def classify(
        self,
        tool_name: str,
        step: str,
        error: str,
        prior_attempts: int,
    ) -> EvolutionContext:
        tool_path = self._find_tool(tool_name)
        size = tool_path.stat().st_size if tool_path else 0
        err_lower = error.lower()
        fingerprint = hashlib.md5(f"{step}:{error[:120]}".encode()).hexdigest()[:10]

        # --- Type A: Infrastructure bugs (deterministic, fix in code) ---
        if step == "analysis" and "could not analyze" in err_lower:
            return self._ctx(tool_name, "INFRA", size, prior_attempts, error,
                             fingerprint, "InfraRepair")

        if "file not found" in err_lower and ("storage" in err_lower or "data/" in err_lower):
            return self._ctx(tool_name, "INFRA", size, prior_attempts, error,
                             fingerprint, "InfraRepair")

        # --- Type D: Dependency blocked (specific, never retryable) ---
        for lib in self._BLOCKED_LIBS:
            if lib.lower() in err_lower:
                return self._ctx(tool_name, "DEP_BLOCKED", size, prior_attempts, error,
                                 fingerprint, "DepBlocked")

        if "missing dependencies" in err_lower or "libraries:" in err_lower:
            return self._ctx(tool_name, "DEP_BLOCKED", size, prior_attempts, error,
                             fingerprint, "DepBlocked")

        # --- Type B: Context overflow (large tool + empty/syntax output) ---
        is_empty_output = (
            step == "code_generation"
            and ("empty code" in err_lower or "empty output" in err_lower or not error.strip())
        )
        is_syntax_on_large = (
            step == "code_generation"
            and "syntax error" in err_lower
            and size > OVERFLOW_SIZE_BYTES
        )
        if (is_empty_output or is_syntax_on_large) and size > OVERFLOW_SIZE_BYTES:
            return self._ctx(tool_name, "OVERFLOW", size, prior_attempts, error,
                             fingerprint, "ChunkEvolution")

        # --- Type C: Pattern loop (same fingerprint seen before, or 2+ attempts) ---
        if prior_attempts >= 2 or self._seen_before(tool_name, fingerprint):
            return self._ctx(tool_name, "PATTERN_LOOP", size, prior_attempts, error,
                             fingerprint, "ConstrainedRewrite")

        return self._ctx(tool_name, "UNKNOWN", size, prior_attempts, error,
                         fingerprint, "Default")

    # ------------------------------------------------------------------

    def _ctx(self, tool_name, ftype, size, attempts, error, fp, strategy) -> EvolutionContext:
        logger.info(f"[Classifier] {tool_name} → {ftype} → {strategy} (size={size}, attempts={attempts})")
        return EvolutionContext(
            failure_type=ftype,
            tool_name=tool_name,
            tool_size_bytes=size,
            prior_attempts=attempts,
            last_error=error,
            error_fingerprint=fp,
            recommended_strategy=strategy,
        )

    def _seen_before(self, tool_name: str, fingerprint: str) -> bool:
        """Check if this exact error fingerprint has been seen for this tool before."""
        try:
            from infrastructure.persistence.sqlite.cua_database import get_conn
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT hit_count FROM evolution_constraints WHERE tool_name=? AND fingerprint=?",
                    (tool_name, fingerprint)
                ).fetchone()
            return bool(row and row[0] >= 1)
        except Exception:
            return False

    def _find_tool(self, tool_name: str) -> Optional[Path]:
        """Quick file lookup — exact case first."""
        for base in [Path("tools/experimental"), Path("tools")]:
            p = base / f"{tool_name}.py"
            if p.exists():
                return p
        return None
