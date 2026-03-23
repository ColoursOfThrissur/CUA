"""
CredentialService — tool-scoped wrapper around CredentialStore.

Injected as self.services.credentials in ToolServices.
The caller_tool is set at construction time so access checks are automatic.
"""
from __future__ import annotations

from typing import List, Optional
from core.credential_store import get_credential_store


class CredentialService:
    """
    Tool-scoped credential access.

    Tools call:
        value = self.services.credentials.get("my_api_key")
        self.services.credentials.set("my_api_key", "abc123")
        self.services.credentials.exists("my_api_key")
    """

    def __init__(self, caller_tool: str = ""):
        self._caller = caller_tool
        self._store = get_credential_store()

    def get(self, key: str) -> Optional[str]:
        """Get credential value. Raises PermissionError if tool not in allowed_tools."""
        return self._store.get(key, caller_tool=self._caller)

    def set(
        self,
        key: str,
        value: str,
        description: str = "",
        allowed_tools: Optional[List[str]] = None,
    ) -> None:
        """Store a credential. allowed_tools=None means any tool can read it."""
        self._store.set(key, value, description=description, allowed_tools=allowed_tools)

    def exists(self, key: str) -> bool:
        """Check if a credential key exists (no access restriction on existence check)."""
        return self._store.exists(key)

    def delete(self, key: str) -> bool:
        """Delete a credential."""
        return self._store.delete(key)
