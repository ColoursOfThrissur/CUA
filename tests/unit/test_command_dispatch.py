import asyncio
from types import SimpleNamespace

from domain.entities.task import ExecutionPlan, TaskStep

from api.chat_helpers import ChatRequest, create_chat_handler
from application.commands.command_models import CommandContext
from application.commands.dispatch_command import try_execute_command
from application.use_cases.review.workspace_review import ReviewFinding
from domain.policies.session_permissions import PermissionGate


class _FakeRegistry:
    def __init__(self, tools=None):
        self.tools = tools or []

    def get_all_capabilities(self):
        return []


class _FakeSkillRegistry:
    def __init__(self, skills=None):
        self._skills = skills or []

    def list_all(self):
        return list(self._skills)


class _FakeConversationMemory:
    def __init__(self):
        self.saved = []

    def get_history(self, session_id, limit=20):
        return []

    def save_message(self, session_id, role, content):
        self.saved.append((session_id, role, content))


class _FakeMemorySystem:
    def __init__(self):
        self.notes = []

    def get_session(self, session_id):
        return None

    def create_session(self, session_id):
        return None

    def touch_session(self, session_id):
        return None

    def get_memory_overview(self):
        return {
            "counts": {"user": 1, "project": len(self.notes), "total": 1 + len(self.notes)},
            "recent": list(reversed(self.notes[-5:])),
        }

    def list_memory_notes(self, scope=None, limit=10):
        notes = list(self.notes)
        if scope:
            notes = [note for note in notes if note["scope"] == scope]
        return list(reversed(notes[-limit:]))

    def search_memory_notes(self, query, limit=10):
        query_lower = query.lower()
        results = []
        for note in self.notes:
            if query_lower in note["content"].lower() or query_lower in note["title"].lower():
                match = dict(note)
                match["score"] = 1
                results.append(match)
        return list(reversed(results[-limit:]))

    def save_memory_note(self, scope, content, source_session_id=None, title=None, metadata=None, scope_key=None):
        note = {
            "id": len(self.notes) + 1,
            "scope": scope,
            "scope_key": scope_key or ("default_user" if scope == "user" else "workspace"),
            "title": title or content[:80],
            "content": content,
            "source_session_id": source_session_id,
            "metadata": metadata or {},
            "created_at": "2026-04-04T00:00:00",
            "updated_at": "2026-04-04T00:00:01",
        }
        self.notes.append(note)
        return note

    def delete_memory_notes(self, note_ids):
        note_id_set = {int(note_id) for note_id in note_ids}
        before = len(self.notes)
        self.notes = [note for note in self.notes if int(note["id"]) not in note_id_set]
        return before - len(self.notes)


class _FakeLogger:
    def log_request(self, session_id, message):
        return None


class MCPAdapterToolStub:
    def __init__(self, server_name="filesystem"):
        self._server_name = server_name

    def get_server_info(self):
        return {"server_name": self._server_name, "connected": True, "tools": ["read_file", "write_file"]}


class _FakeSkill:
    def __init__(self, name, category):
        self.name = name
        self.category = category
        self.description = f"{name} description"
        self.preferred_tools = ["FilesystemTool"]
        self.verification_mode = "output_validation"


