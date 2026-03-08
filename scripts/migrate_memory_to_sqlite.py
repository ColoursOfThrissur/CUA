"""Migrate memory system from JSON files to SQLite."""
import json
import sqlite3
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Migrate existing JSON memory data to SQLite."""
    memory_dir = Path("data/memory")
    db_path = "data/conversations.db"
    
    if not memory_dir.exists():
        logger.info("No memory directory found, nothing to migrate")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Initialize tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_preferences TEXT,
            active_goal TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS execution_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            execution_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learned_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            pattern_data TEXT NOT NULL,
            learned_at TEXT NOT NULL
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_execution_session ON execution_history(session_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_patterns_type ON learned_patterns(pattern_type, learned_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id, timestamp)")
    
    conn.commit()
    
    migrated_sessions = 0
    migrated_patterns = 0
    
    # Migrate session files
    for session_file in memory_dir.glob("session_*.json"):
        try:
            data = json.loads(session_file.read_text())
            session_id = data["session_id"]
            
            # Insert session
            cursor.execute(
                "INSERT OR REPLACE INTO sessions (session_id, user_preferences, active_goal, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (
                    session_id,
                    json.dumps(data.get("user_preferences", {})),
                    data.get("active_goal"),
                    data.get("created_at"),
                    data.get("updated_at")
                )
            )
            
            # Insert messages (if not already in conversations table)
            for msg in data.get("messages", []):
                cursor.execute(
                    "INSERT INTO conversations (session_id, timestamp, role, content, metadata) VALUES (?, ?, ?, ?, ?)",
                    (
                        session_id,
                        msg["timestamp"],
                        msg["role"],
                        msg["content"],
                        json.dumps(msg.get("metadata")) if msg.get("metadata") else None
                    )
                )
            
            # Insert execution history
            for exec_id in data.get("execution_history", []):
                cursor.execute(
                    "INSERT INTO execution_history (session_id, execution_id, timestamp) VALUES (?, ?, ?)",
                    (session_id, exec_id, data.get("updated_at"))
                )
            
            migrated_sessions += 1
            logger.info(f"Migrated session: {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to migrate {session_file}: {e}")
    
    # Migrate learned patterns
    patterns_file = memory_dir / "learned_patterns.json"
    if patterns_file.exists():
        try:
            patterns = json.loads(patterns_file.read_text())
            for pattern_type, pattern_list in patterns.items():
                for pattern_data in pattern_list:
                    learned_at = pattern_data.pop("learned_at", None)
                    cursor.execute(
                        "INSERT INTO learned_patterns (pattern_type, pattern_data, learned_at) VALUES (?, ?, ?)",
                        (pattern_type, json.dumps(pattern_data), learned_at)
                    )
                    migrated_patterns += 1
            
            logger.info(f"Migrated {migrated_patterns} learned patterns")
            
        except Exception as e:
            logger.error(f"Failed to migrate patterns: {e}")
    
    conn.commit()
    conn.close()
    
    logger.info(f"Migration complete: {migrated_sessions} sessions, {migrated_patterns} patterns")
    logger.info("You can now safely delete the data/memory directory")


if __name__ == "__main__":
    migrate()
