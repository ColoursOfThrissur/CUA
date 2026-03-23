import asyncio

from api import improvement_api
from api import server


class _DummyLoop:
    def __init__(self):
        self.approval_lock = asyncio.Lock()
        self.pending_approvals = {"proposal_001": {"approved": None}}

    def approve_proposal(self, proposal_id: str) -> bool:
        if proposal_id not in self.pending_approvals:
            return False
        self.pending_approvals[proposal_id]["approved"] = True
        return True

    def reject_proposal(self, proposal_id: str) -> bool:
        if proposal_id not in self.pending_approvals:
            return False
        self.pending_approvals[proposal_id]["approved"] = False
        return True


def test_boot_health_smoke():
    payload = asyncio.run(server.health())

    assert payload["status"] == "healthy"
    assert "system_available" in payload
    assert "routers_available" in payload


def test_improvement_approval_smoke():
    dummy_loop = _DummyLoop()
    improvement_api.set_loop_instance(dummy_loop)

    request = improvement_api.ApprovalRequest(proposal_id="proposal_001", approved=True)
    payload = asyncio.run(improvement_api.approve_proposal(request))

    assert payload["success"] is True
    assert dummy_loop.pending_approvals["proposal_001"]["approved"] is True
