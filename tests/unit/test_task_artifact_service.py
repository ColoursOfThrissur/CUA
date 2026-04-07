from uuid import uuid4

from application.services.session_workflow_service import SessionWorkflowService
from application.services.task_artifact_service import TaskArtifactService
from application.services.worktree_event_service import WorktreeEventService
from application.use_cases.execution.execution_engine import ExecutionState, StepResult, StepStatus
from domain.entities.task import ExecutionPlan, TaskStep
from infrastructure.persistence.file_storage.conversation_memory import ConversationMemory
from infrastructure.persistence.file_storage.memory_system import MemorySystem
from infrastructure.persistence.sqlite.cua_database import get_conn


def _sample_plan():
    return ExecutionPlan(
        goal="Review and ship phase 2",
        steps=[
            TaskStep(
                step_id="step_1",
                description="Inspect docs",
                tool_name="FilesystemTool",
                operation="read_file",
                parameters={"path": "docs/CLAUDE_CODE_ADOPTION_PLAN.md"},
                dependencies=[],
                expected_output="doc contents",
                max_retries=2,
            ),
            TaskStep(
                step_id="step_2",
                description="Update README",
                tool_name="FilesystemTool",
                operation="write_file",
                parameters={"path": "README.md"},
                dependencies=["step_1"],
                expected_output="updated readme",
                max_retries=1,
            ),
        ],
        estimated_duration=5,
        complexity="medium",
        requires_approval=True,
    )


def test_task_artifact_service_tracks_plan_and_restore_roundtrip():
    session_id = f"task-artifact-{uuid4().hex[:8]}"
    service = TaskArtifactService()
    plan = _sample_plan()

    with get_conn() as conn:
        conn.execute("DELETE FROM task_artifacts WHERE session_id = ?", (session_id,))

    task_id = service.create_task_from_plan(
        session_id=session_id,
        plan=plan,
        status="awaiting_approval",
        source="unit_test",
    )

    restored_plan, restored_task_id = service.restore_pending_plan(session_id)
    tasks = service.get_session_tasks(session_id, limit=5)

    assert restored_task_id == task_id
    assert restored_plan.goal == plan.goal
    assert len(restored_plan.steps) == 2
    assert tasks[0]["status"] == "awaiting_approval"
    assert tasks[0]["total_subtasks"] == 2

    state = ExecutionState(plan=plan, task_id=task_id, session_id=session_id)
    state.status = "completed"
    state.step_results = {
        "step_1": StepResult(step_id="step_1", status=StepStatus.COMPLETED, output={"ok": True}, retry_count=0),
        "step_2": StepResult(step_id="step_2", status=StepStatus.COMPLETED, output="done", retry_count=1),
    }
    service.attach_execution(task_id, "exec-123")
    service.update_from_execution_state(task_id, state)

    updated = service.get_task(task_id)
    assert updated.status == "completed"
    assert updated.completed_subtasks == 2
    assert updated.subtasks[1].attempts == 2


def test_task_artifact_service_preserves_workflow_metadata():
    session_id = f"task-workflow-{uuid4().hex[:8]}"
    service = TaskArtifactService()
    plan = _sample_plan()
    setattr(
        plan,
        "workflow_metadata",
        {
            "planning_mode": "deep",
            "execution_mode": "isolated_worktree",
            "worktree": {
                "label": "feature-a",
                "git_root": "C:/repo",
                "worktree_path": "C:/repo/.worktrees/feature-a",
            },
        },
    )

    with get_conn() as conn:
        conn.execute("DELETE FROM task_artifacts WHERE session_id = ?", (session_id,))

    task_id = service.create_task_from_plan(
        session_id=session_id,
        plan=plan,
        status="awaiting_approval",
        source="unit_test",
    )

    restored_plan, restored_task_id = service.restore_pending_plan(session_id)
    task = service.get_task(task_id)
    session_tasks = service.get_session_tasks(session_id, limit=5)

    assert restored_task_id == task_id
    assert getattr(restored_plan, "workflow_metadata", {})["execution_mode"] == "isolated_worktree"
    assert task.plan["workflow_metadata"]["worktree"]["label"] == "feature-a"
    assert session_tasks[0]["workflow_metadata"]["worktree"]["worktree_path"].endswith("feature-a")


