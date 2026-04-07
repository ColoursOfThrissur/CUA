from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from api.chat.skill_handler import build_planner_context, select_skill_for_message
from application.commands.command_models import CommandContext, CommandDefinition, CommandResult
from application.services.memory_maintenance_service import MemoryMaintenanceService
from application.services.worktree_event_service import WorktreeEventService
from application.services.worktree_handoff_service import WorktreeHandoffService
from application.services.worktree_policy_service import WorktreePolicyService
from application.services.worktree_task_service import WorktreeTaskService
from application.services.worktree_isolation_service import WorktreeIsolationService
from application.use_cases.review.workspace_review import WorkspaceReviewUseCase
from domain.policies.immutable_brain_stem import RiskLevel


def _status_snapshot(runtime) -> Dict[str, Any]:
    registry = getattr(runtime, "registry", None)
    skill_registry = getattr(runtime, "skill_registry", None)
    llm_client = getattr(runtime, "llm_client", None)
    tools = list(getattr(registry, "tools", []) or [])
    mcp_tools = [tool for tool in tools if tool.__class__.__name__.startswith("MCPAdapterTool")]

    system_available = bool(getattr(runtime, "system_available", False))
    init_error = getattr(runtime, "init_error", None)

    status = "healthy"
    if not system_available:
        status = "unhealthy"
    elif init_error:
        status = "degraded"

    return {
        "status": status,
        "system_available": system_available,
        "runtime_init_error": init_error,
        "tools": len(tools),
        "skills": len(skill_registry.list_all()) if skill_registry else 0,
        "mcp_tools": len(mcp_tools),
        "model": getattr(llm_client, "model", None),
        "session_count": len(getattr(runtime, "_sessions_ref", {}) or {}),
    }


def _check(name: str, status: str, detail: str) -> Dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def _doctor_checks(runtime, sessions: Dict[str, Any]) -> List[Dict[str, str]]:
    snapshot = _status_snapshot(runtime)
    checks: List[Dict[str, str]] = [
        _check(
            "runtime",
            "pass" if snapshot["system_available"] else "fail",
            "Runtime initialized" if snapshot["system_available"] else (snapshot["runtime_init_error"] or "Runtime unavailable"),
        ),
        _check(
            "llm_model",
            "pass" if snapshot["model"] else "warn",
            f"Active model: {snapshot['model']}" if snapshot["model"] else "No active LLM model",
        ),
        _check(
            "tool_registry",
            "pass" if snapshot["tools"] > 0 else "fail",
            f"{snapshot['tools']} tools loaded",
        ),
        _check(
            "skill_registry",
            "pass" if snapshot["skills"] > 0 else "warn",
            f"{snapshot['skills']} skills loaded",
        ),
        _check(
            "mcp",
            "pass" if snapshot["mcp_tools"] > 0 else "warn",
            f"{snapshot['mcp_tools']} MCP-backed tools loaded",
        ),
        _check(
            "sessions",
            "pass",
            f"{len(sessions)} in-memory sessions active",
        ),
    ]

    try:
        from infrastructure.persistence.sqlite.cua_database import get_conn

        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
        checks.append(_check("database", "pass", "cua.db reachable"))
    except Exception as e:
        checks.append(_check("database", "fail", f"Database check failed: {e}"))

    try:
        from infrastructure.persistence.credential_store import get_credential_store

        store = get_credential_store()
        credential_count = len(store.list_keys())
        store_file = Path("data/credentials.enc")
        if store_file.exists() and credential_count == 0:
            checks.append(_check("credentials", "warn", "Credential store file exists but no readable credentials were loaded"))
        else:
            checks.append(_check("credentials", "pass", f"{credential_count} credentials available"))
    except Exception as e:
        checks.append(_check("credentials", "warn", f"Credential store unavailable: {e}"))

    scheduler = getattr(runtime, "scheduler", None)
    checks.append(
        _check(
            "improvement_scheduler",
            "pass" if getattr(scheduler, "running", False) else "warn",
            "Improvement scheduler running" if getattr(scheduler, "running", False) else "Improvement scheduler not running",
        )
    )
    maintenance_loop = getattr(runtime, "memory_maintenance_loop", None)
    checks.append(
        _check(
            "memory_maintenance",
            "pass" if getattr(maintenance_loop, "running", False) else "warn",
            "Memory maintenance loop running" if getattr(maintenance_loop, "running", False) else "Memory maintenance loop not running",
        )
    )

    try:
        from infrastructure.metrics.scheduler import get_metrics_scheduler

        metrics_scheduler = get_metrics_scheduler()
        checks.append(
            _check(
                "metrics_scheduler",
                "pass" if getattr(metrics_scheduler, "running", False) else "warn",
                "Metrics scheduler running" if getattr(metrics_scheduler, "running", False) else "Metrics scheduler not running",
            )
        )
    except Exception as e:
        checks.append(_check("metrics_scheduler", "warn", f"Metrics scheduler unavailable: {e}"))

    return checks


def run_status_command(context: CommandContext, args: str) -> CommandResult:
    snapshot = _status_snapshot(context.runtime)
    lines = [
        f"System status: {snapshot['status']}",
        f"Runtime available: {snapshot['system_available']}",
        f"Active model: {snapshot['model'] or 'unconfigured'}",
        f"Tools loaded: {snapshot['tools']}",
        f"Skills loaded: {snapshot['skills']}",
        f"MCP tools loaded: {snapshot['mcp_tools']}",
        f"Active sessions: {len(context.sessions)}",
    ]
    if snapshot["runtime_init_error"]:
        lines.append(f"Runtime init error: {snapshot['runtime_init_error']}")

    execution_result = {
        "success": True,
        "mode": "command",
        "command": "status",
        "status_snapshot": snapshot,
        "components": [
            {
                "type": "table",
                "renderer": "table",
                "title": "Runtime Status",
                "columns": ["field", "value"],
                "data": [
                    {"field": "status", "value": snapshot["status"]},
                    {"field": "runtime_available", "value": str(snapshot["system_available"])},
                    {"field": "active_model", "value": snapshot["model"] or "unconfigured"},
                    {"field": "tools_loaded", "value": str(snapshot["tools"])},
                    {"field": "skills_loaded", "value": str(snapshot["skills"])},
                    {"field": "mcp_tools_loaded", "value": str(snapshot["mcp_tools"])},
                    {"field": "active_sessions", "value": str(len(context.sessions))},
                ],
            }
        ],
    }
    return CommandResult(response_text="\n".join(lines), execution_result=execution_result)


