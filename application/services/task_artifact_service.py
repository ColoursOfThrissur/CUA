"""Persistent task artifact service backed by cua.db."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from domain.entities.task import ExecutionPlan, TaskStep
from domain.entities.task_artifact import TaskArtifact, TaskArtifactStep
from infrastructure.persistence.sqlite.cua_database import get_conn


class _EmptyPreview:
    def get_preview(self) -> Dict[str, Any]:
        return {"available": False, "message": "No staging preview is available for task artifacts."}


class TaskArtifactService:
    """Creates and updates task artifacts that survive planning, approval, and execution."""

    ACTIVE_STATUSES = {"awaiting_approval", "in_progress"}
    TERMINAL_STATUSES = {"completed", "completed_with_errors", "failed", "aborted", "rejected"}

    def __init__(self) -> None:
        self.staging_areas: Dict[str, Any] = {}

    def create_task_from_plan(
        self,
        *,
        session_id: str,
        plan: ExecutionPlan,
        status: str,
        source: str = "chat",
        task_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        priority: str = "normal",
    ) -> str:
        now = datetime.now().isoformat()
        task_id = task_id or f"task_{uuid4().hex[:12]}"
        subtasks = self._artifact_steps_from_plan(plan)
        target_file = self._infer_target_file(plan)
        payload = self._artifact_payload(
            task_id=task_id,
            session_id=session_id,
            description=plan.goal,
            goal=plan.goal,
            status=status,
            priority=priority,
            source=source,
            total_subtasks=len(subtasks),
            completed_subtasks=0,
            target_file=target_file,
            execution_id=execution_id,
            plan_json=self._serialize_plan(plan),
            step_results_json=[asdict(step) for step in subtasks],
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        with get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO task_artifacts (
                    task_id, session_id, execution_id, status, description, goal, priority, source,
                    target_file, total_subtasks, completed_subtasks, plan_json, step_results_json,
                    created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._payload_values(payload),
            )
        self.staging_areas[task_id] = _EmptyPreview()
        return task_id

    def attach_execution(self, task_id: str, execution_id: str, status: str = "in_progress") -> None:
        now = datetime.now().isoformat()
        with get_conn() as conn:
            conn.execute(
                "UPDATE task_artifacts SET execution_id = ?, status = ?, updated_at = ? WHERE task_id = ?",
                (execution_id, status, now, task_id),
            )

    def mark_status(self, task_id: str, status: str, completed: bool = False) -> None:
        now = datetime.now().isoformat()
        completed_at = now if completed or status in {"completed", "completed_with_errors", "failed", "aborted", "rejected"} else None
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE task_artifacts
                SET status = ?, updated_at = ?, completed_at = COALESCE(?, completed_at)
                WHERE task_id = ?
                """,
                (status, now, completed_at, task_id),
            )

    def update_from_execution_state(self, task_id: str, state: Any) -> None:
        artifact = self.get_task(task_id)
        if artifact is None:
            return
        step_map = {step.step_id: step for step in self._deserialize_plan(artifact.plan).steps} if artifact.plan else {}
        subtasks: List[TaskArtifactStep] = []
        completed_subtasks = 0
        for existing in artifact.subtasks:
            result = getattr(state, "step_results", {}).get(existing.subtask_id)
            task_step = step_map.get(existing.subtask_id)
            status = self._map_step_status(getattr(getattr(result, "status", None), "value", None) or existing.status)
            if status == "completed":
                completed_subtasks += 1
            output_preview = self._preview_output(getattr(result, "output", None)) if result else existing.output_preview
            attempts = (getattr(result, "retry_count", 0) or 0) + (1 if result else existing.attempts)
            subtasks.append(
                TaskArtifactStep(
                    subtask_id=existing.subtask_id,
                    title=task_step.description if task_step else existing.title,
                    methods=list(existing.methods),
                    status=status,
                    attempts=attempts,
                    max_attempts=(task_step.max_retries if task_step else existing.max_attempts) or 1,
                    error=getattr(result, "error", None) if result else existing.error,
                    output_preview=output_preview,
                )
            )

        task_status = getattr(state, "status", "in_progress") or "in_progress"
        if task_status == "running":
            task_status = "in_progress"
        completed_at = datetime.now().isoformat() if task_status in self.TERMINAL_STATUSES else None
        now = datetime.now().isoformat()
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE task_artifacts
                SET status = ?, completed_subtasks = ?, step_results_json = ?, updated_at = ?, completed_at = COALESCE(?, completed_at)
                WHERE task_id = ?
                """,
                (
                    task_status,
                    completed_subtasks,
                    json.dumps([asdict(step) for step in subtasks]),
                    now,
                    completed_at,
                    task_id,
                ),
            )

    def get_status(self) -> Dict[str, Any]:
        task = self._fetch_latest(statuses=list(self.ACTIVE_STATUSES))
        if task is None:
            return {
                "available": True,
                "active": False,
                "parent_task": None,
                "reason": "No active workflow task",
            }
        return {"available": True, "active": True, "parent_task": self._to_parent_task(task)}

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM task_artifacts
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._to_parent_task(self._row_to_artifact(row)) for row in rows]

    def get_session_tasks(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM task_artifacts
                WHERE session_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [self._to_parent_task(self._row_to_artifact(row)) for row in rows]

    def get_task(self, task_id: str) -> Optional[TaskArtifact]:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM task_artifacts WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._row_to_artifact(row) if row else None

    def find_latest_session_task(
        self,
        session_id: str,
        statuses: Optional[List[str]] = None,
    ) -> Optional[TaskArtifact]:
        return self._fetch_latest(session_id=session_id, statuses=statuses)

    def restore_pending_plan(self, session_id: str) -> Tuple[Optional[ExecutionPlan], Optional[str]]:
        artifact = self.find_latest_session_task(session_id, statuses=["awaiting_approval"])
        if artifact is None or not artifact.plan:
            return None, None
        return self._deserialize_plan(artifact.plan), artifact.task_id

    def serialize_plan(self, plan: ExecutionPlan) -> Dict[str, Any]:
        return self._serialize_plan(plan)

    def abort_parent_task(self, parent_id: str) -> Dict[str, Any]:
        artifact = self.get_task(parent_id)
        if artifact is None:
            return {"success": False, "error": "Task not found", "parent_id": parent_id}
        if artifact.execution_id and artifact.status == "in_progress":
            return {
                "success": False,
                "error": "Abort is not supported for already running execution tasks yet.",
                "parent_id": parent_id,
            }
        self.mark_status(parent_id, "aborted", completed=True)
        return {"success": True, "parent_id": parent_id, "status": "aborted"}

    def _fetch_latest(
        self,
        *,
        session_id: Optional[str] = None,
        statuses: Optional[List[str]] = None,
    ) -> Optional[TaskArtifact]:
        query = "SELECT * FROM task_artifacts"
        conditions = []
        params: List[Any] = []
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            conditions.append(f"status IN ({placeholders})")
            params.extend(statuses)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY updated_at DESC LIMIT 1"
        with get_conn() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        return self._row_to_artifact(row) if row else None

    def _artifact_steps_from_plan(self, plan: ExecutionPlan) -> List[TaskArtifactStep]:
        steps = []
        for step in plan.steps:
            steps.append(
                TaskArtifactStep(
                    subtask_id=step.step_id,
                    title=step.description,
                    methods=[f"{step.tool_name}.{step.operation}"],
                    status="pending",
                    attempts=0,
                    max_attempts=max(1, int(step.max_retries or 1)),
                    error=None,
                )
            )
        return steps

    def _serialize_plan(self, plan: ExecutionPlan) -> Dict[str, Any]:
        payload = asdict(plan)
        workflow_metadata = getattr(plan, "workflow_metadata", None)
        if workflow_metadata:
            payload["workflow_metadata"] = workflow_metadata
        return payload

    def _deserialize_plan(self, payload: Dict[str, Any]) -> ExecutionPlan:
        if isinstance(payload, str):
            payload = json.loads(payload)
        steps = [TaskStep(**step) for step in payload.get("steps", [])]
        plan = ExecutionPlan(
            goal=payload.get("goal", ""),
            steps=steps,
            estimated_duration=payload.get("estimated_duration", 0),
            complexity=payload.get("complexity", "unknown"),
            requires_approval=bool(payload.get("requires_approval", False)),
        )
        if payload.get("workflow_metadata"):
            setattr(plan, "workflow_metadata", payload["workflow_metadata"])
        return plan

    def _artifact_payload(self, **kwargs) -> Dict[str, Any]:
        return kwargs

    def _payload_values(self, payload: Dict[str, Any]) -> tuple:
        return (
            payload["task_id"],
            payload["session_id"],
            payload.get("execution_id"),
            payload["status"],
            payload["description"],
            payload["goal"],
            payload["priority"],
            payload["source"],
            payload.get("target_file", ""),
            payload["total_subtasks"],
            payload["completed_subtasks"],
            json.dumps(payload.get("plan_json")) if payload.get("plan_json") is not None else None,
            json.dumps(payload.get("step_results_json", [])),
            payload.get("created_at"),
            payload.get("updated_at"),
            payload.get("completed_at"),
        )

    def _row_to_artifact(self, row) -> TaskArtifact:
        plan_data = json.loads(row["plan_json"]) if row["plan_json"] else None
        step_rows = json.loads(row["step_results_json"] or "[]")
        subtasks = [TaskArtifactStep(**step) for step in step_rows]
        return TaskArtifact(
            task_id=row["task_id"],
            session_id=row["session_id"],
            description=row["description"],
            goal=row["goal"],
            status=row["status"],
            priority=row["priority"],
            source=row["source"],
            total_subtasks=row["total_subtasks"],
            completed_subtasks=row["completed_subtasks"],
            target_file=row["target_file"] or "",
            execution_id=row["execution_id"],
            plan=plan_data,
            subtasks=subtasks,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )

    def _to_parent_task(self, artifact: TaskArtifact) -> Dict[str, Any]:
        return {
            "parent_id": artifact.task_id,
            "description": artifact.description,
            "goal": artifact.goal,
            "status": artifact.status,
            "priority": artifact.priority,
            "source": artifact.source,
            "target_file": artifact.target_file,
            "session_id": artifact.session_id,
            "execution_id": artifact.execution_id,
            "total_subtasks": artifact.total_subtasks,
            "completed_subtasks": artifact.completed_subtasks,
            "created_at": artifact.created_at,
            "updated_at": artifact.updated_at,
            "workflow_metadata": (artifact.plan or {}).get("workflow_metadata", {}),
            "subtasks": [asdict(step) for step in artifact.subtasks],
        }

    def _map_step_status(self, status: str) -> str:
        mapping = {"running": "in_progress"}
        return mapping.get(status, status or "pending")

    def _preview_output(self, output: Any, max_chars: int = 240) -> Optional[str]:
        if output is None:
            return None
        try:
            if isinstance(output, (dict, list)):
                text = json.dumps(output, default=str)
            else:
                text = str(output)
        except Exception:
            text = str(output)
        return text[:max_chars] + ("..." if len(text) > max_chars else "")

    def _infer_target_file(self, plan: ExecutionPlan) -> str:
        file_like_keys = ("path", "file_path", "source", "destination", "target_file")
        for step in plan.steps:
            params = getattr(step, "parameters", {}) or {}
            for key in file_like_keys:
                value = params.get(key)
                if isinstance(value, str) and value:
                    return value
        return ""
