"""Compatibility exports for the chat message handler."""

from api.chat_handler import ChatRequest, ChatResponse, create_chat_handler

__all__ = ["ChatRequest", "ChatResponse", "create_chat_handler"]
