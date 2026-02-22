"""Tool Evolution Flow - Same pattern as tool creation."""
import logging
from typing import Tuple, Optional
from pathlib import Path
from core.tool_evolution_logger import get_evolution_logger
from core.correlation_context import CorrelationContextManager

logger = logging.getLogger(__name__)
evo_logger = get_evolution_logger()


class ToolEvolutionOrchestrator:
    """Orchestrates tool evolution with same flow as tool creation."""
    
    def __init__(self, quality_analyzer, expansion_mode, llm_client):
        self.quality_analyzer = quality_analyzer
        self.expansion_mode = expansion_mode
        self.llm_client = llm_client
        self.conversation_log = []
    
    def evolve_tool(
        self,
        tool_name: str,
        user_prompt: Optional[str] = None,
        auto_approve: bool = False
    ) -> Tuple[bool, str]:
        """
        Complete flow for evolving existing tool.
        Same pattern as create_new_tool but for improvements.
        
        Steps:
        1. Analyze current tool (observability + code)
        2. LLM proposes changes (spec)
        3. Generate improved code
        4. Validate changes
        5. Sandbox test
        6. Send to pending approval
        """
        
        # Create correlation context for this evolution
        with CorrelationContextManager() as correlation_id:
            logger.info(f"Starting evolution for: {tool_name} [correlation_id={correlation_id}]")
            
            # Step 1: Analyze current tool
            self._log_conversation("SYSTEM", f"Analyzing {tool_name}...")
            
            from core.tool_evolution.analyzer import ToolAnalyzer
            analyzer = ToolAnalyzer(self.quality_analyzer)
            
            evolution_id = None
            health_before = 0
            
            try:
                analysis = analyzer.analyze_tool(tool_name, user_prompt)
                if not analysis:
                    evolution_id = evo_logger.log_run(tool_name, user_prompt, "failed", "analysis", "Could not analyze tool")
                    return False, f"Could not analyze tool: {tool_name}"
                
                health_before = analysis.get('health_score', 0)
                evolution_id = evo_logger.log_run(tool_name, user_prompt, "in_progress", "analysis", None, health_before=health_before)
                
                # Store analysis artifact with original code
                evo_logger.log_artifact(evolution_id, "analysis", "analyze", analysis)
                evo_logger.log_artifact(evolution_id, "original_code", "analyze", analysis.get('current_code', ''))
                
                logger.info(f"[Evolution {evolution_id}] Analysis complete, health: {health_before}")
                self._log_conversation("ANALYSIS", analysis['summary'])
            except Exception as e:
                if evolution_id:
                    evo_logger.log_artifact(evolution_id, "error", "analysis", {"error": str(e)})
                else:
                    evolution_id = evo_logger.log_run(tool_name, user_prompt, "failed", "analysis", str(e))
                return False, f"Analysis failed: {str(e)}"
            
            # Step 2: LLM proposes changes
            from core.tool_evolution.proposal_generator import EvolutionProposalGenerator
            proposal_gen = EvolutionProposalGenerator(self.llm_client)
            
            try:
                proposal = proposal_gen.generate_proposal(analysis)
                if not proposal:
                    evo_logger.log_run(tool_name, user_prompt, "failed", "proposal", "Failed to generate proposal", health_before=health_before)
                    return False, "Failed to generate improvement proposal"
                
                # Store proposal artifact
                evo_logger.log_artifact(evolution_id, "proposal", "propose", proposal)
                
                self._log_conversation("PROPOSAL", proposal['description'])
                
                # Check confidence
                confidence = proposal.get('confidence', 0)
                if confidence < 0.5:
                    evo_logger.log_run(tool_name, user_prompt, "failed", "proposal", f"Low confidence: {confidence:.2f}", confidence, health_before)
                    return False, f"Low confidence proposal ({confidence:.2f})"
            except Exception as e:
                evo_logger.log_artifact(evolution_id, "error", "proposal", {"error": str(e)})
                evo_logger.log_run(tool_name, user_prompt, "failed", "proposal", str(e), health_before=health_before)
                return False, f"Proposal generation failed: {str(e)}"
            
            # Step 3-5: Generate, validate, and test with retry on sandbox failure
            code_gen = self._select_generator()
            sandbox_error = None
            
            for attempt in range(2):
                try:
                    # Generate code
                    improved_code = code_gen.generate_improved_code(
                        analysis['current_code'],
                        proposal,
                        sandbox_error=sandbox_error
                    )
                    if not improved_code:
                        evo_logger.log_run(tool_name, user_prompt, "failed", "code_generation", "Failed to generate code", confidence, health_before)
                        return False, "Failed to generate improved code"
                    
                    evo_logger.log_artifact(evolution_id, "improved_code", f"attempt_{attempt+1}", improved_code)
                    logger.info(f"[Evolution {evolution_id}] Code generated (attempt {attempt+1})")
                    
                    # Check dependencies
                    from core.dependency_checker import DependencyChecker
                    dep_checker = DependencyChecker()
                    dep_report = dep_checker.check_code(improved_code)
                    evo_logger.log_artifact(evolution_id, "dependencies", f"attempt_{attempt+1}", {
                        "missing_libraries": dep_report.missing_libraries,
                        "missing_services": dep_report.missing_services
                    })
                    if dep_report.has_missing():
                        proposal['dependencies'] = {
                            'missing_libraries': dep_report.missing_libraries,
                            'missing_services': dep_report.missing_services
                        }
                    
                    # Validate
                    from core.tool_evolution.validator import EvolutionValidator
                    validator = EvolutionValidator()
                    is_valid, error = validator.validate(
                        original_code=analysis['current_code'],
                        improved_code=improved_code,
                        proposal=proposal
                    )
                    evo_logger.log_artifact(evolution_id, "validation", f"attempt_{attempt+1}", {"is_valid": is_valid, "error": error})
                    if not is_valid:
                        evo_logger.log_run(tool_name, user_prompt, "failed", "validation", error, confidence, health_before)
                        return False, f"Validation failed: {error}"
                    
                    self._log_conversation("VALIDATION", "Code validated")
                    
                    # Sandbox test
                    from core.tool_evolution.sandbox_runner import EvolutionSandboxRunner
                    sandbox = EvolutionSandboxRunner(self.expansion_mode)
                    sandbox_passed, sandbox_output = sandbox.test_improved_tool(
                        tool_name,
                        improved_code,
                        analysis['tool_path'],
                        new_service_specs=proposal.get('new_service_specs')
                    )
                    evo_logger.log_artifact(evolution_id, "sandbox", f"attempt_{attempt+1}", {
                        "passed": sandbox_passed,
                        "output": sandbox_output
                    })
                    
                    if sandbox_passed:
                        self._log_conversation("SANDBOX", "Sandbox tests passed")
                        break
                    else:
                        sandbox_error = sandbox_output
                        logger.warning(f"[Evolution {evolution_id}] Sandbox failed (attempt {attempt+1})")
                        if attempt == 0:
                            continue
                        else:
                            evo_logger.log_run(tool_name, user_prompt, "failed", "sandbox", "Failed after retry", confidence, health_before)
                            return False, f"Sandbox failed after retry: {sandbox_output}"
                
                except Exception as e:
                    evo_logger.log_artifact(evolution_id, "error", f"attempt_{attempt+1}", {"error": str(e)})
                    if attempt == 1:
                        evo_logger.log_run(tool_name, user_prompt, "failed", "generation", str(e), confidence, health_before)
                        return False, f"Generation failed: {str(e)}"
            
            # Step 6: Send to pending approval
            try:
                success, msg = self._create_pending_evolution(
                    tool_name,
                    improved_code,
                    proposal,
                    analysis,
                    evolution_id
                )
                
                if success:
                    self._log_conversation("COMPLETE", f"Evolution ready for approval: {tool_name}")
                    evo_logger.log_run(tool_name, user_prompt, "success", "complete", None, confidence, health_before)
                    logger.info(f"[Evolution {evolution_id}] Complete - pending approval")
                else:
                    evo_logger.log_run(tool_name, user_prompt, "failed", "pending", msg, confidence, health_before)
                    logger.error(f"[Evolution {evolution_id}] Failed to create pending: {msg}")
                
                return success, msg
            except Exception as e:
                evo_logger.log_artifact(evolution_id, "error", "pending", {"error": str(e)})
                evo_logger.log_run(tool_name, user_prompt, "failed", "pending", str(e), confidence, health_before)
                return False, f"Failed to create pending evolution: {str(e)}"
    
    def _select_generator(self):
        """Select generator based on model (matches creation pattern)."""
        from pathlib import Path
        import json
        from core.tool_evolution.code_generator import EvolutionCodeGenerator
        
        # Check model capabilities config
        config_path = Path("config/model_capabilities.json")
        if config_path.exists():
            try:
                with open(config_path) as f:
                    capabilities = json.load(f)
                    model = str(getattr(self.llm_client, "model", "")).lower()
                    
                    # Match model pattern
                    for pattern, config in capabilities.items():
                        if pattern in model:
                            logger.info(f"Using {config['strategy']} strategy for {model}")
                            break
            except Exception as e:
                logger.warning(f"Failed to load model capabilities: {e}")
        
        # Single generator for now (can add Qwen-specific later)
        return EvolutionCodeGenerator(self.llm_client)
    
    def _create_pending_evolution(self, tool_name, improved_code, proposal, analysis, evolution_id):
        """Create pending evolution for approval (like experimental tools)."""
        from core.pending_evolutions_manager import PendingEvolutionsManager
        
        manager = PendingEvolutionsManager()
        
        evolution_data = {
            "tool_name": tool_name,
            "original_code": analysis['current_code'],
            "improved_code": improved_code,
            "proposal": proposal,
            "health_before": analysis.get('health_score', 0),
            "conversation_log": self.conversation_log,
            "status": "pending_approval",
            "evolution_id": evolution_id,
            "code_size": len(improved_code),
            "capabilities_count": len(analysis.get('capabilities', [])),
            "required_services": proposal.get('required_services', []),
            "required_libraries": proposal.get('required_libraries', []),
            "new_service_specs": proposal.get('new_service_specs', {}),
            "service_descriptions": proposal.get('service_descriptions', {})
        }
        
        manager.add_pending_evolution(tool_name, evolution_data)
        
        return True, f"Evolution pending approval: {tool_name}"
    
    def _log_conversation(self, step: str, message: str):
        """Log conversation for user visibility."""
        self.conversation_log.append({
            "step": step,
            "message": message
        })
        logger.info(f"[{step}] {message}")
    
    def get_conversation_log(self):
        """Get conversation log for UI display."""
        return self.conversation_log
    
    def _cleanup_failed_evolution(self, tool_name: str):
        """Cleanup artifacts if evolution fails (matches creation pattern)."""
        # Evolution doesn't create files until approval, so just log
        logger.info(f"Evolution failed for {tool_name}, no cleanup needed (pending approval system)")