def run_doctor_command(context: CommandContext, args: str) -> CommandResult:
    checks = _doctor_checks(context.runtime, context.sessions)
    fail_count = sum(1 for check in checks if check["status"] == "fail")
    warn_count = sum(1 for check in checks if check["status"] == "warn")
    overall = "healthy" if fail_count == 0 and warn_count == 0 else ("degraded" if fail_count == 0 else "unhealthy")

    lines = [f"Doctor result: {overall}"]
    for check in checks:
        badge = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}.get(check["status"], "INFO")
        lines.append(f"[{badge}] {check['name']}: {check['detail']}")

    execution_result = {
        "success": fail_count == 0,
        "mode": "command",
        "command": "doctor",
        "doctor": {
            "overall_status": overall,
            "fail_count": fail_count,
            "warn_count": warn_count,
            "checks": checks,
        },
        "components": [
            {
                "type": "table",
                "renderer": "table",
                "title": "Doctor Checks",
                "columns": ["name", "status", "detail"],
                "data": checks,
            }
        ],
    }
    return CommandResult(response_text="\n".join(lines), success=fail_count == 0, execution_result=execution_result)


def _session_service(context: CommandContext):
    service = getattr(context.runtime, "session_workflow_service", None)
    if service is None:
        raise RuntimeError("Session workflow service is not available")
    return service


def _memory_system(context: CommandContext):
    memory = getattr(context.runtime, "memory_system", None)
    if memory is None:
        raise RuntimeError("Memory system is not available")
    return memory


def _target_session_id(context: CommandContext, args: str) -> str:
    target = (args or "").strip()
    return target or context.session_id


def _task_planner(context: CommandContext):
    planner = getattr(context.runtime, "task_planner", None)
    if planner is None:
        raise RuntimeError("Task planner is not available")
    return planner


def _build_plan_payload(plan) -> Dict[str, Any]:
    payload = asdict(plan)
    workflow_metadata = getattr(plan, "workflow_metadata", None)
    if workflow_metadata:
        payload["workflow_metadata"] = workflow_metadata
    return payload


def _parse_deep_plan_request(raw_args: str) -> Tuple[str, bool]:
    raw = (raw_args or "").strip()
    lowered = raw.lower()
    if lowered.startswith("isolated "):
        return raw[9:].strip(), True
    if lowered.startswith("isolate "):
        return raw[8:].strip(), True
    return raw, False


def run_session_command(context: CommandContext, args: str) -> CommandResult:
    service = _session_service(context)
    arg = (args or "").strip()
    if arg == "list":
        sessions = service.list_sessions(limit=10)
        lines = ["Recent sessions:"]
        for session in sessions:
            lines.append(
                f"- {session['session_id']} | messages={session['message_count']} | "
                f"active_goal={session['active_goal'] or 'none'}"
            )
        return CommandResult(
            response_text="\n".join(lines),
            execution_result={
                "success": True,
                "mode": "command",
                "command": "session",
                "sessions": sessions,
                "components": [
                    {
                        "type": "table",
                        "renderer": "table",
                        "title": "Recent Sessions",
                        "columns": ["session_id", "active_goal", "message_count", "updated_at"],
                        "data": sessions,
                    }
                ],
            },
        )

    session_id = _target_session_id(context, arg)
    overview = service.get_session_overview(session_id, context.sessions)
    if not overview["exists"]:
        return CommandResult(
            response_text=f"Session '{session_id}' was not found.",
            success=False,
            execution_result={"success": False, "error": "session_not_found"},
        )

    lines = [
        f"Session: {session_id}",
        f"Messages: {overview['message_count']}",
        f"Loaded in runtime: {overview['loaded_in_runtime']}",
        f"Active goal: {overview['active_goal'] or 'none'}",
        f"Pending plan: {overview['has_pending_plan']}",
        f"Tracked tasks: {len(overview['tasks'])}",
    ]
    return CommandResult(
        response_text="\n".join(lines),
        execution_result={
            "success": True,
            "mode": "command",
            "command": "session",
            "session_overview": overview,
            "components": [
                {
                    "type": "table",
                    "renderer": "table",
                    "title": "Session Overview",
                    "columns": ["field", "value"],
                    "data": [
                        {"field": "session_id", "value": session_id},
                        {"field": "message_count", "value": str(overview["message_count"])},
                        {"field": "loaded_in_runtime", "value": str(overview["loaded_in_runtime"])},
                        {"field": "active_goal", "value": overview["active_goal"] or "none"},
                        {"field": "pending_plan", "value": str(overview["has_pending_plan"])},
                        {"field": "tracked_tasks", "value": str(len(overview["tasks"]))},
                    ],
                }
            ],
        },
    )


def run_summary_command(context: CommandContext, args: str) -> CommandResult:
    service = _session_service(context)
    session_id = _target_session_id(context, args)
    summary = service.summarize_session(session_id, context.sessions)
    if not summary["overview"]["exists"]:
        return CommandResult(
            response_text=f"Session '{session_id}' was not found.",
            success=False,
            execution_result={"success": False, "error": "session_not_found"},
        )
    return CommandResult(
        response_text=summary["summary_text"],
        execution_result={
            "success": True,
            "mode": "command",
            "command": "summary",
            "session_summary": summary,
        },
    )


