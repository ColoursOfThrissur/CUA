"""
Hybrid Improvement Engine - RAG + Agent-Based + Memory
Combines error prioritization, memory, validation, and context optimization
"""
from typing import Dict, List, Optional
from infrastructure.persistence.file_storage.improvement_memory import ImprovementMemory
from infrastructure.failure_handling.error_prioritizer import ErrorPrioritizer
from infrastructure.validation.test_validator import TestValidator
from application.services.context_optimizer import ContextOptimizer
from planner.llm_client import LLMClient
from application.dto.proposal_generator import ProposalGenerator
import logging

logger = logging.getLogger(__name__)

class HybridImprovementEngine:
    def __init__(self, llm_client=None, orchestrator=None):
        self.memory = ImprovementMemory()
        self.prioritizer = ErrorPrioritizer()
        self.validator = TestValidator()
        self.context_optimizer = ContextOptimizer()
        
        # Lazy initialization - will be set when needed
        self._llm_client = llm_client
        self._orchestrator = orchestrator
        self._proposal_generator = None
    
    @property
    def llm_client(self):
        if self._llm_client is None:
            from planner.llm_client import LLMClient
            self._llm_client = LLMClient()
        return self._llm_client
    
    @property
    def proposal_generator(self):
        if self._proposal_generator is None:
            from infrastructure.analysis.system_analyzer import SystemAnalyzer
            from infrastructure.code_generation.patch_generator import PatchGenerator
            from updater.orchestrator import UpdateOrchestrator
            
            analyzer = SystemAnalyzer()
            patch_gen = PatchGenerator()
            orchestrator = self._orchestrator or UpdateOrchestrator(repo_path=".")
            
            self._proposal_generator = ProposalGenerator(
                self.llm_client,
                analyzer,
                patch_gen,
                orchestrator
            )
        return self._proposal_generator
    
    def analyze_and_improve(self, custom_prompt: str = None, max_iterations: int = 3) -> Dict:
        """Main improvement loop with hybrid approach"""
        logger.info("Starting hybrid improvement analysis")
        
        # Step 1: Error-based prioritization
        priority_files = self.prioritizer.get_priority_files(max_files=5)
        logger.info(f"Priority files identified: {[f[0] for f in priority_files]}")
        
        if not priority_files and not custom_prompt:
            return {
                'status': 'no_issues',
                'message': 'No errors found and no custom prompt provided'
            }
        
        # Step 2: Select target file
        if custom_prompt:
            # LLM decides which file to improve based on prompt
            target_file = self._select_file_for_prompt(custom_prompt, priority_files)
        else:
            # Use highest priority file
            target_file = priority_files[0][0] if priority_files else None
        
        if not target_file:
            return {
                'status': 'no_target',
                'message': 'Could not determine target file'
            }
        
        logger.info(f"Target file selected: {target_file}")
        
        # Step 3: Check memory for past attempts
        past_attempts = self.memory.get_similar_attempts(target_file)
        success_rate = self.memory.get_success_rate(target_file)
        
        logger.info(f"Past attempts: {len(past_attempts)}, Success rate: {success_rate:.2%}")
        
        # Step 4: Get optimized context
        error_context = self.prioritizer.get_error_context(target_file)
        context = self.context_optimizer.get_optimized_context(
            target_file,
            error_context=error_context
        )
        
        # Step 5: Generate proposal with full context
        proposal = self._generate_smart_proposal(
            target_file=target_file,
            context=context,
            past_attempts=past_attempts,
            custom_prompt=custom_prompt,
            max_iterations=max_iterations
        )
        
        if not proposal:
            return {
                'status': 'no_proposal',
                'message': 'Could not generate improvement proposal'
            }
        
        # Step 6: Validate proposal
        validation = self._validate_proposal(proposal, target_file)
        
        # Step 7: Store in memory
        self.memory.store_attempt(
            file_path=target_file,
            change_type=proposal.get('change_type', 'improvement'),
            description=proposal.get('description', ''),
            patch=proposal.get('patch', ''),
            outcome='success' if validation['valid'] else 'failed',
            error_message=validation.get('details') if not validation['valid'] else None,
            test_results=validation.get('tests'),
            metrics={'success_rate': success_rate}
        )
        
        return {
            'status': 'success' if validation['valid'] else 'failed',
            'target_file': target_file,
            'proposal': proposal,
            'validation': validation,
            'context': {
                'past_attempts': len(past_attempts),
                'success_rate': success_rate,
                'error_count': error_context.get('count', 0)
            }
        }
    
    def _select_file_for_prompt(self, prompt: str, priority_files: List) -> Optional[str]:
        """Use LLM to select best file for custom prompt"""
        file_list = [f[0] for f in priority_files] if priority_files else []
        
        llm_prompt = f"""Given this improvement request: "{prompt}"
        
Available files with recent errors:
{chr(10).join(f"- {f}" for f in file_list)}

Which file should be improved? Return just the file path.
"""
        
        try:
            response = self.llm_client._call_llm(
                llm_prompt,
                temperature=0.2,
                max_tokens=512,
                expect_json=False
            )
            # Extract file path from response
            for file_path in file_list:
                if file_path in response:
                    return file_path
            return file_list[0] if file_list else None
        except Exception as e:
            logger.error(f"Error selecting file: {e}")
            return file_list[0] if file_list else None
    
    def _generate_smart_proposal(self, target_file: str, context: Dict,
                                 past_attempts: List, custom_prompt: str,
                                 max_iterations: int) -> Optional[Dict]:
        """Generate proposal with iterative refinement"""
        
        # Build comprehensive prompt
        prompt = self._build_improvement_prompt(
            target_file=target_file,
            context=context,
            past_attempts=past_attempts,
            custom_prompt=custom_prompt
        )
        
        # Try generating with refinement
        for iteration in range(max_iterations):
            try:
                logger.info(f"Generation attempt {iteration + 1}/{max_iterations}")
                
                response = self.llm_client._call_llm(
                    prompt,
                    temperature=0.2,
                    max_tokens=2048,
                    expect_json=True
                )
                proposal = self.proposal_generator.parse_llm_response(response)
                
                if proposal:
                    # Quick syntax check
                    if self._quick_validate(proposal):
                        return proposal
                    else:
                        # Refine prompt with error feedback
                        prompt = self._refine_prompt(prompt, "Syntax error in generated code")
                
            except Exception as e:
                logger.error(f"Generation error: {e}")
                prompt = self._refine_prompt(prompt, str(e))
        
        return None
    
    def _build_improvement_prompt(self, target_file: str, context: Dict,
                                  past_attempts: List, custom_prompt: str) -> str:
        """Build comprehensive improvement prompt"""
        prompt = f"""Improve the following Python file: {target_file}

TARGET FILE CONTENT:
```python
{context['target_file']['content']}
```

FILE STRUCTURE:
- Classes: {', '.join([c['name'] for c in context['target_file']['summary']['classes']])}
- Functions: {', '.join(context['target_file']['summary']['functions'][:5])}
- Lines: {context['target_file']['summary']['lines']}

"""
        
        # Add error context
        if context.get('error_context', {}).get('count', 0) > 0:
            prompt += f"""
RECENT ERRORS ({context['error_context']['count']} occurrences):
{chr(10).join([f"- {err['type']}" for err in context['error_context'].get('recent_errors', [])[:3]])}
"""
        
        # Add past attempts
        if past_attempts:
            prompt += f"""
PAST IMPROVEMENT ATTEMPTS:
{chr(10).join([f"- {att['change_type']}: {att['outcome']}" for att in past_attempts[:3]])}
"""
        
        # Add custom prompt
        if custom_prompt:
            prompt += f"""
SPECIFIC REQUEST: {custom_prompt}
"""
        
        prompt += """
Generate a code improvement proposal as JSON:
{
  "description": "What you're improving",
  "change_type": "bugfix|feature|refactor|optimization",
  "patch": "unified diff format",
  "files_changed": ["list of files"],
  "risk_level": 0.0-1.0
}
"""
        
        return prompt
    
    def _refine_prompt(self, original_prompt: str, error_feedback: str) -> str:
        """Refine prompt based on error feedback"""
        return f"""{original_prompt}

PREVIOUS ATTEMPT FAILED:
{error_feedback}

Please fix the issue and try again.
"""
    
    def _quick_validate(self, proposal: Dict) -> bool:
        """Quick validation without running tests"""
        # Check if patch is valid
        patch = proposal.get('patch', '')
        return len(patch) > 0 and ('+++' in patch or '---' in patch)
    
    def _validate_proposal(self, proposal: Dict, target_file: str) -> Dict:
        """Full validation with tests"""
        return self.validator.validate_change(target_file, run_tests=True)
