"""
Self-Improvement Loop - Compatibility wrapper for new modular architecture
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

class SelfImprovementLoop:
    """Compatibility wrapper - delegates to new modular components"""
    
    def __init__(self, llm_client, orchestrator, max_iterations=10):
        # Initialize components
        self.llm_client = llm_client
        self.update_orchestrator = orchestrator
        self.analyzer = SystemAnalyzer()
        self.patch_gen = PatchGenerator()
        self.plan_history = PlanHistory()
        self.analytics = ImprovementAnalytics()
        self.llm_logger = LLMLogger()
        
        # Initialize new modular components
        self.task_analyzer = TaskAnalyzer(llm_client, self.analyzer, self.llm_logger)
        self.proposal_generator = ProposalGenerator(llm_client, self.analyzer, self.patch_gen, orchestrator)
        self.sandbox_tester = SandboxTester(self.analyzer)
        
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
        self.state = self.controller.state
        self.logs = self.controller.logs
        self.pending_approvals = self.controller.pending_approvals
        self.custom_focus = None
        self.dry_run = False
        self.preview_proposals = self.controller.preview_proposals
    
    def add_log(self, log_type: str, message: str, proposal_id=None):
        """Delegate to controller"""
        return self.controller.add_log(log_type, message, proposal_id)
    
    async def start_loop(self):
        """Delegate to controller"""
        self.controller.custom_focus = self.custom_focus
        self.controller.dry_run = self.dry_run
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

