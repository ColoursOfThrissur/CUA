"""
EvolutionConstraintMemory — persists what the LLM cannot be trusted to remember.

Writes constraints to cua.db (evolution_constraints table).
Injected into every generation prompt for that tool so the model is told
the constraints explicitly rather than having to infer them from error history.
"""
import re
import hashlib
import logging
from typing import Optional
from core.sqlite_logging import get_logger

logger = get_logger("evolution_constraint_memory")

# DDL — called once on first use
_DDL = """
CREATE TABLE IF NOT EXISTS evolution_constraints (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name   TEXT NOT NULL,
    type        TEXT NOT NULL,
    value       TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    hit_count   INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(tool_name, fingerprint)
)
"""


class EvolutionConstraintMemory:
    """Persists per-tool evolution constraints extracted from failure errors."""

    def __init__(self):
        self._ensure_table()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_failure(self, tool_name: str, step: str, error: str) -> None:
        """Extract a constraint from a failure and persist it."""
        constraint = self._extract_constraint(step, error)
        if constraint:
            self._upsert(tool_name, constraint)

    def build_constraint_block(self, tool_name: str) -> str:
        """Return a formatted block to inject into every LLM prompt for this tool."""
        constraints = self._load(tool_name)
        if not constraints:
            return ""

        lines = ["HARD CONSTRAINTS — follow these exactly, no exceptions:"]
        for c in constraints:
            ctype, value = c["type"], c["value"]
            if ctype == "blocked_lib":
                lines.append(f"- DO NOT import or use '{value}'. It is not available in this environment.")
            elif ctype == "blocked_pattern":
                lines.append(f"- DO NOT write '{value}' anywhere in the code.")
            elif ctype == "forbidden_capability":
                lines.append(f"- DO NOT register or define capability '{value}'. It already exists — do not add a second registration.")
            elif ctype == "require_target_scope":
                lines.append(f"- Only rewrite the functions listed in target_functions. Do NOT rewrite the entire file.")
            elif ctype == "no_hardcoded_urls":
                lines.append("- DO NOT hardcode any URLs (e.g. example.com). Use kwargs parameters instead.")
        return "\n".join(lines)

    def get_failure_count(self, tool_name: str, fingerprint: str) -> int:
        """Return how many times this exact error fingerprint has been seen for this tool."""
        try:
            from core.cua_db import get_conn
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT hit_count FROM evolution_constraints WHERE tool_name=? AND fingerprint=?",
                    (tool_name, fingerprint)
                ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    @staticmethod
    def make_fingerprint(step: str, error: str) -> str:
        return hashlib.md5(f"{step}:{error[:120]}".encode()).hexdigest()[:10]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _extract_constraint(self, step: str, error: str) -> Optional[dict]:
        err_lower = error.lower()

        # Blocked library
        for lib in ("pandas", "numpy", "graphviz", "matplotlib", "plotly", "scipy",
                    "sklearn", "tensorflow", "torch", "PIL", "cv2"):
            if lib.lower() in err_lower:
                return {"type": "blocked_lib", "value": lib}

        # Hardcoded URL
        if "example.com" in err_lower or "hardcoded" in err_lower and "url" in err_lower:
            return {"type": "no_hardcoded_urls", "value": "example.com"}

        # Duplicate capability
        if "duplicate capability" in err_lower:
            m = re.search(r"'(\w+)'", error)
            if m:
                return {"type": "forbidden_capability", "value": m.group(1)}

        # Bare undefined function (ThreadPoolExecutor, output_validation, etc.)
        if "calls undefined function" in err_lower:
            m = re.search(r"undefined function '(\w+)\(\)'", error)
            if m:
                return {"type": "blocked_pattern", "value": f"{m.group(1)}()"}

        # Context overflow / empty code on large tool
        if step == "code_generation" and ("empty code" in err_lower or "empty output" in err_lower):
            return {"type": "require_target_scope", "value": "true"}

        return None

    def seed_known_constraints(self, tool_name: str) -> None:
        """Pre-seed universal constraints so they're injected from attempt 1.
        Called by flow.py before proposal generation.
        """
        universal = [
            {"type": "no_hardcoded_urls", "value": "example.com"},
            {"type": "blocked_lib", "value": "pandas"},
            {"type": "blocked_lib", "value": "graphviz"},
            {"type": "blocked_lib", "value": "matplotlib"},
        ]
        for c in universal:
            self._upsert(tool_name, c)

    def _upsert(self, tool_name: str, constraint: dict) -> None:
        fp = hashlib.md5(f"{constraint['type']}:{constraint['value']}".encode()).hexdigest()[:10]
        try:
            from core.cua_db import get_conn
            with get_conn() as conn:
                conn.execute("""
                    INSERT INTO evolution_constraints (tool_name, type, value, fingerprint)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(tool_name, fingerprint) DO UPDATE SET
                        hit_count = hit_count + 1,
                        updated_at = datetime('now')
                """, (tool_name, constraint["type"], constraint["value"], fp))
        except Exception as e:
            logger.warning(f"Could not persist constraint for {tool_name}: {e}")

    def _load(self, tool_name: str) -> list:
        try:
            from core.cua_db import get_conn
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT type, value FROM evolution_constraints WHERE tool_name=? ORDER BY hit_count DESC",
                    (tool_name,)
                ).fetchall()
            return [{"type": r[0], "value": r[1]} for r in rows]
        except Exception:
            return []

    def _ensure_table(self) -> None:
        try:
            from core.cua_db import get_conn
            with get_conn() as conn:
                conn.execute(_DDL)
        except Exception as e:
            logger.warning(f"Could not create evolution_constraints table: {e}")
