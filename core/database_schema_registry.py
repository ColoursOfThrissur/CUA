"""Database schema registry for LLM-assisted database queries."""

DATABASE_SCHEMAS = {
    "tool_creation.db": {
        "description": "Tool creation attempts and outcomes",
        "tables": {
            "tool_creations": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "correlation_id": "TEXT - Request correlation ID",
                    "tool_name": "TEXT - Name of tool being created",
                    "user_prompt": "TEXT - User's creation request",
                    "status": "TEXT - 'success', 'failed', 'pending'",
                    "step": "TEXT - Last completed step",
                    "error_message": "TEXT - Error if failed",
                    "code_size": "INTEGER - Size of generated code",
                    "capabilities_count": "INTEGER - Number of capabilities",
                    "timestamp": "REAL - Unix timestamp",
                    "created_at": "TEXT - ISO format timestamp"
                },
                "indexes": ["tool_name", "status", "timestamp", "correlation_id"],
                "common_queries": [
                    "SELECT * FROM tool_creations WHERE tool_name=? ORDER BY timestamp DESC",
                    "SELECT status, COUNT(*) FROM tool_creations GROUP BY status",
                    "SELECT * FROM tool_creations WHERE status='failed' ORDER BY timestamp DESC",
                    "SELECT * FROM tool_creations WHERE correlation_id=?"
                ]
            },
            "creation_artifacts": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "creation_id": "INTEGER - FK to tool_creations",
                    "correlation_id": "TEXT - Request correlation ID",
                    "artifact_type": "TEXT - spec, code, validation, sandbox",
                    "step": "TEXT - Step that produced artifact",
                    "content": "TEXT - Artifact content",
                    "timestamp": "REAL - Unix timestamp",
                    "created_at": "TEXT - ISO format timestamp"
                },
                "indexes": ["creation_id", "artifact_type"],
                "common_queries": [
                    "SELECT * FROM creation_artifacts WHERE creation_id=? ORDER BY timestamp"
                ]
            }
        }
    },
    
    "chat_history.db": {
        "description": "Alternative chat history storage",
        "tables": {
            "messages": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "session_id": "TEXT - Session identifier",
                    "timestamp": "REAL - Unix timestamp",
                    "role": "TEXT - 'user' or 'assistant'",
                    "content": "TEXT - Message content",
                    "metadata": "TEXT - Additional metadata as JSON"
                },
                "indexes": ["session_id", "timestamp"],
                "common_queries": [
                    "SELECT * FROM messages WHERE session_id=? ORDER BY timestamp",
                    "SELECT DISTINCT session_id FROM messages ORDER BY timestamp DESC",
                    "SELECT * FROM messages ORDER BY timestamp DESC LIMIT 50"
                ]
            }
        }
    },
    
    "logs.db": {
        "description": "System logs from all services",
        "tables": {
            "logs": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "timestamp": "TEXT - ISO format timestamp",
                    "correlation_id": "TEXT - Request correlation ID",
                    "service": "TEXT - Service name that generated log",
                    "level": "TEXT - Log level (info, warning, error, debug)",
                    "message": "TEXT - Log message content",
                    "context": "TEXT - Additional context as JSON",
                    "created_at": "DATETIME"
                },
                "indexes": ["timestamp", "service", "level", "correlation_id"],
                "common_queries": [
                    "SELECT * FROM logs WHERE level='error' ORDER BY timestamp DESC LIMIT 10",
                    "SELECT service, COUNT(*) FROM logs GROUP BY service",
                    "SELECT * FROM logs WHERE service='tool.ContextSummarizerTool' ORDER BY timestamp DESC",
                    "SELECT * FROM logs WHERE correlation_id=? ORDER BY timestamp"
                ]
            }
        }
    },
    
    "conversations.db": {
        "description": "Chat conversation history",
        "tables": {
            "conversations": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "session_id": "TEXT - Unique session identifier",
                    "timestamp": "REAL - Unix timestamp",
                    "role": "TEXT - 'user' or 'assistant'",
                    "content": "TEXT - Message content",
                    "metadata": "TEXT - Additional metadata as JSON"
                },
                "indexes": ["session_id", "timestamp"],
                "common_queries": [
                    "SELECT * FROM conversations WHERE session_id=? ORDER BY timestamp",
                    "SELECT DISTINCT session_id FROM conversations ORDER BY timestamp DESC",
                    "SELECT role, content FROM conversations ORDER BY timestamp DESC LIMIT 10"
                ]
            }
        }
    },
    
    "tool_executions.db": {
        "description": "Tool execution history and performance metrics",
        "tables": {
            "executions": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "correlation_id": "TEXT - Request correlation ID",
                    "parent_execution_id": "INTEGER - Parent execution for nested calls",
                    "tool_name": "TEXT - Name of the tool",
                    "operation": "TEXT - Operation/capability name",
                    "success": "INTEGER - 1 for success, 0 for failure",
                    "error": "TEXT - Error message if failed",
                    "error_stack_trace": "TEXT - Full stack trace",
                    "execution_time_ms": "REAL - Execution time in milliseconds",
                    "parameters": "TEXT - Input parameters as JSON",
                    "output_data": "TEXT - Full output data (truncated)",
                    "output_size": "INTEGER - Size of output in bytes",
                    "timestamp": "REAL - Unix timestamp",
                    "created_at": "TEXT - ISO format timestamp",
                    "risk_score": "REAL - Risk score 0-1"
                },
                "indexes": ["tool_name", "operation", "success", "timestamp", "correlation_id", "parent_execution_id"],
                "common_queries": [
                    "SELECT tool_name, COUNT(*) as count, AVG(success) as success_rate FROM executions GROUP BY tool_name",
                    "SELECT * FROM executions WHERE tool_name=? ORDER BY timestamp DESC LIMIT 20",
                    "SELECT * FROM executions WHERE success=0 ORDER BY timestamp DESC",
                    "SELECT * FROM executions WHERE correlation_id=? ORDER BY timestamp",
                    "SELECT * FROM executions WHERE parent_execution_id=?"
                ]
            },
            "execution_context": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "execution_id": "INTEGER - FK to executions",
                    "correlation_id": "TEXT - Request correlation ID",
                    "service_calls": "TEXT - Services used as JSON array",
                    "llm_calls_count": "INTEGER - Number of LLM calls",
                    "llm_tokens_used": "INTEGER - Total tokens used",
                    "created_at": "TEXT - ISO format timestamp"
                },
                "indexes": ["execution_id"],
                "common_queries": [
                    "SELECT * FROM execution_context WHERE execution_id=?"
                ]
            }
        }
    },
    
    "tool_evolution.db": {
        "description": "Tool evolution attempts and results",
        "tables": {
            "evolution_runs": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "correlation_id": "TEXT - Request correlation ID",
                    "tool_name": "TEXT - Name of tool being evolved",
                    "user_prompt": "TEXT - User's improvement request",
                    "status": "TEXT - 'success', 'failed', 'pending', 'approved'",
                    "step": "TEXT - Last completed step",
                    "error_message": "TEXT - Error if failed",
                    "confidence": "REAL - Confidence score 0-1",
                    "health_before": "REAL - Health score before evolution",
                    "health_after": "REAL - Health score after evolution",
                    "timestamp": "TEXT - ISO format timestamp",
                    "created_at": "DATETIME"
                },
                "indexes": ["tool_name", "status", "timestamp", "correlation_id"],
                "common_queries": [
                    "SELECT * FROM evolution_runs WHERE tool_name=? ORDER BY timestamp DESC",
                    "SELECT tool_name, COUNT(*) as attempts, SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as successes FROM evolution_runs GROUP BY tool_name",
                    "SELECT * FROM evolution_runs WHERE status='failed' ORDER BY timestamp DESC",
                    "SELECT * FROM evolution_runs WHERE correlation_id=? ORDER BY timestamp",
                    "SELECT tool_name, AVG(health_after - health_before) as avg_improvement FROM evolution_runs WHERE health_after IS NOT NULL GROUP BY tool_name"
                ]
            },
            "evolution_artifacts": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "evolution_id": "INTEGER - FK to evolution_runs",
                    "correlation_id": "TEXT - Request correlation ID",
                    "artifact_type": "TEXT - analysis, proposal, code, validation, sandbox, error",
                    "step": "TEXT - Step that produced artifact",
                    "content": "TEXT - Artifact content",
                    "timestamp": "TEXT - ISO format timestamp",
                    "created_at": "DATETIME"
                },
                "indexes": ["evolution_id", "artifact_type"],
                "common_queries": [
                    "SELECT * FROM evolution_artifacts WHERE evolution_id=? ORDER BY timestamp",
                    "SELECT * FROM evolution_artifacts WHERE artifact_type='error' ORDER BY timestamp DESC"
                ]
            }
        }
    },
    
    "analytics.db": {
        "description": "Self-improvement metrics and analytics",
        "tables": {
            "improvement_metrics": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "timestamp": "REAL - Unix timestamp",
                    "iteration": "INTEGER - Iteration number",
                    "proposal_desc": "TEXT - Description of proposal",
                    "risk_level": "TEXT - 'low', 'medium', 'high'",
                    "test_passed": "BOOLEAN - Whether tests passed",
                    "apply_success": "BOOLEAN - Whether changes applied successfully",
                    "duration_seconds": "REAL - Duration of iteration",
                    "error_type": "TEXT - Type of error if failed"
                },
                "indexes": ["timestamp", "iteration", "risk_level"],
                "common_queries": [
                    "SELECT COUNT(*), AVG(test_passed), AVG(apply_success) FROM improvement_metrics",
                    "SELECT risk_level, COUNT(*) FROM improvement_metrics GROUP BY risk_level",
                    "SELECT * FROM improvement_metrics ORDER BY timestamp DESC LIMIT 10"
                ]
            }
        }
    },
    
    "failure_patterns.db": {
        "description": "Failed changes and error patterns",
        "tables": {
            "failures": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "timestamp": "TEXT - ISO format timestamp",
                    "file_path": "TEXT - Path to file that failed",
                    "change_type": "TEXT - Type of change attempted",
                    "failure_reason": "TEXT - Reason for failure",
                    "error_message": "TEXT - Full error message",
                    "methods_affected": "TEXT - Methods that were changed",
                    "lines_changed": "INTEGER - Number of lines changed",
                    "metadata": "TEXT - Additional metadata as JSON"
                },
                "indexes": ["timestamp", "file_path", "change_type"],
                "common_queries": [
                    "SELECT change_type, COUNT(*) FROM failures GROUP BY change_type",
                    "SELECT * FROM failures WHERE file_path LIKE ? ORDER BY timestamp DESC",
                    "SELECT failure_reason, COUNT(*) as count FROM failures GROUP BY failure_reason ORDER BY count DESC"
                ]
            }
        }
    },
    
    "improvement_memory.db": {
        "description": "Successful improvements and their outcomes",
        "tables": {
            "improvements": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "timestamp": "TEXT - ISO format timestamp",
                    "file_path": "TEXT - Path to improved file",
                    "change_type": "TEXT - Type of improvement",
                    "description": "TEXT - Description of improvement",
                    "patch": "TEXT - Git-style patch",
                    "outcome": "TEXT - 'success', 'partial', 'failed'",
                    "error_message": "TEXT - Error if any",
                    "test_results": "TEXT - Test results as JSON",
                    "metrics": "TEXT - Performance metrics as JSON"
                },
                "indexes": ["timestamp", "file_path", "outcome"],
                "common_queries": [
                    "SELECT change_type, COUNT(*) FROM improvements WHERE outcome='success' GROUP BY change_type",
                    "SELECT * FROM improvements WHERE file_path=? ORDER BY timestamp DESC",
                    "SELECT * FROM improvements ORDER BY timestamp DESC LIMIT 10"
                ]
            }
        }
    },
    
    "plan_history.db": {
        "description": "Execution plan history",
        "tables": {
            "plan_history": {
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "plan_id": "TEXT - Unique plan identifier",
                    "timestamp": "REAL - Unix timestamp",
                    "iteration": "INTEGER - Iteration number",
                    "description": "TEXT - Plan description",
                    "proposal": "TEXT - Proposal details as JSON",
                    "patch": "TEXT - Git-style patch",
                    "risk_level": "TEXT - 'low', 'medium', 'high'",
                    "test_result": "TEXT - Test results",
                    "apply_result": "TEXT - Apply results",
                    "status": "TEXT - 'pending', 'applied', 'failed', 'rolled_back'",
                    "rollback_commit": "TEXT - Git commit for rollback"
                },
                "indexes": ["plan_id", "timestamp", "status"],
                "common_queries": [
                    "SELECT * FROM plan_history WHERE plan_id=? ORDER BY iteration",
                    "SELECT status, COUNT(*) FROM plan_history GROUP BY status",
                    "SELECT * FROM plan_history ORDER BY timestamp DESC LIMIT 10"
                ]
            }
        }
    }
}


