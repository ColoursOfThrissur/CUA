from application.use_cases.autonomy.autonomous_agent import AgentGoal, AutonomousAgent
from application.use_cases.execution.execution_engine import ExecutionState, ExecutionPlan, StepResult, StepStatus
from domain.entities.task import TaskStep


class FakeLLMClient:
    def __init__(self, response):
        self.response = response

    def _call_llm(self, prompt, temperature=0.1, expect_json=True):
        return self.response


def _build_agent(llm_response=None):
    agent = AutonomousAgent.__new__(AutonomousAgent)
    agent.llm_client = FakeLLMClient(llm_response)
    return agent


def _build_state(*results):
    step_results = {result.step_id: result for result in results}
    steps = [
        TaskStep(
            step_id=result.step_id,
            description=result.step_id,
            tool_name="TestTool",
            operation="execute",
            parameters={},
            dependencies=[],
            expected_output="done",
        )
        for result in results
    ]
    return ExecutionState(
        plan=ExecutionPlan(goal="demo", steps=steps, estimated_duration=1, complexity="simple"),
        step_results=step_results,
    )


def test_build_verification_prompt_keeps_richer_evidence():
    agent = _build_agent()
    titles = [f"Game {index}" for index in range(1, 30)]
    state = _build_state(
        StepResult(
            step_id="step_1",
            status=StepStatus.COMPLETED,
            output={"titles": titles, "games": titles},
        )
    )
    goal = AgentGoal(
        goal_text="open steam and list my library games",
        success_criteria=["Visible game titles must be extracted as text in the final outputs."],
    )

    prompt = agent._build_verification_prompt(goal, state, "session-1")

    assert "Game 20" in prompt
    assert "LATEST WORLD STATE" in prompt


def test_heuristic_goal_check_accepts_library_click_plus_games():
    agent = _build_agent()
    goal = AgentGoal(
        goal_text="open steam and list all games that i have in my library",
        success_criteria=["Steam must be on the LIBRARY view, not just the STORE page."],
    )
    state = _build_state(
        StepResult(
            step_id="step_1",
            status=StepStatus.COMPLETED,
            output={"target": "Library", "success": True},
        ),
        StepResult(
            step_id="step_2",
            status=StepStatus.COMPLETED,
            output={"games": ["Apex Legends", "Counter-Strike 2", "Dota 2"]},
        ),
    )

    verification = agent._heuristic_goal_check(goal, state, list(state.step_results.values()))

    assert verification["success"] is True


def test_verify_results_overrides_truncation_false_negative():
    llm_response = {
        "success": False,
        "reason": "The execution results were cut off before completion.",
        "details": "The titles list appears truncated and partial.",
        "missing_parts": ["full list"],
    }
    agent = _build_agent(llm_response)
    goal = AgentGoal(
        goal_text="open steam and list all games that i have in my library",
        success_criteria=[
            "Steam must be on the LIBRARY view, not just the STORE page.",
            "Visible game titles must be extracted as text in the final outputs.",
        ],
    )
    state = _build_state(
        StepResult(
            step_id="step_1",
            status=StepStatus.COMPLETED,
            output={"target": "Library", "success": True},
        ),
        StepResult(
            step_id="step_2",
            status=StepStatus.COMPLETED,
            output={"games": ["Apex Legends", "Counter-Strike 2", "Dota 2"]},
        ),
    )

    verification = agent._verify_results(goal, state, "session-1")

    assert verification["success"] is True
    assert "Heuristic override" in verification["reason"]
