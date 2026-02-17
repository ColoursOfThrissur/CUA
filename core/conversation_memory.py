"""
Conversation Memory - Persistent chat history
"""
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

class ConversationMemory:
    def __init__(self, db_path: str = "data/conversations.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session 
            ON conversations(session_id, timestamp)
        """)
        
        conn.commit()
        conn.close()
    
    def save_message(self, session_id: str, role: str, content: str, metadata: Dict = None):
        """Save a message to conversation history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO conversations (session_id, timestamp, role, content, metadata)
            VALUES (?, ?, ?, ?, ?)
        """, (
            session_id,
            datetime.now().timestamp(),
            role,
            content,
            json.dumps(metadata) if metadata else None
        ))
        
        conn.commit()
        conn.close()
    
    def get_history(self, session_id: str, limit: int = 20) -> List[Dict]:
        """Get conversation history for a session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT role, content, timestamp, metadata
            FROM conversations
            WHERE session_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (session_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Reverse to get chronological order
        messages = []
        for row in reversed(rows):
            messages.append({
                "role": row[0],
                "content": row[1],
                "timestamp": row[2],
                "metadata": json.loads(row[3]) if row[3] else None
            })
        
        return messages
    
    def clear_history(self, session_id: str):
        """Clear conversation history for a session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM conversations WHERE session_id = ?
        """, (session_id,))
        
        conn.commit()
        conn.close()
    
    def get_all_sessions(self) -> List[str]:
        """Get list of all session IDs"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT session_id FROM conversations
            ORDER BY MAX(timestamp) DESC
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [row[0] for row in rows]
