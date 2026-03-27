"""
Conversation Memory - Persistent chat history using centralized cua.db
"""
import json
from typing import List, Dict
from datetime import datetime

from core.cua_db import get_conn


class ConversationMemory:
    def __init__(self, db_path: str = None):
        # db_path ignored — always use cua.db
        pass
    
    def save_message(self, session_id: str, role: str, content: str, metadata: Dict = None):
        """Save a message to conversation history in cua.db"""
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO conversations (session_id, timestamp, role, content, metadata) VALUES (?, ?, ?, ?, ?)",
                    (session_id, datetime.now().timestamp(), role, content, json.dumps(metadata) if metadata else None)
                )
        except Exception as e:
            print(f"[WARN] Failed to save conversation message: {e}")
    
    def get_history(self, session_id: str, limit: int = 20) -> List[Dict]:
        """Get conversation history for a session from cua.db"""
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT role, content, timestamp, metadata FROM conversations WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (session_id, limit)
                ).fetchall()
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
        except Exception as e:
            print(f"[WARN] Failed to get conversation history: {e}")
            return []
    
    def clear_history(self, session_id: str):
        """Clear conversation history for a session in cua.db"""
        try:
            with get_conn() as conn:
                conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        except Exception as e:
            print(f"[WARN] Failed to clear conversation history: {e}")
    
    def get_all_sessions(self) -> List[str]:
        """Get list of all session IDs from cua.db"""
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT DISTINCT session_id FROM conversations ORDER BY MAX(timestamp) DESC"
                ).fetchall()
                return [row[0] for row in rows]
        except Exception as e:
            print(f"[WARN] Failed to get all sessions: {e}")
            return []
    
    def clear_all(self):
        """Clear all conversation history from cua.db"""
        try:
            with get_conn() as conn:
                conn.execute("DELETE FROM conversations")
        except Exception as e:
            print(f"[WARN] Failed to clear all conversations: {e}")
