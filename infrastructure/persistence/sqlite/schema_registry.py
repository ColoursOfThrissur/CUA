"""Database schema registry for LLM-assisted database queries.

All tables live in data/cua.db (WAL mode, single file).
Legacy per-DB files are no longer written.
"""

DATABASE_SCHEMAS = {
    "cua.db": {
        "description": "Consolidated CUA database — all tables in one file with WAL mode",
        "tables": {
            "executions": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "correlation_id": "TEXT",
                    "parent_execution_id": "INTEGER",
                    "tool_name": "TEXT",
                    "operation": "TEXT",
                    "success": "INTEGER - 1/0",
                    "error": "TEXT",
                    "error_stack_trace": "TEXT",
                    "execution_time_ms": "REAL",
                    "parameters": "TEXT - JSON",
                    "output_data": "TEXT - JSON truncated at 10k",
                    "output_size": "INTEGER",
                    "risk_score": "REAL 0-1",
                    "timestamp": "REAL - Unix",
                    "created_at": "TEXT",
                },
                "indexes": ["tool_name", "timestamp", "correlation_id", "parent_execution_id"],
                "common_queries": [
                    "SELECT tool_name, COUNT(*), AVG(success) FROM executions GROUP BY tool_name",
                    "SELECT * FROM executions WHERE tool_name=? ORDER BY timestamp DESC LIMIT 20",
                    "SELECT * FROM executions WHERE success=0 ORDER BY timestamp DESC",
                ],
            },
            "execution_context": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "execution_id": "INTEGER FK executions",
                    "correlation_id": "TEXT",
                    "service_calls": "TEXT - JSON array",
                    "llm_calls_count": "INTEGER",
                    "llm_tokens_used": "INTEGER",
                    "created_at": "TEXT",
                },
                "indexes": ["execution_id"],
                "common_queries": ["SELECT * FROM execution_context WHERE execution_id=?"],
            },
            "evolution_runs": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "correlation_id": "TEXT",
                    "tool_name": "TEXT",
                    "user_prompt": "TEXT",
                    "status": "TEXT - success/failed/pending/approved",
                    "step": "TEXT",
                    "error_message": "TEXT",
                    "confidence": "REAL",
                    "health_before": "REAL",
                    "health_after": "REAL",
                    "timestamp": "TEXT",
                    "created_at": "DATETIME",
                },
                "indexes": ["tool_name", "status", "correlation_id"],
                "common_queries": [
                    "SELECT * FROM evolution_runs WHERE tool_name=? ORDER BY timestamp DESC",
                    "SELECT tool_name, AVG(health_after-health_before) FROM evolution_runs WHERE health_after IS NOT NULL GROUP BY tool_name",
                ],
            },
            "evolution_artifacts": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "evolution_id": "INTEGER FK evolution_runs",
                    "correlation_id": "TEXT",
                    "artifact_type": "TEXT - analysis/proposal/code/validation/sandbox/error",
                    "step": "TEXT",
                    "content": "TEXT",
                    "timestamp": "TEXT",
                    "created_at": "DATETIME",
                },
                "indexes": ["evolution_id", "artifact_type"],
                "common_queries": ["SELECT * FROM evolution_artifacts WHERE evolution_id=? ORDER BY timestamp"],
            },
            "tool_creations": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "correlation_id": "TEXT",
                    "tool_name": "TEXT",
                    "user_prompt": "TEXT",
                    "status": "TEXT - success/failed/pending",
                    "step": "TEXT",
                    "error_message": "TEXT",
                    "code_size": "INTEGER",
                    "capabilities_count": "INTEGER",
                    "timestamp": "REAL",
                    "created_at": "TEXT",
                },
                "indexes": ["tool_name", "status", "correlation_id"],
                "common_queries": [
                    "SELECT * FROM tool_creations WHERE tool_name=? ORDER BY timestamp DESC",
                    "SELECT status, COUNT(*) FROM tool_creations GROUP BY status",
                ],
            },
            "creation_artifacts": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "creation_id": "INTEGER FK tool_creations",
                    "correlation_id": "TEXT",
                    "artifact_type": "TEXT - spec/code/validation/sandbox",
                    "step": "TEXT",
                    "content": "TEXT",
                    "timestamp": "REAL",
                    "created_at": "TEXT",
                },
                "indexes": ["creation_id"],
                "common_queries": ["SELECT * FROM creation_artifacts WHERE creation_id=? ORDER BY timestamp"],
            },
            "logs": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "timestamp": "TEXT",
                    "correlation_id": "TEXT",
                    "service": "TEXT",
                    "level": "TEXT - info/warning/error/debug",
                    "message": "TEXT",
                    "context": "TEXT - JSON",
                    "created_at": "DATETIME",
                },
                "indexes": ["timestamp", "service", "level", "correlation_id"],
                "common_queries": [
                    "SELECT * FROM logs WHERE level='error' ORDER BY timestamp DESC LIMIT 20",
                    "SELECT service, COUNT(*) FROM logs GROUP BY service",
                ],
            },
            "conversations": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "session_id": "TEXT",
                    "timestamp": "REAL",
                    "role": "TEXT - user/assistant",
                    "content": "TEXT",
                    "metadata": "TEXT - JSON",
                },
                "indexes": ["session_id"],
                "common_queries": ["SELECT * FROM conversations WHERE session_id=? ORDER BY timestamp"],
            },
            "sessions": {
                "columns": {
                    "session_id": "TEXT PRIMARY KEY",
                    "user_preferences": "TEXT - JSON",
                    "active_goal": "TEXT",
                    "created_at": "TEXT",
                    "updated_at": "TEXT",
                },
                "indexes": ["session_id"],
                "pk": "session_id",
                "common_queries": ["SELECT * FROM sessions ORDER BY updated_at DESC"],
            },
            "learned_patterns": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "pattern_type": "TEXT",
                    "pattern_data": "TEXT - JSON",
                    "learned_at": "TEXT",
                },
                "indexes": ["pattern_type"],
                "common_queries": ["SELECT * FROM learned_patterns ORDER BY learned_at DESC LIMIT 20"],
            },
            "failures": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "timestamp": "TEXT",
                    "file_path": "TEXT",
                    "change_type": "TEXT",
                    "failure_reason": "TEXT",
                    "error_message": "TEXT",
                    "methods_affected": "TEXT",
                    "lines_changed": "INTEGER",
                    "metadata": "TEXT - JSON",
                },
                "indexes": ["timestamp", "file_path"],
                "common_queries": [
                    "SELECT failure_reason, COUNT(*) FROM failures GROUP BY failure_reason ORDER BY COUNT(*) DESC",
                    "SELECT * FROM failures ORDER BY timestamp DESC LIMIT 20",
                ],
            },
            "risk_weights": {
                "columns": {
                    "pattern": "TEXT PRIMARY KEY",
                    "weight": "REAL",
                    "failure_count": "INTEGER",
                    "last_updated": "TEXT",
                },
                "indexes": ["pattern"],
                "pk": "pattern",
                "common_queries": ["SELECT * FROM risk_weights ORDER BY weight DESC"],
            },
            "improvements": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "timestamp": "TEXT",
                    "file_path": "TEXT",
                    "change_type": "TEXT",
                    "description": "TEXT",
                    "patch": "TEXT",
                    "outcome": "TEXT - success/partial/failed",
                    "error_message": "TEXT",
                    "test_results": "TEXT - JSON",
                    "metrics": "TEXT - JSON",
                },
                "indexes": ["timestamp", "file_path", "outcome"],
                "common_queries": [
                    "SELECT change_type, COUNT(*) FROM improvements WHERE outcome='success' GROUP BY change_type",
                    "SELECT * FROM improvements ORDER BY timestamp DESC LIMIT 10",
                ],
            },
            "plan_history": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "plan_id": "TEXT",
                    "timestamp": "REAL",
                    "iteration": "INTEGER",
                    "description": "TEXT",
                    "proposal": "TEXT - JSON",
                    "patch": "TEXT",
                    "risk_level": "TEXT",
                    "test_result": "TEXT",
                    "apply_result": "TEXT",
                    "status": "TEXT - pending/applied/failed/rolled_back",
                    "rollback_commit": "TEXT",
                },
                "indexes": ["plan_id", "status"],
                "common_queries": [
                    "SELECT status, COUNT(*) FROM plan_history GROUP BY status",
                    "SELECT * FROM plan_history ORDER BY timestamp DESC LIMIT 10",
                ],
            },
            "worktree_events": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "timestamp": "TEXT",
                    "event_type": "TEXT",
                    "worktree_label": "TEXT",
                    "worktree_path": "TEXT",
                    "session_id": "TEXT",
                    "task_id": "TEXT",
                    "execution_id": "TEXT",
                    "details_json": "TEXT - JSON",
                },
                "indexes": ["timestamp", "event_type", "session_id", "worktree_label"],
                "common_queries": [
                    "SELECT event_type, COUNT(*) FROM worktree_events GROUP BY event_type",
                    "SELECT * FROM worktree_events ORDER BY id DESC LIMIT 20",
                ],
            },
            "improvement_metrics": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "timestamp": "REAL",
                    "iteration": "INTEGER",
                    "proposal_desc": "TEXT",
                    "risk_level": "TEXT",
                    "test_passed": "BOOLEAN",
                    "apply_success": "BOOLEAN",
                    "duration_seconds": "REAL",
                    "error_type": "TEXT",
                },
                "indexes": ["timestamp"],
                "common_queries": ["SELECT COUNT(*), AVG(test_passed), AVG(apply_success) FROM improvement_metrics"],
            },
            "tool_metrics_hourly": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "tool_name": "TEXT",
                    "hour_timestamp": "TEXT",
                    "total_executions": "INTEGER",
                    "successes": "INTEGER",
                    "failures": "INTEGER",
                    "avg_duration_ms": "REAL",
                    "error_rate_percent": "REAL",
                    "created_at": "TEXT",
                },
                "indexes": ["tool_name", "hour_timestamp"],
                "common_queries": [
                    "SELECT tool_name, SUM(total_executions), AVG(error_rate_percent) FROM tool_metrics_hourly GROUP BY tool_name",
                ],
            },
            "system_metrics_hourly": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "hour_timestamp": "TEXT",
                    "total_chat_requests": "INTEGER",
                    "total_tool_calls": "INTEGER",
                    "total_evolutions": "INTEGER",
                    "evolution_success_rate": "REAL",
                    "avg_response_time_ms": "REAL",
                    "unique_tools_used": "INTEGER",
                    "created_at": "TEXT",
                },
                "indexes": ["hour_timestamp"],
                "common_queries": ["SELECT * FROM system_metrics_hourly ORDER BY hour_timestamp DESC LIMIT 24"],
            },
            "auto_evolution_metrics": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "hour_timestamp": "TEXT",
                    "tools_analyzed": "INTEGER",
                    "evolutions_triggered": "INTEGER",
                    "evolutions_pending": "INTEGER",
                    "evolutions_approved": "INTEGER",
                    "evolutions_rejected": "INTEGER",
                    "avg_health_improvement": "REAL",
                    "created_at": "TEXT",
                },
                "indexes": ["hour_timestamp"],
                "common_queries": ["SELECT * FROM auto_evolution_metrics ORDER BY hour_timestamp DESC LIMIT 24"],
            },
            "resolved_gaps": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "capability": "TEXT NOT NULL",
                    "resolution_action": "TEXT - create_tool/reroute/mcp/api_wrap",
                    "tool_name": "TEXT",
                    "resolved_at": "TEXT",
                    "notes": "TEXT",
                },
                "indexes": ["capability", "resolved_at"],
                "common_queries": [
                    "SELECT * FROM resolved_gaps ORDER BY resolved_at DESC LIMIT 20",
                    "SELECT capability, resolution_action FROM resolved_gaps WHERE capability=?",
                ],
            },
        },
    }
}


