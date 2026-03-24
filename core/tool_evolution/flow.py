"""Tool Evolution Flow - Same pattern as tool creation."""
import logging
from typing import Tuple, Optional, Any
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
        self.last_skill_updates = []
    
    def evolve_tool(
        self,
        tool_name: str,
        user_prompt: Optional[str] = None,
        auto_approve: bool = False,
        execution_context: Optional[Any] = None
    ) -> Tuple[bool, str]:
        # Reset per-evolution state
        self.conversation_log = []
        self.last_skill_updates = []
        
        # Create correlation context for this evolution
        with CorrelationContextManager() as correlation_id:
            logger.info(f"Starting evolution for: {tool_name} [correlation_id={correlation_id}]")
            evolution_id = None
            try:
                return self._evolve_tool_inner(tool_name, user_prompt, auto_approve, execution_context)
            except Exception as e:
                import traceback as _tb
                if evolution_id is None:
                    evolution_id = evo_logger.log_run(tool_name, user_prompt, "failed", "unhandled_exception", f"{type(e).__name__}: {e}")
                else:
                    evo_logger.log_artifact(evolution_id, "traceback", "unhandled_exception", _tb.format_exc())
                    evo_logger.log_run(tool_name, user_prompt, "failed", "unhandled_exception", f"{type(e).__name__}: {e}")
                logger.error(f"Unhandled exception in tool evolution: {e}", exc_info=True)
                raise

    def _evolve_tool_inner(
        self,
        tool_name: str,
        user_prompt: Optional[str] = None,
        auto_approve: bool = False,
        execution_context: Optional[Any] = None
    ) -> Tuple[bool, str]:
        # Step 1: Analyze current tool
        self._log_conversation("SYSTEM", f"Analyzing {tool_name}...")

        from core.tool_evolution.analyzer import ToolAnalyzer
        analyzer = ToolAnalyzer(self.quality_analyzer)
            
        evolution_id = None
        health_before = 0
        
        try:
            # Pass execution context to analyzer for context-aware analysis
            analysis = analyzer.analyze_tool(tool_name, user_prompt, execution_context=execution_context)
            if not analysis:
                evolution_id = evo_logger.log_run(tool_name, user_prompt, "failed", "analysis", "Could not analyze tool")
                return False, f"Could not analyze tool: {tool_name}"
            
            health_before = analysis.get('health_score', 0)
            evolution_id = evo_logger.log_run(tool_name, user_prompt, "in_progress", "analysis", None, health_before=health_before)
            
            # Store analysis artifact with original code and execution context
            evo_logger.log_artifact(evolution_id, "analysis", "analyze", analysis)
            evo_logger.log_artifact(evolution_id, "original_code", "analyze", analysis.get('current_code', ''))
            
            # Store execution context metrics if provided
            if execution_context:
                context_metrics = {
                    "execution_time": getattr(execution_context, 'execution_time_seconds', 0),
                    "retry_count": getattr(execution_context, 'retry_count', 0),
                    "errors_encountered": getattr(execution_context, 'errors_encountered', []),
                    "verification_mode": getattr(execution_context, 'verification_mode', None),
                    "warnings": getattr(execution_context, 'warnings', [])
                }
                evo_logger.log_artifact(evolution_id, "execution_context", "analyze", context_metrics)
            
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
                evo_logger.log_run(tool_name, user_prompt, "failed", "proposal", "Failed to generate proposal", health_before=health_before, evolution_id=evolution_id)
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
        validation_error = None
        confidence = proposal.get('confidence', 0)
        
        for attempt in range(3):  # Increased from 2 to allow validation feedback retry
            try:
                # Generate code (and pass validation error for feedback on retry)
                improved_code = code_gen.generate_improved_code(
                    analysis['current_code'],
                    proposal,
                    sandbox_error=sandbox_error,
                    validation_error=validation_error
                )
                
                # Validate generated code
                if not improved_code or not improved_code.strip():
                    evo_logger.log_artifact(evolution_id, "error", f"attempt_{attempt+1}", {"error": "Empty code"})
                    if attempt == 2:
                        evo_logger.log_run(tool_name, user_prompt, "failed", "code_generation", "Empty code", confidence, health_before)
                        return False, "Failed to generate improved code: empty output"
                    continue
                
                if len(improved_code) < 100:
                    evo_logger.log_artifact(evolution_id, "error", f"attempt_{attempt+1}", {"error": f"Code too short: {len(improved_code)}"})
                    if attempt == 2:
                        evo_logger.log_run(tool_name, user_prompt, "failed", "code_generation", f"Code too short: {len(improved_code)}", confidence, health_before)
                        return False, "Failed to generate improved code: too short"
                    continue
                
                if 'class ' not in improved_code:
                    evo_logger.log_artifact(evolution_id, "error", f"attempt_{attempt+1}", {"error": "No class definition"})
                    if attempt == 2:
                        evo_logger.log_run(tool_name, user_prompt, "failed", "code_generation", "No class definition", confidence, health_before)
                        return False, "Failed to generate improved code: no class"
                    continue
                
                # Early syntax check — gives actionable feedback before full validation
                try:
                    import ast as _ast
                    _ast.parse(improved_code)
                except SyntaxError as syn_err:
                    syntax_msg = f"Syntax error in generated code: {syn_err}"
                    evo_logger.log_artifact(evolution_id, "error", f"attempt_{attempt+1}", {"error": syntax_msg})
                    logger.warning(f"[Evolution {evolution_id}] {syntax_msg} (attempt {attempt+1})")
                    validation_error = syntax_msg
                    if attempt < 2:
                        continue
                    evo_logger.log_run(tool_name, user_prompt, "failed", "code_generation", syntax_msg, confidence, health_before)
                    return False, f"Generated code has syntax errors after all retries: {syn_err}"
                
                evo_logger.log_artifact(evolution_id, "improved_code", f"attempt_{attempt+1}", improved_code)
                logger.info(f"[Evolution {evolution_id}] Code generated (attempt {attempt+1}), length: {len(improved_code)}")
                
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

                    # If evolution introduces missing services, generate pending service proposals and stop.
                    if dep_report.missing_services or dep_report.pending_services:
                        try:
                            from core.service_generation_integration import ServiceGenerationIntegration
                            svc_integration = ServiceGenerationIntegration()
                            svc_result = svc_integration.validate_and_generate_services(
                                improved_code,
                                class_name=None,
                                context=(user_prompt or f"Evolution for {tool_name}"),
                                requested_by="tool_evolution",
                            )
                            evo_logger.log_artifact(evolution_id, "pending_services", f"attempt_{attempt+1}", svc_result)
                            if svc_result.get("pending_approval"):
                                evo_logger.log_run(
                                    tool_name,
                                    user_prompt,
                                    "blocked",
                                    "services_pending",
                                    svc_result.get("error"),
                                    confidence,
                                    health_before,
                                )
                                return False, f"Missing services detected; generated pending service proposals for approval. {svc_result.get('error')}"
                        except Exception as e:
                            evo_logger.log_artifact(evolution_id, "service_generation_error", f"attempt_{attempt+1}", {"error": str(e)})
                            evo_logger.log_run(tool_name, user_prompt, "failed", "services", str(e), confidence, health_before)
                            return False, f"Missing services detected but service generation failed: {e}"
                
                # Validate (BEFORE sandbox test)
                from core.tool_evolution.validator import EvolutionValidator
                validator = EvolutionValidator()
                is_valid, error = validator.validate(
                    original_code=analysis['current_code'],
                    improved_code=improved_code,
                    proposal=proposal
                )
                evo_logger.log_artifact(evolution_id, "validation", f"attempt_{attempt+1}", {"is_valid": is_valid, "error": error})
                
                if not is_valid:
                    validation_error = error
                    logger.warning(f"[Evolution {evolution_id}] Validation failed (attempt {attempt+1}): {error}")
                    if attempt < 2:
                        # Retry with validation feedback
                        logger.info(f"[Evolution {evolution_id}] Retrying code generation with validation feedback")
                        continue
                    else:
                        # All attempts exhausted
                        evo_logger.log_run(tool_name, user_prompt, "failed", "validation", error, confidence, health_before)
                        return False, f"Validation failed after all retries: {error}"
                
                self._log_conversation("VALIDATION", "Code validated")
                
                # Sandbox test
                from core.tool_evolution.sandbox_runner import EvolutionSandboxRunner
                sandbox = EvolutionSandboxRunner(self.expansion_mode)
                sandbox_passed, sandbox_output = sandbox.test_improved_tool(
                    tool_name,
                    improved_code,
                    analysis['tool_path'],
                    new_service_specs=proposal.get('new_service_specs'),
                    network_only=proposal.get('network_only', False)
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
                logger.error(f"[Evolution {evolution_id}] Generation error (attempt {attempt+1}): {e}")
                if attempt == 2:
                    evo_logger.log_run(tool_name, user_prompt, "failed", "generation", str(e), confidence, health_before)
                    return False, f"Generation failed: {str(e)}"
                continue
        
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
        self.last_skill_updates = self._plan_skill_updates(tool_name, analysis)
        
        # Create backup of original file before any changes
        backup_path = self._create_backup(tool_name, analysis['tool_path'])
        
        evolution_data = {
        "tool_name": tool_name,
        "original_code": analysis['current_code'],
        "improved_code": improved_code,
        "proposal": proposal,
        "tool_spec": proposal.get("tool_spec"),
        "health_before": analysis.get('health_score', 0),
        "conversation_log": self.conversation_log,
        "status": "pending_approval",
        "evolution_id": evolution_id,
        "code_size": len(improved_code),
        "capabilities_count": len(analysis.get('capabilities', [])),
        "required_services": proposal.get('required_services', []),
        "required_libraries": proposal.get('required_libraries', []),
        "new_service_specs": proposal.get('new_service_specs', {}),
        "service_descriptions": proposal.get('service_descriptions', {}),
        "skill_updates": self.last_skill_updates,
        "backup_path": backup_path,  # Store backup location
        "tool_path": analysis['tool_path']
        }
        
        manager.add_pending_evolution(tool_name, evolution_data)
        
        return True, f"Evolution pending approval: {tool_name}"

    def _plan_skill_updates(self, tool_name: str, analysis: dict):
        try:
            from core.skills import SkillUpdater
            updater = SkillUpdater()
            operations = []
            for capability in analysis.get("capabilities", []) or []:
                name = capability.get("name") if isinstance(capability, dict) else None
                if name:
                    operations.append(name)
            return updater.plan_tool_evolution_updates(
                tool_name,
                operations=operations,
                gap_context={
                    "gap_type": "tool_evolution",
                    "suggested_action": "improve_skill_workflow",
                    "reasons": [analysis.get("summary")] if analysis.get("summary") else [],
                },
            )
        except Exception:
            return []
    
    def _create_backup(self, tool_name: str, tool_path: str) -> Optional[str]:
        """Create backup of original tool file."""
        try:
            from pathlib import Path
            import shutil
            from datetime import datetime
            tool_file = Path(tool_path)
            if not tool_file.exists():
                logger.warning(f"Tool file not found for backup: {tool_path}")
                return None
            backup_dir = Path("data/tool_backups")
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{tool_name}_{timestamp}.py.bak"
            backup_path = backup_dir / backup_name
            shutil.copy2(tool_file, backup_path)
            logger.info(f"Created backup: {backup_path}")
            return str(backup_path)
        except Exception as e:
            logger.error(f"Failed to create backup for {tool_name}: {e}")
            return None
    
    def rollback_evolution(self, tool_name: str, backup_path: str) -> Tuple[bool, str]:
        """Rollback tool to backup version."""
        try:
            from pathlib import Path
            import shutil
            backup_file = Path(backup_path)
            if not backup_file.exists():
                return False, f"Backup file not found: {backup_path}"
            tool_file = self._find_tool_file(tool_name)
            if not tool_file:
                return False, f"Tool file not found: {tool_name}"
            shutil.copy2(backup_file, tool_file)
            logger.info(f"Rolled back {tool_name} from {backup_path}")
            return True, f"Successfully rolled back {tool_name}"
        except Exception as e:
            logger.error(f"Rollback failed for {tool_name}: {e}")
            return False, f"Rollback failed: {str(e)}"
    
    def _find_tool_file(self, tool_name: str) -> Optional[Path]:
        """Find tool file path."""
        from pathlib import Path
        try:
            from core.tool_registry_manager import ToolRegistryManager
            resolved = ToolRegistryManager().resolve_source_file(tool_name)
            if resolved and resolved.exists():
                return resolved
        except Exception:
            pass
        
        # Check experimental directory
        exp_path = Path("tools/experimental") / f"{tool_name}.py"
        if exp_path.exists():
            return exp_path
        core_path = Path("tools") / f"{tool_name.lower()}.py"
        if core_path.exists():
            return core_path
        return None
    
    def _log_conversation(self, step: str, message: str):
        """Log conversation for user visibility."""
        self.conversation_log.append({
        "step": step,
        "message": message
        })
        logger.info(f"[{step}] {message}")
        
        # Broadcast trace event
        from api.trace_ws import broadcast_trace_sync
        status = "in_progress" if step not in ["COMPLETE", "VALIDATION", "SANDBOX"] else "success"
        broadcast_trace_sync("evolution", f"{step}: {message}", status)
    
    def get_conversation_log(self):
        """Get conversation log for UI display."""
        return self.conversation_log
    
    def _cleanup_failed_evolution(self, tool_name: str):
        """Cleanup artifacts if evolution fails (matches creation pattern)."""
        # Evolution doesn't create files until approval, so just log
        logger.info(f"Evolution failed for {tool_name}, no cleanup needed (pending approval system)")