def test_session_workflow_service_can_resume_and_export(tmp_path):
    session_id = f"session-flow-{uuid4().hex[:8]}"
    memory = MemorySystem()
    conversation = ConversationMemory()
    tasks = TaskArtifactService()
    worktree_events = WorktreeEventService()
    workflow = SessionWorkflowService(memory, conversation, tasks, export_dir=str(tmp_path))
    plan = _sample_plan()
    setattr(
        plan,
        "workflow_metadata",
        {
            "planning_mode": "deep",
            "execution_mode": "isolated_worktree",
            "worktree": {
                "label": "feature-export",
                "git_root": "C:/repo",
                "worktree_path": "C:/repo/.worktrees/feature-export",
            },
        },
    )

    with get_conn() as conn:
        conn.execute("DELETE FROM task_artifacts WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM worktree_events WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM worktree_events WHERE worktree_label = ?", ("feature-export",))
        conn.execute("DELETE FROM worktree_events WHERE worktree_path = ?", ("C:/repo/.worktrees/feature-export",))

    memory.create_session(session_id)
    conversation.save_message(session_id, "user", "please resume this work")
    conversation.save_message(session_id, "assistant", "plan ready")
    tasks.create_task_from_plan(
        session_id=session_id,
        plan=plan,
        status="awaiting_approval",
        source="unit_test",
    )
    worktree_events.record_event(
        "prepared_for_execution",
        worktree_label="feature-export",
        worktree_path="C:/repo/.worktrees/feature-export",
        session_id=session_id,
        details={"goal": plan.goal},
    )

    live_sessions = {}
    resumed = workflow.resume_session(session_id, live_sessions)
    exported = workflow.export_session(session_id, live_sessions)

    assert resumed["success"] is True
    assert resumed["restored_pending_plan"] is True
    assert "pending_agent_plan" in live_sessions[session_id]
    assert exported["path"].endswith(".json")
    assert len(exported["payload"]["messages"]) == 2
    assert len(exported["payload"]["tasks"]) == 1
    assert len(exported["payload"]["worktree_events"]) == 1
    assert exported["payload"]["worktree_events"][0]["event_type"] == "prepared_for_execution"


def test_session_workflow_service_can_compact_and_store_summary_memory(tmp_path):
    session_id = f"session-compact-{uuid4().hex[:8]}"
    memory = MemorySystem()
    conversation = ConversationMemory()
    tasks = TaskArtifactService()
    workflow = SessionWorkflowService(memory, conversation, tasks, export_dir=str(tmp_path))

    with get_conn() as conn:
        conn.execute("DELETE FROM memory_entries WHERE source_session_id = ?", (session_id,))
        conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    memory.create_session(session_id)
    memory.set_active_goal(session_id, "compact this session")
    for idx in range(12):
        role = "user" if idx % 2 == 0 else "assistant"
        conversation.save_message(session_id, role, f"message {idx}")

    live_sessions = {session_id: {"messages": conversation.get_history(session_id, limit=20)}}
    compacted = workflow.compact_session(session_id, live_sessions, keep_recent=4)
    compacted_history = conversation.get_history(session_id, limit=20)
    notes = memory.list_memory_notes(scope="project", limit=10)

    assert compacted["success"] is True
    assert compacted["removed_count"] == 8
    assert len(compacted_history) == 5
    assert compacted_history[0]["role"] == "system"
    assert "Compacted session context." in compacted_history[0]["content"]
    assert any(note["source_session_id"] == session_id for note in notes)
