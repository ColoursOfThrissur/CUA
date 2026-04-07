from pathlib import Path
from datetime import datetime, timedelta, timezone

from application.services.worktree_handoff_service import WorktreeHandoffService
from application.services.memory_maintenance_service import MemoryMaintenanceService
from application.services.worktree_policy_service import WorktreePolicyService
from application.services.worktree_task_service import WorktreeTaskService


class _MemoryStub:
    def __init__(self):
        self.notes = [
            {
                "id": 1,
                "scope": "project",
                "scope_key": "repo",
                "title": "Session compacted: a",
                "content": "Compacted session context.",
                "metadata": {"type": "session_compaction"},
                "updated_at": "2026-04-04T00:00:03",
            },
            {
                "id": 2,
                "scope": "project",
                "scope_key": "repo",
                "title": "Session compacted: a",
                "content": "Compacted session context.",
                "metadata": {"type": "session_compaction"},
                "updated_at": "2026-04-03T00:00:03",
            },
            {
                "id": 3,
                "scope": "user",
                "scope_key": "default_user",
                "title": "Preference",
                "content": "Prefer review findings first",
                "metadata": {},
                "updated_at": "2026-04-04T00:00:04",
            },
        ]

    def list_memory_notes(self, limit=500):
        return list(self.notes)[:limit]

    def delete_memory_notes(self, note_ids):
        note_id_set = {int(note_id) for note_id in note_ids}
        self.notes = [note for note in self.notes if int(note["id"]) not in note_id_set]
        return len(note_id_set)


class _StrategicMemoryStub:
    def run_maintenance(self, stale_days=120):
        return {"removed_records": 2, "remaining_records": 7}


def test_memory_maintenance_service_prunes_duplicates_and_reports_stats():
    service = MemoryMaintenanceService(_MemoryStub(), _StrategicMemoryStub())

    report = service.run_maintenance(keep_recent_compactions=1)

    assert report["deleted_notes"] == 1
    assert report["duplicate_notes_removed"] == 1
    assert report["strategic_memory"]["removed_records"] == 2


def test_worktree_task_service_creates_new_branch_when_ready(tmp_path, monkeypatch):
    service = WorktreeTaskService(repo_path=str(tmp_path))

    monkeypatch.setattr(
        service.readiness,
        "get_readiness",
        lambda: {
            "ready": True,
            "status": "ready",
            "reason": "clean repo",
            "git_root": str(tmp_path),
            "branch": "main",
        },
    )

    calls = []

    def fake_run_git(args, cwd=None):
        calls.append((tuple(args), str(cwd or service.repo_path)))
        if args[:2] == ["branch", "--list"]:
            return ""
        if args[:2] == ["worktree", "add"]:
            return "created\n"
        raise RuntimeError(f"unexpected args: {args}")

    monkeypatch.setattr(service, "_run_git", fake_run_git)

    result = service.create_worktree("feature-plan")

    assert result["success"] is True
    assert result["branch_name"] == "forge/feature-plan"
    assert Path(result["worktree_path"]).name == "feature-plan"
    assert any(call[0][:3] == ("worktree", "add", "-b") for call in calls)


def test_worktree_task_service_lists_managed_worktrees(tmp_path, monkeypatch):
    service = WorktreeTaskService(repo_path=str(tmp_path))

    monkeypatch.setattr(
        service.readiness,
        "get_readiness",
        lambda: {
            "ready": True,
            "status": "ready",
            "reason": "clean repo",
            "git_root": str(tmp_path),
            "branch": "main",
        },
    )

    def fake_run_git(args, cwd=None):
        if args == ["worktree", "list", "--porcelain"]:
            return (
                f"worktree {tmp_path}\n"
                "HEAD abc123\n"
                "branch refs/heads/main\n\n"
                f"worktree {tmp_path / '.worktrees' / 'feature-plan'}\n"
                "HEAD def456\n"
                "branch refs/heads/forge/feature-plan\n"
            )
        if args[:1] == ["-C"] and args[-2:] == ["status", "--short"]:
            return ""
        raise RuntimeError(f"unexpected args: {args}")

    monkeypatch.setattr(service, "_run_git", fake_run_git)

    result = service.list_worktrees()

    assert result["success"] is True
    assert result["managed_count"] == 1
    assert any(item["label"] == "feature-plan" for item in result["worktrees"])


