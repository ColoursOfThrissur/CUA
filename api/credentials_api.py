"""
Credentials API — manage stored credentials.

Security rules:
  - GET endpoints NEVER return raw credential values.
  - SET requires the value in the request body (not query params).
  - All endpoints are local-only (no auth token needed since CUA is local).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from core.credential_store import get_credential_store

router = APIRouter(prefix="/credentials", tags=["credentials"])


class SetCredentialRequest(BaseModel):
    key: str
    value: str
    description: str = ""
    allowed_tools: Optional[List[str]] = None
    expires_at: Optional[str] = None  # ISO-8601 datetime string


class UpdateScopeRequest(BaseModel):
    allowed_tools: List[str]


@router.get("/list")
def list_credentials():
    """List all credential keys and metadata. Values are never returned."""
    store = get_credential_store()
    return {"credentials": store.list_keys(), "total": len(store.list_keys())}


@router.post("/set")
def set_credential(req: SetCredentialRequest):
    """Store or update a credential."""
    if not req.key.strip():
        raise HTTPException(status_code=422, detail="key must not be empty")
    if not req.value:
        raise HTTPException(status_code=422, detail="value must not be empty")
    store = get_credential_store()
    store.set(
        req.key.strip(),
        req.value,
        description=req.description,
        allowed_tools=req.allowed_tools,
        expires_at=req.expires_at,
    )
    return {"success": True, "key": req.key.strip()}


@router.delete("/{key}")
def delete_credential(key: str):
    """Delete a credential by key."""
    store = get_credential_store()
    deleted = store.delete(key)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Credential '{key}' not found")
    return {"success": True, "key": key}


@router.get("/{key}/exists")
def credential_exists(key: str):
    """Check if a credential key exists."""
    store = get_credential_store()
    return {"key": key, "exists": store.exists(key)}


@router.patch("/{key}/scope")
def update_credential_scope(key: str, req: UpdateScopeRequest):
    """Update which tools are allowed to read a credential."""
    store = get_credential_store()
    updated = store.update_allowed_tools(key, req.allowed_tools)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Credential '{key}' not found")
    return {"success": True, "key": key, "allowed_tools": req.allowed_tools}
