"""
Updater Module - Safe auto-update pipeline
"""
from updater.orchestrator import UpdateOrchestrator, UpdateResult
from updater.risk_scorer import RiskScorer, UpdateRiskLevel
from updater.update_gate import UpdateGate, ApprovalStatus

__all__ = [
    'UpdateOrchestrator',
    'UpdateResult',
    'RiskScorer',
    'UpdateRiskLevel',
    'UpdateGate',
    'ApprovalStatus'
]
