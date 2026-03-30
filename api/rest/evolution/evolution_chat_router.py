"""API endpoints for agentic evolution chat."""
from fastapi import APIRouter, WebSocket, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
import asyncio

from application.use_cases.evolution.agentic_evolution_chat import AgenticEvolutionChat, EvolutionMessage
from domain.services.tool_quality_analyzer import ToolQualityAnalyzer

router = APIRouter()

# Active chat sessions
_sessions: Dict[str, AgenticEvolutionChat] = {}
_llm_client = None
_analyzer = None


def set_evolution_dependencies(llm_client, analyzer):
    """Set dependencies for evolution chat."""
    global _llm_client, _analyzer
    _llm_client = llm_client
    _analyzer = analyzer


class StartEvolutionRequest(BaseModel):
    tool_name: Optional[str] = None
    prompt: Optional[str] = None


class RespondRequest(BaseModel):
    session_id: str
    response: str


@router.post("/evolution/start")
async def start_evolution(request: StartEvolutionRequest):
    """Start evolution conversation."""
    if not _llm_client or not _analyzer:
        raise HTTPException(status_code=500, detail="Evolution system not initialized")
    
    chat = AgenticEvolutionChat(_llm_client, _analyzer)
    _sessions[chat.session_id] = chat
    
    # Start appropriate flow
    if request.tool_name:
        # System-initiated
        asyncio.create_task(chat.start_system_evolution(request.tool_name))
    elif request.prompt:
        # User-initiated
        asyncio.create_task(chat.start_user_evolution(request.prompt))
    else:
        raise HTTPException(status_code=400, detail="Must provide tool_name or prompt")
    
    return {
        "session_id": chat.session_id,
        "status": "started"
    }


@router.post("/evolution/respond")
async def respond_to_evolution(request: RespondRequest):
    """User responds to evolution step."""
    chat = _sessions.get(request.session_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await chat.handle_user_response(request.response)
    
    return {"status": "ok"}


@router.get("/evolution/status/{session_id}")
async def get_evolution_status(session_id: str):
    """Get current evolution status."""
    chat = _sessions.get(session_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session_id,
        "current_step": chat.current_step.value if chat.current_step else None,
        "waiting_for_response": chat.waiting_for_response,
        "messages_count": len(chat.messages)
    }


@router.get("/evolution/messages/{session_id}")
async def get_evolution_messages(session_id: str):
    """Get all messages in evolution conversation."""
    chat = _sessions.get(session_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "messages": [
            {
                "step": msg.step.value,
                "text": msg.text,
                "code": msg.code,
                "diff": msg.diff,
                "needs_confirmation": msg.needs_confirmation,
                "metadata": msg.metadata
            }
            for msg in chat.messages
        ]
    }


@router.websocket("/evolution/ws/{session_id}")
async def evolution_websocket(websocket: WebSocket, session_id: str):
    """Real-time evolution chat via WebSocket."""
    await websocket.accept()
    
    chat = _sessions.get(session_id)
    if not chat:
        await websocket.send_json({"error": "Session not found"})
        await websocket.close()
        return
    
    # Set callback to send messages to WebSocket
    async def send_to_websocket(message: EvolutionMessage):
        await websocket.send_json({
            "step": message.step.value,
            "text": message.text,
            "code": message.code,
            "diff": message.diff,
            "needs_confirmation": message.needs_confirmation,
            "metadata": message.metadata
        })
    
    chat.set_message_callback(send_to_websocket)
    
    try:
        # Listen for user responses
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "response":
                await chat.handle_user_response(data.get("response", ""))
            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()


@router.get("/evolution/weak-tools")
async def get_weak_tools_for_evolution():
    """Get weak tools that need evolution."""
    if not _analyzer:
        raise HTTPException(status_code=500, detail="Analyzer not initialized")
    
    weak_tools = _analyzer.get_weak_tools(days=7, min_usage=5)
    
    return {
        "weak_tools": [
            {
                "tool_name": tool.tool_name,
                "health_score": tool.health_score,
                "recommendation": tool.recommendation,
                "issues": tool.issues
            }
            for tool in weak_tools
        ]
    }
