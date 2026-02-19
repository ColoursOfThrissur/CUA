"""
Self-Improvement Loop - Enhanced with Hybrid Improvement Engine
"""
from core.loop_controller import LoopController, LoopStatus, LoopState
from core.task_analyzer import TaskAnalyzer
from core.proposal_generator import ProposalGenerator
from core.sandbox_tester import SandboxTester
from core.system_analyzer import SystemAnalyzer
from core.patch_generator import PatchGenerator
from core.plan_history import PlanHistory
from core.improvement_analytics import ImprovementAnalytics
from core.llm_logger import LLMLogger
from core.hybrid_improvement_engine import HybridImprovementEngine
from core.pending_tools_manager import PendingToolsManager
import logging
import asyncio

logger = logging.getLogger(__name__)

class SelfImprovementLoop:
    """Enhanced with Hybrid Improvement Engine"""
    
    def __init__(self, llm_client, orchestrator, max_iterations=10, libraries_manager=None):
        # Initialize components
        self.llm_client = llm_client
        self.update_orchestrator = orchestrator
        self.analyzer = SystemAnalyzer()
        self.patch_gen = PatchGenerator()
        self.plan_history = PlanHistory()
        self.analytics = ImprovementAnalytics()
        self.llm_logger = LLMLogger()
        self.libraries_manager = libraries_manager
        self._pending_tools_manager = PendingToolsManager()
        
        # Initialize hybrid engine with dependencies
        self.hybrid_engine = HybridImprovementEngine(
            llm_client=llm_client,
            orchestrator=orchestrator
        )
        logger.info("Hybrid Improvement Engine initialized with dependencies")
        
        # Initialize new modular components
        self.task_analyzer = TaskAnalyzer(llm_client, self.analyzer, self.llm_logger)
        self.proposal_generator = ProposalGenerator(llm_client, self.analyzer, self.patch_gen, orchestrator)
        self.sandbox_tester = SandboxTester(self.analyzer, libraries_manager)
        
        # Initialize controller
        self.controller = LoopController(
            llm_client,
            orchestrator,
            self.task_analyzer,
            self.proposal_generator,
            self.sandbox_tester,
            self.plan_history,
            self.analytics,
            max_iterations
        )
        
        # Expose controller properties for compatibility
        self.max_iterations = max_iterations
    
    @property
    def state(self):
        """Dynamic property - always read from controller"""
        return self.controller.state
    
    @property
    def logs(self):
        """Dynamic property - always read from controller"""
        return self.controller.logs
    
    @logs.setter
    def logs(self, value):
        """Allow setting logs on controller"""
        self.controller.logs = value
    
    @property
    def pending_approvals(self):
        """Dynamic property - always read from controller"""
        return self.controller.pending_approvals
    
    @property
    def approval_lock(self):
        """Dynamic property - always read from controller"""
        return self.controller.approval_lock
    
    @property
    def preview_proposals(self):
        """Dynamic property - always read from controller"""
        return self.controller.preview_proposals
    
    @property
    def custom_focus(self):
        """Get custom focus from controller"""
        return self.controller.custom_focus
    
    @custom_focus.setter
    def custom_focus(self, value):
        """Set custom focus on controller"""
        self.controller.custom_focus = value
    
    @property
    def dry_run(self):
        """Get dry_run from controller"""
        return self.controller.dry_run
    
    @dry_run.setter
    def dry_run(self, value):
        """Set dry_run on controller"""
        self.controller.dry_run = value

    @property
    def continuous_mode(self):
        """Get continuous_mode from controller"""
        return self.controller.continuous_mode

    @continuous_mode.setter
    def continuous_mode(self, value):
        """Set continuous_mode on controller"""
        self.controller.continuous_mode = value

    @property
    def in_critical_section(self):
        """Get in_critical_section from controller"""
        return self.controller.in_critical_section
    
    @property
    def task_manager(self):
        """Task manager removed - return None for compatibility"""
        return None
    
    @property
    def pending_tools_manager(self):
        """Pending tools manager for user approval workflow."""
        return self._pending_tools_manager
    
    def add_log(self, log_type: str, message: str, proposal_id=None):
        """Delegate to controller"""
        return self.controller.add_log(log_type, message, proposal_id)
    
    async def start_loop(self):
        """Enhanced start with hybrid engine"""
        # Validate custom_focus before running hybrid engine
        if self.controller.custom_focus:
            try:
                logger.info(f"Running hybrid engine with focus: {self.controller.custom_focus[:50]}...")
                result = await asyncio.to_thread(
                    self.hybrid_engine.analyze_and_improve,
                    custom_prompt=self.controller.custom_focus,
                    max_iterations=3
                )
                
                # Validate result structure
                if not result or not isinstance(result, dict):
                    logger.warning("Hybrid engine returned invalid result (None or not dict)")
                elif result.get('status') == 'success' and result.get('proposal'):
                    logger.info(f"Hybrid engine succeeded: {result.get('target_file', 'unknown')}")
                    # Inject proposal into controller preview
                    if hasattr(self.controller, '_inject_proposal'):
                        self.controller._inject_proposal(result['proposal'])
                    else:
                        logger.warning("Controller missing _inject_proposal method")
                else:
                    logger.info(f"Hybrid engine skipped: {result.get('status', 'unknown')} - {result.get('message', 'no message')}")
                
            except Exception as e:
                logger.error(f"Hybrid engine failed: {e}", exc_info=True)
                # Don't let hybrid failure block normal loop
        else:
            logger.info("Skipping hybrid engine - no custom focus set")
        
        # Continue with normal loop
        return await self.controller.start_loop()
    
    async def stop_loop(self, mode: str = "graceful"):
        """Delegate to controller"""
        return await self.controller.stop_loop(mode)
    
    def approve_proposal(self, proposal_id: str) -> bool:
        """Delegate to controller"""
        return self.controller.approve_proposal(proposal_id)
    
    def reject_proposal(self, proposal_id: str) -> bool:
        """Delegate to controller"""
        return self.controller.reject_proposal(proposal_id)
    
    def get_status(self):
        """Delegate to controller"""
        return self.controller.get_status()
    
    def set_evolution_mode(self, enabled: bool):
        """Delegate to controller"""
        return self.controller.set_evolution_mode(enabled)
    
    @property
    def evolution_bridge(self):
        """Access evolution bridge from controller"""
        return self.controller.evolution_bridge
