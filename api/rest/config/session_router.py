"""Session Management API - Manage conversation sessions."""
from fastapi import APIRouter, HTTPException
from typing import Dict, List

from infrastructure.persistence.sqlite.cua_database import get_conn

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/list")
async def list_sessions() -> Dict:
    """List all active sessions"""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT s.session_id, s.active_goal, s.created_at, s.updated_at,
                       COUNT(c.id) as message_count
                FROM sessions s
                LEFT JOIN conversations c ON s.session_id = c.session_id
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC
                """
            ).fetchall()

        sessions = [
            {
                "session_id": row[0],
                "active_goal": row[1],
                "created_at": row[2],
                "updated_at": row[3],
                "message_count": row[4],
            }
            for row in rows
        ]

        return {"sessions": sessions}
    except Exception as e:
        raise HTTPException(500, f"Failed to list sessions: {str(e)}")


@router.get("/{session_id}")
async def get_session(session_id: str) -> Dict:
    """Get session details with messages"""
    from infrastructure.persistence.file_storage.memory_system import MemorySystem
    
    memory = MemorySystem()
    context = memory.get_session(session_id)
    
    if not context:
        raise HTTPException(404, "Session not found")
    
    return {
        "session_id": context.session_id,
        "active_goal": context.active_goal,
        "created_at": context.created_at,
        "updated_at": context.updated_at,
        "user_preferences": context.user_preferences,
        "execution_history": context.execution_history,
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp,
                "metadata": msg.metadata
            }
            for msg in context.messages
        ]
    }


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> Dict:
    """Delete a session"""
    from infrastructure.persistence.file_storage.memory_system import MemorySystem
    
    memory = MemorySystem()
    
    try:
        memory.clear_session(session_id)
        return {"success": True, "message": f"Session {session_id} deleted"}
    except Exception as e:
        raise HTTPException(500, f"Failed to delete session: {str(e)}")


@router.post("/{session_id}/clear-messages")
async def clear_messages(session_id: str) -> Dict:
    """Clear messages from a session but keep session"""
    from infrastructure.persistence.file_storage.memory_system import MemorySystem
    
    memory = MemorySystem()
    
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        
        # Clear from cache
        if session_id in memory.active_sessions:
            memory.active_sessions[session_id].messages = []
        
        return {"success": True, "message": "Messages cleared"}
    except Exception as e:
        raise HTTPException(500, f"Failed to clear messages: {str(e)}")