def get_schema_for_database(db_name: str) -> dict:
    """Get schema for a specific database. Legacy DB names return empty dict."""
    return DATABASE_SCHEMAS.get(db_name, {})


def get_all_databases() -> list:
    return list(DATABASE_SCHEMAS.keys())


def get_schema_summary() -> str:
    lines = ["CUA Database Schema Summary\n"]
    for db_name, db_info in DATABASE_SCHEMAS.items():
        lines.append(f"\n{db_name}: {db_info['description']}")
        for table_name, table_info in db_info["tables"].items():
            lines.append(f"  Table: {table_name}")
            lines.append(f"    Columns: {', '.join(table_info['columns'].keys())}")
    return "\n".join(lines)


def get_schema_for_llm(db_name: str = None) -> str:
    schemas = {db_name: DATABASE_SCHEMAS.get(db_name)} if db_name else DATABASE_SCHEMAS
    lines = []
    for db, info in schemas.items():
        if not info:
            continue
        lines.append(f"Database: {db}")
        lines.append(f"Purpose: {info['description']}")
        for table, tinfo in info["tables"].items():
            lines.append(f"\nTable: {table}")
            lines.append("Columns:")
            for col, desc in tinfo["columns"].items():
                lines.append(f"  - {col}: {desc}")
            if tinfo.get("common_queries"):
                lines.append("Common queries:")
                for q in tinfo["common_queries"]:
                    lines.append(f"  - {q}")
        lines.append("")
    return "\n".join(lines)
