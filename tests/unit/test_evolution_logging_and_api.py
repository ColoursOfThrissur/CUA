import asyncio
import sqlite3
from types import SimpleNamespace


def test_evolution_logger_updates_single_run_row(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    from infrastructure.logging.tool_evolution_logger import ToolEvolutionLogger

    logger = ToolEvolutionLogger()
    evolution_id = logger.log_run(
        tool_name="SmokeTool",
        user_prompt="Improve smoke tool",
        status="in_progress",
        step="analysis",
        health_before=72.0,
    )
    logger.update_run(
        evolution_id,
        status="failed",
        step="validation",
        error_message="Validation failed",
        confidence=0.61,
        health_before=72.0,
    )

    conn = sqlite3.connect("data/cua.db")
    try:
        rows = conn.execute(
            "SELECT id, status, step, error_message, confidence, health_before FROM evolution_runs"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    assert rows[0][0] == evolution_id
    assert rows[0][1] == "failed"
    assert rows[0][2] == "validation"
    assert rows[0][3] == "Validation failed"
    assert rows[0][4] == 0.61
    assert rows[0][5] == 72.0


def test_auto_evolution_config_updates_active_coordinated_orchestrator(monkeypatch):
    from api.rest.evolution import auto_evolution_api
    from api.rest.evolution.auto_evolution_api import ConfigUpdate

    coordinated_auto = SimpleNamespace(config={"mode": "balanced"})

    def update_config(config):
        coordinated_auto.config.update(config)

    coordinated_auto.update_config = update_config
    coordinated_engine = SimpleNamespace(auto_orchestrator=coordinated_auto)

    monkeypatch.setattr(auto_evolution_api, "coordinated_engine", coordinated_engine, raising=False)
    monkeypatch.setattr(auto_evolution_api, "orchestrator", None, raising=False)

    result = asyncio.run(
        auto_evolution_api.update_config(
            ConfigUpdate(mode="reactive", max_concurrent=4, learning_enabled=False)
        )
    )

    assert result["success"] is True
    assert coordinated_auto.config["mode"] == "reactive"
    assert coordinated_auto.config["max_concurrent"] == 4
    assert coordinated_auto.config["learning_enabled"] is False
