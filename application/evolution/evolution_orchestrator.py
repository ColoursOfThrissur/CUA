"""
Auto-Evolution Orchestrator - Main engine for automatic tool improvements
"""
import asyncio
from typing import Dict, Optional
from domain.services.tool_quality_analyzer import ToolQualityAnalyzer
from infrastructure.analysis.llm_tool_health_analyzer import LLMToolHealthAnalyzer
from application.use_cases.tool_lifecycle.tool_evolution_flow import ToolEvolutionOrchestrator as EvolutionFlow
from application.use_cases.evolution.evolution_queue import EvolutionQueue
from infrastructure.testing.llm_test_orchestrator import LLMTestOrchestrator
from infrastructure.persistence.sqlite.logging import SQLiteLogger
from infrastructure.logging.tool_execution_logger import get_execution_logger
from shared.utils.trace_bridge import broadcast_trace_sync

from application.evolution.evolution_scanner import EvolutionScanner
from application.evolution.evolution_processor import EvolutionProcessor
from application.evolution.gap_analyzer_clean import GapAnalyzer
from application.evolution.context_builder import ContextBuilder
from application.evolution.learning_manager import LearningManager

class EvolutionOrchestrator:
    def __init__(self, llm_client=None, registry=None):
        self.logger = SQLiteLogger()
        self.llm_client = llm_client
        self.registry = registry
        self.config = {
            "mode": "balanced",  # reactive, proactive, balanced, experimental
            "scan_interval": 3600,  # 1 hour
            "max_concurrent": 2,
            "min_health_threshold": 50,
            "auto_approve_threshold": 90,  # Auto-approve if test score >= 90
            "learning_enabled": True,
            "enable_enhancements": True,  # Queue HEALTHY tools with improvements too
            "max_new_tools_per_scan": 3,  # tools to create per scan from gaps
        }
        self.queue = EvolutionQueue()
        self.quality_analyzer = ToolQualityAnalyzer(get_execution_logger())
        self.llm_health_analyzer = LLMToolHealthAnalyzer()
        self.test_orchestrator = None
        self.evolution_flow = None
        
        self.scanner = EvolutionScanner(self.logger, self.llm_client, self.registry, self.quality_analyzer, self.llm_health_analyzer, self.queue, self.config)
        self.processor = None # will be initialized in ensure_initialized
        self.gap_analyzer = GapAnalyzer(self.logger, self.llm_client, self.registry)
        self.context_builder = ContextBuilder(self.logger)
        self.learning_manager = LearningManager(self.logger)
        
        self.running = False

    async def ensure_initialized(self):
        """Initialize dependent sub-systems without starting background loops."""
        if not self.llm_client or not self.registry:
            raise ValueError("LLM client and registry required")
        if not self.test_orchestrator:
            self.test_orchestrator = LLMTestOrchestrator(self.llm_client, self.registry)
        if not self.evolution_flow:
            from application.services.expansion_mode import ExpansionMode
            self.evolution_flow = EvolutionFlow(
                quality_analyzer=self.quality_analyzer,
                expansion_mode=ExpansionMode(enabled=True),
                llm_client=self.llm_client
            )
        if not self.processor:
            self.processor = EvolutionProcessor(self.logger, self.queue, self.config, self.llm_client, self.test_orchestrator, self.evolution_flow, self.quality_analyzer)


    async def run_cycle(self, max_items: Optional[int] = None, rescan: bool = True) -> Dict:
        """Run a single scan-and-process cycle without background loops."""
        await self.ensure_initialized()
        broadcast_trace_sync("auto", "Auto-evolution scan starting", "in_progress", {"stage": "scan_start"})
        if rescan:
            self.queue.clear_queue()
            await self.scanner._scan_and_queue()
        processed = 0
        failures = 0
        limit = max_items if max_items is not None else len(self.queue.queue)
        while processed < limit:
            evolution = self.queue.get_next()
            if not evolution:
                break
            await self.processor._process_evolution(evolution)
            processed += 1
            if self.queue.failed.get(evolution.tool_name):
                failures += 1
        return {
            "scanned": True,
            "processed": processed,
            "failures": failures,
            "remaining_queue": len(self.queue.queue),
        }
        
    async def start(self):
        """Start auto-evolution engine"""
        await self.ensure_initialized()
        
        self.running = True
        self.logger.info(f"Auto-evolution orchestrator started (mode: {self.config['mode']})")
        
        await self.scanner.start()
        await self.processor.start()
        
    async def stop(self):
        """Stop auto-evolution engine"""
        self.running = False
        await self.scanner.stop()
        await self.processor.stop()
        self.logger.info("Auto-evolution orchestrator stopped")

    def update_config(self, config: Dict):
        """Update orchestrator configuration"""
        self.config.update(config)
        self.scanner.config = self.config
        self.processor.config = self.config
        self.logger.info(f"Configuration updated: {config}")

    def get_status(self) -> Dict:
        """Get orchestrator status"""
        return {
            "running": self.running,
            "scanning": self.scanner.scanning,
            "scan_progress": self.scanner.scan_progress if self.scanner.scanning else None,
            "mode": self.config["mode"],
            "queue_size": len(self.queue.queue),
            "in_progress": 1 if self.queue.in_progress else 0,
            "config": self.config
        }