class _FakeSessionWorkflowService:
    def list_sessions(self, limit=10):
        return [
            {
                "session_id": "session-a",
                "active_goal": "ship phase 2",
                "created_at": "2026-04-04T00:00:00",
                "updated_at": "2026-04-04T01:00:00",
                "message_count": 4,
            }
        ]

    def get_session_overview(self, session_id, live_sessions):
        exists = session_id != "missing"
        return {
            "session_id": session_id,
            "exists": exists,
            "active_goal": "ship phase 2" if exists else None,
            "created_at": "2026-04-04T00:00:00" if exists else None,
            "updated_at": "2026-04-04T01:00:00" if exists else None,
            "message_count": 4 if exists else 0,
            "loaded_in_runtime": session_id in live_sessions,
            "has_pending_plan": exists,
            "recent_messages": [
                {"role": "user", "content": "please ship phase 2"},
                {"role": "assistant", "content": "working on it"},
            ] if exists else [],
            "tasks": [{"parent_id": "task-1", "status": "awaiting_approval"}] if exists else [],
            "execution_history": [],
        }

    def summarize_session(self, session_id, live_sessions):
        overview = self.get_session_overview(session_id, live_sessions)
        return {"overview": overview, "summary_text": f"Session {session_id}\nMessages: {overview['message_count']}"}

    def export_session(self, session_id, live_sessions):
        return {
            "path": f"data/exports/{session_id}.json",
            "payload": {"session": {"session_id": session_id}, "messages": [], "tasks": []},
        }

    def resume_session(self, session_id, live_sessions):
        if session_id == "missing":
            return {"success": False, "session_id": session_id, "error": "Session not found"}
        live_sessions[session_id] = {"messages": [{"role": "user", "content": "resume me"}]}
        live_sessions[session_id]["pending_agent_plan"] = {"goal": "restored"}
        return {
            "success": True,
            "session_id": session_id,
            "message_count": 1,
            "restored_pending_plan": True,
            "active_goal": "ship phase 2",
            "task_count": 1,
        }

    def compact_session(self, session_id, live_sessions, keep_recent=8):
        if session_id == "missing":
            return {"success": False, "session_id": session_id, "error": "Session not found"}
        live_sessions.setdefault(session_id, {"messages": []})
        live_sessions[session_id]["messages"] = [
            {"role": "system", "content": "Compacted session context."},
            {"role": "user", "content": "latest request"},
        ]
        return {
            "success": True,
            "session_id": session_id,
            "already_compact": False,
            "summary_text": "Compacted session context.",
            "removed_count": 4,
            "retained_count": keep_recent,
            "message_count": 2,
        }


class _FakeTaskPlanner:
    def plan_task(self, goal, context=None):
        return ExecutionPlan(
            goal=goal,
            steps=[
                TaskStep(
                    step_id="step_1",
                    description="Inspect workspace",
                    tool_name="GlobTool",
                    operation="glob",
                    parameters={"pattern": "**/*.py"},
                    dependencies=[],
                    expected_output="matching files",
                ),
                TaskStep(
                    step_id="step_2",
                    description="Review current focus file",
                    tool_name="FilesystemTool",
                    operation="read_file",
                    parameters={"path": "README.md"},
                    dependencies=["step_1"],
                    expected_output="file contents",
                ),
            ],
            estimated_duration=12,
            complexity="complex",
            requires_approval=False,
        )


class _FakeTaskManager:
    def create_task_from_plan(self, session_id, plan, status, source):
        return f"task-{session_id}"


def _runtime():
    memory_system = _FakeMemorySystem()
    memory_system.save_memory_note("user", "remember preferred review style", source_session_id="seed")
    return SimpleNamespace(
        system_available=True,
        init_error=None,
        registry=_FakeRegistry(tools=[object(), MCPAdapterToolStub()]),
        llm_client=SimpleNamespace(model="qwen3.5:9b"),
        skill_registry=_FakeSkillRegistry(skills=[_FakeSkill("conversation", "conversation"), _FakeSkill("code_workspace", "development")]),
        skill_selector=None,
        conversation_memory=_FakeConversationMemory(),
        task_planner=_FakeTaskPlanner(),
        execution_engine=None,
        autonomous_agent=None,
        tool_orchestrator=None,
        circuit_breaker=None,
        logger=_FakeLogger(),
        scheduler=SimpleNamespace(running=True),
        session_workflow_service=_FakeSessionWorkflowService(),
        task_manager=_FakeTaskManager(),
        memory_system=memory_system,
        permission_gate=None,
    )


def test_try_execute_command_returns_status_snapshot():
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    result = try_execute_command(
        CommandContext(
            runtime=runtime,
            session_id="s1",
            request_message="/status",
            sessions=sessions,
        )
    )

    assert result is not None
    assert result.success is True
    assert result.execution_result["command"] == "status"
    assert result.execution_result["status_snapshot"]["tools"] == 2
    assert "System status: healthy" in result.response_text


def test_try_execute_command_returns_unknown_command_error():
    runtime = _runtime()

    result = try_execute_command(
        CommandContext(
            runtime=runtime,
            session_id="s1",
            request_message="/not-a-real-command",
            sessions={},
        )
    )

    assert result is not None
    assert result.success is False
    assert result.execution_result["error"] == "unknown_command"
    assert "Unknown command" in result.response_text