def get_schema_for_database(db_name: str) -> dict:
    """Get schema for a specific database."""
    return DATABASE_SCHEMAS.get(db_name, {})


def get_all_databases() -> list:
    """Get list of all database names."""
    return list(DATABASE_SCHEMAS.keys())


def get_schema_summary() -> str:
    """Get human-readable summary of all schemas."""
    lines = ["CUA Database Schema Summary\n"]
    for db_name, db_info in DATABASE_SCHEMAS.items():
        lines.append(f"\n{db_name}: {db_info['description']}")
        for table_name, table_info in db_info['tables'].items():
            lines.append(f"  Table: {table_name}")
            lines.append(f"    Columns: {', '.join(table_info['columns'].keys())}")
    return "\n".join(lines)


def get_schema_for_llm(db_name: str = None) -> str:
    """Get schema formatted for LLM consumption."""
    if db_name:
        schemas = {db_name: DATABASE_SCHEMAS.get(db_name)}
    else:
        schemas = DATABASE_SCHEMAS
    
    lines = []
    for db, info in schemas.items():
        if not info:
            continue
        lines.append(f"Database: {db}")
        lines.append(f"Purpose: {info['description']}")
        for table, tinfo in info['tables'].items():
            lines.append(f"\nTable: {table}")
            lines.append("Columns:")
            for col, desc in tinfo['columns'].items():
                lines.append(f"  - {col}: {desc}")
            if tinfo.get('common_queries'):
                lines.append("Common queries:")
                for q in tinfo['common_queries']:
                    lines.append(f"  - {q}")
        lines.append("")
    
    return "\n".join(lines)
