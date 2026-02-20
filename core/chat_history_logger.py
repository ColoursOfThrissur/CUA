"""Chat history logging."""
import sqlite3
from datetime import datetime
from pathlib import Path


class ChatHistoryLogger:
    """Log all chat interactions."""
    
    def __init__(self, db_path: str = "data/chat_history.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    mode TEXT,
                    success INTEGER,
                    timestamp TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON chat_messages(session_id)")
            conn.commit()
    
    def log_message(self, session_id: str, role: str, content: str, 
                   mode: str = None, success: bool = True):
        """Log chat message."""
        timestamp = datetime.now().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO chat_messages 
                   (session_id, role, content, mode, success, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, role, content, mode, 1 if success else 0, timestamp)
            )
            conn.commit()


_logger = None


def get_chat_logger() -> ChatHistoryLogger:
    """Get singleton logger."""
    global _logger
    if _logger is None:
        _logger = ChatHistoryLogger()
    return _logger
