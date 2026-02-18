"""Event bus for real-time system events."""
from typing import Callable, Dict, List
from dataclasses import dataclass
from datetime import datetime
import asyncio

@dataclass
class Event:
    type: str
    data: dict
    timestamp: str = None
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._queue = asyncio.Queue()
    
    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: str, callback: Callable):
        """Unsubscribe from event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(callback)
    
    async def emit(self, event_type: str, data: dict):
        """Emit event to all subscribers."""
        event = Event(type=event_type, data=data)
        await self._queue.put(event)
        
        # Notify subscribers
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    print(f"Event callback error: {e}")
    
    async def get_event(self):
        """Get next event from queue."""
        return await self._queue.get()

# Global event bus instance
_event_bus = EventBus()

def get_event_bus() -> EventBus:
    return _event_bus