def run_export_command(context: CommandContext, args: str) -> CommandResult:
    service = _session_service(context)
    session_id = _target_session_id(context, args)
    overview = service.get_session_overview(session_id, context.sessions)
    if not overview["exists"]:
        return CommandResult(
            response_text=f"Session '{session_id}' was not found.",
            success=False,
            execution_result={"success": False, "error": "session_not_found"},
        )
    exported = service.export_session(session_id, context.sessions)
    return CommandResult(
        response_text=f"Session export created at {exported['path']}",
        execution_result={
            "success": True,
            "mode": "command",
            "command": "export",
            "export_path": exported["path"],
            "export_payload": exported["payload"],
        },
    )


def run_resume_command(context: CommandContext, args: str) -> CommandResult:
    service = _session_service(context)
    session_id = _target_session_id(context, args)
    resumed = service.resume_session(session_id, context.sessions)
    if not resumed["success"]:
        return CommandResult(
            response_text=f"Session '{session_id}' was not found.",
            success=False,
            execution_result={"success": False, "mode": "command", "command": "resume", "error": "session_not_found"},
        )

    lines = [
        f"Resumed session: {session_id}",
        f"Messages restored: {resumed['message_count']}",
        f"Active goal: {resumed['active_goal'] or 'none'}",
        f"Tasks tracked: {resumed['task_count']}",
        f"Pending plan restored: {resumed['restored_pending_plan']}",
    ]
    return CommandResult(
        response_text="\n".join(lines),
        execution_result={
            "success": True,
            "mode": "command",
            "command": "resume",
            "resume": resumed,
        },
    )


def run_compact_command(context: CommandContext, args: str) -> CommandResult:
    service = _session_service(context)
    raw = (args or "").strip()
    keep_recent = 8
    session_id = context.session_id

    if raw.isdigit():
        keep_recent = max(2, int(raw))
    elif raw:
        session_id = raw

    compacted = service.compact_session(session_id, context.sessions, keep_recent=keep_recent)
    if not compacted["success"]:
        return CommandResult(
            response_text=f"Session '{session_id}' was not found.",
            success=False,
            execution_result={"success": False, "mode": "command", "command": "compact", "error": "session_not_found"},
        )

    if compacted.get("already_compact"):
        response_text = compacted["summary_text"]
    else:
        response_text = (
            f"Compacted session: {session_id}\n"
            f"Removed messages: {compacted['removed_count']}\n"
            f"Retained messages: {compacted['retained_count']}\n"
            f"{compacted['summary_text']}"
        )

    return CommandResult(
        response_text=response_text,
        execution_result={
            "success": True,
            "mode": "command",
            "command": "compact",
            "compaction": compacted,
        },
    )


def run_memory_command(context: CommandContext, args: str) -> CommandResult:
    memory = _memory_system(context)
    raw = (args or "").strip()
    try:
        if not raw:
            overview = memory.get_memory_overview()
            lines = [
                "Explicit memory overview:",
                f"User notes: {overview['counts']['user']}",
                f"Project notes: {overview['counts']['project']}",
                f"Total notes: {overview['counts']['total']}",
            ]
            for note in overview["recent"]:
                lines.append(f"- [{note['scope']}] {note['title']}")
            return CommandResult(
                response_text="\n".join(lines),
                execution_result={
                    "success": True,
                    "mode": "command",
                    "command": "memory",
                    "memory_overview": overview,
                    "components": [
                        {
                            "type": "table",
                            "renderer": "table",
                            "title": "Memory Overview",
                            "columns": ["scope", "count"],
                            "data": [
                                {"scope": "user", "count": str(overview["counts"]["user"])},
                                {"scope": "project", "count": str(overview["counts"]["project"])},
                                {"scope": "total", "count": str(overview["counts"]["total"])},
                            ],
                        }
                    ],
                },
            )

        action, _, remainder = raw.partition(" ")
        action = action.lower()
        remainder = remainder.strip()

        if action == "list":
            scope = remainder or None
            notes = memory.list_memory_notes(scope=scope, limit=10)
            lines = [f"Memory notes ({scope or 'all scopes'}):"]
            for note in notes:
                lines.append(f"- [{note['scope']}] {note['title']}: {note['content'][:120]}")
            if not notes:
                lines.append("No memory notes found.")
            return CommandResult(
                response_text="\n".join(lines),
                execution_result={
                    "success": True,
                    "mode": "command",
                    "command": "memory",
                    "memory_notes": notes,
                },
            )

        if action == "search":
            if not remainder:
                return CommandResult(
                    response_text="Usage: /memory search <query>",
                    success=False,
                    execution_result={"success": False, "mode": "command", "command": "memory", "error": "missing_query"},
                )
            notes = memory.search_memory_notes(remainder, limit=10)
            lines = [f"Memory search results for '{remainder}':"]
            for note in notes:
                lines.append(f"- [{note['scope']}] {note['title']} (score={note['score']}): {note['content'][:120]}")
            if not notes:
                lines.append("No matching memory notes found.")
            return CommandResult(
                response_text="\n".join(lines),
                execution_result={
                    "success": True,
                    "mode": "command",
                    "command": "memory",
                    "memory_search": {"query": remainder, "results": notes},
                },
            )

        if action == "save":
            scope = "project"
            content = remainder
            first_token, _, after_scope = remainder.partition(" ")
            if first_token.lower() in {"user", "project"}:
                scope = first_token.lower()
                content = after_scope.strip()
            if not content:
                return CommandResult(
                    response_text="Usage: /memory save [user|project] <content>",
                    success=False,
                    execution_result={"success": False, "mode": "command", "command": "memory", "error": "missing_content"},
                )
            note = memory.save_memory_note(
                scope=scope,
                content=content,
                source_session_id=context.session_id,
            )
            return CommandResult(
                response_text=f"Saved {scope} memory note: {note['title']}",
                execution_result={
                    "success": True,
                    "mode": "command",
                    "command": "memory",
                    "saved_note": note,
                },
            )
        if action == "maintain":
            from infrastructure.persistence.file_storage.strategic_memory import get_strategic_memory

            report = MemoryMaintenanceService(
                memory_system=memory,
                strategic_memory=get_strategic_memory(),
            ).run_maintenance()
            lines = [
                "Memory maintenance completed.",
                f"Notes scanned: {report['notes_scanned']}",
                f"Deleted notes: {report['deleted_notes']}",
                f"Duplicate notes removed: {report['duplicate_notes_removed']}",
                f"Compaction notes removed: {report['compaction_notes_removed']}",
                f"Strategic records removed: {report['strategic_memory']['removed_records']}",
            ]
            return CommandResult(
                response_text="\n".join(lines),
                execution_result={
                    "success": True,
                    "mode": "command",
                    "command": "memory",
                    "memory_maintenance": report,
                },
            )
    except ValueError as exc:
        return CommandResult(
            response_text=str(exc),
            success=False,
            execution_result={"success": False, "mode": "command", "command": "memory", "error": "invalid_scope"},
        )

    return CommandResult(
        response_text="Usage: /memory, /memory list [scope], /memory search <query>, /memory save [user|project] <content>, /memory maintain",
        success=False,
        execution_result={"success": False, "mode": "command", "command": "memory", "error": "invalid_subcommand"},
    )


