"""WebSocket endpoint for real-time trace events."""
from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from typing import Set
import json
import asyncio

router = APIRouter()

# Active WebSocket connections
active_connections: Set[WebSocket] = set()


@router.websocket("/ws/trace")
async def trace_websocket(websocket: WebSocket):
    """WebSocket endpoint for trace events."""
    await websocket.accept()
    active_connections.add(websocket)
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)


async def broadcast_trace(trace_type: str, message: str, status: str = "in_progress"):
    """Broadcast trace event to all connected clients."""
    if not active_connections:
        return
    
    event = {
        "type": trace_type,
        "message": message,
        "status": status,
        "timestamp": asyncio.get_event_loop().time()
    }
    
    disconnected = set()
    for connection in active_connections:
        try:
            await connection.send_json(event)
        except:
            disconnected.add(connection)
    
    # Remove disconnected clients
    active_connections.difference_update(disconnected)


def broadcast_trace_sync(trace_type: str, message: str, status: str = "in_progress"):
    """Synchronous wrapper for broadcast_trace."""
    if not active_connections:
        return
    
    import threading
    
    def _broadcast():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(broadcast_trace(trace_type, message, status))
            loop.close()
        except:
            pass
    
    thread = threading.Thread(target=_broadcast, daemon=True)
    thread.start()
