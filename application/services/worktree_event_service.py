"""Persistence and query helpers for isolated worktree lifecycle events."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from infrastructure.messaging.event_bus import get_event_bus
from infrastructure.persistence.sqlite.cua_database import get_conn


class WorktreeEventService:
    """Record and retrieve worktree lifecycle events for observability and exports."""

    def record_event(
        self,
        event_type: str,
        *,
        worktree_label: str = "",
        worktree_path: str = "",
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": str(event_type or "").strip(),
            "worktree_label": str(worktree_label or "").strip() or None,
            "worktree_path": str(worktree_path or "").strip() or None,
            "session_id": str(session_id or "").strip() or None,
            "task_id": str(task_id or "").strip() or None,
            "execution_id": str(execution_id or "").strip() or None,
            "details": details or {},
        }
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO worktree_events (
                    timestamp, event_type, worktree_label, worktree_path,
                    session_id, task_id, execution_id, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["timestamp"],
                    payload["event_type"],
                    payload["worktree_label"],
                    payload["worktree_path"],
                    payload["session_id"],
                    payload["task_id"],
                    payload["execution_id"],
                    json.dumps(payload["details"], ensure_ascii=True),
                ),
            )
        try:
            get_event_bus().emit_sync("worktree_event", payload)
        except Exception:
            pass
        return payload

    def list_events(
        self,
        *,
        limit: int = 100,
        session_id: Optional[str] = None,
        worktree_label: Optional[str] = None,
        worktree_path: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        clauses = ["1=1"]
        params: List[Any] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if worktree_label:
            clauses.append("worktree_label = ?")
            params.append(worktree_label)
        if worktree_path:
            clauses.append("worktree_path = ?")
            params.append(worktree_path)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        params.append(max(1, int(limit)))
        with get_conn() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM worktree_events
                WHERE {' AND '.join(clauses)}
                ORDER BY id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_payload(row) for row in rows]

    def list_for_session(
        self,
        session_id: str,
        *,
        tasks: Optional[Iterable[Dict[str, Any]]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        task_list = list(tasks or [])
        labels = set()
        paths = set()
        for task in task_list:
            metadata = task.get("workflow_metadata") or {}
            worktree = metadata.get("worktree") or {}
            if worktree.get("label"):
                labels.add(str(worktree["label"]))
            if worktree.get("worktree_path"):
                paths.add(str(worktree["worktree_path"]))

        events = self.list_events(limit=max(limit * 4, 50))
        filtered: List[Dict[str, Any]] = []
        for event in events:
            if event.get("session_id") == session_id:
                filtered.append(event)
                continue
            if event.get("worktree_path") and event["worktree_path"] in paths:
                filtered.append(event)
                continue
            if event.get("worktree_label") and event["worktree_label"] in labels:
                filtered.append(event)

        filtered.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
        return filtered[:limit]

    def count_events(self) -> int:
        with get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM worktree_events").fetchone()[0]

    def _row_to_payload(self, row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "event_type": row["event_type"],
            "worktree_label": row["worktree_label"],
            "worktree_path": row["worktree_path"],
            "session_id": row["session_id"],
            "task_id": row["task_id"],
            "execution_id": row["execution_id"],
            "details": json.loads(row["details_json"]) if row["details_json"] else {},
        }