def test_worktree_task_service_lists_lifecycle_metadata_and_cleanup_guidance(tmp_path, monkeypatch):
    service = WorktreeTaskService(repo_path=str(tmp_path))

    monkeypatch.setattr(
        service.readiness,
        "get_readiness",
        lambda: {
            "ready": True,
            "status": "ready",
            "reason": "clean repo",
            "git_root": str(tmp_path),
            "branch": "main",
        },
    )

    worktree_dir = tmp_path / ".worktrees" / "feature-plan"

    def fake_run_git(args, cwd=None):
        if args[:2] == ["branch", "--list"]:
            return ""
        if args[:2] == ["worktree", "add"]:
            worktree_dir.mkdir(parents=True, exist_ok=True)
            return "created\n"
        if args == ["worktree", "list", "--porcelain"]:
            return (
                f"worktree {tmp_path}\n"
                "HEAD abc123\n"
                "branch refs/heads/main\n\n"
                f"worktree {worktree_dir}\n"
                "HEAD def456\n"
                "branch refs/heads/forge/feature-plan\n"
            )
        if args[:1] == ["-C"] and args[-2:] == ["status", "--short"]:
            return ""
        raise RuntimeError(f"unexpected args: {args}")

    monkeypatch.setattr(service, "_run_git", fake_run_git)

    created = service.create_worktree("feature-plan")
    listed = service.list_worktrees()
    item = next(entry for entry in listed["worktrees"] if entry["managed"])

    assert created["metadata"]["created_at"]
    assert item["created_at"]
    assert item["cleanup_recommendation"]["action"] == "keep_recent"
    assert listed["cleanup_candidate_count"] == 0


def test_worktree_task_service_flags_stale_clean_worktrees_for_cleanup(tmp_path, monkeypatch):
    service = WorktreeTaskService(repo_path=str(tmp_path))
    worktree_dir = tmp_path / ".worktrees" / "feature-plan"
    worktree_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        service.readiness,
        "get_readiness",
        lambda: {
            "ready": True,
            "status": "ready",
            "reason": "clean repo",
            "git_root": str(tmp_path),
            "branch": "main",
        },
    )

    stale_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    WorktreeTaskService._write_metadata(
        worktree_dir,
        {
            "version": 1,
            "label": "feature-plan",
            "git_root": str(tmp_path),
            "worktree_path": str(worktree_dir),
            "created_at": stale_time,
            "last_activity_at": stale_time,
        },
    )

    def fake_run_git(args, cwd=None):
        if args == ["worktree", "list", "--porcelain"]:
            return (
                f"worktree {tmp_path}\n"
                "HEAD abc123\n"
                "branch refs/heads/main\n\n"
                f"worktree {worktree_dir}\n"
                "HEAD def456\n"
                "branch refs/heads/forge/feature-plan\n"
            )
        if args[:1] == ["-C"] and args[-2:] == ["status", "--short"]:
            return ""
        raise RuntimeError(f"unexpected args: {args}")

    monkeypatch.setattr(service, "_run_git", fake_run_git)

    result = service.list_worktrees()
    item = next(entry for entry in result["worktrees"] if entry["managed"])

    assert item["cleanup_recommendation"]["action"] == "remove_now"
    assert result["cleanup_candidate_count"] == 1


def test_worktree_task_service_blocks_dirty_remove_without_force(tmp_path, monkeypatch):
    service = WorktreeTaskService(repo_path=str(tmp_path))
    worktree_dir = tmp_path / ".worktrees" / "feature-plan"
    worktree_dir.mkdir(parents=True)

    monkeypatch.setattr(
        service.readiness,
        "get_readiness",
        lambda: {
            "ready": True,
            "status": "ready",
            "reason": "clean repo",
            "git_root": str(tmp_path),
            "branch": "main",
        },
    )

    def fake_run_git(args, cwd=None):
        if args[:1] == ["-C"] and args[-2:] == ["status", "--short"]:
            return " M api/server.py\n"
        raise RuntimeError(f"unexpected args: {args}")

    monkeypatch.setattr(service, "_run_git", fake_run_git)

    result = service.remove_worktree("feature-plan", force=False)

    assert result["success"] is False
    assert result["error"] == "dirty_worktree"