def test_doctor_command_reports_checks(monkeypatch):
    runtime = _runtime()

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query):
            return self

        def fetchone(self):
            return (1,)

    class _Store:
        def list_keys(self):
            return ["api_key"]

    monkeypatch.setattr(
        "infrastructure.persistence.sqlite.cua_database.get_conn",
        lambda: _Conn(),
    )
    monkeypatch.setattr(
        "infrastructure.persistence.credential_store.get_credential_store",
        lambda: _Store(),
    )
    monkeypatch.setattr(
        "infrastructure.metrics.scheduler.get_metrics_scheduler",
        lambda: SimpleNamespace(running=True),
    )

    result = try_execute_command(
        CommandContext(
            runtime=runtime,
            session_id="s1",
            request_message="/doctor",
            sessions={"s1": {"messages": []}},
        )
    )

    assert result is not None
    assert result.execution_result["command"] == "doctor"
    assert result.execution_result["doctor"]["overall_status"] in {"healthy", "degraded"}
    assert any(check["name"] == "database" for check in result.execution_result["doctor"]["checks"])
    assert "Doctor result:" in result.response_text


def test_chat_handler_routes_slash_command_before_skill_flow():
    runtime = _runtime()
    sessions = {}
    stop_chat, chat = create_chat_handler(runtime, sessions, refresh_registry=lambda: None)

    response = asyncio.run(chat(ChatRequest(message="/status", session_id="session-1")))

    assert response.success is True
    assert response.execution_result["command"] == "status"
    assert response.execution_result["mode"] == "command"
    assert response.response.startswith("System status:")
    assert sessions["session-1"]["messages"][-1]["skill"] == "command"


def test_session_and_summary_commands_use_session_workflow_service():
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    session_result = try_execute_command(
        CommandContext(
            runtime=runtime,
            session_id="s1",
            request_message="/session",
            sessions=sessions,
        )
    )
    summary_result = try_execute_command(
        CommandContext(
            runtime=runtime,
            session_id="s1",
            request_message="/summary",
            sessions=sessions,
        )
    )

    assert session_result.success is True
    assert session_result.execution_result["command"] == "session"
    assert "Tracked tasks: 1" in session_result.response_text
    assert summary_result.success is True
    assert summary_result.execution_result["command"] == "summary"
    assert "Messages: 4" in summary_result.response_text


def test_export_and_resume_commands_report_results():
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    export_result = try_execute_command(
        CommandContext(
            runtime=runtime,
            session_id="s1",
            request_message="/export",
            sessions=sessions,
        )
    )
    resume_result = try_execute_command(
        CommandContext(
            runtime=runtime,
            session_id="s1",
            request_message="/resume",
            sessions=sessions,
        )
    )

    assert export_result.success is True
    assert export_result.execution_result["command"] == "export"
    assert export_result.execution_result["export_path"].endswith("s1.json")
    assert resume_result.success is True
    assert resume_result.execution_result["command"] == "resume"
    assert sessions["s1"]["pending_agent_plan"]["goal"] == "restored"


def test_memory_and_compact_commands_report_results():
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    save_result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/memory save project keep README roadmap synced", sessions=sessions)
    )
    search_result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/memory search roadmap", sessions=sessions)
    )
    compact_result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/compact 6", sessions=sessions)
    )

    assert save_result.success is True
    assert save_result.execution_result["saved_note"]["scope"] == "project"
    assert search_result.success is True
    assert "roadmap" in search_result.response_text.lower()
    assert compact_result.success is True
    assert compact_result.execution_result["command"] == "compact"
    assert "Compacted session:" in compact_result.response_text