def run_worktree_command(context: CommandContext, args: str) -> CommandResult:
    raw = (args or "").strip()
    service = WorktreeTaskService()
    event_service = WorktreeEventService()
    handoff_service = WorktreeHandoffService()

    if raw.lower() == "list":
        listed = service.list_worktrees()
        if not listed["success"]:
            return CommandResult(
                response_text=f"Worktree listing blocked: {listed['reason']}",
                success=False,
                execution_result={"success": False, "mode": "command", "command": "worktree", "worktree_list": listed},
            )
        lines = [
            f"Known worktrees: {len(listed['worktrees'])}",
            f"Cleanup candidates: {listed.get('cleanup_candidate_count', 0)}",
        ]
        for worktree in listed["worktrees"][:12]:
            cleanup = worktree.get("cleanup_recommendation") or {}
            lines.append(
                f"- {worktree['label'] or Path(worktree['path']).name} | branch={worktree['branch'] or 'detached'} | "
                f"dirty={worktree['dirty']} | managed={worktree['managed']} | "
                f"idle_hours={worktree.get('idle_hours')} | cleanup={cleanup.get('action', 'n/a')} | "
                f"handoff={((worktree.get('handoff') or {}).get('owner') or 'none')}"
            )
        if not listed["worktrees"]:
            lines.append("No git worktrees are registered for this repository.")
        return CommandResult(
            response_text="\n".join(lines),
            success=True,
            execution_result={
                "success": True,
                "mode": "command",
                "command": "worktree",
                "worktree_list": listed,
                "components": [
                    {
                        "type": "table",
                        "renderer": "table",
                        "title": "Registered Worktrees",
                        "columns": ["label", "branch", "dirty", "managed", "idle_hours", "cleanup_recommendation", "path"],
                        "data": [
                            {
                                **item,
                                "cleanup_recommendation": (item.get("cleanup_recommendation") or {}).get("action", ""),
                            }
                            for item in listed["worktrees"]
                        ]
                        or [{"label": "none", "branch": "", "dirty": False, "managed": False, "path": ""}],
                    }
                ],
            },
        )

    if raw.lower() == "handoff list":
        listed = handoff_service.list_handoffs()
        lines = [f"Active handoffs: {listed.get('handoff_count', 0)}"]
        for item in listed.get("handoffs", [])[:12]:
            handoff = item.get("handoff") or {}
            lines.append(
                f"- {item.get('label')} -> {handoff.get('owner')} | purpose={handoff.get('purpose', '')} | expires={handoff.get('expires_at', '')}"
            )
        if not listed.get("handoffs"):
            lines.append("No active worktree handoffs are currently registered.")
        return CommandResult(
            response_text="\n".join(lines),
            success=True,
            execution_result={
                "success": True,
                "mode": "command",
                "command": "worktree",
                "worktree_handoffs": listed,
            },
        )

    if raw.lower().startswith("handoff release "):
        label = raw[16:].strip()
        try:
            released = handoff_service.release_handoff(label)
        except RuntimeError as exc:
            return CommandResult(
                response_text=f"Worktree handoff release blocked: {exc}",
                success=False,
                execution_result={"success": False, "mode": "command", "command": "worktree", "error": "handoff_release_failed"},
            )
        if not released["success"]:
            return CommandResult(
                response_text=f"Worktree handoff release blocked: {released['reason']}",
                success=False,
                execution_result={"success": False, "mode": "command", "command": "worktree", "worktree_handoff_release": released},
            )
        return CommandResult(
            response_text=f"Released handoff for {released['label']} from {released['handoff'].get('owner')}.",
            success=True,
            execution_result={
                "success": True,
                "mode": "command",
                "command": "worktree",
                "worktree_handoff_release": released,
            },
        )

    if raw.lower().startswith("handoff "):
        payload = raw[8:].strip()
        if not payload:
            return CommandResult(
                response_text="Usage: /worktree handoff <label> <owner> [purpose] or /worktree handoff release <label>",
                success=False,
                execution_result={"success": False, "mode": "command", "command": "worktree", "error": "missing_handoff_args"},
            )
        parts = payload.split()
        if len(parts) < 2:
            return CommandResult(
                response_text="Usage: /worktree handoff <label> <owner> [purpose]",
                success=False,
                execution_result={"success": False, "mode": "command", "command": "worktree", "error": "missing_handoff_owner"},
            )
        label, owner = parts[0], parts[1]
        purpose = " ".join(parts[2:]).strip() or "bounded handoff"
        pending_task_id = context.sessions.get(context.session_id, {}).get("pending_task_id")
        try:
            handed_off = handoff_service.assign_handoff(
                label,
                owner=owner,
                purpose=purpose,
                session_id=context.session_id,
                task_id=pending_task_id,
            )
        except RuntimeError as exc:
            return CommandResult(
                response_text=f"Worktree handoff blocked: {exc}",
                success=False,
                execution_result={"success": False, "mode": "command", "command": "worktree", "error": "handoff_failed"},
            )
        if not handed_off["success"]:
            return CommandResult(
                response_text=f"Worktree handoff blocked: {handed_off['reason']}",
                success=False,
                execution_result={"success": False, "mode": "command", "command": "worktree", "worktree_handoff": handed_off},
            )
        return CommandResult(
            response_text=(
                f"Assigned worktree {handed_off['label']} to {handed_off['handoff']['owner']}.\n"
                f"Purpose: {handed_off['handoff']['purpose']}\n"
                f"Cleanup expectation: {handed_off['handoff']['cleanup_expectation']}"
            ),
            success=True,
            execution_result={
                "success": True,
                "mode": "command",
                "command": "worktree",
                "worktree_handoff": handed_off,
            },
        )

    if raw.lower() in {"cleanup", "cleanup preview"}:
        cleanup = service.cleanup_worktrees(apply=False)
        lines = [
            f"Cleanup candidates: {cleanup.get('candidate_count', 0)}",
            "Review the candidates below. Re-run with /worktree cleanup apply to remove clean stale worktrees.",
        ]
        for item in cleanup.get("candidates", [])[:12]:
            recommendation = item.get("cleanup_recommendation") or {}
            lines.append(
                f"- {item.get('label') or Path(item.get('path') or '').name} | "
                f"idle_hours={item.get('idle_hours')} | action={recommendation.get('action', 'n/a')}"
            )
        if not cleanup.get("candidates"):
            lines.append("No clean stale Forge-managed worktrees are ready for cleanup.")
        event_service.record_event(
            "cleanup_preview_for_session",
            session_id=context.session_id,
            details={
                "candidate_count": cleanup.get("candidate_count", 0),
                "candidate_labels": cleanup.get("candidate_labels", []),
            },
        )
        return CommandResult(
            response_text="\n".join(lines),
            success=True,
            execution_result={
                "success": True,
                "mode": "command",
                "command": "worktree",
                "worktree_cleanup": cleanup,
            },
        )

    if raw.lower() == "cleanup apply":
        cleanup = service.cleanup_worktrees(apply=True)
        lines = [
            f"Cleanup removed: {cleanup.get('removed_count', 0)}",
            f"Cleanup failed: {cleanup.get('failed_count', 0)}",
        ]
        for item in cleanup.get("removed", [])[:12]:
            lines.append(f"- removed {item.get('label')} -> {item.get('worktree_path')}")
        for item in cleanup.get("failed", [])[:12]:
            lines.append(f"- failed {item.get('label')}: {item.get('reason')}")
        if not cleanup.get("removed") and not cleanup.get("failed"):
            lines.append("No clean stale Forge-managed worktrees required cleanup.")
        event_service.record_event(
            "cleanup_applied_for_session",
            session_id=context.session_id,
            details={
                "removed_count": cleanup.get("removed_count", 0),
                "failed_count": cleanup.get("failed_count", 0),
            },
        )
        return CommandResult(
            response_text="\n".join(lines),
            success=True,
            execution_result={
                "success": True,
                "mode": "command",
                "command": "worktree",
                "worktree_cleanup": cleanup,
            },
        )

    if raw.lower().startswith("create "):
        label = raw[7:].strip()
        created = service.create_worktree(label)
        if not created["success"]:
            return CommandResult(
                response_text=f"Worktree creation blocked: {created['reason']}",
                success=False,
                execution_result={"success": False, "mode": "command", "command": "worktree", "worktree_create": created},
            )
        lines = [
            f"Worktree created: {created['label']}",
            f"Branch: {created['branch_name']}",
            f"Base branch: {created['base_branch']}",
            f"Path: {created['worktree_path']}",
        ]
        event_service.record_event(
            "created_for_session",
            worktree_label=created["label"],
            worktree_path=created["worktree_path"],
            session_id=context.session_id,
            details={"command": "/worktree create"},
        )
        return CommandResult(
            response_text="\n".join(lines),
            success=True,
            execution_result={"success": True, "mode": "command", "command": "worktree", "worktree_create": created},
        )

    if raw.lower().startswith("remove "):
        remainder = raw[7:].strip()
        force = False
        if remainder.lower().endswith(" --force"):
            force = True
            remainder = remainder[:-8].strip()
        removed = service.remove_worktree(remainder, force=force)
        if not removed["success"]:
            return CommandResult(
                response_text=f"Worktree removal blocked: {removed['reason']}",
                success=False,
                execution_result={"success": False, "mode": "command", "command": "worktree", "worktree_remove": removed},
            )
        lines = [
            f"Worktree removed: {removed['label']}",
            f"Path: {removed['worktree_path']}",
            f"Force: {removed['force']}",
            "Branch preserved for manual follow-up if you still need it.",
        ]
        event_service.record_event(
            "removed_for_session",
            worktree_label=removed["label"],
            worktree_path=removed["worktree_path"],
            session_id=context.session_id,
            details={"command": "/worktree remove", "force": removed["force"]},
        )
        return CommandResult(
            response_text="\n".join(lines),
            success=True,
            execution_result={"success": True, "mode": "command", "command": "worktree", "worktree_remove": removed},
        )

    readiness = WorktreeIsolationService().get_readiness()
    policy = WorktreePolicyService().recommend(goal="", readiness=readiness)
    lines = [
        f"Worktree readiness: {readiness['status']}",
        f"Ready: {readiness['ready']}",
        f"Reason: {readiness['reason']}",
        f"Isolation policy: broad refactors, renames, migrations, or destructive sweeps should use isolated worktrees.",
    ]
    if readiness.get("branch"):
        lines.append(f"Branch: {readiness['branch']}")
    if readiness.get("git_root"):
        lines.append(f"Git root: {readiness['git_root']}")
    for changed in readiness.get("changed_files", [])[:8]:
        lines.append(f"- {changed}")

    return CommandResult(
        response_text="\n".join(lines),
        success=True,
        execution_result={
            "success": True,
            "mode": "command",
            "command": "worktree",
            "worktree": readiness,
            "worktree_policy": policy,
            "components": [
                {
                    "type": "table",
                    "renderer": "table",
                    "title": "Worktree Readiness",
                    "columns": ["name", "status", "detail"],
                    "data": readiness.get("checks", []),
                }
            ],
        },
    )


