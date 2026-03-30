"""
Central SQLite access layer — all CUA tables live in data/cua.db.

WAL mode is enabled once at startup so concurrent readers never block writers.
A module-level lock serialises writes from parallel tool executions.

Usage (internal loggers):
    from infrastructure.persistence.sqlite.cua_database import get_conn, DB_PATH

    with get_conn() as conn:
        conn.execute("INSERT INTO ...")
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Iterator
from contextlib import contextmanager

DB_PATH = Path("data/cua.db")

_lock = threading.Lock()
_initialised = False


def _ensure_init() -> None:
    global _initialised
    if _initialised:
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _create_all_tables(conn)
        conn.commit()
    _initialised = True


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Context manager — yields a connection serialised by the module lock."""
    _ensure_init()
    with _lock:
        conn = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Schema — all tables in one place
# ---------------------------------------------------------------------------

def _create_all_tables(conn: sqlite3.Connection) -> None:
    stmts = [
        # ── tool_executions ──────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            correlation_id TEXT,
            parent_execution_id INTEGER,
            tool_name TEXT NOT NULL,
            operation TEXT NOT NULL,
            success INTEGER NOT NULL,
            error TEXT,
            error_stack_trace TEXT,
            execution_time_ms REAL,
            parameters TEXT,
            output_data TEXT,
            output_size INTEGER,
            risk_score REAL,
            timestamp REAL NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_exec_tool ON executions(tool_name)",
        "CREATE INDEX IF NOT EXISTS idx_exec_ts ON executions(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_exec_corr ON executions(correlation_id)",
        "CREATE INDEX IF NOT EXISTS idx_exec_parent ON executions(parent_execution_id)",

        """CREATE TABLE IF NOT EXISTS execution_context (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id INTEGER NOT NULL,
            correlation_id TEXT,
            service_calls TEXT,
            llm_calls_count INTEGER DEFAULT 0,
            llm_tokens_used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (execution_id) REFERENCES executions(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_exec_ctx_eid ON execution_context(execution_id)",

        # ── tool_evolution ───────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS evolution_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            correlation_id TEXT,
            tool_name TEXT NOT NULL,
            user_prompt TEXT,
            status TEXT NOT NULL,
            step TEXT,
            error_message TEXT,
            confidence REAL,
            health_before REAL,
            health_after REAL,
            timestamp TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_evo_tool ON evolution_runs(tool_name)",
        "CREATE INDEX IF NOT EXISTS idx_evo_status ON evolution_runs(status)",
        "CREATE INDEX IF NOT EXISTS idx_evo_corr ON evolution_runs(correlation_id)",

        """CREATE TABLE IF NOT EXISTS evolution_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evolution_id INTEGER NOT NULL,
            correlation_id TEXT,
            artifact_type TEXT NOT NULL,
            step TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (evolution_id) REFERENCES evolution_runs(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_evo_art_eid ON evolution_artifacts(evolution_id)",
        "CREATE INDEX IF NOT EXISTS idx_evo_art_type ON evolution_artifacts(artifact_type)",

        # ── tool_creation ────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS tool_creations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            correlation_id TEXT,
            tool_name TEXT NOT NULL,
            user_prompt TEXT,
            status TEXT NOT NULL,
            step TEXT,
            error_message TEXT,
            code_size INTEGER,
            capabilities_count INTEGER,
            timestamp REAL NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_tc_tool ON tool_creations(tool_name)",
        "CREATE INDEX IF NOT EXISTS idx_tc_status ON tool_creations(status)",
        "CREATE INDEX IF NOT EXISTS idx_tc_corr ON tool_creations(correlation_id)",

        """CREATE TABLE IF NOT EXISTS creation_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creation_id INTEGER NOT NULL,
            correlation_id TEXT,
            artifact_type TEXT NOT NULL,
            step TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp REAL NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (creation_id) REFERENCES tool_creations(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_ca_cid ON creation_artifacts(creation_id)",

        # ── logs ─────────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            correlation_id TEXT,
            service TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            context TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_log_ts ON logs(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_log_svc ON logs(service)",
        "CREATE INDEX IF NOT EXISTS idx_log_lvl ON logs(level)",
        "CREATE INDEX IF NOT EXISTS idx_log_corr ON logs(correlation_id)",

        # ── conversations / chat ─────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            timestamp REAL,
            role TEXT,
            content TEXT,
            metadata TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_conv_sess ON conversations(session_id)",

        """CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_preferences TEXT,
            active_goal TEXT,
            created_at TEXT,
            updated_at TEXT
        )""",

        """CREATE TABLE IF NOT EXISTS learned_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT,
            pattern_data TEXT,
            learned_at TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_lp_type ON learned_patterns(pattern_type)",

        # ── analytics ────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS improvement_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            iteration INTEGER,
            proposal_desc TEXT,
            risk_level TEXT,
            test_passed BOOLEAN,
            apply_success BOOLEAN,
            duration_seconds REAL,
            error_type TEXT
        )""",

        """CREATE TABLE IF NOT EXISTS attempt_terminal_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            iteration INTEGER,
            file_path TEXT,
            status TEXT,
            generated INTEGER,
            sandbox_passed INTEGER,
            applied INTEGER
        )""",

        # ── failure_patterns ─────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            file_path TEXT,
            change_type TEXT,
            failure_reason TEXT,
            error_message TEXT,
            methods_affected TEXT,
            lines_changed INTEGER,
            metadata TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_fail_ts ON failures(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_fail_fp ON failures(file_path)",

        """CREATE TABLE IF NOT EXISTS risk_weights (
            pattern TEXT PRIMARY KEY,
            weight REAL,
            failure_count INTEGER,
            last_updated TEXT
        )""",

        # ── improvement_memory ───────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS improvements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            file_path TEXT,
            change_type TEXT,
            description TEXT,
            patch TEXT,
            outcome TEXT,
            error_message TEXT,
            test_results TEXT,
            metrics TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_imp_ts ON improvements(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_imp_fp ON improvements(file_path)",

        # ── plan_history ─────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS plan_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id TEXT,
            timestamp REAL,
            iteration INTEGER,
            description TEXT,
            proposal TEXT,
            patch TEXT,
            risk_level TEXT,
            test_result TEXT,
            apply_result TEXT,
            status TEXT,
            rollback_commit TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_ph_pid ON plan_history(plan_id)",
        "CREATE INDEX IF NOT EXISTS idx_ph_status ON plan_history(status)",

        # ── metrics ──────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS tool_metrics_hourly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT,
            hour_timestamp TEXT,
            total_executions INTEGER,
            successes INTEGER,
            failures INTEGER,
            avg_duration_ms REAL,
            p50_duration_ms REAL,
            p95_duration_ms REAL,
            p99_duration_ms REAL,
            error_rate_percent REAL,
            avg_output_size REAL,
            created_at TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_tmh_tool ON tool_metrics_hourly(tool_name)",

        """CREATE TABLE IF NOT EXISTS system_metrics_hourly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hour_timestamp TEXT,
            total_chat_requests INTEGER,
            total_tool_calls INTEGER,
            total_evolutions INTEGER,
            evolution_success_rate REAL,
            avg_response_time_ms REAL,
            unique_tools_used INTEGER,
            created_at TEXT
        )""",

        """CREATE TABLE IF NOT EXISTS auto_evolution_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hour_timestamp TEXT,
            tools_analyzed INTEGER,
            evolutions_triggered INTEGER,
            evolutions_pending INTEGER,
            evolutions_approved INTEGER,
            evolutions_rejected INTEGER,
            avg_health_improvement REAL,
            created_at TEXT
        )""",

        # ── resolved_gaps (capability resolver feedback loop) ─────────────
        """CREATE TABLE IF NOT EXISTS resolved_gaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capability TEXT NOT NULL,
            resolution_action TEXT,
            tool_name TEXT,
            resolved_at TEXT NOT NULL,
            notes TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_rg_cap ON resolved_gaps(capability)",
        "CREATE INDEX IF NOT EXISTS idx_rg_ts ON resolved_gaps(resolved_at)",
        
        # ── screen_cache (semantic caching for vision) ────────────────────
        """CREATE TABLE IF NOT EXISTS screen_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            perceptual_hash TEXT NOT NULL UNIQUE,
            screen_analysis TEXT NOT NULL,
            ui_elements TEXT,
            visual_state TEXT,
            image_path TEXT,
            hit_count INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            last_accessed TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_sc_hash ON screen_cache(perceptual_hash)",
        "CREATE INDEX IF NOT EXISTS idx_sc_accessed ON screen_cache(last_accessed)",
        
        # ── trajectory_memory (successful action sequences) ────────────────
        """CREATE TABLE IF NOT EXISTS trajectory_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            intent_pattern TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            success_count INTEGER DEFAULT 1,
            failure_count INTEGER DEFAULT 0,
            avg_execution_time_ms REAL,
            last_used TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_tm_pattern ON trajectory_memory(intent_pattern)",
        "CREATE INDEX IF NOT EXISTS idx_tm_success ON trajectory_memory(success_count)",
        
        # ── execution_telemetry (detailed performance metrics) ─────────────
        """CREATE TABLE IF NOT EXISTS execution_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id INTEGER,
            tool_name TEXT NOT NULL,
            operation TEXT NOT NULL,
            duration_ms REAL NOT NULL,
            retry_count INTEGER DEFAULT 0,
            self_healed INTEGER DEFAULT 0,
            error_type TEXT,
            cache_hit INTEGER DEFAULT 0,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (execution_id) REFERENCES executions(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_et_tool ON execution_telemetry(tool_name)",
        "CREATE INDEX IF NOT EXISTS idx_et_op ON execution_telemetry(operation)",
        "CREATE INDEX IF NOT EXISTS idx_et_ts ON execution_telemetry(timestamp)",
    ]
    for stmt in stmts:
        conn.execute(stmt)
