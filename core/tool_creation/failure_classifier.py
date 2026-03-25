"""
CreationFailureClassifier — classifies tool creation failures into typed categories
so the retry loop uses the right strategy instead of blindly retrying.

Failure types:
  DEP_BLOCKED   — blocked/uninstallable library (pandas, graphviz, etc.) — stop retrying
  OVERFLOW      — spec too large / LLM returned empty code — reduce scope
  PATTERN_LOOP  — same error fingerprint repeating — constrained rewrite
  INFRA         — pipeline bug (file not found, class not found) — fix pipeline
  UNKNOWN       — default retry
"""
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Libraries that cannot be installed in the CUA environment
_BLOCKED_LIBS = {
    "pandas", "numpy", "graphviz", "matplotlib", "plotly", "scipy",
    "sklearn", "tensorflow", "torch", "PIL", "cv2", "seaborn",
}


@dataclass
class CreationFailureContext:
    failure_type: str           # DEP_BLOCKED | OVERFLOW | PATTERN_LOOP | INFRA | UNKNOWN
    tool_name: str
    step: str
    last_error: str
    prior_attempts: int
    error_fingerprint: str      # md5[:10] of step:error
    recommended_strategy: str   # DepBlocked | ReduceScope | ConstrainedRewrite | InfraRepair | Default
    should_abort: bool          # True = stop all retries immediately


class CreationFailureClassifier:
    """Classifies a creation failure and recommends the appropriate retry strategy."""

    def classify(
        self,
        tool_name: str,
        step: str,
        error: str,
        prior_attempts: int,
    ) -> CreationFailureContext:
        err_lower = (error or "").lower()
        fingerprint = hashlib.md5(f"{step}:{error[:120]}".encode()).hexdigest()[:10]

        # --- DEP_BLOCKED: blocked library — never retryable ---
        for lib in _BLOCKED_LIBS:
            if lib.lower() in err_lower:
                return self._ctx(tool_name, "DEP_BLOCKED", step, error, prior_attempts,
                                 fingerprint, "DepBlocked", should_abort=True)

        if "missing required library" in err_lower or "installation failed" in err_lower:
            return self._ctx(tool_name, "DEP_BLOCKED", step, error, prior_attempts,
                             fingerprint, "DepBlocked", should_abort=True)

        # --- OVERFLOW: empty/too-short code output on large spec ---
        if step in ("code_generation", "sandbox") and (
            "empty" in err_lower or "too short" in err_lower or "no class" in err_lower
        ):
            return self._ctx(tool_name, "OVERFLOW", step, error, prior_attempts,
                             fingerprint, "ReduceScope", should_abort=False)

        # --- INFRA: pipeline bugs ---
        if "tool file not found" in err_lower or "could not load tool class" in err_lower:
            return self._ctx(tool_name, "INFRA", step, error, prior_attempts,
                             fingerprint, "InfraRepair", should_abort=False)

        if "failed to generate tool spec" in err_lower or "llm returned none" in err_lower:
            return self._ctx(tool_name, "INFRA", step, error, prior_attempts,
                             fingerprint, "InfraRepair", should_abort=False)

        # --- PATTERN_LOOP: same fingerprint seen before or too many attempts ---
        if prior_attempts >= 3 or self._seen_before(tool_name, fingerprint):
            return self._ctx(tool_name, "PATTERN_LOOP", step, error, prior_attempts,
                             fingerprint, "ConstrainedRewrite", should_abort=False)

        return self._ctx(tool_name, "UNKNOWN", step, error, prior_attempts,
                         fingerprint, "Default", should_abort=False)

    def record_attempt(self, tool_name: str, fingerprint: str) -> None:
        """Persist fingerprint so next cycle can detect pattern loops."""
        try:
            from core.cua_db import get_conn
            with get_conn() as conn:
                conn.execute(
                    """INSERT INTO evolution_constraints (tool_name, fingerprint, hit_count, created_at)
                       VALUES (?, ?, 1, datetime('now'))
                       ON CONFLICT(tool_name, fingerprint)
                       DO UPDATE SET hit_count = hit_count + 1""",
                    (tool_name, fingerprint)
                )
        except Exception:
            pass  # non-critical

    def _seen_before(self, tool_name: str, fingerprint: str) -> bool:
        try:
            from core.cua_db import get_conn
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT hit_count FROM evolution_constraints WHERE tool_name=? AND fingerprint=?",
                    (tool_name, fingerprint)
                ).fetchone()
            return bool(row and row[0] >= 1)
        except Exception:
            return False

    def _ctx(self, tool_name, ftype, step, error, attempts, fp, strategy, should_abort) -> CreationFailureContext:
        logger.info(f"[CreationClassifier] {tool_name}/{step} → {ftype} → {strategy} (attempts={attempts}, abort={should_abort})")
        return CreationFailureContext(
            failure_type=ftype,
            tool_name=tool_name,
            step=step,
            last_error=error,
            prior_attempts=attempts,
            error_fingerprint=fp,
            recommended_strategy=strategy,
            should_abort=should_abort,
        )