def run_plan_command(context: CommandContext, args: str) -> CommandResult:
    goal, isolated_mode = _parse_deep_plan_request(args)
    if not goal:
        return CommandResult(
            response_text="Usage: /plan <goal> or /plan isolated <goal>",
            success=False,
            execution_result={"success": False, "mode": "command", "command": "plan", "error": "missing_goal"},
        )

    planner = _task_planner(context)
    skill_selection = select_skill_for_message(
        goal,
        getattr(context.runtime, "skill_registry", None),
        getattr(context.runtime, "skill_selector", None),
        getattr(context.runtime, "llm_client", None),
        getattr(context.runtime, "registry", None),
    )
    planner_context = build_planner_context(
        skill_selection,
        getattr(context.runtime, "skill_registry", None),
        user_request=goal,
    ) or {}

    skill_context = dict(planner_context.get("skill_context") or {})
    planning_hints = dict(skill_context.get("planning_hints") or {})
    planning_hints["planning_mode"] = "deep"
    workflow_guidance = list(skill_context.get("workflow_guidance") or [])
    workflow_guidance.append("Surface assumptions explicitly and bias toward resumable checkpoints.")
    skill_context.update(
        {
            "planning_mode": "deep",
            "planning_hints": planning_hints,
            "workflow_guidance": workflow_guidance,
            "include_past_plans": True,
            "include_memory_context": True,
            "include_previous_context": True,
            "include_adaptive_rules": True,
            "use_compact_schema": False,
        }
    )
    planner_context["skill_context"] = skill_context

    plan = planner.plan_task(goal, planner_context)
    readiness = WorktreeIsolationService().get_readiness()
    policy = WorktreePolicyService().recommend(goal=goal, plan=plan, readiness=readiness)
    workflow_metadata: Dict[str, Any] = {"planning_mode": "deep", "isolation_policy": policy}
    if isolated_mode:
        worktree_service = WorktreeTaskService()
        label = worktree_service.derive_label(goal)
        created = worktree_service.create_worktree(label)
        if not created["success"]:
            return CommandResult(
                response_text=f"Isolated planning blocked: {created['reason']}",
                success=False,
                execution_result={
                    "success": False,
                    "mode": "command",
                    "command": "plan",
                    "error": "worktree_prepare_failed",
                    "worktree_create": created,
                },
            )
        workflow_metadata.update(
            {
                "execution_mode": "isolated_worktree",
                "worktree": created,
            }
        )
    plan.requires_approval = True
    if workflow_metadata:
        setattr(plan, "workflow_metadata", workflow_metadata)
    context.sessions.setdefault(context.session_id, {"messages": []})
    context.sessions[context.session_id]["pending_agent_plan"] = plan
    context.sessions[context.session_id]["pending_agent_plan_iteration"] = None

    task_manager = getattr(context.runtime, "task_manager", None)
    task_id = None
    if task_manager:
        task_id = task_manager.create_task_from_plan(
            session_id=context.session_id,
            plan=plan,
            status="awaiting_approval",
            source="planned_command",
        )
        context.sessions[context.session_id]["pending_task_id"] = task_id

    lines = [
        "Deep plan prepared.",
        f"Goal: {goal}",
        f"Complexity: {plan.complexity}",
        f"Estimated duration: {plan.estimated_duration}",
        f"Steps: {len(plan.steps)}",
        "Reply 'go ahead' to execute it.",
    ]
    if isolated_mode:
        worktree = workflow_metadata.get("worktree", {})
        WorktreeEventService().record_event(
            "prepared_for_execution",
            worktree_label=worktree.get("label", ""),
            worktree_path=worktree.get("worktree_path", ""),
            session_id=context.session_id,
            task_id=task_id,
            details={"goal": goal, "planning_mode": "deep"},
        )
        lines.insert(1, f"Prepared isolated worktree: {worktree.get('label')}")
        lines.append(f"Worktree path: {worktree.get('worktree_path')}")
    elif policy.get("level") in {"suggested", "required"}:
        if policy.get("level") == "required":
            WorktreeEventService().record_event(
                "isolation_recommended",
                session_id=context.session_id,
                task_id=task_id,
                details={"goal": goal, "recommended_mode": policy.get("recommended_mode", "inline")},
            )
        lines.append(f"Isolation guidance: {policy['level']} -> {policy['reason']}")
        if policy.get("level") == "required" and policy.get("can_prepare"):
            lines.append(f"Recommended next command: /plan isolated {goal}")
        if not policy.get("can_prepare") and policy.get("blocked_reason"):
            lines.append(f"Preparation blocked right now: {policy['blocked_reason']}")
    return CommandResult(
        response_text="\n".join(lines),
        success=True,
        execution_result={
            "success": True,
            "mode": "command",
            "command": "plan",
            "plan": _build_plan_payload(plan),
            "task_id": task_id,
            "planning_mode": "deep",
            "workflow_metadata": workflow_metadata,
            "isolation_policy": policy,
            "suggested_command": f"/plan isolated {goal}" if (not isolated_mode and policy.get("level") == "required" and policy.get("can_prepare")) else None,
            "components": [
                {
                    "type": "table",
                    "renderer": "table",
                    "title": "Plan Steps",
                    "columns": ["step_id", "description", "tool_name", "operation", "dependencies"],
                    "data": [
                        {
                            "step_id": step.step_id,
                            "description": step.description,
                            "tool_name": step.tool_name,
                            "operation": step.operation,
                            "dependencies": ", ".join(step.dependencies),
                        }
                        for step in plan.steps
                    ],
                },
                *(
                    [
                        {
                            "type": "table",
                            "renderer": "table",
                            "title": "Isolation Policy",
                            "columns": ["field", "value"],
                            "data": [
                                {"field": "policy_level", "value": policy.get("level", "optional")},
                                {"field": "recommended_mode", "value": policy.get("recommended_mode", "inline")},
                                {"field": "repo_aware_steps", "value": policy.get("repo_aware_steps", 0)},
                                {"field": "can_prepare", "value": policy.get("can_prepare", False)},
                            ],
                        },
                        {
                            "type": "table",
                            "renderer": "table",
                            "title": "Execution Profile",
                            "columns": ["field", "value"],
                            "data": [
                                {"field": "mode", "value": workflow_metadata.get("execution_mode", "inline")},
                                {"field": "worktree_label", "value": workflow_metadata.get("worktree", {}).get("label", "")},
                                {"field": "worktree_path", "value": workflow_metadata.get("worktree", {}).get("worktree_path", "")},
                            ],
                        }
                    ]
                    if isolated_mode
                    else [
                        {
                            "type": "table",
                            "renderer": "table",
                            "title": "Isolation Policy",
                            "columns": ["field", "value"],
                            "data": [
                                {"field": "policy_level", "value": policy.get("level", "optional")},
                                {"field": "recommended_mode", "value": policy.get("recommended_mode", "inline")},
                                {"field": "repo_aware_steps", "value": policy.get("repo_aware_steps", 0)},
                                {"field": "can_prepare", "value": policy.get("can_prepare", False)},
                            ],
                        }
                    ]
                ),
            ],
        },
    )


