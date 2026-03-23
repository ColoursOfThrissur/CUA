"""WebSocket endpoint for real-time trace events."""
from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from typing import Set
import json
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Active WebSocket connections
active_connections: Set[WebSocket] = set()


@router.websocket("/ws/trace")
async def trace_websocket(websocket: WebSocket):
    """WebSocket endpoint for trace events."""
    await websocket.accept()
    active_connections.add(websocket)
    logger.debug(f"WebSocket connected. Total: {len(active_connections)}")
    
    try:
        while True:
            # Keep connection alive by checking for disconnects
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=300)  # 5 min timeout
            except asyncio.TimeoutError:
                # Connection idle, but still active - keep it open
                continue
    except WebSocketDisconnect:
        logger.debug(f"WebSocket disconnected normally")
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
    finally:
        active_connections.discard(websocket)
        logger.debug(f"WebSocket removed. Total: {len(active_connections)}")


async def broadcast_trace(trace_type: str, message: str, status: str = "in_progress", details: dict | None = None):
    """Broadcast trace event to all connected clients."""
    if not active_connections:
        return
    
    try:
        event = {
            "type": trace_type,
            "message": message,
            "status": status,
            "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop() else 0,
            "details": details or {},
        }
    except Exception as e:
        logger.warning(f"Failed to build trace event: {e}")
        return
    
    disconnected = set()
    for connection in active_connections:
        try:
            # Check if connection is still healthy before sending
            if connection.application_state.value != 1:  # ASGI app state 1 = connected
                disconnected.add(connection)
                continue
            
            await asyncio.wait_for(connection.send_json(event), timeout=5)
        except asyncio.TimeoutError:
            logger.warning(f"WebSocket send timeout")
            disconnected.add(connection)
        except RuntimeError as e:
            if "WebSocket is not connected" in str(e):
                logger.debug(f"WebSocket not connected, removing")
                disconnected.add(connection)
            else:
                logger.warning(f"WebSocket runtime error: {e}")
                disconnected.add(connection)
        except Exception as e:
            logger.debug(f"WebSocket send error: {type(e).__name__}: {e}")
            disconnected.add(connection)
    
    # Remove disconnected clients
    active_connections.difference_update(disconnected)


def broadcast_trace_sync(trace_type: str, message: str, status: str = "in_progress", details: dict | None = None):
    """Synchronous wrapper for broadcast_trace - safe for calling from sync code."""
    if not active_connections:
        return
    
    import threading
    
    def _broadcast():
        try:
            # Try to get existing event loop
            try:
                loop = asyncio.get_running_loop()
                # If we're here, we're in an async context - schedule the coroutine
                asyncio.create_task(broadcast_trace(trace_type, message, status, details))
            except RuntimeError:
                # No running loop in this thread, create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(broadcast_trace(trace_type, message, status, details))
                finally:
                    loop.close()
        except Exception as e:
            logger.warning(f"broadcast_trace_sync error: {e}")
