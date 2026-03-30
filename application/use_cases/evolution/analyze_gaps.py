"""
Use Case: Analyze System Gaps
Orchestrates gap analysis by coordinating domain service, infrastructure, and persistence.
"""
import asyncio
from typing import List, Protocol
import json


class ILogger(Protocol):
    def info(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...


class ILLMProvider(Protocol):
    async def generate(self, prompt: str, temperature: float, max_tokens: int) -> str: ...


class IGapRepository(Protocol):
    def record_gap(self, gap) -> None: ...
    def get_gap(self, capability: str): ...


class ISystemSnapshotBuilder(Protocol):
    def build_snapshot(self): ...


class IEventBroadcaster(Protocol):
    def broadcast(self, source: str, message: str, status: str, metadata: dict) -> None: ...


class AnalyzeSystemGaps:
    """Use case for proactive system gap analysis."""
    
    def __init__(
        self,
        logger: ILogger,
        llm_provider: ILLMProvider,
        gap_repository: IGapRepository,
        snapshot_builder: ISystemSnapshotBuilder,
        event_broadcaster: IEventBroadcaster,
        gap_analysis_service
    ):
        self.logger = logger
        self.llm = llm_provider
        self.gap_repo = gap_repository
        self.snapshot_builder = snapshot_builder
        self.events = event_broadcaster
        self.service = gap_analysis_service
    
    async def execute(self) -> int:
        """Execute gap analysis and return count of new gaps found."""
        try:
            from domain.entities.gap import CapabilityGap
            
            system_snapshot = self.snapshot_builder.build_snapshot()
            raw_gaps = await self._query_llm_for_gaps(system_snapshot)
            valid_gap_data = self.service.filter_valid_gaps(raw_gaps, system_snapshot)
            
            found = 0
            for gap_data in valid_gap_data:
                existing = self.gap_repo.get_gap(gap_data["capability"])
                if existing and getattr(existing, "resolution_attempted", False):
                    continue
                
                gap = CapabilityGap(
                    capability=gap_data["capability"],
                    confidence=gap_data["confidence"],
                    reason=gap_data["reason"],
                    target_tool=gap_data.get("target_tool")
                )
                
                self.gap_repo.record_gap(gap)
                found += 1
                
                self.logger.info(f"System gap identified: {gap.capability} (conf={gap.confidence:.2f}) — {gap.reason}")
                self.events.broadcast(
                    "auto",
                    f"System gap found: {gap.capability}",
                    "in_progress",
                    {"stage": "system_analysis", "capability": gap.capability, "confidence": gap.confidence}
                )
            
            if found:
                self.logger.info(f"System analysis found {found} new capability gaps")
            
            return found
            
        except Exception as e:
            self.logger.warning(f"System gap analysis skipped: {e}")
            return 0
    
    async def _query_llm_for_gaps(self, system) -> List[dict]:
        """Query LLM for capability gaps."""
        prompt = self._build_gap_analysis_prompt(system)
        raw = await self.llm.generate(prompt, temperature=0.1, max_tokens=800)
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, list) else []
    
    def _build_gap_analysis_prompt(self, system) -> str:
        """Build prompt for LLM gap analysis."""
        return (
            "You are analyzing a local autonomous agent platform to find missing tool capabilities.\n"
            "This platform plans tasks, routes via skills, calls tools, creates/evolves tools.\n"
            "Desktop automation is one subsystem, not the whole product.\n\n"
            f"SKILLS: {', '.join(s.name for s in system.skills)}\n"
            f"EXISTING TOOLS: {', '.join(system.existing_tools)}\n"
            f"COVERED CAPABILITIES (sample): {', '.join(sorted(system.covered_capabilities)[:30])}\n\n"
            "What tool capabilities are clearly missing for a general-purpose autonomous agent?\n"
            "Consider: what each skill needs, what gaps exist between skills and tools.\n\n"
            "Return JSON array of up to 3 gaps (most impactful first):\n"
            '[{"capability": "short_name", "confidence": 0.0-1.0, "reason": "max 8 words", '
            '"suggested_tool_name": "ToolNameTool"}]\n'
            "Only include gaps where confidence >= 0.75. Keep reason under 8 words. If nothing is missing return []"
        )
