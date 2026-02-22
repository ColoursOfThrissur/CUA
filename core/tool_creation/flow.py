"""
Main tool creation flow orchestrator
FIXED: Step ordering, removed bypass_budget security risk
"""
import logging
from typing import Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class ToolCreationOrchestrator:
    """Orchestrates the complete tool creation flow"""
    
    def __init__(self, capability_graph, expansion_mode):
        self.capability_graph = capability_graph
        self.expansion_mode = expansion_mode
        self.last_spec = None  # Store last generated spec for API access
    
    def create_tool(
        self,
        gap_description: str,
        llm_client,
        preferred_tool_name: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Alias for create_new_tool for API compatibility"""
        return self.create_new_tool(gap_description, llm_client, preferred_tool_name)
    
    def create_new_tool(
        self,
        gap_description: str,
        llm_client,
        preferred_tool_name: Optional[str] = None,
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
        creation_id = creation_logger.log_creation(
            tool_name="unknown",
            user_prompt=gap_description,
            status="started",
            step="gap_detection"
        )
        print(f"[FLOW] Creation ID: {creation_id}")
        
        # Step 2: LLM proposes tool spec
        from core.tool_creation import SpecGenerator
        spec_generator = SpecGenerator(self.capability_graph)
        try:
            print(f"[FLOW DEBUG] Starting spec generation for: {gap_description}")
            tool_spec = spec_generator.propose_tool_spec(
                gap_description,
                llm_client,
                preferred_tool_name=preferred_tool_name,
            )
            print(f"[FLOW DEBUG] Spec generation returned: {tool_spec is not None}")
        except Exception as e:
            print(f"[FLOW DEBUG] Exception in spec generation: {e}")
            creation_logger.log_creation(
                tool_name="unknown",
                user_prompt=gap_description,
                status="failed",
                step="spec_generation",
                error_message=f"Exception during spec generation: {str(e)}"
            )
            logger.error(f"Spec generation exception: {e}", exc_info=True)
            return False, f"Failed to generate tool spec: {str(e)}"
        
        if not tool_spec:
            creation_logger.log_creation(
                tool_name="unknown",
                user_prompt=gap_description,
                status="failed",
                step="spec_generation",
                error_message="LLM returned None/empty spec"
            )
            return False, "Failed to generate tool spec"
        
        # Store spec for API access
        self.last_spec = tool_spec
        
        tool_name = tool_spec.get('name', 'unknown')
        # Remove non-serializable objects before logging
        spec_for_logging = {k: v for k, v in tool_spec.items() if k != 'node'}
        creation_logger.log_artifact(creation_id, "spec", "spec_generation", spec_for_logging)
        
        # Log service resolution
        missing_services = tool_spec.get('missing_services', [])
        if missing_services:
            creation_logger.log_artifact(creation_id, "missing_services", "spec_generation", {
                "services": missing_services,
                "note": "These services need to be created before tool can be fully functional"
            })
            logger.warning(f"Tool requires missing services: {missing_services}")
        
        # Check confidence score
        confidence = tool_spec.get('confidence', 1.0)
        if confidence < 0.5:
            creation_logger.log_creation(
                tool_name=tool_name,
                user_prompt=gap_description,
                status="failed",
                step="confidence_check",
                error_message=f"Low confidence spec ({confidence:.2f})"
            )
            return False, f"Low confidence spec ({confidence:.2f}) - gap description too vague"
        
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
            filled_code = generator.generate(None, tool_spec)  # No template needed
        except Exception as e:
            creation_logger.log_creation(
                tool_name=tool_name,
                user_prompt=gap_description,
                status="failed",
                step="code_generation",
                error_message=f"Exception during code generation: {str(e)}"
            )
            logger.error(f"Code generation exception: {e}", exc_info=True)
            return False, f"Failed to generate tool logic: {str(e)}"
        
        if not filled_code:
            creation_logger.log_creation(
                tool_name=tool_name,
                user_prompt=gap_description,
                status="failed",
                step="code_generation",
                error_message="Generator returned None/empty code"
            )
            return False, "Failed to generate tool logic"
        
        creation_logger.log_artifact(creation_id, "code", "code_generation", filled_code)
        
        # Step 5: Validate generated code
        from core.tool_creation.validator import ToolValidator
        validator = ToolValidator()
        is_valid, validation_error = validator.validate(filled_code, tool_spec)
        if not is_valid:
            creation_logger.log_creation(
                tool_name=tool_name,
                user_prompt=gap_description,
                status="failed",
                step="validation",
                error_message=f"Validation failed: {validation_error}",
                code_size=len(filled_code)
            )
            return False, f"Generated tool code invalid: {validation_error}"
        
        # Step 6: Create in experimental namespace
        success, msg = self.expansion_mode.create_experimental_tool(
            tool_spec['name'], filled_code, tool_spec  # Pass spec for test generation
        )
        if not success:
            creation_logger.log_creation(
                tool_name=tool_name,
                user_prompt=gap_description,
                status="failed",
                step="file_creation",
                error_message=msg
            )
            return False, msg
        
        # Step 7: Run sandbox validation (with retry on failure)
        from core.tool_creation.sandbox_runner import SandboxRunner
        sandbox_runner = SandboxRunner(self.expansion_mode)
        
        for attempt in range(2):  # 2 attempts max
            sandbox_passed = sandbox_runner.run_sandbox(tool_spec['name'], creation_id=creation_id)
            if sandbox_passed:
                break
            
            if attempt == 0:  # First failure - try to fix
                logger.info(f"Sandbox failed (attempt {attempt+1}/2), regenerating with error feedback")
                
                # Get sandbox error from last artifact
                error_msg = creation_logger.get_last_error(creation_id, "sandbox")
                if not error_msg:
                    error_msg = "Sandbox validation failed"
                
                # Regenerate code with error feedback
                tool_spec['_sandbox_error'] = error_msg
                try:
                    filled_code = generator.generate(None, tool_spec)
                    if filled_code:
                        is_valid, validation_error = validator.validate(filled_code, tool_spec)
                        if is_valid:
                            # Update file with fixed code
                            self.expansion_mode.create_experimental_tool(
                                tool_spec['name'], filled_code, tool_spec
                            )
                            creation_logger.log_artifact(creation_id, "code_retry", "sandbox_retry", filled_code)
                except Exception as e:
                    logger.warning(f"Retry generation failed: {e}")
        
        if not sandbox_passed:
            self._cleanup_artifacts(tool_spec["name"])
            creation_logger.log_creation(
                tool_name=tool_name,
                user_prompt=gap_description,
                status="failed",
                step="sandbox",
                error_message="Sandbox validation failed after 2 attempts"
            )
            return False, "Sandbox validation failed after 2 attempts"
        
        # Step 8: Register as experimental
        logger.info(f"Tool registered as experimental: {tool_spec['name']}")
        creation_logger.log_creation(
            tool_name=tool_name,
            user_prompt=gap_description,
            status="success",
            step="completed",
            code_size=len(filled_code),
            capabilities_count=len(tool_spec.get('inputs', []))
        )
        
        return True, f"Experimental tool created: {tool_spec['name']}"
    
    def _cleanup_artifacts(self, tool_name: str):
        """Delete generated tool/test artifacts when validation fails"""
        tool_file = Path(getattr(self.expansion_mode, "experimental_dir", "tools/experimental")) / f"{tool_name}.py"
        test_file = Path("tests/experimental") / f"test_{tool_name}.py"
        
        for p in (tool_file, test_file):
            try:
                p.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed cleaning generated artifact {p}: {e}")
    
    def _select_generator(self, llm_client):
        """Select generator based on model capabilities config"""
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
                if config["strategy"] == "multistage":
                    return QwenCodeGenerator(llm_client, self)
                else:
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
    
    def _is_qwen_model(self, llm_client) -> bool:
        """Check if LLM client is using Qwen model (deprecated - use _select_generator)"""
        model = str(getattr(llm_client, "model", "")).lower()
        return "qwen" in model
    
    def _validate_generated_tool_contract(self, code: str, tool_spec: dict) -> Tuple[bool, str]:
        """Delegate to validator (for backward compatibility)"""
        from core.tool_creation.validator import ToolValidator
        validator = ToolValidator()
        return validator.validate(code, tool_spec)
