"""Compatibility exports for chat routing.

The runtime still wires `/chat` directly in `api/server.py`. This module exists so
the refactored `api/rest/chat` package resolves to the working chat handler path.
"""

from api.chat_handler import ChatRequest, ChatResponse, create_chat_handler

__all__ = ["ChatRequest", "ChatResponse", "create_chat_handler"]
