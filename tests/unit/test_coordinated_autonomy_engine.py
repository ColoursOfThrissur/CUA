import asyncio

from core.coordinated_autonomy_engine import CoordinatedAutonomyEngine


class _FakeState:
    def __init__(self):
        self.status = type("Status", (), {"value": "stopped"})()
        self.current_iteration = 0


class _FakeController:
    def __init__(self):
        self.max_iterations = 0
        self.preview_proposals = []


class _FakeLoop:
    def __init__(self):
        self.controller = _FakeController()
        self.state = _FakeState()
        self.dry_run = False
        self.continuous_mode = False

    async def start_loop(self):
        self.state.status.value = "running"
        self.state.current_iteration = self.controller.max_iterations
        self.state.status.value = "stopped"
        return {"status": "started"}


class _FakeAutoOrchestrator:
    def __init__(self):
        self.calls = 0

    async def run_cycle(self, max_items=None):
        self.calls += 1
        return {"processed": max_items or 0, "remaining_queue": 0}

    def get_status(self):
        return {"running": False}


def test_coordinated_engine_runs_cycle(monkeypatch):
    class _FakeBaseline:
        def check_baseline(self):
            return True, "ok", []

    class _FakeGapTracker:
        def get_prioritized_gaps(self):
            return [type("Gap", (), {"capability": "web:source_fetch"})()]

    monkeypatch.setattr("core.coordinated_autonomy_engine.BaselineHealthChecker", _FakeBaseline, raising=False)
    monkeypatch.setattr("core.coordinated_autonomy_engine.GapTracker", _FakeGapTracker, raising=False)

    engine = CoordinatedAutonomyEngine(
        improvement_loop=_FakeLoop(),
        llm_client=object(),
        registry=object(),
        auto_orchestrator=_FakeAutoOrchestrator(),
    )

    result = asyncio.run(engine.run_cycle())

    assert result["success"] is True
    assert result["gap_summary"]["count"] == 1
    assert result["auto_evolution"]["processed"] == engine.config["max_evolutions_per_cycle"]
    assert result["improvement_loop"]["iterations_completed"] == engine.config["improvement_iterations_per_cycle"]


def test_coordinated_engine_stops_on_baseline_failure(monkeypatch):
    class _FailBaseline:
        def check_baseline(self):
            return False, "bad baseline", ["failure_a"]

    class _FakeGapTracker:
        def get_prioritized_gaps(self):
            return []

    monkeypatch.setattr("core.coordinated_autonomy_engine.BaselineHealthChecker", _FailBaseline, raising=False)
    monkeypatch.setattr("core.coordinated_autonomy_engine.GapTracker", _FakeGapTracker, raising=False)

    auto = _FakeAutoOrchestrator()
    engine = CoordinatedAutonomyEngine(
        improvement_loop=_FakeLoop(),
        llm_client=object(),
        registry=object(),
        auto_orchestrator=auto,
    )

    result = asyncio.run(engine.run_cycle())

    assert result["success"] is False
    assert result["stage"] == "baseline"
    assert auto.calls == 0


def test_coordinated_engine_resets_low_value_counter_on_productive_cycle(monkeypatch):
    class _FakeBaseline:
        def check_baseline(self):
            return True, "ok", []

    class _FakeGapTracker:
        def get_prioritized_gaps(self):
            return [type("Gap", (), {"capability": "web:source_fetch"})()]

    monkeypatch.setattr("core.coordinated_autonomy_engine.BaselineHealthChecker", _FakeBaseline, raising=False)
    monkeypatch.setattr("core.coordinated_autonomy_engine.GapTracker", _FakeGapTracker, raising=False)

    loop = _FakeLoop()
    loop.controller.preview_proposals = [{"id": "p1"}]
    engine = CoordinatedAutonomyEngine(
        improvement_loop=loop,
        llm_client=object(),
        registry=object(),
        auto_orchestrator=_FakeAutoOrchestrator(),
    )
    engine.consecutive_low_value_cycles = 1

    pending_counts = iter(
        [
            {"pending_tools": 0, "pending_evolutions": 0},
            {"pending_tools": 1, "pending_evolutions": 0},
        ]
    )
    monkeypatch.setattr(engine, "_collect_pending_counts", lambda: next(pending_counts))
    monkeypatch.setattr(
        engine,
        "_collect_quality_summary",
        lambda: {
            "total_tools": 1,
            "avg_health_score": 80.0,
            "healthy_tools": 1,
            "monitor_tools": 0,
            "weak_tools": 0,
            "quarantine_tools": 0,
        },
    )

    result = asyncio.run(engine.run_cycle())

    assert result["quality_gate"]["low_value"] is False
    assert result["quality_gate"]["new_pending_tools"] == 1
    assert engine.consecutive_low_value_cycles == 0


def test_coordinated_engine_flags_pause_on_low_value_cycle(monkeypatch):
    class _FakeBaseline:
        def check_baseline(self):
            return True, "ok", []

    class _FakeGapTracker:
        def get_prioritized_gaps(self):
            return [type("Gap", (), {"capability": "web:source_fetch"})()]

    class _NoopAuto:
        async def run_cycle(self, max_items=None):
            return {"processed": 0, "failures": 0, "remaining_queue": 0}

        def get_status(self):
            return {"running": False}

    monkeypatch.setattr("core.coordinated_autonomy_engine.BaselineHealthChecker", _FakeBaseline, raising=False)
    monkeypatch.setattr("core.coordinated_autonomy_engine.GapTracker", _FakeGapTracker, raising=False)

    engine = CoordinatedAutonomyEngine(
        improvement_loop=_FakeLoop(),
        llm_client=object(),
        registry=object(),
        auto_orchestrator=_NoopAuto(),
    )
    engine.config["max_consecutive_low_value_cycles"] = 1

    pending_counts = iter(
        [
            {"pending_tools": 0, "pending_evolutions": 0},
            {"pending_tools": 0, "pending_evolutions": 0},
        ]
    )
    quality_counts = iter(
        [
            {
                "total_tools": 1,
                "avg_health_score": 80.0,
                "healthy_tools": 1,
                "monitor_tools": 0,
                "weak_tools": 0,
                "quarantine_tools": 0,
            },
            {
                "total_tools": 1,
                "avg_health_score": 80.0,
                "healthy_tools": 1,
                "monitor_tools": 0,
                "weak_tools": 0,
                "quarantine_tools": 0,
            },
        ]
    )
    monkeypatch.setattr(engine, "_collect_pending_counts", lambda: next(pending_counts))
    monkeypatch.setattr(engine, "_collect_quality_summary", lambda: next(quality_counts))

    result = asyncio.run(engine.run_cycle())

    assert result["quality_gate"]["low_value"] is True
    assert result["quality_gate"]["should_pause"] is True
    assert "no actionable outputs" in result["quality_gate"]["reason"]
