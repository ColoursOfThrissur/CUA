"""Session Management API - Manage conversation sessions."""
from fastapi import APIRouter, HTTPException
from typing import Dict, List

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/list")
async def list_sessions() -> Dict:
    """List all active sessions"""
    from core.memory_system import MemorySystem
    from pathlib import Path
    import sqlite3
    
    memory = MemorySystem()
    
    try:
        conn = sqlite3.connect(memory.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.session_id, s.active_goal, s.created_at, s.updated_at,
                   COUNT(c.id) as message_count
            FROM sessions s
            LEFT JOIN conversations c ON s.session_id = c.session_id
            GROUP BY s.session_id
            ORDER BY s.updated_at DESC
        """)
        
        sessions = []
        for row in cursor.fetchall():
            sessions.append({
                "session_id": row[0],
                "active_goal": row[1],
                "created_at": row[2],
                "updated_at": row[3],
                "message_count": row[4]
            })
        
        conn.close()
        
        return {"sessions": sessions}
    except Exception as e:
        raise HTTPException(500, f"Failed to list sessions: {str(e)}")


@router.get("/{session_id}")
async def get_session(session_id: str) -> Dict:
    """Get session details with messages"""
    from core.memory_system import MemorySystem
    
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
    from core.memory_system import MemorySystem
    
    memory = MemorySystem()
    
    try:
        memory.clear_session(session_id)
        return {"success": True, "message": f"Session {session_id} deleted"}
    except Exception as e:
        raise HTTPException(500, f"Failed to delete session: {str(e)}")


@router.post("/{session_id}/clear-messages")
async def clear_messages(session_id: str) -> Dict:
    """Clear messages from a session but keep session"""
    from core.memory_system import MemorySystem
    import sqlite3
    
    memory = MemorySystem()
    
    try:
        conn = sqlite3.connect(memory.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
        
        # Clear from cache
        if session_id in memory.active_sessions:
            memory.active_sessions[session_id].messages = []
        
        return {"success": True, "message": "Messages cleared"}
    except Exception as e:
        raise HTTPException(500, f"Failed to clear messages: {str(e)}")
