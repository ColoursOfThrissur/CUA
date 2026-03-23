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
        
        # Read evolution context files for guidance
        evolution_context = self._read_evolution_context()
        
        # Get service context from dependency checker
        service_context = self._build_service_context()
        
        # Format LLM issues and improvements
        llm_issues_text = self._format_llm_issues(analysis.get('llm_issues', []))
        llm_improvements_text = self._format_llm_improvements(analysis.get('llm_improvements', []))
        
        # Add context priorities if available
        context_priorities_text = ""
        if analysis.get('context_priorities'):
            context_priorities_text = "\n\nEXECUTION CONTEXT PRIORITIES (from recent failures):\n" + "\n".join(analysis['context_priorities'])
        
        prompt = f"""Analyze this tool and propose ONLY necessary improvements.

Tool: {analysis['tool_name']}
Health Score: {analysis['health_score']:.1f}/100
Code Quality: {analysis.get('code_quality_category', 'UNKNOWN')}
Success Rate: {analysis['success_rate']:.1%}
{f"User Request: {analysis['user_prompt']}" if analysis.get('user_prompt') else ""}

LLM CODE ANALYSIS:
{llm_issues_text}

SUGGESTED IMPROVEMENTS:
{llm_improvements_text}
{context_priorities_text}

Current Code:
```python
{analysis['current_code']}
```

EVOLUTION GUIDELINES:
{evolution_context}

AVAILABLE SERVICES (tools must use self.services.X with EXACT signatures below):
{service_context}

WARNING: DO NOT add parameters to service methods that are not listed above. These are the ONLY allowed parameters.

CRITICAL DECISION RULES:
1. If EXECUTION_CONTEXT_PRIORITIES exist → PRIORITIZE THOSE FIRST (real failures from production)
2. If LLM_ISSUES contains HIGH severity bugs → FIX THEM (broken code, missing imports, undefined methods)
3. If code_quality_category is WEAK or NEEDS_IMPROVEMENT → FIX CODE ISSUES
4. If SUGGESTED_IMPROVEMENTS has HIGH priority items → ADD THE FIRST ONE (others will be done in next evolutions)
5. If SUGGESTED_IMPROVEMENTS has MEDIUM priority items (and no HIGH) → ADD THE FIRST ONE
6. If SUGGESTED_IMPROVEMENTS has LOW priority items (and no HIGH/MEDIUM) → ADD THE FIRST ONE
7. If only runtime issues (low success rate) but code is HEALTHY with no bugs and no improvements → SKIP
8. DO NOT fix "low success rate" by adding generic error handling if code already has proper error handling

IMPORTANT: Implement ONE improvement at a time. After approval, the next evolution will pick the next improvement.

IMPORTANT RULES:
- ONLY fix issues that are actually broken or causing failures
- DO NOT change working code for style preferences
- DO NOT add generic "improve error handling" if error handling already exists
- DO NOT refactor code that works correctly
- DO NOT add operations that don't exist in original tool UNLESS in SUGGESTED_IMPROVEMENTS
- Focus on HIGH severity bugs and clear architecture violations
- Ignore LOW severity style suggestions
- If code uses undefined methods, fix by using self.services.X instead
- If code has missing imports, fix by using self.services.X instead of direct imports
- DO NOT add parameters to service methods beyond what's listed in AVAILABLE SERVICES
- Validate all service calls match available service methods above EXACTLY
- Low success rate with HEALTHY code = external factors (network, browser), NOT code bugs

Generate improvement proposal as JSON:
{{
  "action_type": "fix_bug" | "add_capability" | "improve_logic" | "refactor",
  "description": "What specific issue to fix or feature to add (ONE improvement only)",
  "changes": ["Change 1", "Change 2"],
  "expected_improvement": "Expected outcome",
  "confidence": 0.0-1.0,
  "risk_level": 0.0-1.0,
  "justification": "Why this change is necessary",
  "network_only": true | false,  // Set true if tool ONLY works with network/browser (no local operations)
  "required_services": ["service_name"],
  "required_libraries": ["library_name"],
  "new_service_specs": {{
    "service_name": {{
      "description": "What this service should do",
      "methods": ["method1(param1)", "method2()"]
    }}
  }}
}}

ACTION_TYPE RULES:
- "fix_bug": Fix broken code (undefined methods, wrong service calls, missing imports) - MODIFY existing handlers
- "add_capability": Add NEW operation to tool (new handler method + register in capabilities) - CREATE new handler
- "improve_logic": Enhance existing handler logic (better error handling, validation) - MODIFY existing handlers
- "refactor": Restructure code for clarity/performance - MODIFY existing handlers

CRITICAL: Pick ONLY ONE improvement from SUGGESTED_IMPROVEMENTS (the highest priority one).
Other improvements will be implemented in subsequent evolutions after this one is approved.

NOTE: Only include required_services/required_libraries/new_service_specs if adding NEW features that need them.
For existing services, just use them - don't list in required_services.
For NEW services not in AVAILABLE SERVICES, specify in new_service_specs with description and methods needed.

If NO critical issues found AND no improvements suggested, return: {{"skip": true, "reason": "Tool is working correctly"}}

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
            logger.error(f"Proposal generation error: {e}")
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
        
        # Validate action_type if present
        if 'action_type' in proposal:
            valid_actions = ['fix_bug', 'add_capability', 'improve_logic', 'refactor']
            if proposal.get('action_type') not in valid_actions:
                return False
        
        # Validate new_service_specs structure if present
        if 'new_service_specs' in proposal:
            for svc_name, svc_spec in proposal['new_service_specs'].items():
                if not isinstance(svc_spec, dict):
                    return False
                if 'description' not in svc_spec or 'methods' not in svc_spec:
                    return False
        
        return has_required
    
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