def run_review_command(context: CommandContext, args: str) -> CommandResult:
    review = WorkspaceReviewUseCase().review(security=False)
    if not review["ok"]:
        return CommandResult(
            response_text=review["summary"],
            success=False,
            execution_result={"success": False, "mode": "command", "command": "review", "error": review["error"]},
        )

    findings = review["findings"]
    lines = [review["summary"]]
    for finding in findings:
        location = ""
        if finding.file_path:
            location = f" ({finding.file_path}:{finding.line_number or 1})"
        lines.append(f"[{finding.severity.upper()}] {finding.summary}{location}")
    return CommandResult(
        response_text="\n".join(lines),
        execution_result={
            "success": True,
            "mode": "command",
            "command": "review",
            "review": {
                "summary": review["summary"],
                "changed_files": review["changed_files"],
                "findings": [
                    {
                        "severity": item.severity,
                        "summary": item.summary,
                        "file_path": item.file_path,
                        "line_number": item.line_number,
                    }
                    for item in findings
                ],
            },
            "components": [
                {
                    "type": "table",
                    "renderer": "table",
                    "title": "Review Findings",
                    "columns": ["severity", "summary", "file_path", "line_number"],
                    "data": [
                        {
                            "severity": item.severity,
                            "summary": item.summary,
                            "file_path": item.file_path or "",
                            "line_number": str(item.line_number or ""),
                        }
                        for item in findings
                    ],
                },
                {
                    "type": "diff",
                    "renderer": "diff",
                    "title": "Workspace Diff",
                    "payload": review.get("diff", {}),
                },
            ],
        },
    )


