from types import SimpleNamespace

from fastapi.testclient import TestClient

import api.server as server_module
from api.bootstrap import RuntimeState
from api.chat_handler import ChatResponse


class _FakeRegistry:
    def __init__(self, tools=None, capabilities=None):
        self.tools = tools or []
        self._capabilities = capabilities or []

    def get_all_capabilities(self):
        return list(self._capabilities)


class _FakeSkillRegistry:
    def __init__(self, skills=None):
        self._skills = skills or []

    def list_all(self):
        return list(self._skills)


def test_health_endpoint_returns_503_when_runtime_fails_to_initialize(monkeypatch):
    failing_runtime = RuntimeState(system_available=False, init_error="bootstrap failed")

    async def stop_handler():
        return {"success": False, "message": "bootstrap failed"}

    async def chat_handler(request):
        return ChatResponse(
            response=f"System not available. Echo: {request.message}",
            session_id=request.session_id or "test-session",
            success=False,
            execution_result={"success": False, "error": "bootstrap failed"},
        )

    monkeypatch.setattr(server_module, "build_runtime", lambda bundle: failing_runtime)
    monkeypatch.setattr(server_module, "shutdown_runtime", lambda runtime: None)
    monkeypatch.setattr(server_module, "create_chat_handler", lambda runtime, sessions, refresh: (stop_handler, chat_handler))

    with TestClient(server_module.app) as client:
        health = client.get("/health")
        status = client.get("/status")

    assert health.status_code == 503
    assert health.json()["status"] == "unhealthy"
    assert health.json()["runtime_init_error"] == "bootstrap failed"
    assert status.status_code == 200
    assert status.json()["status"] == "unhealthy"


def test_lifespan_initializes_runtime_and_chat_handlers(monkeypatch):
    runtime = RuntimeState(
        system_available=True,
        registry=_FakeRegistry(tools=[object(), object()], capabilities=["a", "b", "c"]),
        skill_registry=_FakeSkillRegistry(skills=["conversation", "computer_automation"]),
    )

    async def stop_handler():
        return {"success": True, "message": "Stop requested"}

    async def chat_handler(request):
        return ChatResponse(
            response=f"ready:{request.message}",
            session_id=request.session_id or "session-123",
            success=True,
            execution_result={"success": True},
        )

    monkeypatch.setattr(server_module, "build_runtime", lambda bundle: runtime)
    monkeypatch.setattr(server_module, "shutdown_runtime", lambda runtime: None)
    monkeypatch.setattr(server_module, "create_chat_handler", lambda runtime, sessions, refresh: (stop_handler, chat_handler))

    with TestClient(server_module.app) as client:
        health = client.get("/health")
        status = client.get("/status")
        chat = client.post("/chat", json={"message": "hello"})
        stop = client.post("/chat/stop")

    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    assert status.json()["tools"] == 2
    assert status.json()["capabilities"] == 3
    assert status.json()["skills"] == 2
    assert chat.status_code == 200
    assert chat.json()["response"] == "ready:hello"
    assert stop.json()["success"] is True
