"""Chat history logging."""
from datetime import datetime
from pathlib import Path

from core.sqlite_logging import get_logger
from core.sqlite_utils import safe_connect, safe_close

logger = get_logger("chat_history_logger")


class ChatHistoryLogger:
    """Log all chat interactions."""
    
    def __init__(self, db_path: str = "data/chat_history.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        conn = safe_connect(self.db_path)
        if not conn:
            logger.warning("Chat history DB unavailable; chat logging disabled for now")
            return
        try:
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
        finally:
            safe_close(conn)
    
    def log_message(self, session_id: str, role: str, content: str, 
                   mode: str = None, success: bool = True):
        """Log chat message."""
        timestamp = datetime.now().isoformat()
        
        conn = safe_connect(self.db_path)
        if not conn:
            return
        try:
            conn.execute(
                """INSERT INTO chat_messages 
                   (session_id, role, content, mode, success, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, role, content, mode, 1 if success else 0, timestamp)
            )
            conn.commit()
        finally:
            safe_close(conn)


_logger = None


def get_chat_logger() -> ChatHistoryLogger:
    """Get singleton logger."""
    global _logger
    if _logger is None:
        _logger = ChatHistoryLogger()
    return _logger