def run_security_review_command(context: CommandContext, args: str) -> CommandResult:
    review = WorkspaceReviewUseCase().review(security=True)
    if not review["ok"]:
        return CommandResult(
            response_text=review["summary"],
            success=False,
            execution_result={"success": False, "mode": "command", "command": "security-review", "error": review["error"]},
        )

    findings = review["findings"]
    lines = [review["summary"]]
    for finding in findings:
        location = ""
        if finding.file_path:
            location = f" ({finding.file_path}:{finding.line_number or 1})"
        lines.append(f"[{finding.severity.upper()}] {finding.summary}{location}")
    return CommandResult(
        response_text="\n".join(lines),
        execution_result={
            "success": True,
            "mode": "command",
            "command": "security-review",
            "security_review": {
                "summary": review["summary"],
                "changed_files": review["changed_files"],
                "diff": review.get("diff", {}),
                "findings": [
                    {
                        "severity": item.severity,
                        "summary": item.summary,
                        "file_path": item.file_path,
                        "line_number": item.line_number,
                    }
                    for item in findings
                ],
            },
            "components": [
                {
                    "type": "diff",
                    "renderer": "diff",
                    "title": "Workspace Diff",
                    "payload": review.get("diff", {}),
                }
            ],
        },
    )


def run_mcp_command(context: CommandContext, args: str) -> CommandResult:
    registry = getattr(context.runtime, "registry", None)
    tools = list(getattr(registry, "tools", []) or [])
    adapters = []
    for tool in tools:
        if not tool.__class__.__name__.startswith("MCPAdapterTool"):
            continue
        if hasattr(tool, "get_server_info"):
            try:
                adapters.append(tool.get_server_info())
                continue
            except Exception as exc:
                adapters.append({"server_name": getattr(tool, "_server_name", tool.__class__.__name__), "connected": False, "error": str(exc)})
                continue
        adapters.append({"server_name": getattr(tool, "_server_name", tool.__class__.__name__), "connected": True})

    lines = [f"MCP adapters: {len(adapters)} loaded"]
    for adapter in adapters:
        lines.append(
            f"- {adapter.get('server_name', 'unknown')} | connected={adapter.get('connected', False)} | "
            f"tools={len(adapter.get('tools', [])) if isinstance(adapter.get('tools'), list) else adapter.get('tool_count', 0)}"
        )
    if not adapters:
        lines.append("No MCP adapters are currently loaded.")
    return CommandResult(
        response_text="\n".join(lines),
        execution_result={
            "success": True,
            "mode": "command",
            "command": "mcp",
            "mcp": {"adapters": adapters, "total": len(adapters)},
            "components": [
                {
                    "type": "table",
                    "renderer": "table",
                    "title": "MCP Adapters",
                    "columns": ["server_name", "connected", "error"],
                    "data": adapters or [{"server_name": "none", "connected": False, "error": ""}],
                }
            ],
        },
    )


