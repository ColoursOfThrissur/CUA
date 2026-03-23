import json

from core.tool_registry_manager import ToolRegistryManager


def test_get_registry_filters_disabled_tools(tmp_path):
    registry_path = tmp_path / "tool_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "tools": {
                    "BrowserAutomationTool": {"name": "BrowserAutomationTool"},
                    "LocalRunNoteTool": {"name": "LocalRunNoteTool"},
                },
                "last_sync": "2026-03-21T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    manager = ToolRegistryManager(registry_path=str(registry_path))
    registry = manager.get_registry()

    assert "BrowserAutomationTool" in registry["tools"]
    assert "LocalRunNoteTool" not in registry["tools"]


def test_update_tool_rejects_disabled_tool(tmp_path):
    registry_path = tmp_path / "tool_registry.json"
    registry_path.write_text(json.dumps({"tools": {}, "last_sync": None}), encoding="utf-8")

    manager = ToolRegistryManager(registry_path=str(registry_path))
    result = manager.update_tool({"name": "LocalRunNoteTool", "source_file": "tools/experimental/LocalRunNoteTool.py"})

    assert result is False
