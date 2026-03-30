"""
Gap Analyzer Adapter - Wires clean architecture components to existing system
Maintains backward compatibility with evolution_orchestrator.py
"""
import asyncio
from infrastructure.persistence.sqlite.logging import SQLiteLogger
from domain.services.gap_tracker import GapTracker
from domain.services.gap_detector import CapabilityGap as CoreCapabilityGap
from shared.utils.trace_bridge import broadcast_trace_sync

from domain.services.gap_analysis_service import GapAnalysisService
from domain.entities.gap import CapabilityGap as DomainCapabilityGap
from application.use_cases.evolution.analyze_gaps import AnalyzeSystemGaps
from infrastructure.persistence.file_storage.system_snapshot_builder import SystemSnapshotBuilder


class LLMProviderAdapter:
    """Adapter for LLM client."""
    def __init__(self, llm_client):
        self._client = llm_client
    
    async def generate(self, prompt: str, temperature: float, max_tokens: int) -> str:
        return await asyncio.to_thread(
            self._client._call_llm,
            prompt,
            temperature,
            max_tokens,
            True
        )


class GapRepositoryAdapter:
    """Adapter for gap persistence using existing GapTracker."""
    def __init__(self):
        self._tracker = GapTracker()
    
    def record_gap(self, gap: DomainCapabilityGap):
        """Convert domain gap to core gap and record."""
        core_gap = CoreCapabilityGap(
            capability=gap.capability,
            confidence=gap.confidence,
            reason=gap.reason,
            domain=gap.domain,
            gap_type=gap.gap_type,
            suggested_action=gap.suggested_action
        )
        if gap.target_tool:
            core_gap.target_tool = gap.target_tool
        self._tracker.record_gap(core_gap)
    
    def get_gap(self, capability: str):
        """Get existing gap."""
        return self._tracker.gaps.get(capability)


class EventBroadcasterAdapter:
    """Adapter for event broadcasting."""
    def broadcast(self, source: str, message: str, status: str, metadata: dict):
        broadcast_trace_sync(source, message, status, metadata)


class GapAnalyzer:
    """
    Clean Architecture Adapter for Gap Analysis.
    Maintains backward compatibility with existing code while using new architecture.
    """
    
    def __init__(self, logger: SQLiteLogger, llm_client, registry):
        # Infrastructure adapters
        llm_adapter = LLMProviderAdapter(llm_client)
        gap_repo = GapRepositoryAdapter()
        snapshot_builder = SystemSnapshotBuilder(registry)
        event_broadcaster = EventBroadcasterAdapter()
        
        # Domain service
        gap_service = GapAnalysisService()
        
        # Use case
        self._use_case = AnalyzeSystemGaps(
            logger=logger,
            llm_provider=llm_adapter,
            gap_repository=gap_repo,
            snapshot_builder=snapshot_builder,
            event_broadcaster=event_broadcaster,
            gap_analysis_service=gap_service
        )
    
    async def analyze_gaps(self) -> int:
        """Execute gap analysis use case. Returns count of gaps found."""
        return await self._use_case.execute()
