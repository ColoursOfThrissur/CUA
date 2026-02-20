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
        
        # Step 1: Detect capability gap
        logger.info(f"Capability gap detected: {gap_description}")
        
        # Step 2: LLM proposes tool spec
        from core.tool_creation import SpecGenerator
        spec_generator = SpecGenerator(self.capability_graph)
        tool_spec = spec_generator.propose_tool_spec(
            gap_description,
            llm_client,
            preferred_tool_name=preferred_tool_name,
        )
        if not tool_spec:
            return False, "Failed to generate tool spec"
        
        # Check confidence score
        confidence = tool_spec.get('confidence', 1.0)
        if confidence < 0.5:
            return False, f"Low confidence spec ({confidence:.2f}) - gap description too vague"
        
        # Log human review requirement
        if tool_spec.get('requires_human_review'):
            logger.warning(f"Tool requires human review: confidence={confidence:.2f}, risk={tool_spec.get('risk_level', 0.5):.2f}")
        
        # Step 3: Skip graph validation (capability_graph doesn't have register_tool)
        # Graph is built dynamically from existing tools
        
        # Step 4: Generate code with LLM (skip scaffolding for new architecture)
        from core.tool_creation.code_generator import QwenCodeGenerator, DefaultCodeGenerator
        generator = self._select_generator(llm_client)
        
        filled_code = generator.generate(None, tool_spec)  # No template needed
        if not filled_code:
            return False, "Failed to generate tool logic"
        
        # Step 5: Validate generated code
        from core.tool_creation.validator import ToolValidator
        validator = ToolValidator()
        is_valid, validation_error = validator.validate(filled_code, tool_spec)
        if not is_valid:
            return False, f"Generated tool code invalid: {validation_error}"
        
        # Step 6: Create in experimental namespace
        success, msg = self.expansion_mode.create_experimental_tool(
            tool_spec['name'], filled_code, tool_spec  # Pass spec for test generation
        )
        if not success:
            return False, msg
        
        # Step 7: Run sandbox validation
        from core.tool_creation.sandbox_runner import SandboxRunner
        sandbox_runner = SandboxRunner(self.expansion_mode)
        sandbox_passed = sandbox_runner.run_sandbox(tool_spec['name'])
        if not sandbox_passed:
            self._cleanup_artifacts(tool_spec["name"])
            return False, "Sandbox validation failed"
        
        # Step 8: Register as experimental
        logger.info(f"Tool registered as experimental: {tool_spec['name']}")
        
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
