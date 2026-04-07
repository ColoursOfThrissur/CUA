from application.services.worktree_isolation_service import WorktreeIsolationService


def test_worktree_readiness_reports_unavailable_when_not_git_repo(monkeypatch):
    service = WorktreeIsolationService(repo_path=".")

    monkeypatch.setattr(
        service,
        "_run_git",
        lambda args: (_ for _ in ()).throw(RuntimeError("not a git repo")),
    )

    result = service.get_readiness()

    assert result["ready"] is False
    assert result["status"] == "unavailable"
    assert result["checks"][0]["status"] == "fail"


def test_worktree_readiness_reports_dirty_workspace(monkeypatch):
    service = WorktreeIsolationService(repo_path=".")

    def fake_run_git(args):
        if args == ["rev-parse", "--is-inside-work-tree"]:
            return "true\n"
        if args == ["rev-parse", "--show-toplevel"]:
            return "C:/repo\n"
        if args == ["branch", "--show-current"]:
            return "main\n"
        if args == ["status", "--short"]:
            return " M api/server.py\n?? docs/new.md\n"
        raise RuntimeError(f"unexpected args: {args}")

    monkeypatch.setattr(service, "_run_git", fake_run_git)

    result = service.get_readiness()

    assert result["ready"] is False
    assert result["status"] == "needs_attention"
    assert result["branch"] == "main"
    assert len(result["changed_files"]) == 2
