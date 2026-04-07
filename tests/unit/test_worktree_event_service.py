from uuid import uuid4

from application.services.task_artifact_service import TaskArtifactService
from application.services.worktree_event_service import WorktreeEventService
from domain.entities.task import ExecutionPlan, TaskStep
from infrastructure.persistence.sqlite.cua_database import get_conn


def _plan_with_worktree():
    plan = ExecutionPlan(
        goal="Ship isolated change",
        steps=[
            TaskStep(
                step_id="step_1",
                description="Inspect repo",
                tool_name="GlobTool",
                operation="glob",
                parameters={"pattern": "**/*.py"},
                dependencies=[],
                expected_output="files",
            )
        ],
        estimated_duration=3,
        complexity="medium",
        requires_approval=True,
    )
    setattr(
        plan,
        "workflow_metadata",
        {
            "execution_mode": "isolated_worktree",
            "worktree": {
                "label": "feature-events",
                "worktree_path": "C:/repo/.worktrees/feature-events",
            },
        },
    )
    return plan


def test_worktree_event_service_records_and_filters_session_events():
    session_id = f"worktree-events-{uuid4().hex[:8]}"
    service = WorktreeEventService()
    tasks = TaskArtifactService()

    with get_conn() as conn:
        conn.execute("DELETE FROM task_artifacts WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM worktree_events WHERE session_id = ?", (session_id,))

    tasks.create_task_from_plan(
        session_id=session_id,
        plan=_plan_with_worktree(),
        status="awaiting_approval",
        source="unit_test",
    )
    service.record_event(
        "prepared_for_execution",
        worktree_label="feature-events",
        worktree_path="C:/repo/.worktrees/feature-events",
        session_id=session_id,
        details={"goal": "Ship isolated change"},
    )
    service.record_event(
        "routed_step",
        worktree_label="feature-events",
        worktree_path="C:/repo/.worktrees/feature-events",
        details={"tool_name": "FilesystemTool"},
    )

    session_tasks = tasks.get_session_tasks(session_id, limit=5)
    events = service.list_for_session(session_id, tasks=session_tasks, limit=10)

    assert len(events) >= 2
    assert {event["event_type"] for event in events} >= {"prepared_for_execution", "routed_step"}
