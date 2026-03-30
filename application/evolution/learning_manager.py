"""
Learning Manager - Learns from the results of evolutions.
"""
from typing import Dict
from infrastructure.persistence.sqlite.logging import SQLiteLogger
from application.use_cases.evolution.evolution_queue import QueuedEvolution

class LearningManager:
    def __init__(self, logger: SQLiteLogger):
        self.logger = logger

    def learn(self, evolution: QueuedEvolution, result: Dict, test_score: float):
        """Record evolution outcome to improvement_memory.db for future threshold adjustment."""
        try:
            from infrastructure.persistence.file_storage.improvement_memory import ImprovementMemory
            mem = ImprovementMemory()
            kind = (evolution.metadata or {}).get("kind", "evolve_tool")
            mem.store_attempt(
                file_path=evolution.tool_name,
                change_type=kind,
                description=evolution.reason or "",
                patch="",
                outcome="success" if result.get("success") else "failed",
                error_message=result.get("message") if not result.get("success") else None,
                test_results={"overall_score": test_score, "auto_approved": result.get("auto_approved", False)},
                metrics={"priority_score": evolution.priority_score, "test_score": test_score},
            )
        except Exception as _e:
            self.logger.warning(f"Failed to record improvement memory: {_e}")
