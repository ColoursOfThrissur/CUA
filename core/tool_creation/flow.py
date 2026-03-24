"""
Main tool creation flow orchestrator
FIXED: Step ordering, removed bypass_budget security risk
"""
import logging
from typing import Optional, Tuple
from pathlib import Path
from api.trace_ws import broadcast_trace_sync

logger = logging.getLogger(__name__)


class ToolCreationOrchestrator:
    """Orchestrates the complete tool creation flow"""
    
    def __init__(self, capability_graph, expansion_mode, skill_registry=None, llm_client=None):
        self.capability_graph = capability_graph
        self.expansion_mode = expansion_mode
        self.skill_registry = skill_registry
        self.llm_client = llm_client
        self.last_spec = None  # Store last generated spec for API access
        self.last_skill_updates = []
        self.skill_aware_orchestrator = None
        if skill_registry and llm_client:
            from core.tool_creation.skill_aware_creation import SkillAwareCreationOrchestrator
            self.skill_aware_orchestrator = SkillAwareCreationOrchestrator(skill_registry, llm_client)
    
    def create_tool(
        self,
        gap_description: str,
        llm_client,
        preferred_tool_name: Optional[str] = None,
        skill_context: Optional[dict] = None,
    ) -> Tuple[bool, str]:
        """Alias for create_new_tool for API compatibility"""
        return self.create_new_tool(gap_description, llm_client, preferred_tool_name, skill_context=skill_context)
    
    def create_new_tool(
        self,
        gap_description: str,
        llm_client,
        preferred_tool_name: Optional[str] = None,
        skill_context: Optional[dict] = None,
    ) -> Tuple[bool, str]:
        """
        Complete flow for creating new tool
        FIXED: Removed bypass_budget parameter (security risk)
        FIXED: Check budget BEFORE scaffolding (correct order)
        """
        from core.tool_creation_logger import get_tool_creation_logger
        creation_logger = get_tool_creation_logger()
        
        # Step 1: Detect capability gap
        logger.info(f"Capability gap detected: {gap_description}")
        print(f"[FLOW] Step 1: Starting tool creation for: {gap_description[:50]}...")
        broadcast_trace_sync("creation", f"Starting tool creation: {gap_description[:80]}", "in_progress", {"stage": "gap_detection"})
        creation_id = creation_logger.log_creation(
            tool_name="unknown",
            user_prompt=gap_description,
            status="started",
            step="gap_detection"
        )
        print(f"[FLOW] Creation ID: {creation_id}")

        try:
            return self._create_new_tool_inner(gap_description, llm_client, preferred_tool_name, skill_context, creation_id, creation_logger)
        except Exception as e:
            import traceback as _tb
            creation_logger.update_creation(
                creation_id, tool_name="unknown", status="failed",
                step="unhandled_exception", error_message=f"{type(e).__name__}: {e}",
            )
            creation_logger.log_artifact(creation_id, "traceback", "unhandled_exception", _tb.format_exc())
            logger.error(f"Unhandled exception in tool creation: {e}", exc_info=True)
            broadcast_trace_sync("creation", f"Tool creation crashed: {e}", "error", {"stage": "unhandled_exception"})
            raise

    def _create_new_tool_inner(
        self,
        gap_description: str,
        llm_client,
        preferred_tool_name: Optional[str],
        skill_context: Optional[dict],
        creation_id: int,
        creation_logger,
    ) -> Tuple[bool, str]:
        
        # Step 1.5: Auto-detect or create skill if not provided
        if not skill_context and self.skill_aware_orchestrator:
            logger.info("[SKILL-AWARE] No skill context provided, auto-detecting...")
            broadcast_trace_sync("creation", "Detecting target skill", "in_progress", {"stage": "skill_detection"})
            try:
                skill_context = self.skill_aware_orchestrator.detect_or_create_skill(gap_description)
                creation_logger.log_artifact(creation_id, "skill_context", "skill_detection", skill_context)
                
                if skill_context.get("source") == "created_skill":
                    logger.info(f"[SKILL-AWARE] Created new skill: {skill_context.get('target_skill')}")
                    broadcast_trace_sync("creation", f"Created new skill: {skill_context.get('target_skill')}", "success", {"stage": "skill_detection"})
                elif skill_context.get("target_skill"):
                    logger.info(f"[SKILL-AWARE] Detected skill: {skill_context.get('target_skill')}")
                    broadcast_trace_sync("creation", f"Detected skill: {skill_context.get('target_skill')}", "success", {"stage": "skill_detection"})
                else:
                    logger.info("[SKILL-AWARE] No skill match, creating general-purpose tool")
                    broadcast_trace_sync("creation", "No skill match, creating general tool", "info", {"stage": "skill_detection"})
            except Exception as e:
                logger.warning(f"[SKILL-AWARE] Skill detection failed: {e}")
                creation_logger.log_artifact(creation_id, "skill_detection_error", "skill_detection", {"error": str(e)})
                # Continue without skill context
        
        # Step 2: LLM proposes tool spec
        from core.tool_creation import SpecGenerator
        spec_generator = SpecGenerator(self.capability_graph)
        try:
            print(f"[FLOW DEBUG] Starting spec generation for: {gap_description}")
            broadcast_trace_sync("creation", "Generating tool specification", "in_progress", {"stage": "spec_generation"})
            tool_spec = spec_generator.propose_tool_spec(
                gap_description,
                llm_client,
                preferred_tool_name=preferred_tool_name,
                skill_context=skill_context,
            )
            print(f"[FLOW DEBUG] Spec generation returned: {tool_spec is not None}")
        except Exception as e:
            print(f"[FLOW DEBUG] Exception in spec generation: {e}")
            creation_logger.update_creation(
                creation_id,
                tool_name="unknown",
                user_prompt=gap_description,
                status="failed",
                step="spec_generation",
                error_message=f"Exception during spec generation: {str(e)}",
            )
            logger.error(f"Spec generation exception: {e}", exc_info=True)
            broadcast_trace_sync("creation", f"Spec generation failed: {e}", "error", {"stage": "spec_generation"})
            return False, f"Failed to generate tool spec: {str(e)}"
        
        if not tool_spec:
            creation_logger.update_creation(
                creation_id,
                tool_name="unknown",
                user_prompt=gap_description,
                status="failed",
                step="spec_generation",
                error_message="LLM returned None/empty spec",
            )
            broadcast_trace_sync("creation", "Spec generation returned no result", "error", {"stage": "spec_generation"})
            return False, "Failed to generate tool spec"
        
        # Store spec for API access
        self.last_spec = tool_spec
        
        tool_name = tool_spec.get('name', 'unknown')

        # Guardrail: if the tool already exists in the registry, prefer evolution over creating duplicates.
        try:
            from core.tool_registry_manager import ToolRegistryManager

            def _norm(name: str) -> str:
                return "".join(ch for ch in (name or "").lower() if ch.isalnum())

            registry = ToolRegistryManager().get_registry() or {}
            existing_tools = (registry.get("tools") or {}) if isinstance(registry, dict) else {}
            collision = None
            for existing_name, data in existing_tools.items():
                if _norm(existing_name) == _norm(tool_name):
                    src = str((data or {}).get("source_file") or "")
                    collision = {"tool_name": existing_name, "source_file": src}
                    break

            if collision and collision["tool_name"] != tool_name:
                tool_spec["name"] = collision["tool_name"]
                tool_name = collision["tool_name"]

            if collision and collision.get("source_file"):
                src_path = Path(collision["source_file"])
                if not src_path.exists():
                    src_path = Path(collision["source_file"].replace("\\", "/"))
                if src_path.exists():
                    creation_logger.update_creation(
                        creation_id,
                        tool_name=tool_name,
                        status="failed",
                        step="name_collision",
                        error_message=f"Tool already exists: {collision['tool_name']} ({str(src_path).replace('\\', '/')})",
                    )
                    creation_logger.log_artifact(creation_id, "name_collision", "spec_generation", collision)
                    return False, f"Tool '{tool_name}' already exists. Use tool evolution instead of creating a duplicate."
        except Exception:
            pass

        creation_logger.update_creation(
            creation_id,
            tool_name=tool_name,
            status="started",
            step="spec_generation",
        )
        # Remove non-serializable objects before logging
        spec_for_logging = {k: v for k, v in tool_spec.items() if k != 'node'}
        creation_logger.log_artifact(creation_id, "spec", "spec_generation", spec_for_logging)
        broadcast_trace_sync("creation", f"Spec ready for {tool_name}", "success", {"stage": "spec_generation", "tool_name": tool_name})
        
        # Log service resolution
        missing_services = tool_spec.get('missing_services', [])
        if missing_services:
            creation_logger.log_artifact(creation_id, "missing_services", "spec_generation", {
                "services": missing_services,
                "note": "These services need to be created before tool can be fully functional"
            })
            logger.warning(f"Tool requires missing services: {missing_services}")
        
        # Check confidence score — threshold is model-aware (local models self-report lower)
        confidence = tool_spec.get('confidence', 1.0)
        _min_conf = 0.5
        try:
            import json as _json
            _cap_path = Path("config/model_capabilities.json")
            if _cap_path.exists():
                _caps = _json.loads(_cap_path.read_text())
                _model = str(getattr(llm_client, "model", "")).lower()
                for _pat, _cfg in _caps.items():
                    if _pat in _model:
                        _min_conf = float(_cfg.get("min_confidence", 0.5))
                        break
        except Exception:
            pass
        if confidence < _min_conf:
            creation_logger.update_creation(
                creation_id,
                tool_name=tool_name,
                status="failed",
                step="confidence_check",
                error_message=f"Low confidence spec ({confidence:.2f})",
            )
            return False, f"Low confidence spec ({confidence:.2f}) - gap description too vague (min={_min_conf})"
        
        # Log human review requirement
        if tool_spec.get('requires_human_review'):
            logger.warning(f"Tool requires human review: confidence={confidence:.2f}, risk={tool_spec.get('risk_level', 0.5):.2f}")
        
        # Step 3: Skip graph validation (capability_graph doesn't have register_tool)
        # Graph is built dynamically from existing tools
        
        # Step 4: Generate code with LLM (skip scaffolding for new architecture)
        from core.tool_creation.code_generator import QwenCodeGenerator, DefaultCodeGenerator
        generator = self._select_generator(llm_client)
        
        # Pass creation_id to generator for logging
        tool_spec['_creation_id'] = creation_id
        
        try:
            broadcast_trace_sync("creation", f"Generating code for {tool_name}", "in_progress", {"stage": "code_generation", "tool_name": tool_name})
            filled_code = generator.generate(None, tool_spec)  # No template needed
        except Exception as e:
            creation_logger.update_creation(
                creation_id,
                tool_name=tool_name,
                status="failed",
                step="code_generation",
                error_message=f"Exception during code generation: {str(e)}",
            )
            logger.error(f"Code generation exception: {e}", exc_info=True)
            broadcast_trace_sync("creation", f"Code generation failed for {tool_name}: {e}", "error", {"stage": "code_generation", "tool_name": tool_name})
            return False, f"Failed to generate tool logic: {str(e)}"
        
        if not filled_code:
            creation_logger.update_creation(
                creation_id,
                tool_name=tool_name,
                status="failed",
                step="code_generation",
                error_message="Generator returned None/empty code",
            )
            broadcast_trace_sync("creation", f"Code generation returned no output for {tool_name}", "error", {"stage": "code_generation", "tool_name": tool_name})
            return False, "Failed to generate tool logic"

        generation_meta = tool_spec.get("_generation_meta") if isinstance(tool_spec, dict) else None
        if isinstance(generation_meta, dict):
            creation_logger.log_artifact(creation_id, "generation_meta", "code_generation", generation_meta)
        
        creation_logger.log_artifact(creation_id, "code", "code_generation", filled_code)
        
        # Step 5: Validate generated code
        from core.tool_creation.validator import ToolValidator
        validator = ToolValidator()
        broadcast_trace_sync("creation", f"Validating {tool_name}", "in_progress", {"stage": "validation", "tool_name": tool_name})
        
        # Get skill definition for service validation
        skill_definition = None
        if skill_context and self.skill_registry:
            skill_name = skill_context.get("target_skill") or skill_context.get("skill_name")
            if skill_name:
                skill_definition = self.skill_registry.get(skill_name)
        
        is_valid, validation_error = validator.validate(filled_code, tool_spec, skill_definition)
        
        # Validate skill alignment if skill_context provided
        if is_valid and skill_context:
            skill_validation_error = self._validate_skill_alignment(tool_spec, skill_context)
            if skill_validation_error:
                is_valid = False
                validation_error = skill_validation_error
        
        if not is_valid:
            # If validation failed due to missing services, generate them into the pending-services queue.
            try:
                missing_services = validator.enhanced_validator.get_missing_services()
            except Exception:
                missing_services = []

            if missing_services:
                try:
                    from core.service_generation_integration import ServiceGenerationIntegration
                    svc_integration = ServiceGenerationIntegration()
                    svc_result = svc_integration.validate_and_generate_services(
                        filled_code,
                        class_name=None,
                        context=gap_description,
                        requested_by="tool_creation",
                    )
                    creation_logger.log_artifact(creation_id, "pending_services", "validation", svc_result)
                    if svc_result.get("pending_approval"):
                        creation_logger.update_creation(
                            creation_id,
                            tool_name=tool_name,
                            status="blocked",
                            step="services_pending",
                            error_message=svc_result.get("error"),
                            code_size=len(filled_code),
                        )
                        return False, f"Missing services detected; generated pending service proposals for approval. {svc_result.get('error')}"
                except Exception as e:
                    creation_logger.log_artifact(creation_id, "service_generation_error", "validation", {"error": str(e)})

            creation_logger.update_creation(
                creation_id,
                tool_name=tool_name,
                status="failed",
                step="validation",
                error_message=f"Validation failed: {validation_error}",
                code_size=len(filled_code),
            )
            broadcast_trace_sync("creation", f"Validation failed for {tool_name}: {validation_error}", "error", {"stage": "validation", "tool_name": tool_name})
            return False, f"Generated tool code invalid: {validation_error}"
        
        # Step 5.5: Check and resolve dependencies
        from core.dependency_checker import DependencyChecker
        from core.dependency_resolver import DependencyResolver
        
        dep_checker = DependencyChecker()
        dep_report = dep_checker.check_code(filled_code)
        
        if dep_report.has_missing():
            logger.info(f"Found missing dependencies: libs={dep_report.missing_libraries}, services={dep_report.missing_services}")
            creation_logger.log_artifact(creation_id, "dependencies", "dependency_check", {
                "missing_libraries": dep_report.missing_libraries,
                "missing_services": dep_report.missing_services,
                "pending_services": dep_report.pending_services
            })
            
            # Try to resolve
            dep_resolver = DependencyResolver(llm_client=llm_client)
            
            # Install missing libraries
            for lib in dep_report.missing_libraries:
                logger.info(f"Installing library: {lib}")
                success, msg = dep_resolver.install_library(lib)
                if success:
                    logger.info(f"Installed {lib}: {msg}")
                else:
                    logger.warning(f"Failed to install {lib}: {msg}")
                    creation_logger.update_creation(
                        creation_id,
                        tool_name=tool_name,
                        status="failed",
                        step="dependency_resolution",
                        error_message=f"Failed to install required library: {lib} - {msg}",
                    )
                    return False, f"Missing required library: {lib}. Installation failed: {msg}"
            
            # Services: generate pending proposals and block until approved.
            if dep_report.missing_services or dep_report.pending_services:
                try:
                    from core.service_generation_integration import ServiceGenerationIntegration
                    svc_integration = ServiceGenerationIntegration()
                    svc_result = svc_integration.validate_and_generate_services(
                        filled_code,
                        class_name=None,
                        context=gap_description,
                        requested_by="tool_creation",
                    )
                    creation_logger.log_artifact(creation_id, "pending_services", "dependency_check", svc_result)
                    if svc_result.get("pending_approval"):
                        creation_logger.update_creation(
                            creation_id,
                            tool_name=tool_name,
                            status="blocked",
                            step="services_pending",
                            error_message=svc_result.get("error"),
                            code_size=len(filled_code),
                        )
                        return False, f"Tool requires new/updated services; generated pending service proposals for approval. {svc_result.get('error')}"
                except Exception as e:
                    creation_logger.log_artifact(creation_id, "service_generation_error", "dependency_check", {"error": str(e)})
                    return False, f"Tool requires missing services but service generation failed: {e}"
        
        # Step 6: Create in experimental namespace
        success, msg = self.expansion_mode.create_experimental_tool(
            tool_spec['name'], filled_code, tool_spec  # Pass spec for test generation
        )
        if not success:
            creation_logger.update_creation(
                creation_id,
                tool_name=tool_name,
                status="failed",
                step="file_creation",
                error_message=msg,
            )
            return False, msg
        
        # Step 7: Run sandbox validation (with retry on failure)
        from core.tool_creation.sandbox_runner import SandboxRunner
        sandbox_runner = SandboxRunner(self.expansion_mode)
        
        max_retries = 5  # Increased from 2 to 5
        for attempt in range(max_retries):
            sandbox_passed = sandbox_runner.run_sandbox(tool_spec['name'], creation_id=creation_id)
            if sandbox_passed:
                break
            
            if attempt < max_retries - 1:  # Not last attempt - try to fix
                logger.info(f"Sandbox failed (attempt {attempt+1}/{max_retries}), regenerating with error feedback")
                
                # Get sandbox error and validation error
                error_msg = creation_logger.get_last_error(creation_id, "sandbox") or "Sandbox validation failed"
                
                # Build correction prompt with specific fixes
                correction_prompt = self._build_correction_prompt(
                    tool_spec,
                    filled_code,
                    error_msg,
                    validation_error if not is_valid else None
                )
                
                # Regenerate with corrections
                tool_spec['_correction_prompt'] = correction_prompt
                tool_spec['_retry_attempt'] = attempt + 1
                
                try:
                    # Use slightly higher temperature for retries to explore alternatives
                    filled_code = generator.generate(None, tool_spec)
                    if filled_code:
                        is_valid, validation_error = validator.validate(filled_code, tool_spec)
                        if is_valid:
                            # Update file with fixed code
                            self.expansion_mode.create_experimental_tool(
                                tool_spec['name'], filled_code, tool_spec
                            )
                            creation_logger.log_artifact(creation_id, f"code_retry_{attempt+1}", "sandbox_retry", filled_code)
                        else:
                            # Log validation failure for next retry
                            creation_logger.log_artifact(creation_id, f"validation_error_{attempt+1}", "validation", validation_error)
                except Exception as e:
                    logger.warning(f"Retry generation failed: {e}")
        
        if not sandbox_passed:
            self._cleanup_artifacts(tool_spec["name"])
            creation_logger.update_creation(
                creation_id,
                tool_name=tool_name,
                status="failed",
                step="sandbox",
                error_message=f"Sandbox validation failed after {max_retries} attempts",
            )
            return False, f"Sandbox validation failed after {max_retries} attempts"
        
        # Step 8: Update skill with new tool
        if skill_context and self.skill_aware_orchestrator:
            try:
                update_result = self.skill_aware_orchestrator.update_skill_with_tool(skill_context, tool_spec)
                creation_logger.log_artifact(creation_id, "skill_update", "completed", update_result)
                if update_result.get("success"):
                    logger.info(f"[SKILL-AWARE] Updated skill '{skill_context.get('target_skill')}' with tool '{tool_spec['name']}'")
                else:
                    logger.warning(f"[SKILL-AWARE] Failed to update skill: {update_result.get('error')}")
            except Exception as e:
                logger.warning(f"[SKILL-AWARE] Skill update failed: {e}")
                creation_logger.log_artifact(creation_id, "skill_update_error", "completed", {"error": str(e)})
        
        # Step 9: Register as experimental
        logger.info(f"Tool registered as experimental: {tool_spec['name']}")

        # If stage 2 didn't produce validated code, we still create a safe scaffold (stub) but flag it.
        generation_meta = tool_spec.get("_generation_meta") if isinstance(tool_spec, dict) else None
        is_stub = bool(
            isinstance(generation_meta, dict)
            and generation_meta.get("stage1_valid")
            and generation_meta.get("stage2_attempted")
            and not generation_meta.get("stage2_valid")
        )

        final_status = "success_stub" if is_stub else "success"
        final_step = "completed_stub" if is_stub else "completed"
        final_error = None
        if is_stub:
            final_error = generation_meta.get("stage2_error") or "Created scaffold only; stage 2 implementation not validated"
            creation_logger.log_artifact(
                creation_id,
                "needs_evolution",
                "completed",
                {"reason": final_error, "note": "Tool created as scaffold; queue evolution to fill in handlers."},
            )

            # Auto-queue evolution for the newly created stub tool (still requires explicit user approval later).
            try:
                from core.evolution_queue import get_evolution_queue, QueuedEvolution
                queue = get_evolution_queue()
                queue.add(
                    QueuedEvolution(
                        # Use the actual tool module/class name as registered in the repo.
                        # Avoid str.capitalize() here (it lowercases the rest and breaks CamelCase).
                        tool_name=str(tool_spec.get("name") or tool_name),
                        urgency_score=90.0,
                        impact_score=70.0,
                        feasibility_score=75.0,
                        timing_score=90.0,
                        reason=f"Stub tool created; needs evolution. {final_error}",
                        metadata={"kind": "evolve_tool", "source": "tool_creation", "creation_id": creation_id},
                    )
                )
                creation_logger.log_artifact(creation_id, "auto_queued_evolution", "completed", {"tool": tool_name})
            except Exception as e:
                creation_logger.log_artifact(creation_id, "auto_queue_error", "completed", {"error": str(e)})

        creation_logger.update_creation(
            creation_id,
            tool_name=tool_name,
            status=final_status,
            step=final_step,
            error_message=final_error,
            code_size=len(filled_code),
            capabilities_count=len(tool_spec.get('inputs', [])),
        )
        
        if is_stub:
            self._capture_skill_updates(tool_spec)
            return True, f"Experimental tool created: {tool_spec['name']} (scaffold only; queued for evolution)"
        self._capture_skill_updates(tool_spec)
        return True, f"Experimental tool created: {tool_spec['name']}"

    def _capture_skill_updates(self, tool_spec: dict):
        try:
            from core.skills import SkillUpdater

            updater = SkillUpdater()
            self.last_skill_updates = []
            plan = updater.plan_tool_creation_update(
                skill_name=str(tool_spec.get("target_skill") or "").strip(),
                tool_name=str(tool_spec.get("name") or "").strip(),
                operations=[item.get("operation") for item in tool_spec.get("inputs", []) if isinstance(item, dict) and item.get("operation")],
                output_types=list(tool_spec.get("outputs") or []),
                gap_context={
                    "gap_type": tool_spec.get("gap_type"),
                    "suggested_action": tool_spec.get("suggested_action"),
                    "reasons": list(tool_spec.get("reasons") or []),
                    "example_tasks": list(tool_spec.get("example_tasks") or []),
                    "example_errors": list(tool_spec.get("example_errors") or []),
                },
            )
            if plan:
                self.last_skill_updates.append(plan)
        except Exception:
            self.last_skill_updates = []
    
    def _cleanup_artifacts(self, tool_name: str):
        """Delete generated tool/test artifacts when validation fails"""
        tool_file = Path(getattr(self.expansion_mode, "experimental_dir", "tools/experimental")) / f"{tool_name}.py"
        test_file = Path("tests/experimental") / f"test_{tool_name}.py"
        
        for p in (tool_file, test_file):
            try:
                p.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed cleaning generated artifact {p}: {e}")
    
    def _build_correction_prompt(self, tool_spec: dict, failed_code: str, sandbox_error: str, validation_error: str = None) -> str:
        """Build targeted correction prompt based on specific errors"""
        parts = ["PREVIOUS ATTEMPT FAILED. Fix these specific issues:\n"]

        if validation_error:
            parts.append(f"VALIDATION ERROR:\n{validation_error}\n")

        if sandbox_error:
            # Always include raw error first so Qwen sees the exact traceback line
            parts.append(f"SANDBOX ERROR (raw):\n{sandbox_error[:600]}\n")

        parts.append("REGENERATE the complete corrected code.")
        return '\n'.join(parts)

    def _select_generator(self, llm_client):
        """Select generator based on model capabilities config."""
        from pathlib import Path
        import json
        from core.tool_creation.code_generator import QwenCodeGenerator, DefaultCodeGenerator

        config_path = Path("config/model_capabilities.json")
        if config_path.exists():
            try:
                with open(config_path) as f:
                    capabilities = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load model capabilities config: {e}")
                capabilities = self._get_default_capabilities()
        else:
            capabilities = self._get_default_capabilities()

        model = str(getattr(llm_client, "model", "")).lower()

        # Match model pattern
        for pattern, config in capabilities.items():
            if pattern in model:
                if config.get("strategy") == "multistage":
                    return QwenCodeGenerator(llm_client, self)
                return DefaultCodeGenerator(llm_client, self)

        # Default fallback
        return DefaultCodeGenerator(llm_client, self)
    
    def _get_default_capabilities(self) -> dict:
        """Default model capabilities if config missing"""
        return {
            "qwen": {"strategy": "multistage", "max_lines": 200},
            "gpt-4": {"strategy": "singleshot", "max_lines": 800},
            "claude": {"strategy": "singleshot", "max_lines": 800},
            "gpt-3.5": {"strategy": "singleshot", "max_lines": 500}
        }
    
    def _validate_skill_alignment(self, tool_spec: dict, skill_context: dict) -> Optional[str]:
        """Validate tool aligns with skill expectations."""
        skill_name = skill_context.get("skill_name")
        if not skill_name:
            return None
        
        # Check input types match skill expected_input_types
        skill_input_types = skill_context.get("expected_input_types", [])
        tool_inputs = tool_spec.get("inputs", [])
        
        if skill_input_types:
            tool_param_types = set()
            for inp in tool_inputs:
                if isinstance(inp, dict):
                    for param in inp.get("parameters", []):
                        if isinstance(param, dict):
                            tool_param_types.add(param.get("type", ""))
            
            # At least one input type should match
            if not any(t in skill_input_types for t in tool_param_types):
                return f"Tool input types {tool_param_types} don't match skill expected types {skill_input_types}"
        
        # Check output types match skill expected_output_types
        skill_output_types = skill_context.get("expected_output_types", [])
        tool_outputs = tool_spec.get("outputs", [])
        
        if skill_output_types and tool_outputs:
            if not any(out in skill_output_types for out in tool_outputs):
                return f"Tool output types {tool_outputs} don't match skill expected types {skill_output_types}"
        
        # Check verification_mode compatibility
        verification_mode = skill_context.get("verification_mode")
        if verification_mode == "source_backed":
            # Tool must return sources
            has_sources = any("source" in str(out).lower() for out in tool_outputs)
            if not has_sources:
                return f"Skill requires source_backed verification but tool doesn't return sources"
        
        return None
    
    def _is_qwen_model(self, llm_client) -> bool:
        """Check if LLM client is using Qwen model (deprecated - use _select_generator)"""
        model = str(getattr(llm_client, "model", "")).lower()
        return "qwen" in model
    
    def _validate_generated_tool_contract(self, code: str, tool_spec: dict) -> Tuple[bool, str]:
        """Delegate to validator (for backward compatibility)"""
        from core.tool_creation.validator import ToolValidator
        validator = ToolValidator()
        return validator.validate(code, tool_spec)
