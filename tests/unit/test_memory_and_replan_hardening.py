from contextlib import contextmanager
import sqlite3

from application.use_cases.execution.execution_engine import ExecutionEngine, ExecutionState, StepResult, StepStatus
from domain.entities.task import ExecutionPlan, TaskStep
from infrastructure.llm.prompt_builder import PlanningPromptBuilder
from infrastructure.persistence.file_storage.evolution_constraint_memory import EvolutionConstraintMemory
from infrastructure.persistence.file_storage.strategic_memory import StrategicMemory


def test_strategic_memory_retrieves_semantically_similar_finance_goal(tmp_path):
    memory = StrategicMemory(tmp_path / "strategic_memory.json")
    memory.record(
        goal="Fetch AAPL stock",
        skill_name="web_research",
        steps=[{"tool_name": "HTTPTool", "operation": "get", "domain": "web"}],
        success=True,
        duration_s=1.2,
    )

    matches = memory.retrieve(
        goal="Get Apple financial data",
        skill_name="web_research",
        top_k=1,
        min_win_rate=0.0,
    )

    assert matches
    assert matches[0].goal_sample == "Fetch AAPL stock"


def test_prompt_builder_includes_completed_artifacts_for_replan():
    builder = PlanningPromptBuilder()
    prompt = builder.build_replan_prompt(
        original_goal="Download a paragraph and summarize it",
        remaining_steps=[
            TaskStep(
                step_id="step_2",
                description="Summarize the downloaded text",
                tool_name="ContextSummarizerTool",
                operation="summarize",
                parameters={},
                dependencies=["step_1"],
                expected_output="summary",
            )
        ],
        completed_summary={"step_1": "Downloaded source text successfully"},
        completed_artifacts={
            "step_1": {
                "kind": "text",
                "output": "Apple reported stronger services revenue while iPhone demand stayed stable.",
                "truncated": False,
            }
        },
        failed_errors={"step_2": "summarizer timeout"},
        available_tools={"ContextSummarizerTool": []},
    )

    assert "COMPLETED STEP ARTIFACTS" in prompt
    assert "Apple reported stronger services revenue" in prompt
    assert "Prefer reusing completed step artifacts" in prompt


def test_execution_engine_builds_replan_artifacts_with_payloads():
    plan = ExecutionPlan(goal="demo", steps=[], estimated_duration=1, complexity="low")
    state = ExecutionState(plan=plan)
    state.step_results["step_1"] = StepResult(
        step_id="step_1",
        status=StepStatus.COMPLETED,
        output={"text": "hello world", "items": [1, 2, 3]},
    )

    engine = ExecutionEngine(tool_registry=None)
    artifacts = engine._build_replan_artifacts(state)

    assert "step_1" in artifacts
    assert artifacts["step_1"]["kind"] == "structured"
    assert "hello world" in artifacts["step_1"]["output"]


def test_constraint_memory_prunes_stale_and_excess_constraints(tmp_path, monkeypatch):
    import infrastructure.persistence.sqlite.cua_database as cua_db

    db_path = tmp_path / "constraints.db"

    @contextmanager
    def fake_get_conn():
        conn = sqlite3.connect(db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    monkeypatch.setattr(cua_db, "get_conn", fake_get_conn)

    memory = EvolutionConstraintMemory()

    with fake_get_conn() as conn:
        for index in range(10):
            conn.execute(
                """
                INSERT INTO evolution_constraints (tool_name, type, value, fingerprint, hit_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                ("DemoTool", "blocked_pattern", f"bad_{index}()", f"fp_{index}", index + 2),
            )
        conn.execute(
            """
            INSERT INTO evolution_constraints (tool_name, type, value, fingerprint, hit_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now', '-45 days'), datetime('now', '-45 days'))
            """,
            ("DemoTool", "blocked_pattern", "obsolete()", "fp_old", 1),
        )

    memory.prune_constraints("DemoTool", max_constraints=3, stale_days=30)

    with fake_get_conn() as conn:
        rows = conn.execute(
            "SELECT value FROM evolution_constraints WHERE tool_name=? ORDER BY hit_count DESC, updated_at DESC",
            ("DemoTool",),
        ).fetchall()

    assert len(rows) == 3
    assert {row[0] for row in rows} == {"bad_9()", "bad_8()", "bad_7()"}
