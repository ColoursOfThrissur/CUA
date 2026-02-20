"""
Tool Generation Orchestrator - Incremental tool generation with phase-based approach
"""
import logging
from typing import Optional, Dict, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class ToolGenerationOrchestrator:
    """Orchestrates tool generation in small incremental phases to stay under token limits"""
    
    def __init__(self, llm_client, tool_creation_flow):
        self.llm_client = llm_client
        self.flow = tool_creation_flow
        self.max_tokens_per_phase = 400  # Reduced for thin tools (was 800)
    
    def generate_tool(self, tool_spec: dict) -> Optional[str]:
        """
        Generate complete tool incrementally using deterministic scaffold + incremental handlers
        Returns: complete code or None
        """
        logger.info(f"=== ORCHESTRATED TOOL GENERATION: {tool_spec['name']} ===")
        
        # Phase 1: Use existing deterministic scaffold (0 LLM tokens)
        prompt_spec = self.flow._tool_spec_prompt_payload(tool_spec)
        skeleton = self.flow._build_deterministic_stage1_scaffold(prompt_spec, tool_spec)
        logger.info(f"Phase 1 (deterministic scaffold): {len(skeleton)} chars")
        
        # Validate scaffold
        is_valid, error = self.flow._validate_generated_tool_contract(skeleton, tool_spec)
        if not is_valid and "does not reference required capability parameters" not in str(error):
            logger.error(f"Scaffold validation failed: {error}")
            return None
        
        # Phase 2: Implement handlers incrementally
        code = skeleton
        stage_targets = self.flow._get_qwen_stage_targets(code, tool_spec)
        
        if not stage_targets:
            logger.warning("No handler targets found, returning scaffold")
            return skeleton
        
        for handler_name in stage_targets:
            logger.info(f"Generating handler: {handler_name}")
            next_code = self._generate_handler_incremental(
                current_code=code,
                handler_name=handler_name,
                prompt_spec=prompt_spec,
                tool_spec=tool_spec
            )
            if not next_code:
                logger.error(f"Handler {handler_name} generation failed")
                return None
            code = next_code
            logger.info(f"Handler {handler_name} complete")
        
        # Final validation
        is_valid, error = self.flow._validate_generated_tool_contract(code, tool_spec)
        if not is_valid:
            logger.error(f"Final validation failed: {error}")
            return None
        
        logger.info(f"=== GENERATION COMPLETE: {len(code)} chars ===")
        return code
    

    

    

    

    
    def _generate_handler_incremental(self, current_code: str, handler_name: str, prompt_spec: dict, tool_spec: dict) -> Optional[str]:
        """Generate one handler using existing flow logic"""
        contract = self.flow._contract_pack()
        
        # Reuse existing method generation from flow
        return self.flow._generate_qwen_method_step(
            current_code=current_code,
            method_name=handler_name,
            prompt_spec=prompt_spec,
            contract=contract,
            tool_spec=tool_spec,
            llm_client=self.llm_client
        )
    