def test_plan_and_memory_maintain_commands_report_results(monkeypatch):
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    monkeypatch.setattr(
        "application.commands.builtin.system_commands.select_skill_for_message",
        lambda *args, **kwargs: {
            "matched": True,
            "skill_name": "code_workspace",
            "category": "development",
            "confidence": 0.92,
        },
    )
    monkeypatch.setattr(
        "application.commands.builtin.system_commands.build_planner_context",
        lambda *args, **kwargs: {
            "skill_context": {
                "skill_name": "code_workspace",
                "preferred_tools": ["GlobTool", "FilesystemTool"],
                "planning_hints": {},
                "workflow_guidance": [],
            }
        },
    )
    monkeypatch.setattr(
        "application.commands.builtin.system_commands.MemoryMaintenanceService.run_maintenance",
        lambda self, **kwargs: {
            "success": True,
            "notes_scanned": 4,
            "deleted_notes": 1,
            "duplicate_notes_removed": 1,
            "compaction_notes_removed": 0,
            "strategic_memory": {"removed_records": 2, "remaining_records": 8},
        },
    )

    plan_result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/plan audit the repo and propose safe fixes", sessions=sessions)
    )
    maintain_result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/memory maintain", sessions=sessions)
    )

    assert plan_result.success is True
    assert plan_result.execution_result["planning_mode"] == "deep"
    assert sessions["s1"]["pending_agent_plan"].goal == "audit the repo and propose safe fixes"
    assert maintain_result.success is True
    assert maintain_result.execution_result["memory_maintenance"]["deleted_notes"] == 1


def test_isolated_plan_command_prepares_worktree(monkeypatch):
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    monkeypatch.setattr(
        "application.commands.builtin.system_commands.select_skill_for_message",
        lambda *args, **kwargs: {
            "matched": True,
            "skill_name": "code_workspace",
            "category": "development",
            "confidence": 0.92,
        },
    )
    monkeypatch.setattr(
        "application.commands.builtin.system_commands.build_planner_context",
        lambda *args, **kwargs: {
            "skill_context": {
                "skill_name": "code_workspace",
                "preferred_tools": ["GlobTool", "FilesystemTool"],
                "planning_hints": {},
                "workflow_guidance": [],
            }
        },
    )
    monkeypatch.setattr(
        "application.commands.builtin.system_commands.WorktreeTaskService.create_worktree",
        lambda self, label: {
            "success": True,
            "label": label,
            "branch_name": f"forge/{label}",
            "base_branch": "main",
            "worktree_path": f"C:/repo/.worktrees/{label}",
            "branch_exists": False,
        },
    )

    result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/plan isolated implement phase 8 controls", sessions=sessions)
    )

    assert result.success is True
    assert result.execution_result["workflow_metadata"]["execution_mode"] == "isolated_worktree"
    assert "Prepared isolated worktree:" in result.response_text
    assert getattr(sessions["s1"]["pending_agent_plan"], "workflow_metadata", {})["worktree"]["label"] == "implement-phase-8-controls"


def test_deep_plan_command_reports_isolation_policy_guidance(monkeypatch):
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    monkeypatch.setattr(
        "application.commands.builtin.system_commands.select_skill_for_message",
        lambda *args, **kwargs: {
            "matched": True,
            "skill_name": "code_workspace",
            "category": "development",
            "confidence": 0.92,
        },
    )
    monkeypatch.setattr(
        "application.commands.builtin.system_commands.build_planner_context",
        lambda *args, **kwargs: {
            "skill_context": {
                "skill_name": "code_workspace",
                "preferred_tools": ["GlobTool", "FilesystemTool"],
                "planning_hints": {},
                "workflow_guidance": [],
            }
        },
    )
    monkeypatch.setattr(
        "application.commands.builtin.system_commands.WorktreeIsolationService.get_readiness",
        lambda self: {"ready": True, "reason": "clean repo", "status": "ready", "git_root": "C:/repo", "branch": "main"},
    )

    result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/plan refactor the repository search flow", sessions=sessions)
    )

    assert result.success is True
    assert result.execution_result["isolation_policy"]["level"] in {"suggested", "required"}
    assert "Isolation guidance:" in result.response_text


