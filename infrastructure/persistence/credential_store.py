"""
CredentialStore - encrypted at-rest credential storage for CUA.

Design:
  - Fernet symmetric encryption (cryptography package).
  - Key derived from a machine-local secret stored in data/.cua_keyfile.
    On first run the key is generated and saved; subsequent runs load it.
  - Credentials stored in data/credentials.enc as an encrypted JSON blob.
  - Each credential entry has an optional `allowed_tools` list.
    When set, only those tool names can call get().
  - Raw values are NEVER returned by the API - only metadata.

Usage from tool code:
    api_key = self.services.credentials.get("openai_api_key")
    self.services.credentials.set("openai_api_key", "sk-...", allowed_tools=["MyTool"])
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

_KEYFILE = Path("data/.cua_keyfile")
_STORE_FILE = Path("data/credentials.enc")


def _load_or_create_key() -> bytes:
    """Load Fernet key from disk, creating it on first run."""
    _KEYFILE.parent.mkdir(parents=True, exist_ok=True)
    if _KEYFILE.exists():
        return _KEYFILE.read_bytes().strip()
    try:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
    except ImportError:
        # cryptography not installed - fall back to base64-encoded os.urandom
        import base64
        key = base64.urlsafe_b64encode(os.urandom(32))
    _KEYFILE.write_bytes(key)
    # Restrict permissions on Unix
    try:
        os.chmod(_KEYFILE, 0o600)
    except Exception:
        pass
    return key


def _get_fernet():
    try:
        from cryptography.fernet import Fernet
        return Fernet(_load_or_create_key())
    except ImportError:
        return None


class CredentialStore:
    """
    Encrypted credential store.  Thread-safe for single-process use.
    """

    def __init__(self):
        self._fernet = _get_fernet()
        self._data: Dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API (used by CredentialService and the API layer)
    # ------------------------------------------------------------------

    def set(
        self,
        key: str,
        value: str,
        description: str = "",
        allowed_tools: Optional[List[str]] = None,
        expires_at: Optional[str] = None,
    ) -> None:
        """Store or update a credential.

        expires_at: optional ISO-8601 datetime string (e.g. '2026-12-31T00:00:00').
        get() returns None and logs a warning once the credential is past this time.
        """
        if not key or not isinstance(key, str):
            raise ValueError("Credential key must be a non-empty string")
        if not isinstance(value, str):
            raise ValueError("Credential value must be a string")
        self._data[key] = {
            "value": value,
            "description": description or "",
            "allowed_tools": allowed_tools or [],  # empty = unrestricted
            "expires_at": expires_at or None,
        }
        self._save()

    def get(self, key: str, caller_tool: Optional[str] = None) -> Optional[str]:
        """
        Retrieve a credential value.

        Returns None if key not found, access denied, or credential is expired.
        """
        import logging
        _log = logging.getLogger(__name__)
        entry = self._data.get(key)
        if not entry:
            return None
        # TTL check
        expires_at = entry.get("expires_at")
        if expires_at:
            try:
                from datetime import datetime, timezone
                exp = datetime.fromisoformat(expires_at)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > exp:
                    _log.warning(f"Credential '{key}' expired at {expires_at} - returning None")
                    return None
            except Exception:
                pass
        allowed = entry.get("allowed_tools") or []
        if allowed and caller_tool and caller_tool not in allowed:
            raise PermissionError(
                f"Tool '{caller_tool}' is not allowed to access credential '{key}'"
            )
        return entry.get("value")

    def delete(self, key: str) -> bool:
        """Delete a credential. Returns True if it existed."""
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def list_keys(self) -> List[dict]:
        """Return metadata for all credentials - values are never included."""
        return [
            {
                "key": k,
                "description": v.get("description", ""),
                "allowed_tools": v.get("allowed_tools") or [],
                "has_value": bool(v.get("value")),
                "expires_at": v.get("expires_at"),
            }
            for k, v in self._data.items()
        ]

    def exists(self, key: str) -> bool:
        return key in self._data

    def update_allowed_tools(self, key: str, allowed_tools: List[str]) -> bool:
        if key not in self._data:
            return False
        self._data[key]["allowed_tools"] = allowed_tools
        self._save()
        return True

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        import logging
        _log = logging.getLogger(__name__)
        _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(self._data).encode()
        if self._fernet:
            payload = self._fernet.encrypt(raw)
        else:
            import base64
            payload = base64.b64encode(raw)
        # Atomic write: write to .tmp then replace to avoid corruption on crash
        tmp = _STORE_FILE.with_suffix(".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, _STORE_FILE)

    def _load(self) -> None:
        import logging
        _log = logging.getLogger(__name__)
        if not _STORE_FILE.exists():
            self._data = {}
            return
        try:
            payload = _STORE_FILE.read_bytes()
            if self._fernet:
                raw = self._fernet.decrypt(payload)
            else:
                import base64
                raw = base64.b64decode(payload)
            self._data = json.loads(raw.decode())
        except Exception as e:
            # Log visibly - silent reset means lost credentials with no trace
            _log.error(f"CredentialStore failed to load '{_STORE_FILE}': {e} - starting with empty store")
            self._data = {}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_store: Optional[CredentialStore] = None


def get_credential_store() -> CredentialStore:
    global _store
    if _store is None:
        _store = CredentialStore()
    return _store
