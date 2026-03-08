"""Memory System - Manages conversation context and learned patterns."""
import json
import logging
import sqlite3
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ConversationMessage:
    """Single message in conversation."""
    role: str  # user, assistant, system
    content: str
    timestamp: str
    metadata: Dict[str, Any] = None


@dataclass
class ConversationContext:
    """Context for a conversation session."""
    session_id: str
    messages: List[ConversationMessage]
    user_preferences: Dict[str, Any]
    active_goal: Optional[str] = None
    execution_history: List[str] = None  # execution_ids
    created_at: str = None
    updated_at: str = None
    
    def __post_init__(self):
        if self.execution_history is None:
            self.execution_history = []
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.updated_at is None:
            self.updated_at = datetime.now().isoformat()


class MemorySystem:
    """Manages short-term and long-term memory with SQLite persistence."""
    
    def __init__(self, db_path: str = "data/conversations.db"):
        self.db_path = db_path
        self._init_db()
        
        # In-memory cache for active sessions
        self.active_sessions: Dict[str, ConversationContext] = {}
    
    def create_session(self, session_id: str, user_preferences: Optional[Dict] = None) -> ConversationContext:
        """Create new conversation session."""
        now = datetime.now().isoformat()
        context = ConversationContext(
            session_id=session_id,
            messages=[],
            user_preferences=user_preferences or {},
            created_at=now,
            updated_at=now
        )
        
        self.active_sessions[session_id] = context
        
        # Save to SQLite
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO sessions (session_id, user_preferences, active_goal, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, json.dumps(user_preferences or {}), None, now, now)
        )
        conn.commit()
        conn.close()
        
        logger.info(f"Created session: {session_id}")
        return context
    
    def get_session(self, session_id: str) -> Optional[ConversationContext]:
        """Get conversation session."""
        # Check cache first
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]
        
        # Load from SQLite
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get session metadata
        cursor.execute(
            "SELECT user_preferences, active_goal, created_at, updated_at FROM sessions WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return None
        
        user_prefs, active_goal, created_at, updated_at = row
        
        # Get messages
        cursor.execute(
            "SELECT role, content, timestamp, metadata FROM conversations WHERE session_id = ? ORDER BY timestamp",
            (session_id,)
        )
        messages = [
            ConversationMessage(
                role=r[0],
                content=r[1],
                timestamp=r[2],
                metadata=json.loads(r[3]) if r[3] else None
            )
            for r in cursor.fetchall()
        ]
        
        # Get execution history
        cursor.execute(
            "SELECT execution_id FROM execution_history WHERE session_id = ? ORDER BY timestamp",
            (session_id,)
        )
        execution_history = [r[0] for r in cursor.fetchall()]
        
        conn.close()
        
        context = ConversationContext(
            session_id=session_id,
            messages=messages,
            user_preferences=json.loads(user_prefs) if user_prefs else {},
            active_goal=active_goal,
            execution_history=execution_history,
            created_at=created_at,
            updated_at=updated_at
        )
        
        self.active_sessions[session_id] = context
        return context
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ):
        """Add message to conversation."""
        context = self.get_session(session_id)
        if not context:
            context = self.create_session(session_id)
        
        now = datetime.now().isoformat()
        message = ConversationMessage(
            role=role,
            content=content,
            timestamp=now,
            metadata=metadata
        )
        
        context.messages.append(message)
        context.updated_at = now
        
        # Save to SQLite
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO conversations (session_id, timestamp, role, content, metadata) VALUES (?, ?, ?, ?, ?)",
            (session_id, now, role, content, json.dumps(metadata) if metadata else None)
        )
        cursor.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (now, session_id)
        )
        conn.commit()
        conn.close()
    
    def get_recent_messages(
        self,
        session_id: str,
        limit: int = 10,
        role_filter: Optional[str] = None
    ) -> List[ConversationMessage]:
        """Get recent messages from session."""
        context = self.get_session(session_id)
        if not context:
            return []
        
        messages = context.messages
        
        if role_filter:
            messages = [m for m in messages if m.role == role_filter]
        
        return messages[-limit:]
    
    def get_conversation_summary(self, session_id: str, max_tokens: int = 500) -> str:
        """Get summarized conversation context."""
        context = self.get_session(session_id)
        if not context or not context.messages:
            return "No conversation history."
        
        # Build summary from recent messages
        recent = context.messages[-10:]  # Last 10 messages
        
        summary_parts = []
        if context.active_goal:
            summary_parts.append(f"Current Goal: {context.active_goal}")
        
        summary_parts.append("Recent Conversation:")
        for msg in recent:
            summary_parts.append(f"{msg.role}: {msg.content[:100]}...")
        
        return "\n".join(summary_parts)
    
    def set_active_goal(self, session_id: str, goal: str):
        """Set active goal for session."""
        context = self.get_session(session_id)
        if context:
            now = datetime.now().isoformat()
            context.active_goal = goal
            context.updated_at = now
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sessions SET active_goal = ?, updated_at = ? WHERE session_id = ?",
                (goal, now, session_id)
            )
            conn.commit()
            conn.close()
    
    def add_execution(self, session_id: str, execution_id: str):
        """Link execution to session."""
        context = self.get_session(session_id)
        if context:
            now = datetime.now().isoformat()
            context.execution_history.append(execution_id)
            context.updated_at = now
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO execution_history (session_id, execution_id, timestamp) VALUES (?, ?, ?)",
                (session_id, execution_id, now)
            )
            cursor.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id)
            )
            conn.commit()
            conn.close()
    
    def update_preference(self, session_id: str, key: str, value: Any):
        """Update user preference."""
        context = self.get_session(session_id)
        if context:
            now = datetime.now().isoformat()
            context.user_preferences[key] = value
            context.updated_at = now
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sessions SET user_preferences = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(context.user_preferences), now, session_id)
            )
            conn.commit()
            conn.close()
    
    def learn_pattern(self, pattern_type: str, pattern_data: Dict[str, Any]):
        """Store learned pattern for future use."""
        now = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO learned_patterns (pattern_type, pattern_data, learned_at) VALUES (?, ?, ?)",
            (pattern_type, json.dumps(pattern_data), now)
        )
        conn.commit()
        
        # Keep only recent 100 patterns per type
        cursor.execute(
            """DELETE FROM learned_patterns WHERE id NOT IN (
                SELECT id FROM learned_patterns WHERE pattern_type = ? ORDER BY learned_at DESC LIMIT 100
            ) AND pattern_type = ?""",
            (pattern_type, pattern_type)
        )
        conn.commit()
        conn.close()
        
        logger.info(f"Learned new pattern: {pattern_type}")
    
    def get_patterns(self, pattern_type: str, limit: int = 10) -> List[Dict]:
        """Get learned patterns of specific type."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pattern_data FROM learned_patterns WHERE pattern_type = ? ORDER BY learned_at DESC LIMIT ?",
            (pattern_type, limit)
        )
        patterns = [json.loads(r[0]) for r in cursor.fetchall()]
        conn.close()
        return patterns
    
    def clear_session(self, session_id: str):
        """Clear session from memory and database."""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM execution_history WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
        
        logger.info(f"Cleared session: {session_id}")
    
    def _init_db(self):
        """Initialize SQLite database with required tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_preferences TEXT,
                active_goal TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Execution history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS execution_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
        """)
        
        # Learned patterns table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS learned_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                pattern_data TEXT NOT NULL,
                learned_at TEXT NOT NULL
            )
        """)
        
        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_execution_session ON execution_history(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_patterns_type ON learned_patterns(pattern_type, learned_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id, timestamp)")
        
        conn.commit()
        conn.close()
        
        logger.info("Memory system database initialized")