def test_deep_plan_command_recommends_isolated_follow_up_when_required(monkeypatch):
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    monkeypatch.setattr(
        "application.commands.builtin.system_commands.select_skill_for_message",
        lambda *args, **kwargs: {
            "matched": True,
            "skill_name": "code_workspace",
            "category": "development",
            "confidence": 0.92,
        },
    )
    monkeypatch.setattr(
        "application.commands.builtin.system_commands.build_planner_context",
        lambda *args, **kwargs: {
            "skill_context": {
                "skill_name": "code_workspace",
                "preferred_tools": ["GlobTool", "FilesystemTool"],
                "planning_hints": {},
                "workflow_guidance": [],
            }
        },
    )
    monkeypatch.setattr(
        "application.commands.builtin.system_commands.WorktreeIsolationService.get_readiness",
        lambda self: {"ready": True, "reason": "clean repo", "status": "ready", "git_root": "C:/repo", "branch": "main"},
    )

    result = try_execute_command(
        CommandContext(
            runtime=runtime,
            session_id="s1",
            request_message="/plan rename auth modules across the repository and migrate imports",
            sessions=sessions,
        )
    )

    assert result.success is True
    assert result.execution_result["isolation_policy"]["level"] == "required"
    assert result.execution_result["suggested_command"] == "/plan isolated rename auth modules across the repository and migrate imports"
    assert "Recommended next command: /plan isolated rename auth modules across the repository and migrate imports" in result.response_text


def test_review_mcp_and_skills_commands(monkeypatch):
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    monkeypatch.setattr(
        "application.commands.builtin.system_commands.WorkspaceReviewUseCase.review",
        lambda self, security=False: {
            "ok": True,
            "summary": "Workspace review: 2 changed files, 1 findings.",
            "changed_files": [{"status": "M ", "path": "api/server.py"}],
            "findings": [ReviewFinding("medium", "Debug-only output or breakpoint statement was added.", "api/server.py", 42)],
        },
    )

    review_result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/review", sessions=sessions)
    )
    mcp_result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/mcp", sessions=sessions)
    )
    skills_result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/skills", sessions=sessions)
    )

    assert review_result.success is True
    assert review_result.execution_result["command"] == "review"
    assert "[MEDIUM]" in review_result.response_text
    assert mcp_result.success is True
    assert mcp_result.execution_result["mcp"]["total"] == 1
    assert skills_result.success is True
    assert len(skills_result.execution_result["skills"]) == 2


def test_worktree_command_reports_readiness(monkeypatch):
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    monkeypatch.setattr(
        "application.commands.builtin.system_commands.WorktreeIsolationService.get_readiness",
        lambda self: {
            "ready": False,
            "status": "needs_attention",
            "reason": "Uncommitted changes should be reviewed before creating isolated worktrees.",
            "git_root": "C:/repo",
            "branch": "main",
            "changed_files": [" M api/server.py"],
            "checks": [
                {"name": "git_repo", "status": "pass", "detail": "Git root: C:/repo"},
                {"name": "workspace_state", "status": "warn", "detail": "1 uncommitted path(s) present"},
            ],
        },
    )

    result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/worktree", sessions=sessions)
    )

    assert result.success is True
    assert result.execution_result["command"] == "worktree"
    assert result.execution_result["worktree"]["ready"] is False
    assert "Worktree readiness: needs_attention" in result.response_text


def test_worktree_create_command_reports_created_worktree(monkeypatch):
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    monkeypatch.setattr(
        "application.commands.builtin.system_commands.WorktreeTaskService.create_worktree",
        lambda self, label: {
            "success": True,
            "label": label,
            "branch_name": f"forge/{label}",
            "base_branch": "main",
            "worktree_path": f"C:/repo/.worktrees/{label}",
            "branch_exists": False,
        },
    )

    result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/worktree create feature-a", sessions=sessions)
    )

    assert result.success is True
    assert result.execution_result["worktree_create"]["label"] == "feature-a"
    assert "Worktree created: feature-a" in result.response_text


def test_worktree_list_command_reports_registered_worktrees(monkeypatch):
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    monkeypatch.setattr(
        "application.commands.builtin.system_commands.WorktreeTaskService.list_worktrees",
        lambda self: {
            "success": True,
            "ready": True,
            "managed_count": 1,
            "worktrees": [
                {
                    "label": "feature-a",
                    "branch": "forge/feature-a",
                    "dirty": False,
                    "managed": True,
                    "path": "C:/repo/.worktrees/feature-a",
                }
            ],
        },
    )

    result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/worktree list", sessions=sessions)
    )

    assert result.success is True
    assert result.execution_result["worktree_list"]["managed_count"] == 1
    assert "Known worktrees: 1" in result.response_text


