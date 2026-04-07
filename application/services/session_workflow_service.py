"""Session workflow helpers for overview, summary, export, and resume."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from application.services.context_compactor import ContextCompactor
from application.services.worktree_event_service import WorktreeEventService
from infrastructure.persistence.sqlite.cua_database import get_conn


class SessionWorkflowService:
    """Coordinates session inspection, export, and resume using existing stores."""

    def __init__(
        self,
        memory_system,
        conversation_memory,
        task_manager,
        export_dir: str = "data/exports",
        context_compactor: Optional[ContextCompactor] = None,
    ) -> None:
        self.memory_system = memory_system
        self.conversation_memory = conversation_memory
        self.task_manager = task_manager
        self.export_dir = Path(export_dir)
        self.context_compactor = context_compactor or ContextCompactor()
        self.worktree_events = WorktreeEventService()

    def list_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT s.session_id, s.active_goal, s.created_at, s.updated_at,
                       COUNT(c.id) as message_count
                FROM sessions s
                LEFT JOIN conversations c ON s.session_id = c.session_id
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "session_id": row["session_id"],
                "active_goal": row["active_goal"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "message_count": row["message_count"],
            }
            for row in rows
        ]

    def get_session_overview(self, session_id: str, live_sessions: Dict[str, Any]) -> Dict[str, Any]:
        context = self.memory_system.get_session(session_id)
        messages = self.conversation_memory.get_history(session_id, limit=50)
        tasks = self.task_manager.get_session_tasks(session_id, limit=5)
        pending_plan = live_sessions.get(session_id, {}).get("pending_agent_plan")
        session_worktree_events = self.worktree_events.list_for_session(session_id, tasks=tasks, limit=20)
        return {
            "session_id": session_id,
            "exists": context is not None or bool(messages),
            "active_goal": getattr(context, "active_goal", None) if context else None,
            "created_at": getattr(context, "created_at", None) if context else None,
            "updated_at": getattr(context, "updated_at", None) if context else None,
            "message_count": len(messages),
            "loaded_in_runtime": session_id in live_sessions,
            "has_pending_plan": pending_plan is not None,
            "recent_messages": messages[-5:],
            "tasks": tasks,
            "execution_history": list(getattr(context, "execution_history", []) or []) if context else [],
            "worktree_event_count": len(session_worktree_events),
        }

    def summarize_session(self, session_id: str, live_sessions: Dict[str, Any]) -> Dict[str, Any]:
        overview = self.get_session_overview(session_id, live_sessions)
        messages = overview["recent_messages"]
        latest_user = next((msg["content"] for msg in reversed(messages) if msg.get("role") == "user"), None)
        latest_assistant = next((msg["content"] for msg in reversed(messages) if msg.get("role") == "assistant"), None)
        active_tasks = [task for task in overview["tasks"] if task.get("status") in {"awaiting_approval", "in_progress"}]
        completed_tasks = [task for task in overview["tasks"] if task.get("status") not in {"awaiting_approval", "in_progress"}]
        lines = [
            f"Session {session_id}",
            f"Messages: {overview['message_count']}",
            f"Loaded in runtime: {overview['loaded_in_runtime']}",
            f"Active goal: {overview['active_goal'] or 'none'}",
            f"Pending plan: {overview['has_pending_plan']}",
            f"Active tasks: {len(active_tasks)}",
            f"Recent completed tasks: {len(completed_tasks)}",
        ]
        if latest_user:
            lines.append(f"Latest user request: {latest_user[:180]}")
        if latest_assistant:
            lines.append(f"Latest assistant response: {latest_assistant[:180]}")
        return {"overview": overview, "summary_text": "\n".join(lines)}

    def export_session(self, session_id: str, live_sessions: Dict[str, Any]) -> Dict[str, Any]:
        overview = self.get_session_overview(session_id, live_sessions)
        context = self.memory_system.get_session(session_id)
        plan, task_id = self.task_manager.restore_pending_plan(session_id)
        session_tasks = self.task_manager.get_session_tasks(session_id, limit=50)
        export_payload = {
            "session": {
                "session_id": session_id,
                "active_goal": overview["active_goal"],
                "created_at": overview["created_at"],
                "updated_at": overview["updated_at"],
                "loaded_in_runtime": overview["loaded_in_runtime"],
                "has_pending_plan": overview["has_pending_plan"] or plan is not None,
            },
            "messages": self.conversation_memory.get_history(session_id, limit=500),
            "tasks": session_tasks,
            "execution_history": list(getattr(context, "execution_history", []) or []) if context else [],
            "worktree_events": self.worktree_events.list_for_session(session_id, tasks=session_tasks, limit=100),
            "pending_plan": task_id and plan and self.task_manager.serialize_plan(plan) or None,
        }
        self.export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_path = self.export_dir / f"session_{session_id}_{timestamp}.json"
        export_path.write_text(json.dumps(export_payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return {"path": str(export_path), "payload": export_payload}

    def resume_session(self, session_id: str, live_sessions: Dict[str, Any]) -> Dict[str, Any]:
        context = self.memory_system.get_session(session_id)
        messages = self.conversation_memory.get_history(session_id, limit=100)
        if context is None and not messages:
            return {"success": False, "error": "Session not found", "session_id": session_id}

        if context is None:
            context = self.memory_system.create_session(session_id)

        live_sessions[session_id] = {"messages": messages}

        plan, task_id = self.task_manager.restore_pending_plan(session_id)
        restored_pending = False
        if plan is not None:
            live_sessions[session_id]["pending_agent_plan"] = plan
            live_sessions[session_id]["pending_agent_plan_iteration"] = None
            live_sessions[session_id]["pending_task_id"] = task_id
            restored_pending = True

        return {
            "success": True,
            "session_id": session_id,
            "message_count": len(messages),
            "restored_pending_plan": restored_pending,
            "active_goal": getattr(context, "active_goal", None),
            "task_count": len(self.task_manager.get_session_tasks(session_id, limit=20)),
        }

    def compact_session(
        self,
        session_id: str,
        live_sessions: Dict[str, Any],
        keep_recent: int = 8,
    ) -> Dict[str, Any]:
        overview = self.get_session_overview(session_id, live_sessions)
        if not overview["exists"]:
            return {"success": False, "error": "Session not found", "session_id": session_id}

        messages = self.conversation_memory.get_history(session_id, limit=500)
        compaction = self.context_compactor.compact_messages(
            messages=messages,
            active_goal=overview["active_goal"],
            keep_recent=keep_recent,
        )

        if not compaction["compacted"]:
            return {
                "success": True,
                "session_id": session_id,
                "already_compact": True,
                "summary_text": compaction["summary_text"],
                "message_count": len(messages),
            }

        summary_message = {
            "role": "system",
            "content": compaction["summary_text"],
            "metadata": {
                "type": "session_compaction",
                "removed_count": compaction["removed_count"],
                "retained_count": compaction["retained_count"],
            },
        }
        replacement_messages = [summary_message, *compaction["retained_messages"]]
        self.conversation_memory.replace_history(session_id, replacement_messages)
        self.memory_system.refresh_session(session_id)

        if session_id in live_sessions:
            live_sessions[session_id]["messages"] = self.conversation_memory.get_history(session_id, limit=100)

        if hasattr(self.memory_system, "save_memory_note"):
            self.memory_system.save_memory_note(
                scope="project",
                title=f"Session compacted: {session_id}",
                content=compaction["summary_text"],
                metadata={
                    "type": "session_compaction",
                    "session_id": session_id,
                    "removed_count": compaction["removed_count"],
                    "retained_count": compaction["retained_count"],
                },
                source_session_id=session_id,
            )

        return {
            "success": True,
            "session_id": session_id,
            "already_compact": False,
            "summary_text": compaction["summary_text"],
            "removed_count": compaction["removed_count"],
            "retained_count": compaction["retained_count"],
            "message_count": len(replacement_messages),
        }
