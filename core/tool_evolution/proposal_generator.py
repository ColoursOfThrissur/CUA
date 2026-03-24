"""Proposal generator for tool evolution - matches spec generator pattern."""
import json
from typing import Dict, Any, Optional
from core.architecture_contract import derive_skill_contract_for_tool, enrich_contract_from_skill_context
from core.sqlite_logging import get_logger

logger = get_logger("proposal_generator")


class EvolutionProposalGenerator:
    """Generates improvement proposals using LLM."""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def generate_proposal(self, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate improvement proposal from analysis."""
        
        # Get service context from dependency checker
        service_context = self._build_service_context()
        
        # Format LLM issues and improvements
        llm_issues_text = self._format_llm_issues(analysis.get('llm_issues') or [])
        llm_improvements_text = self._format_llm_improvements(analysis.get('llm_improvements') or [])
        
        # Add context priorities if available
        context_priorities_text = ""
        if analysis.get('context_priorities'):
            context_priorities_text = "\n\nEXECUTION CONTEXT PRIORITIES (from recent failures):\n" + "\n".join(analysis['context_priorities'])
        
        # Limit code included in prompt based on health — HEALTHY tools don't need full code review
        category = analysis.get('code_quality_category', 'UNKNOWN')
        if category in ('WEAK', 'NEEDS_IMPROVEMENT'):
            code_section = f"\nCurrent Code:\n```python\n{analysis['current_code'][:4000]}\n```"
        elif analysis.get('user_prompt'):
            code_section = f"\nCurrent Code (truncated):\n```python\n{analysis['current_code'][:2000]}\n```"
        else:
            code_section = ""  # HEALTHY with no user prompt — skip full code

        prompt = f"""Analyze this tool and propose ONLY necessary improvements.

Tool: {analysis['tool_name']}
Health Score: {analysis['health_score']:.1f}/100
Code Quality: {category}
Success Rate: {analysis['success_rate']:.1%}
{f"User Request: {analysis['user_prompt']}" if analysis.get('user_prompt') else ""}

LLM CODE ANALYSIS:
{llm_issues_text}

SUGGESTED IMPROVEMENTS:
{llm_improvements_text}
{context_priorities_text}
{code_section}

AVAILABLE SERVICES (use self.services.X only): {service_context}

RULES: Fix ONE issue. Prioritize: execution errors > HIGH bugs > WEAK code > improvements. If HEALTHY with no issues → skip.

Generate improvement proposal as JSON:
{{
  "action_type": "fix_bug|add_capability|improve_logic|refactor",
  "description": "One specific improvement",
  "target_functions": ["_handle_method_name"],
  "changes": ["Change 1"],
  "expected_improvement": "Outcome",
  "confidence": 0.0-1.0,
  "risk_level": 0.0-1.0,
  "justification": "Why necessary",
  "network_only": false,
  "required_services": [],
  "required_libraries": [],
  "new_service_specs": {{}}
}}

target_functions: list the exact method names that need changing (e.g. ["_handle_search"]). Leave empty [] only for add_capability.
If NO issues found: {{"skip": true, "reason": "Tool is working correctly"}}
Return ONLY valid JSON."""
        
        try:
            response = self.llm._call_llm(prompt, temperature=0.2, max_tokens=None, expect_json=True)
            proposal = self._parse_response(response)
            
            if not proposal:
                logger.warning(f"Failed to parse proposal from LLM. Raw response (first 500): {str(response)[:500]}")
                return None
            
            # Check if should skip
            if proposal.get('skip'):
                logger.info(f"Skipping evolution: {proposal.get('reason')}")
                return None
            
            # Validate proposal structure
            if not self._validate_proposal(proposal):
                logger.warning(f"Invalid proposal structure. Keys present: {list(proposal.keys())}")
                return None
            
            # Set default action_type if missing (for backward compatibility)
            if 'action_type' not in proposal:
                # Infer from description
                desc_lower = proposal.get('description', '').lower()
                if 'add' in desc_lower and ('capability' in desc_lower or 'feature' in desc_lower or 'operation' in desc_lower):
                    proposal['action_type'] = 'add_capability'
                elif 'fix' in desc_lower or 'bug' in desc_lower or 'broken' in desc_lower:
                    proposal['action_type'] = 'fix_bug'
                elif 'refactor' in desc_lower or 'restructure' in desc_lower:
                    proposal['action_type'] = 'refactor'
                else:
                    proposal['action_type'] = 'improve_logic'
                logger.info(f"Inferred action_type: {proposal['action_type']}")
            
            # Calculate confidence if not provided
            if 'confidence' not in proposal or proposal['confidence'] < 0.5:
                proposal['confidence'] = self._calculate_confidence(proposal, analysis)
            
            # Add analysis context
            proposal['analysis'] = analysis
            proposal["tool_spec"] = enrich_contract_from_skill_context(
                {
                    "name": analysis.get("tool_name"),
                    "domain": "general",
                    "outputs": [],
                    "artifact_types": [],
                    "code": analysis.get("current_code", ""),
                },
                derive_skill_contract_for_tool(analysis.get("tool_name", "")),
            )
            
            # Add service descriptions for UI
            if 'required_services' in proposal:
                proposal['service_descriptions'] = self._get_service_descriptions(
                    proposal['required_services']
                )
            
            return proposal
            
        except Exception as e:
            import traceback
            logger.error(f"Proposal generation error: {e}\n{traceback.format_exc()}")
            return None
    
    def _build_service_context(self) -> str:
        """Build service context from dependency checker (matches spec_generator pattern)."""
        from core.dependency_checker import DependencyChecker
        
        service_specs = {
            'storage': 'save(id, data), get(id), list(limit=10), update(id, updates), delete(id)',
            'llm': 'generate(prompt, temperature=0.3, max_tokens=500)',
            'http': 'get(url), post(url, data), put(url, data), delete(url)',
            'fs': 'read(path), write(path, content), exists(path), list_dir(path)',
            'json': 'parse(text), stringify(data), query(data, path)',
            'shell': 'execute(command, args=[])',
            'logging': 'info(msg), warning(msg), error(msg), debug(msg)',
            'time': 'now_utc(), now_local(), now_utc_iso(), now_local_iso()',
            'ids': 'generate(prefix=""), uuid()',
            'browser': 'open_browser(), navigate(url), get_page_text(), find_element(by, value), take_screenshot(filename), close()'
        }
        
        services_list = []
        for name, methods in service_specs.items():
            if name in DependencyChecker.AVAILABLE_SERVICES:
                services_list.append(f"- self.services.{name}: {methods}")
        
        return "\n".join(services_list)
    
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
        required = ['description', 'changes', 'expected_improvement', 'justification']
        has_required = all(field in proposal for field in required)
        if not has_required:
            return False

        # Ensure changes is a non-None list
        if not isinstance(proposal.get('changes'), list):
            proposal['changes'] = []

        # Validate action_type if present
        if 'action_type' in proposal:
            valid_actions = ['fix_bug', 'add_capability', 'improve_logic', 'refactor']
            if proposal.get('action_type') not in valid_actions:
                return False

        # Validate new_service_specs structure if present — guard against null
        new_service_specs = proposal.get('new_service_specs')
        if new_service_specs is None:
            proposal['new_service_specs'] = {}
        elif isinstance(new_service_specs, dict):
            for svc_name, svc_spec in new_service_specs.items():
                if not isinstance(svc_spec, dict):
                    return False
                if 'description' not in svc_spec or 'methods' not in svc_spec:
                    return False
        else:
            proposal['new_service_specs'] = {}

        # Guard other list/dict fields that LLM may return as null
        for field in ('required_services', 'required_libraries'):
            if not isinstance(proposal.get(field), list):
                proposal[field] = []

        return True
    
    def _calculate_confidence(self, proposal: Dict, analysis: Dict) -> float:
        """Calculate confidence score for proposal."""
        confidence = 1.0

        # Low if no specific changes
        changes = proposal.get('changes') or []
        if not changes or len(changes) < 2:
            confidence -= 0.3

        # Low if vague description
        if len(proposal.get('description', '').split()) < 5:
            confidence -= 0.2

        # Low if health score is very bad (might need redesign)
        if analysis.get('health_score', 0) < 20:
            confidence -= 0.2

        # Low if no user prompt and no clear issues
        if not analysis.get('user_prompt') and len(analysis.get('issues') or []) == 0:
            confidence -= 0.3

        return max(0.0, confidence)
    
    def _parse_response(self, response: str) -> Optional[Dict]:
        """Parse LLM response to extract proposal."""
        if not response:
            return None
        try:
            return json.loads(response)
        except Exception:
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                return json.loads(response[start:end].strip())
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                return json.loads(response[start:end].strip())
            return None
    
    def _format_llm_issues(self, issues: list) -> str:
        """Format LLM issues for prompt."""
        if not issues:
            return "No critical issues found."
        
        formatted = []
        for issue in issues:
            if isinstance(issue, dict):
                severity = issue.get('severity', 'MEDIUM')
                category = issue.get('category', 'Unknown')
                desc = issue.get('description', '')
                formatted.append(f"[{severity}] {category}: {desc}")
        
        return "\n".join(formatted) if formatted else "No critical issues found."
    
    def _format_llm_improvements(self, improvements: list) -> str:
        """Format LLM improvements for prompt."""
        if not improvements:
            return "No specific improvements suggested."
        
        formatted = []
        for imp in improvements:
            if isinstance(imp, dict):
                priority = imp.get('priority', 'MEDIUM')
                imp_type = imp.get('type', 'Unknown')
                desc = imp.get('description', '')
                formatted.append(f"[{priority}] {imp_type}: {desc}")
        
        return "\n".join(formatted) if formatted else "No specific improvements suggested."
    
    def _get_service_descriptions(self, service_names: list) -> dict:
        """Get descriptions for required services."""
        descriptions = {
            'storage': 'Persistent key-value storage for tool data',
            'llm': 'LLM text generation for AI-powered features',
            'http': 'HTTP client for API calls and web requests',
            'fs': 'File system operations (read/write files)',
            'json': 'JSON parsing and manipulation',
            'shell': 'Execute shell commands',
            'logging': 'Structured logging for debugging',
            'time': 'Time and date utilities',
            'ids': 'Generate unique identifiers',
            'browser': 'Browser automation (Selenium-based)'
        }
        
        return {name: descriptions.get(name, 'Unknown service') for name in service_names}
