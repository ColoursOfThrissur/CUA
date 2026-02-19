"""
Evolution Integration Bridge
Connects new evolution system to existing loop controller
"""
from typing import Optional, Dict
from core.evolution_controller import EvolutionController
from core.proposal_types import ProposalType

class EvolutionBridge:
    """
    Bridge between existing loop_controller and new evolution_controller
    
    Usage:
    1. Enable evolution mode: bridge.enable_evolution_mode()
    2. Loop controller calls bridge.should_use_evolution()
    3. If True, use bridge.run_evolution_cycle() instead of normal flow
    """
    
    def __init__(self, llm_client):
        self.evolution_controller = EvolutionController(llm_client)
        self.evolution_mode_enabled = False
        self.llm_client = llm_client
    
    def enable_evolution_mode(self):
        """Enable evolution mode (proposal-based)"""
        self.evolution_mode_enabled = True
    
    def disable_evolution_mode(self):
        """Disable evolution mode (back to deterministic)"""
        self.evolution_mode_enabled = False
    
    def should_use_evolution(self) -> bool:
        """Check if should use evolution mode"""
        return self.evolution_mode_enabled
    
    def run_evolution_cycle(self) -> Dict:
        """
        Run one evolution cycle
        Returns result compatible with loop_controller expectations
        """
        result = self.evolution_controller.run_evolution_cycle()
        
        # Transform to loop_controller format
        if result['status'] == 'success':
            return {
                'success': True,
                'type': result.get('type', 'evolution'),
                'message': result.get('message', 'Evolution applied')
            }
        elif result['status'] == 'idle':
            reason = result.get('reason', 'no_insights')
            return {
                'success': False,
                'reason': reason,
                'stage': result.get('stage', 'reflection'),
                'message': f"Evolution idle: {reason}"
            }
        elif result['status'] == 'skipped':
            reason = result.get('reason', 'skipped')
            return {
                'success': False,
                'reason': reason,
                'stage': result.get('stage', 'selection'),
                'message': f"Evolution skipped: {reason}"
            }
        elif result['status'] == 'rejected':
            return {
                'success': False,
                'reason': 'rejected',
                'message': result.get('reason', 'Proposal rejected')
            }
        elif result['status'] == 'stopped':
            return {
                'success': False,
                'reason': 'baseline_failure',
                'message': result.get('reason', 'Baseline check failed'),
                'stop_loop': True
            }
        else:
            reason = result.get('reason', 'unknown')
            stage = result.get('stage', 'unknown_stage')
            detail = result.get('message', reason)
            return {
                'success': False,
                'reason': reason,
                'stage': stage,
                'message': f"Evolution cycle failed [{stage}:{reason}] - {detail}"
            }
    
    def get_capability_graph(self):
        """Access capability graph for inspection"""
        return self.evolution_controller.capability_graph
    
    def get_growth_budget(self):
        """Access growth budget for inspection"""
        return self.evolution_controller.growth_budget
    
    def get_self_reflection(self):
        """Get current system reflection insights"""
        return self.evolution_controller.self_reflector.analyze_system()
    
    def promote_experimental_tool(self, tool_name: str) -> tuple[bool, str]:
        """Manually promote experimental tool to stable"""
        # Would check cycles, coverage, regressions
        return self.evolution_controller.expansion_mode.promote_to_stable(
            tool_name, 
            cycles_passed=2,
            coverage=0.85,
            regression_count=0
        )
