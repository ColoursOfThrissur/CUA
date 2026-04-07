from pathlib import Path


def test_discover_tool_files_skips_computer_use_support_modules(tmp_path, monkeypatch):
    tools_dir = tmp_path / "tools"
    computer_use_dir = tools_dir / "computer_use"
    computer_use_dir.mkdir(parents=True, exist_ok=True)

    (computer_use_dir / "input_automation_tool.py").write_text("", encoding="utf-8")
    (computer_use_dir / "screen_perception_tool.py").write_text("", encoding="utf-8")
    (computer_use_dir / "system_control_tool.py").write_text("", encoding="utf-8")
    (computer_use_dir / "ocr_clicker.py").write_text("", encoding="utf-8")
    (computer_use_dir / "task_state.py").write_text("", encoding="utf-8")
    (computer_use_dir / "visual_policy.py").write_text("", encoding="utf-8")
    (computer_use_dir / "error_taxonomy.py").write_text("", encoding="utf-8")

    discovered = {path.name for path in computer_use_dir.glob("*_tool.py")}

    assert discovered == {
        "input_automation_tool.py",
        "screen_perception_tool.py",
        "system_control_tool.py",
    }


def test_capability_mapper_scans_only_computer_use_tool_modules(tmp_path):
    tools_dir = tmp_path / "tools"
    computer_use_dir = tools_dir / "computer_use"
    computer_use_dir.mkdir(parents=True, exist_ok=True)

    (computer_use_dir / "input_automation_tool.py").write_text(
        """
from tools.tool_capability import ToolCapability

class InputAutomationTool:
    def register_capabilities(self):
        click_capability = ToolCapability(name="click", description="click", parameters=[], returns="dict", safety_level=None, examples=[])
        self.add_capability(click_capability, self._handle_click)

    def _handle_click(self, **kwargs):
        return {"success": True}
""".strip(),
        encoding="utf-8",
    )
    (computer_use_dir / "ocr_clicker.py").write_text(
        """
class OCRClicker:
    def find_and_click(self, target_text):
        return {"success": True}
""".strip(),
        encoding="utf-8",
    )

    from application.services.capability_mapper import CapabilityMapper

    graph = CapabilityMapper(tools_dir=str(tools_dir)).build_capability_graph()

    assert "click" in graph
    assert not any(key.startswith("ocr_clicker_") for key in graph)
