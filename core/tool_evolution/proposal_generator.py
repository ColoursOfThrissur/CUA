"""Proposal generator for tool evolution - matches spec generator pattern."""
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class EvolutionProposalGenerator:
    """Generates improvement proposals using LLM."""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def generate_proposal(self, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate improvement proposal from analysis."""
        
        # Read evolution context files for guidance
        evolution_context = self._read_evolution_context()
        
        prompt = f"""Analyze this tool and propose ONLY necessary improvements.

Tool: {analysis['tool_name']}
Health Score: {analysis['health_score']:.1f}/100
Success Rate: {analysis['success_rate']:.1%}
Issues: {', '.join(analysis['issues'])}
{f"User Request: {analysis['user_prompt']}" if analysis.get('user_prompt') else ""}

Current Code:
```python
{analysis['current_code']}
```

EVOLUTION GUIDELINES:
{evolution_context}

IMPORTANT:
- ONLY fix issues that are actually broken or causing failures
- DO NOT change working code for style preferences
- DO NOT add features unless explicitly requested
- DO NOT refactor code that works correctly
- Focus on HIGH severity bugs and clear architecture violations
- Ignore LOW severity style suggestions

Generate improvement proposal as JSON:
{{
  "description": "What specific issue to fix",
  "changes": ["Minimal change 1", "Minimal change 2"],
  "expected_improvement": "Expected outcome",
  "confidence": 0.0-1.0,
  "risk_level": 0.0-1.0,
  "justification": "Why this change is necessary"
}}

If NO critical issues found, return: {{"skip": true, "reason": "Tool is working correctly"}}

Return ONLY valid JSON."""
        
        try:
            response = self.llm._call_llm(prompt, temperature=0.2, max_tokens=800, expect_json=True)
            proposal = self._parse_response(response)
            
            if not proposal:
                logger.warning("Failed to parse proposal from LLM")
                return None
            
            # Check if should skip
            if proposal.get('skip'):
                logger.info(f"Skipping evolution: {proposal.get('reason')}")
                return None
            
            # Validate proposal structure
            if not self._validate_proposal(proposal):
                logger.warning("Invalid proposal structure")
                return None
            
            # Calculate confidence if not provided
            if 'confidence' not in proposal or proposal['confidence'] < 0.5:
                proposal['confidence'] = self._calculate_confidence(proposal, analysis)
            
            # Add analysis context
            proposal['analysis'] = analysis
            
            return proposal
            
        except Exception as e:
            logger.error(f"Proposal generation error: {e}")
            return None
    
    def _read_evolution_context(self) -> str:
        """Read evolution guidelines from context files."""
        from pathlib import Path
        context_parts = []
        
        # Read LocalLLMRule if exists
        rule_file = Path(".amazonq/rules/LocalLLMRUle.md")
        if rule_file.exists():
            context_parts.append(rule_file.read_text())
        
        # Add architecture patterns
        context_parts.append("""
ARCHITECTURE PATTERNS:
- Tools use self._cache (with underscore) for caching
- Tools use self.services.X to access services (llm, storage, http, fs, logging)
- SQL queries use parameterized queries (?, params) to prevent injection
- Error handling returns error dicts: {"error": "message"}
- Using .get() on dicts with defaults is correct error handling
""")
        
        return "\n\n".join(context_parts)
    
    def _validate_proposal(self, proposal: Dict) -> bool:
        """Validate proposal has required fields."""
        required = ['description', 'changes', 'expected_improvement']
        return all(field in proposal for field in required)
    
    def _calculate_confidence(self, proposal: Dict, analysis: Dict) -> float:
        """Calculate confidence score for proposal."""
        confidence = 1.0
        
        # Low if no specific changes
        if not proposal.get('changes') or len(proposal['changes']) < 2:
            confidence -= 0.3
        
        # Low if vague description
        if len(proposal.get('description', '').split()) < 5:
            confidence -= 0.2
        
        # Low if health score is very bad (might need redesign)
        if analysis.get('health_score', 0) < 20:
            confidence -= 0.2
        
        # Low if no user prompt and no clear issues
        if not analysis.get('user_prompt') and len(analysis.get('issues', [])) == 0:
            confidence -= 0.3
        
        return max(0.0, confidence)
    
    def _parse_response(self, response: str) -> Optional[Dict]:
        """Parse LLM response to extract proposal."""
        try:
            # Try direct JSON parse
            return json.loads(response)
        except:
            # Try extracting JSON from markdown
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_str = response[start:end].strip()
                return json.loads(json_str)
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                json_str = response[start:end].strip()
                return json.loads(json_str)
            
            return None