def test_worktree_remove_command_reports_removed_worktree(monkeypatch):
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    monkeypatch.setattr(
        "application.commands.builtin.system_commands.WorktreeTaskService.remove_worktree",
        lambda self, label, force=False: {
            "success": True,
            "label": label,
            "worktree_path": f"C:/repo/.worktrees/{label}",
            "force": force,
            "branch_preserved": True,
        },
    )

    result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/worktree remove feature-a", sessions=sessions)
    )

    assert result.success is True
    assert result.execution_result["worktree_remove"]["label"] == "feature-a"
    assert "Worktree removed: feature-a" in result.response_text


def test_worktree_cleanup_preview_command_reports_candidates(monkeypatch):
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    monkeypatch.setattr(
        "application.commands.builtin.system_commands.WorktreeTaskService.cleanup_worktrees",
        lambda self, apply=False: {
            "success": True,
            "mode": "preview",
            "candidate_count": 1,
            "candidates": [
                {
                    "label": "feature-a",
                    "path": "C:/repo/.worktrees/feature-a",
                    "idle_hours": 192,
                    "cleanup_recommendation": {"action": "remove_now"},
                }
            ],
        },
    )

    result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/worktree cleanup", sessions=sessions)
    )

    assert result.success is True
    assert result.execution_result["worktree_cleanup"]["candidate_count"] == 1
    assert "Cleanup candidates: 1" in result.response_text


def test_worktree_cleanup_apply_command_reports_removed_worktrees(monkeypatch):
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    monkeypatch.setattr(
        "application.commands.builtin.system_commands.WorktreeTaskService.cleanup_worktrees",
        lambda self, apply=False: {
            "success": True,
            "mode": "apply",
            "removed_count": 1,
            "failed_count": 0,
            "removed": [{"label": "feature-a", "worktree_path": "C:/repo/.worktrees/feature-a"}],
            "failed": [],
        },
    )

    result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/worktree cleanup apply", sessions=sessions)
    )

    assert result.success is True
    assert result.execution_result["worktree_cleanup"]["removed_count"] == 1
    assert "Cleanup removed: 1" in result.response_text


def test_worktree_handoff_command_assigns_owner(monkeypatch):
    runtime = _runtime()
    sessions = {"s1": {"messages": [], "pending_task_id": "task-123"}}

    monkeypatch.setattr(
        "application.commands.builtin.system_commands.WorktreeHandoffService.assign_handoff",
        lambda self, label, owner, purpose="", session_id=None, task_id=None, cleanup_expectation="release_or_cleanup", lease_hours=24: {
            "success": True,
            "label": label,
            "worktree_path": f"C:/repo/.worktrees/{label}",
            "handoff": {
                "status": "active",
                "owner": owner,
                "purpose": purpose,
                "cleanup_expectation": cleanup_expectation,
                "session_id": session_id,
                "task_id": task_id,
            },
        },
    )

    result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/worktree handoff feature-a worker-a review patch", sessions=sessions)
    )

    assert result.success is True
    assert result.execution_result["worktree_handoff"]["handoff"]["owner"] == "worker-a"
    assert "Assigned worktree feature-a to worker-a." in result.response_text


def test_worktree_handoff_release_command_reports_release(monkeypatch):
    runtime = _runtime()
    sessions = {"s1": {"messages": []}}

    monkeypatch.setattr(
        "application.commands.builtin.system_commands.WorktreeHandoffService.release_handoff",
        lambda self, label, note="": {
            "success": True,
            "label": label,
            "worktree_path": f"C:/repo/.worktrees/{label}",
            "handoff": {"status": "released", "owner": "worker-a"},
        },
    )

    result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/worktree handoff release feature-a", sessions=sessions)
    )

    assert result.success is True
    assert result.execution_result["worktree_handoff_release"]["label"] == "feature-a"
    assert "Released handoff for feature-a from worker-a." in result.response_text


def test_command_permission_denial_blocks_execution():
    runtime = _runtime()
    runtime.permission_gate = PermissionGate()
    runtime.permission_gate.get_session("s1").blocked_commands.add("review")

    result = try_execute_command(
        CommandContext(runtime=runtime, session_id="s1", request_message="/review", sessions={"s1": {"messages": []}})
    )

    assert result is not None
    assert result.success is False
    assert result.execution_result["error"] == "permission_denied"
    assert "blocked" in result.response_text.lower()
