from core.output_analyzer import OutputAnalyzer


def test_output_analyzer_adds_skill_overview_renderer():
    components = OutputAnalyzer.analyze(
        {"logs": [{"level": "INFO", "message": "done"}], "count": 1},
        tool_name="ShellTool",
        operation="run_command",
        preferred_renderer="automation_result",
        summary="I ran the command successfully.",
        skill_name="computer_automation",
        category="computer",
        output_types=["command_output"],
    )

    assert components[0]["renderer"] == "automation_result"
    assert components[0]["type"] == "agent_result"
    assert components[0]["skill"] == "computer_automation"
    assert components[0]["output_types"] == ["command_output"]


def test_output_analyzer_marks_default_renderer_keys():
    components = OutputAnalyzer.analyze([{"name": "a"}], tool_name="FilesystemTool", operation="list_directory")

    assert components[0]["renderer"] == "table"
    assert components[-1]["renderer"] == "json"


def test_output_analyzer_renders_sources_and_links():
    components = OutputAnalyzer.analyze(
        {
            "sources": [{"url": "https://example.com/a", "mode": "http", "success": True}],
            "links": [{"url": "https://example.com/b", "label": "B"}],
            "content": "combined content",
        },
        tool_name="WebAccessTool",
        operation="search_web",
        preferred_renderer="research_summary",
        summary="I found source-backed results.",
        skill_name="web_research",
        category="web",
        output_types=["research_summary"],
    )

    assert components[0]["renderer"] == "research_summary"
    assert components[0]["highlights"][0]["label"] == "Sources"
    assert any(component.get("title") == "Sources" for component in components)
    assert any(component.get("title") == "Links" for component in components)
