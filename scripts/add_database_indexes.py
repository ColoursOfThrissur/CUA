"""Add performance indexes to all observability databases."""
import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_indexes():
    """Add indexes to all databases for 10x query performance"""
    
    databases = {
        "data/logs.db": [
            "CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)",
            "CREATE INDEX IF NOT EXISTS idx_logs_component ON logs(component)",
        ],
        "data/tool_executions.db": [
            "CREATE INDEX IF NOT EXISTS idx_exec_tool ON executions(tool_name, timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_exec_success ON executions(success, timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_exec_time ON executions(execution_time_ms DESC)",
        ],
        "data/tool_evolution.db": [
            "CREATE INDEX IF NOT EXISTS idx_evol_tool ON evolutions(tool_name, timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_evol_status ON evolutions(status)",
        ],
        "data/tool_creation.db": [
            "CREATE INDEX IF NOT EXISTS idx_create_tool ON creations(tool_name, timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_create_status ON creations(status)",
        ],
        "data/conversations.db": [
            "CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id, timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_conv_role ON conversations(role)",
            "CREATE INDEX IF NOT EXISTS idx_session_updated ON sessions(updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_patterns_type_time ON learned_patterns(pattern_type, learned_at DESC)",
        ],
        "data/analytics.db": [
            "CREATE INDEX IF NOT EXISTS idx_analytics_timestamp ON metrics(timestamp DESC)",
        ],
        "data/plan_history.db": [
            "CREATE INDEX IF NOT EXISTS idx_plan_session ON plans(session_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_plan_status ON plans(status)",
        ],
    }
    
    total_indexes = 0
    for db_path, indexes in databases.items():
        if not Path(db_path).exists():
            logger.warning(f"Database not found: {db_path}")
            continue
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            for index_sql in indexes:
                cursor.execute(index_sql)
                total_indexes += 1
                index_name = index_sql.split("idx_")[1].split(" ")[0] if "idx_" in index_sql else "unknown"
                logger.info(f"Created index: idx_{index_name} in {db_path}")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to add indexes to {db_path}: {e}")
    
    logger.info(f"Added {total_indexes} indexes across {len(databases)} databases")


if __name__ == "__main__":
    add_indexes()