def run_skills_command(context: CommandContext, args: str) -> CommandResult:
    skill_registry = getattr(context.runtime, "skill_registry", None)
    raw_skills = list(skill_registry.list_all()) if skill_registry else []
    skills = []
    for skill in raw_skills:
        if isinstance(skill, str):
            skills.append({"name": skill, "category": "unknown", "description": ""})
        else:
            skills.append(
                {
                    "name": skill.name,
                    "category": skill.category,
                    "description": skill.description,
                    "preferred_tools": ", ".join(skill.preferred_tools or []),
                    "verification_mode": getattr(skill, "verification_mode", ""),
                }
            )

    lines = [f"Skills loaded: {len(skills)}"]
    for skill in skills[:12]:
        lines.append(f"- {skill['name']} | category={skill.get('category', 'unknown')}")
    if not skills:
        lines.append("No skills are currently loaded.")
    return CommandResult(
        response_text="\n".join(lines),
        execution_result={
            "success": True,
            "mode": "command",
            "command": "skills",
            "skills": skills,
            "components": [
                {
                    "type": "table",
                    "renderer": "table",
                    "title": "Loaded Skills",
                    "columns": ["name", "category", "verification_mode", "preferred_tools"],
                    "data": skills or [{"name": "none", "category": "unknown", "verification_mode": "", "preferred_tools": ""}],
                }
            ],
        },
    )


def builtin_commands() -> List[CommandDefinition]:
    return [
        CommandDefinition(
            name="status",
            description="Show runtime, model, tool, and session status.",
            handler=run_status_command,
            aliases=[],
            category="system",
            risk_level=RiskLevel.SAFE,
        ),
        CommandDefinition(
            name="doctor",
            description="Run a runtime diagnostics pass and report warnings or failures.",
            handler=run_doctor_command,
            aliases=[],
            category="system",
            risk_level=RiskLevel.LOW,
        ),
        CommandDefinition(
            name="session",
            description="Inspect the current session or list recent sessions.",
            handler=run_session_command,
            aliases=[],
            category="session",
            risk_level=RiskLevel.LOW,
        ),
        CommandDefinition(
            name="summary",
            description="Summarize the current session or a target session.",
            handler=run_summary_command,
            aliases=[],
            category="session",
            risk_level=RiskLevel.LOW,
        ),
        CommandDefinition(
            name="export",
            description="Export session messages, tasks, and pending workflow state to JSON.",
            handler=run_export_command,
            aliases=[],
            category="session",
            risk_level=RiskLevel.LOW,
        ),
        CommandDefinition(
            name="resume",
            description="Reload session messages and pending approval state into the live runtime.",
            handler=run_resume_command,
            aliases=[],
            category="session",
            risk_level=RiskLevel.LOW,
        ),
        CommandDefinition(
            name="compact",
            description="Compact older session history into a deterministic summary and keep recent context.",
            handler=run_compact_command,
            aliases=[],
            category="session",
            risk_level=RiskLevel.LOW,
        ),
        CommandDefinition(
            name="memory",
            description="Inspect, search, and save explicit user/project memory notes.",
            handler=run_memory_command,
            aliases=[],
            category="memory",
            risk_level=RiskLevel.LOW,
        ),
        CommandDefinition(
            name="plan",
            description="Create a deeper approval-gated execution plan without running it yet.",
            handler=run_plan_command,
            aliases=["ultraplan"],
            category="planning",
            risk_level=RiskLevel.LOW,
        ),
        CommandDefinition(
            name="worktree",
            description="Inspect whether the current git workspace is ready for isolated worktree execution.",
            handler=run_worktree_command,
            aliases=[],
            category="system",
            risk_level=RiskLevel.MEDIUM,
        ),
        CommandDefinition(
            name="review",
            description="Review the current workspace diff for likely quality issues.",
            handler=run_review_command,
            aliases=[],
            category="review",
            allowed_tools=["FilesystemTool", "GlobTool", "GrepTool"],
            risk_level=RiskLevel.LOW,
        ),
        CommandDefinition(
            name="security-review",
            description="Review the current workspace diff for likely security issues.",
            handler=run_security_review_command,
            aliases=[],
            category="review",
            allowed_tools=["FilesystemTool", "GlobTool", "GrepTool"],
            risk_level=RiskLevel.MEDIUM,
        ),
        CommandDefinition(
            name="mcp",
            description="Show currently loaded MCP adapters and their status.",
            handler=run_mcp_command,
            aliases=[],
            category="system",
            risk_level=RiskLevel.LOW,
        ),
        CommandDefinition(
            name="skills",
            description="List loaded skills and their categories.",
            handler=run_skills_command,
            aliases=[],
            category="system",
            risk_level=RiskLevel.LOW,
        ),
    ]