def test_worktree_policy_service_requires_isolation_for_repo_wide_changes():
    policy = WorktreePolicyService().recommend(
        goal="rename auth modules across the repository and migrate imports",
        readiness={"ready": True, "reason": "clean repo"},
    )

    assert policy["level"] == "required"
    assert policy["recommended_mode"] == "isolated_worktree"


def test_worktree_task_service_cleanup_preview_and_apply(tmp_path, monkeypatch):
    service = WorktreeTaskService(repo_path=str(tmp_path))
    stale_dir = tmp_path / ".worktrees" / "feature-plan"
    stale_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        service.readiness,
        "get_readiness",
        lambda: {
            "ready": True,
            "status": "ready",
            "reason": "clean repo",
            "git_root": str(tmp_path),
            "branch": "main",
        },
    )

    stale_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    WorktreeTaskService._write_metadata(
        stale_dir,
        {
            "version": 1,
            "label": "feature-plan",
            "git_root": str(tmp_path),
            "worktree_path": str(stale_dir),
            "created_at": stale_time,
            "last_activity_at": stale_time,
        },
    )

    removed = []

    def fake_run_git(args, cwd=None):
        if args == ["worktree", "list", "--porcelain"]:
            return (
                f"worktree {tmp_path}\n"
                "HEAD abc123\n"
                "branch refs/heads/main\n\n"
                f"worktree {stale_dir}\n"
                "HEAD def456\n"
                "branch refs/heads/forge/feature-plan\n"
            )
        if args[:1] == ["-C"] and args[-2:] == ["status", "--short"]:
            return ""
        if args[:2] == ["worktree", "remove"]:
            removed.append(str(args[-1]))
            return ""
        if args[:2] == ["worktree", "prune"]:
            return ""
        raise RuntimeError(f"unexpected args: {args}")

    monkeypatch.setattr(service, "_run_git", fake_run_git)

    preview = service.cleanup_worktrees(apply=False)
    applied = service.cleanup_worktrees(apply=True)

    assert preview["candidate_count"] == 1
    assert preview["candidate_labels"] == ["feature-plan"]
    assert applied["removed_count"] == 1
    assert removed == [str(stale_dir.resolve())]


def test_worktree_handoff_service_assigns_and_releases_handoff(tmp_path, monkeypatch):
    handoffs = WorktreeHandoffService(repo_path=str(tmp_path))
    worktree_dir = tmp_path / ".worktrees" / "feature-plan"
    worktree_dir.mkdir(parents=True, exist_ok=True)
    WorktreeTaskService._write_metadata(
        worktree_dir,
        {
            "version": 1,
            "label": "feature-plan",
            "git_root": str(tmp_path),
            "worktree_path": str(worktree_dir),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_activity_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    def fake_list_worktrees():
        metadata = WorktreeTaskService._read_metadata(worktree_dir) or {}
        return {
            "success": True,
            "worktrees": [
                {
                    "label": "feature-plan",
                    "path": str(worktree_dir),
                    "branch": "forge/feature-plan",
                    "dirty": False,
                    "managed": True,
                    "handoff": metadata.get("handoff", {}),
                }
            ],
        }

    monkeypatch.setattr(handoffs.task_service, "list_worktrees", fake_list_worktrees)

    assigned = handoffs.assign_handoff("feature-plan", owner="worker-a", purpose="review isolated patch", session_id="s1")
    listed = handoffs.list_handoffs()
    released = handoffs.release_handoff("feature-plan", note="done")

    assert assigned["success"] is True
    assert assigned["handoff"]["owner"] == "worker-a"
    assert listed["handoff_count"] == 1
    assert released["success"] is True
    assert released["handoff"]["status"] == "released"
