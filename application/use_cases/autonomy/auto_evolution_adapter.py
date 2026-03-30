"""
Auto-Evolution Orchestrator - Backward-compatible adapter
"""
from application.evolution.evolution_orchestrator import EvolutionOrchestrator

class AutoEvolutionOrchestratorAdapter:
    def __init__(self, llm_client=None, registry=None):
        self._orchestrator = EvolutionOrchestrator(llm_client, registry)

    async def ensure_initialized(self):
        await self._orchestrator.ensure_initialized()

    async def run_cycle(self, max_items=None):
        return await self._orchestrator.run_cycle(max_items)
        
    async def start(self):
        await self._orchestrator.start()
        
    async def stop(self):
        await self._orchestrator.stop()

    def update_config(self, config):
        self._orchestrator.update_config(config)
        
    def get_status(self):
        return self._orchestrator.get_status()

    @property
    def queue(self):
        return self._orchestrator.queue
        
    @property
    def config(self):
        return self._orchestrator.config

    @config.setter
    def config(self, value):
        self._orchestrator.config = value

    # Delegate any other attribute access to the new orchestrator
    def __getattr__(self, name):
        return getattr(self._orchestrator, name)
