import asyncio

from api import improvement_api
from core.gap_detector import GapDetector
from core.gap_tracker import GapRecord


class _FakeCapabilityMapper:
    def has_capability(self, capability: str) -> bool:
        return False


class _DummyLoop:
    llm_client = None


def test_gap_detector_classifies_no_matching_skill():
    detector = GapDetector(_FakeCapabilityMapper())

    gap = detector.analyze_failed_task(
        "Research this topic across web sources",
        "",
        skill_selection={
            "matched": False,
            "category": "web",
            "fallback_mode": "direct_tool_routing",
        },
    )

    assert gap is not None
    assert gap.gap_type == "no_matching_skill"
    assert gap.suggested_action == "improve_skill_routing"
    assert gap.capability == "skill:web"


def test_gap_detector_classifies_missing_tool_within_skill():
    detector = GapDetector(_FakeCapabilityMapper())

    gap = detector.analyze_failed_task(
        "Inspect this codebase and fix this bug",
        "I don't have the capability to do that yet.",
        skill_selection={
            "matched": True,
            "skill_name": "code_workspace",
            "category": "development",
            "fallback_mode": "direct_tool_routing",
        },
    )

    assert gap is not None
    assert gap.gap_type == "matched_skill_missing_tool"
    assert gap.suggested_action == "create_tool"
    assert gap.selected_skill == "code_workspace"


def test_suggest_next_tool_prefers_skill_routing_improvements(monkeypatch):
    import core.gap_tracker as gap_tracker_module

    monkeypatch.setattr(
        gap_tracker_module.GapTracker,
        "get_prioritized_gaps",
        lambda self: [
            GapRecord(
                capability="skill:web",
                first_seen="2026-01-01T00:00:00",
                last_seen="2026-01-02T00:00:00",
                occurrence_count=4,
                confidence_avg=0.84,
                reasons=["No matching skill for an actionable request"],
                gap_type="no_matching_skill",
                suggested_action="improve_skill_routing",
                selected_skill=None,
                selected_category="web",
            )
        ],
    )

    improvement_api.set_loop_instance(_DummyLoop())
    response = asyncio.run(improvement_api.suggest_next_tool())

    assert response.action == "improve_skill_routing"
    assert response.gap_type == "no_matching_skill"
    assert response.suggested_action == "improve_skill_routing"


def test_gap_detector_classifies_actionable_request_without_tool_call():
    detector = GapDetector(_FakeCapabilityMapper())

    gap = detector.analyze_failed_task(
        "play expedition 33 trailer",
        "NO_TOOL_CALLS_FOR_ACTIONABLE_REQUEST",
        skill_selection={
            "matched": True,
            "skill_name": "web_research",
            "category": "web",
            "fallback_mode": "planned_fallback",
        },
    )

    assert gap is not None
    assert gap.gap_type == "actionable_request_no_tool_call"
    assert gap.suggested_action == "improve_skill_routing"
    assert gap.selected_skill == "web_research"


def test_gap_detector_classifies_missing_skill_workflow():
    detector = GapDetector(_FakeCapabilityMapper())

    gap = detector.analyze_failed_task(
        "play expedition 33 trailer",
        "planned fallback: browser workflow missing for playback",
        skill_selection={
            "matched": True,
            "skill_name": "web_research",
            "category": "web",
            "fallback_mode": "planned_fallback",
        },
    )

    assert gap is not None
    assert gap.gap_type == "matched_skill_missing_workflow"
    assert gap.suggested_action == "improve_skill_workflow"
    assert gap.selected_skill == "web_research"
