"""Memory System - Manages conversation context and learned patterns."""
import json
import logging
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
    """Manages short-term and long-term memory."""
    
    def __init__(self, storage_dir: str = "data/memory"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache for active sessions
        self.active_sessions: Dict[str, ConversationContext] = {}
        
        # Learned patterns storage
        self.patterns_file = self.storage_dir / "learned_patterns.json"
        self.patterns = self._load_patterns()
    
    def create_session(self, session_id: str, user_preferences: Optional[Dict] = None) -> ConversationContext:
        """Create new conversation session."""
        context = ConversationContext(
            session_id=session_id,
            messages=[],
            user_preferences=user_preferences or {}
        )
        
        self.active_sessions[session_id] = context
        self._save_session(context)
        
        logger.info(f"Created session: {session_id}")
        return context
    
    def get_session(self, session_id: str) -> Optional[ConversationContext]:
        """Get conversation session."""
        # Check cache first
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]
        
        # Load from disk
        session_file = self.storage_dir / f"session_{session_id}.json"
        if session_file.exists():
            try:
                data = json.loads(session_file.read_text())
                context = ConversationContext(
                    session_id=data["session_id"],
                    messages=[ConversationMessage(**msg) for msg in data["messages"]],
                    user_preferences=data["user_preferences"],
                    active_goal=data.get("active_goal"),
                    execution_history=data.get("execution_history", []),
                    created_at=data["created_at"],
                    updated_at=data["updated_at"]
                )
                self.active_sessions[session_id] = context
                return context
            except Exception as e:
                logger.error(f"Failed to load session {session_id}: {e}")
        
        return None
    
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
        
        message = ConversationMessage(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            metadata=metadata
        )
        
        context.messages.append(message)
        context.updated_at = datetime.now().isoformat()
        
        self._save_session(context)
    
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
            context.active_goal = goal
            context.updated_at = datetime.now().isoformat()
            self._save_session(context)
    
    def add_execution(self, session_id: str, execution_id: str):
        """Link execution to session."""
        context = self.get_session(session_id)
        if context:
            context.execution_history.append(execution_id)
            context.updated_at = datetime.now().isoformat()
            self._save_session(context)
    
    def update_preference(self, session_id: str, key: str, value: Any):
        """Update user preference."""
        context = self.get_session(session_id)
        if context:
            context.user_preferences[key] = value
            context.updated_at = datetime.now().isoformat()
            self._save_session(context)
    
    def learn_pattern(self, pattern_type: str, pattern_data: Dict[str, Any]):
        """Store learned pattern for future use."""
        if pattern_type not in self.patterns:
            self.patterns[pattern_type] = []
        
        pattern_data["learned_at"] = datetime.now().isoformat()
        self.patterns[pattern_type].append(pattern_data)
        
        # Keep only recent patterns (last 100 per type)
        self.patterns[pattern_type] = self.patterns[pattern_type][-100:]
        
        self._save_patterns()
        logger.info(f"Learned new pattern: {pattern_type}")
    
    def get_patterns(self, pattern_type: str, limit: int = 10) -> List[Dict]:
        """Get learned patterns of specific type."""
        return self.patterns.get(pattern_type, [])[-limit:]
    
    def clear_session(self, session_id: str):
        """Clear session from memory and disk."""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        
        session_file = self.storage_dir / f"session_{session_id}.json"
        if session_file.exists():
            session_file.unlink()
        
        logger.info(f"Cleared session: {session_id}")
    
    def _save_session(self, context: ConversationContext):
        """Save session to disk."""
        session_file = self.storage_dir / f"session_{context.session_id}.json"
        
        data = {
            "session_id": context.session_id,
            "messages": [asdict(msg) for msg in context.messages],
            "user_preferences": context.user_preferences,
            "active_goal": context.active_goal,
            "execution_history": context.execution_history,
            "created_at": context.created_at,
            "updated_at": context.updated_at
        }
        
        session_file.write_text(json.dumps(data, indent=2))
    
    def _load_patterns(self) -> Dict[str, List[Dict]]:
        """Load learned patterns from disk."""
        if self.patterns_file.exists():
            try:
                return json.loads(self.patterns_file.read_text())
            except Exception as e:
                logger.error(f"Failed to load patterns: {e}")
        
        return {}
    
    def _save_patterns(self):
        """Save learned patterns to disk."""
        self.patterns_file.write_text(json.dumps(self.patterns, indent=2))
