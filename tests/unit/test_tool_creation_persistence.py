import asyncio
import sqlite3
from pathlib import Path
from types import SimpleNamespace


def test_create_tool_route_persists_creation_and_pending_tool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tools" / "experimental").mkdir(parents=True, exist_ok=True)

    from api.rest.system import improvement_router
    from api.rest.system.improvement_router import CreateToolRequest
    from application.managers.pending_tools_manager import PendingToolsManager
    from infrastructure.logging.tool_creation_logger import ToolCreationLogger
    import application.use_cases.tool_lifecycle.tool_creation_flow as creation_flow_module
    import application.services.skill_registry as skill_registry_module

    class FakeToolCreationOrchestrator:
        def __init__(self, *args, **kwargs):
            self.last_spec = {"name": "SmokeCreateTool", "missing_services": []}
            self.last_skill_updates = [{"skill_name": "general", "action": "create_tool"}]

        def create_tool(self, description, llm_client, preferred_tool_name=None, skill_context=None):
            _ = (llm_client, preferred_tool_name, skill_context)
            creation_logger = ToolCreationLogger()
            creation_id = creation_logger.log_creation(
                tool_name="SmokeCreateTool",
                user_prompt=description,
                status="started",
                step="gap_detection",
            )
            creation_logger.log_artifact(
                creation_id,
                "spec",
                "spec_generation",
                {"name": "SmokeCreateTool", "description": description},
            )
            creation_logger.update_creation(
                creation_id,
                tool_name="SmokeCreateTool",
                status="success",
                step="completed",
                code_size=321,
                capabilities_count=1,
            )

            tool_file = Path("tools/experimental/SmokeCreateTool.py")
            tool_file.write_text(
                "\n".join(
                    [
                        "class SmokeCreateTool:",
                        "    def __init__(self, orchestrator=None):",
                        "        self.orchestrator = orchestrator",
                        "",
                        "    def register_capabilities(self):",
                        "        self.add_capability(",
                        "            ToolCapability(",
                        "                name='smoke',",
                        "                description='Smoke test capability',",
                        "                parameters=[]",
                        "            )",
                        "        )",
                        "",
                        "    def execute(self, operation, **kwargs):",
                        "        return {'success': True, 'data': {'operation': operation, 'kwargs': kwargs}}",
                    ]
                ),
                encoding="utf-8",
            )
            return True, "Experimental tool created: SmokeCreateTool"

    monkeypatch.setattr(creation_flow_module, "ToolCreationOrchestrator", FakeToolCreationOrchestrator)
    monkeypatch.setattr(skill_registry_module.SkillRegistry, "load_all", lambda self: None)
    monkeypatch.setattr(skill_registry_module.SkillRegistry, "get", lambda self, name: None)

    fake_loop = SimpleNamespace(
        llm_client=object(),
        pending_tools_manager=PendingToolsManager(),
    )
    monkeypatch.setattr(improvement_router, "loop_instance", fake_loop, raising=False)

    result = asyncio.run(
        improvement_router.create_tool_from_description(
            payload=CreateToolRequest(
                description="Create a smoke test tool",
                tool_name="SmokeCreateTool",
                target_skill="general",
                target_category="general",
            )
        )
    )

    assert result["success"] is True
    assert result["status"] == "pending_approval"
    assert result["pending_tool_id"]

    conn = sqlite3.connect("data/cua.db")
    try:
        creation_count = conn.execute("SELECT COUNT(*) FROM tool_creations").fetchone()[0]
        artifact_count = conn.execute("SELECT COUNT(*) FROM creation_artifacts").fetchone()[0]
    finally:
        conn.close()

    assert creation_count == 1
    assert artifact_count >= 1
    assert len(fake_loop.pending_tools_manager.get_pending_list()) == 1
