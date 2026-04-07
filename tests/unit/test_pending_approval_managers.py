import json


def test_pending_skills_manager_normalizes_legacy_list_and_records_history(tmp_path):
    storage = tmp_path / "pending_skills.json"
    storage.write_text(
        json.dumps(
            [
                {
                    "id": "skill_1",
                    "skill_name": "legacy_skill",
                    "skill_definition": {"name": "legacy_skill"},
                    "instructions": "demo",
                    "status": "pending",
                    "created_at": "2026-04-07T00:00:00",
                }
            ]
        ),
        encoding="utf-8",
    )

    from application.managers.pending_skills_manager import PendingSkillsManager

    manager = PendingSkillsManager(storage_path=str(storage))
    pending = manager.get_pending_skills()
    assert len(pending) == 1
    assert pending[0]["skill_name"] == "legacy_skill"

    assert manager.approve_skill("skill_1") is True
    assert manager.get_pending_skills() == []

    history = manager.get_history()
    assert len(history) == 1
    assert history[0]["status"] == "approved"
    assert history[0]["approved_at"]


def test_pending_tools_manager_exposes_approval_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    from application.managers.pending_tools_manager import PendingToolsManager

    manager = PendingToolsManager()
    tool_id = manager.add_pending_tool(
        {
            "tool_file": "tools/experimental/ExampleTool.py",
            "description": "Example tool",
        }
    )

    result = manager.approve_tool(tool_id)
    assert result["success"] is True

    pending = manager.get_pending_list()
    history = manager.get_history()

    assert pending == []
    assert len(history) == 1
    assert history[0]["tool_id"] == tool_id
    assert history[0]["status"] == "approved"
    assert history[0]["approved_at"] is not None
