import asyncio

import pytest
from fastapi import HTTPException

import api.auto_evolution_api as auto_api


class _FakeCoordinatedEngine:
    async def start(self):
        return {"success": True}

    async def run_cycle(self):
        return {"success": True}

    def get_status(self):
        return {"running": False}


def test_coordinated_status_reports_reload_block(monkeypatch):
    monkeypatch.setenv("CUA_RELOAD_MODE", "1")
    auto_api.set_coordinated_engine(_FakeCoordinatedEngine())

    result = asyncio.run(auto_api.get_coordinated_status())

    assert result["reload_mode"] is True
    assert result["reload_blocked"] is True
    assert "reload mode" in result["reload_warning"].lower()


def test_coordinated_start_blocked_in_reload_mode(monkeypatch):
    monkeypatch.setenv("CUA_RELOAD_MODE", "1")
    auto_api.set_coordinated_engine(_FakeCoordinatedEngine())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auto_api.start_coordinated_engine())

    assert exc.value.status_code == 409


def test_coordinated_run_cycle_blocked_in_reload_mode(monkeypatch):
    monkeypatch.setenv("CUA_RELOAD_MODE", "1")
    auto_api.set_coordinated_engine(_FakeCoordinatedEngine())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auto_api.run_coordinated_cycle())

    assert exc.value.status_code == 409
