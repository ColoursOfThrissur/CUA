"""Memory System - Manages conversation context and learned patterns using centralized cua.db."""
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

from core.cua_db import get_conn

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
    """Manages short-term and long-term memory with cua.db persistence."""
    
    def __init__(self, db_path: str = None):
        # db_path ignored — always use cua.db
        # In-memory cache for active sessions
        self.active_sessions: Dict[str, ConversationContext] = {}
    
    def create_session(self, session_id: str, user_preferences: Optional[Dict] = None) -> ConversationContext:
        """Create new conversation session in cua.db."""
        now = datetime.now().isoformat()
        context = ConversationContext(
            session_id=session_id,
            messages=[],
            user_preferences=user_preferences or {},
            created_at=now,
            updated_at=now
        )
        
        self.active_sessions[session_id] = context
        
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO sessions (session_id, user_preferences, active_goal, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (session_id, json.dumps(user_preferences or {}), None, now, now)
                )
        except Exception as e:
            logger.warning(f"Failed to save session to cua.db: {e}")
        
        logger.info(f"Created session: {session_id}")
        return context
    
    def get_session(self, session_id: str) -> Optional[ConversationContext]:
        """Get conversation session from cua.db."""
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]
        
        try:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT user_preferences, active_goal, created_at, updated_at FROM sessions WHERE session_id = ?",
                    (session_id,)
                ).fetchone()
                
                if not row:
                    return None
                
                user_prefs, active_goal, created_at, updated_at = row[0], row[1], row[2], row[3]
                
                messages = [
                    ConversationMessage(
                        role=r[0], content=r[1], timestamp=r[2],
                        metadata=json.loads(r[3]) if r[3] else None
                    )
                    for r in conn.execute(
                        "SELECT role, content, timestamp, metadata FROM conversations WHERE session_id = ? ORDER BY timestamp",
                        (session_id,)
                    ).fetchall()
                ]
                
                context = ConversationContext(
                    session_id=session_id,
                    messages=messages,
                    user_preferences=json.loads(user_prefs) if user_prefs else {},
                    active_goal=active_goal,
                    execution_history=[],
                    created_at=created_at,
                    updated_at=updated_at
                )
                
                self.active_sessions[session_id] = context
                return context
        except Exception as e:
            logger.warning(f"Failed to get session from cua.db: {e}")
            return None
    
    def add_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict] = None):
        """Add message to conversation in cua.db."""
        context = self.get_session(session_id)
        if not context:
            context = self.create_session(session_id)
        
        now = datetime.now().isoformat()
        message = ConversationMessage(role=role, content=content, timestamp=now, metadata=metadata)
        
        context.messages.append(message)
        context.updated_at = now
        
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO conversations (session_id, timestamp, role, content, metadata) VALUES (?, ?, ?, ?, ?)",
                    (session_id, now, role, content, json.dumps(metadata) if metadata else None)
                )
                conn.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id))
        except Exception as e:
            logger.warning(f"Failed to add message to cua.db: {e}")
    
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
        """Set active goal for session in cua.db."""
        context = self.get_session(session_id)
        if context:
            now = datetime.now().isoformat()
            context.active_goal = goal
            context.updated_at = now
            
            try:
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE sessions SET active_goal = ?, updated_at = ? WHERE session_id = ?",
                        (goal, now, session_id)
                    )
            except Exception as e:
                logger.warning(f"Failed to set active goal in cua.db: {e}")
    
    def add_execution(self, session_id: str, execution_id: str):
        """Link execution to session (no-op - execution_history table removed)."""
        context = self.get_session(session_id)
        if context:
            context.execution_history.append(execution_id)
            context.updated_at = datetime.now().isoformat()
    
    def update_preference(self, session_id: str, key: str, value: Any):
        """Update user preference in cua.db."""
        context = self.get_session(session_id)
        if context:
            now = datetime.now().isoformat()
            context.user_preferences[key] = value
            context.updated_at = now
            
            try:
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE sessions SET user_preferences = ?, updated_at = ? WHERE session_id = ?",
                        (json.dumps(context.user_preferences), now, session_id)
                    )
            except Exception as e:
                logger.warning(f"Failed to update preference in cua.db: {e}")
    
    def learn_pattern(self, pattern_type: str, pattern_data: Dict[str, Any]):
        """Store learned pattern in cua.db."""
        now = datetime.now().isoformat()
        
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO learned_patterns (pattern_type, pattern_data, learned_at) VALUES (?, ?, ?)",
                    (pattern_type, json.dumps(pattern_data), now)
                )
                # Keep only recent 100 patterns per type
                conn.execute(
                    """DELETE FROM learned_patterns WHERE id NOT IN (
                        SELECT id FROM learned_patterns WHERE pattern_type = ? ORDER BY learned_at DESC LIMIT 100
                    ) AND pattern_type = ?""",
                    (pattern_type, pattern_type)
                )
        except Exception as e:
            logger.warning(f"Failed to learn pattern in cua.db: {e}")
        
        logger.info(f"Learned new pattern: {pattern_type}")
    
    def get_patterns(self, pattern_type: str, limit: int = 10) -> List[Dict]:
        """Get learned patterns from cua.db."""
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT pattern_data FROM learned_patterns WHERE pattern_type = ? ORDER BY learned_at DESC LIMIT ?",
                    (pattern_type, limit)
                ).fetchall()
                return [json.loads(r[0]) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to get patterns from cua.db: {e}")
            return []
    
    def clear_session(self, session_id: str):
        """Clear session from memory and cua.db."""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        
        try:
            with get_conn() as conn:
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        except Exception as e:
            logger.warning(f"Failed to clear session from cua.db: {e}")
        
        logger.info(f"Cleared session: {session_id}")

