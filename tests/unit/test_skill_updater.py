import json
from pathlib import Path

from core.skills import SkillUpdater


def test_skill_updater_applies_tool_creation_update(tmp_path):
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "web_research"
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.json").write_text(
        json.dumps(
            {
                "name": "web_research",
                "category": "web",
                "description": "test",
                "trigger_examples": [],
                "preferred_tools": ["BrowserAutomationTool"],
                "required_tools": [],
                "preferred_connectors": [],
                "input_types": [],
                "output_types": ["research_summary"],
                "verification_mode": "source_backed",
                "risk_level": "medium",
                "ui_renderer": "research_summary",
                "fallback_strategy": "direct_tool_routing",
            }
        ),
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text("# Web Research\n", encoding="utf-8")

    updater = SkillUpdater(str(skills_root))
    plan = updater.plan_tool_creation_update(
        "web_research",
        "VideoPlaybackTool",
        operations=["open_video", "play_video"],
        output_types=["video_playback_result"],
        gap_context={
            "gap_type": "actionable_request_no_tool_call",
            "suggested_action": "improve_skill_routing",
            "reasons": ["Actionable request produced no tool calls despite available execution paths"],
        },
    )

    result = updater.apply_update_plan(plan)

    assert result["success"] is True
    skill_data = json.loads((skill_dir / "skill.json").read_text(encoding="utf-8"))
    assert "VideoPlaybackTool" in skill_data["preferred_tools"]
    assert "video_playback_result" in skill_data["output_types"]
    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "VideoPlaybackTool" in skill_md
    assert "Managed Workflow Updates" in skill_md
    assert "execution-first" in skill_md
    assert "play expedition 33 trailer" not in skill_md


def test_skill_updater_includes_example_request_and_error(tmp_path):
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "web_research"
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.json").write_text(
        json.dumps(
            {
                "name": "web_research",
                "category": "web",
                "description": "test",
                "trigger_examples": [],
                "preferred_tools": [],
                "required_tools": [],
                "preferred_connectors": [],
                "input_types": [],
                "output_types": [],
                "verification_mode": "source_backed",
                "risk_level": "medium",
                "ui_renderer": "research_summary",
                "fallback_strategy": "direct_tool_routing",
            }
        ),
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text("# Web Research\n", encoding="utf-8")

    updater = SkillUpdater(str(skills_root))
    plan = updater.plan_tool_creation_update(
        "web_research",
        "VideoPlaybackTool",
        operations=["open_video", "play_video"],
        gap_context={
            "gap_type": "matched_skill_missing_workflow",
            "suggested_action": "improve_skill_workflow",
            "reasons": ["Workflow path was incomplete for video playback"],
            "example_tasks": ["play expedition 33 trailer"],
            "example_errors": ["planned fallback: browser workflow missing for playback"],
        },
    )

    updater.apply_update_plan(plan)
    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

    assert "play expedition 33 trailer" in skill_md
    assert "browser workflow missing for playback" in skill_md


def test_skill_updater_finds_skills_for_existing_tool():
    updater = SkillUpdater("skills")
    matches = updater.find_skills_for_tool("FilesystemTool")

    assert "computer_automation" in matches or "code_workspace" in matches
