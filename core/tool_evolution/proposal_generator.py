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

        # Fix 7: skip if the last successful proposal for this tool had the same
        # description or same target_functions — prevents the same proposal every cycle.
        tool_name = analysis.get('tool_name', '')
        if not analysis.get('user_prompt') and self._is_duplicate_proposal(tool_name, analysis):
            logger.info(f"Skipping duplicate proposal for {tool_name} — same as last cycle")
            return None

        # Get service context from dependency checker
        service_context = self._build_service_context()
        
        # Format LLM issues and improvements
        llm_issues_text = self._format_llm_issues(analysis.get('llm_issues') or [])
        llm_improvements_text = self._format_llm_improvements(analysis.get('llm_improvements') or [])
        
        # Add context priorities if available
        context_priorities_text = ""
        if analysis.get('context_priorities'):
            context_priorities_text = "\n\nEXECUTION CONTEXT PRIORITIES (from recent failures):\n" + "\n".join(analysis['context_priorities'])
        
        # Always include code — LLM cannot propose targeted fixes without seeing what it's changing
        category = analysis.get('code_quality_category', 'UNKNOWN')
        user_prompt = analysis.get('user_prompt', '')
        code_section = f"\nCurrent Code:\n```python\n{analysis.get('current_code', '')[:6000]}\n```"

        # When user gave explicit instructions, make them the primary directive
        if user_prompt:
            rules_line = "RULES: The User Request above is your PRIMARY directive — implement exactly what was asked. Ignore health score. Populate target_functions with every method that needs changing."
        else:
            rules_line = "RULES: Fix ONE issue. Prioritize: execution errors > HIGH bugs > WEAK code > improvements. If HEALTHY with no issues → skip."

        # Build structured tool context for LLM
        tool_structure = self._extract_tool_structure(analysis.get('current_code', ''))

        # Inject persisted constraints for this tool (from EvolutionConstraintMemory)
        constraint_block = analysis.get('constraint_block', '')
        constraint_section = f"\n{constraint_block}\n" if constraint_block else ""

        prompt = f"""Analyze this tool and propose ONLY necessary improvements.

Tool: {analysis['tool_name']}
Health Score: {analysis['health_score']:.1f}/100
Code Quality: {category}
Success Rate: {analysis['success_rate']:.1%}
{f"User Request: {user_prompt}" if user_prompt else ""}
{constraint_section}
Tool structure (registered capabilities, methods, services):
{tool_structure}

LLM CODE ANALYSIS:
{llm_issues_text}

SUGGESTED IMPROVEMENTS:
{llm_improvements_text}
{context_priorities_text}
{code_section}

AVAILABLE SERVICES (use self.services.X only): {service_context}

{rules_line}

Generate improvement proposal as JSON:
{{
  "action_type": "fix_bug|add_capability|improve_logic|refactor",
  "description": "One specific improvement",
  "target_functions": ["_handle_method_name"],
  "changes": ["Change 1"],
  "implementation_sketch": {{
    "_handle_method_name": [
      "1. Get param_x (type) from kwargs. Return error if missing.",
      "2. Call self.services.X.method() with param_x.",
      "3. Return {{'success': True, 'data': result}}."
    ]
  }},
  "expected_improvement": "Outcome",
  "confidence": 0.0-1.0,
  "risk_level": 0.0-1.0,
  "justification": "Why necessary",
  "network_only": false,
  "required_services": [],
  "required_libraries": [],
  "new_service_specs": {{}}
}}

target_functions: list the exact _handle_* method names that need changing (e.g. ["_handle_search"]). NEVER include 'execute', 'register_capabilities', or '__init__' — only _handle_* methods. Leave empty [] only for add_capability.
implementation_sketch: for EACH method in target_functions, provide numbered pseudocode steps describing exactly what the implementation should do. Rules for sketches:
- Use exact service API signatures: storage.save(id, data) takes TWO args, storage.get(id) takes ONE arg, storage.list(limit=N) returns a list
- SERVICE RETURN TYPES: llm.generate() returns a plain STRING (never a dict) — store it directly, do NOT check isinstance(result, dict); storage.get() returns a dict or None; storage.list() returns a list of dicts; http.get/post() returns a dict with 'status' and 'body' keys
- For filtering/searching: specify the exact field to check and the comparison (e.g. 'keep items where query.lower() in item.get("description","").lower()')
- Every return statement must include 'success' key: return {{'success': True, 'data': ...}} or {{'success': False, 'error': '...'}}
- Use plain English, not Python. Max 6 steps per handler.
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

            # Record this proposal so next cycle can detect duplicates
            self._record_proposal(tool_name, proposal)

            return proposal
            
        except Exception as e:
            import traceback
            logger.error(f"Proposal generation error: {e}\n{traceback.format_exc()}")
            return None
    
    def _is_duplicate_proposal(self, tool_name: str, analysis: Dict) -> bool:
        """Return True if the last evolution for this tool had the same description
        or same target_functions, indicating the LLM is stuck in a loop.
        """
        try:
            from core.cua_db import get_conn
            with get_conn() as conn:
                row = conn.execute(
                    """SELECT ea.content FROM evolution_artifacts ea
                       JOIN evolution_runs er ON ea.evolution_id = er.id
                       WHERE er.tool_name = ? AND ea.artifact_type = 'proposal'
                       ORDER BY ea.created_at DESC LIMIT 1""",
                    (tool_name,)
                ).fetchone()
            if not row:
                return False
            last = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            if not isinstance(last, dict):
                return False
            last_desc = (last.get('description') or '').strip().lower()
            last_targets = sorted(last.get('target_functions') or [])
            # Current analysis doesn't have a proposal yet — compare against LLM issues
            # to detect if the situation is identical (same issues = same proposal likely)
            current_issues = [i.get('description', '') for i in (analysis.get('llm_issues') or [])]
            last_issues_key = last.get('_issues_key', '')
            current_issues_key = '|'.join(sorted(current_issues))[:200]
            if last_issues_key and last_issues_key == current_issues_key:
                logger.debug(f"Duplicate proposal detected for {tool_name}: same issues fingerprint")
                return True
            return False
        except Exception:
            return False

    def _record_proposal(self, tool_name: str, proposal: Dict) -> None:
        """Stamp the proposal with an issues fingerprint for next-cycle dedup."""
        try:
            analysis = proposal.get('analysis') or {}
            issues = [i.get('description', '') for i in (analysis.get('llm_issues') or [])]
            proposal['_issues_key'] = '|'.join(sorted(issues))[:200]
        except Exception:
            pass

    def _extract_tool_structure(self, code: str) -> str:
        """Extract registered capabilities, methods, and services used via AST."""
        import ast as _ast
        lines = []
        try:
            tree = _ast.parse(code)
            caps, methods, services_used = [], [], set()
            for node in _ast.walk(tree):
                if isinstance(node, _ast.FunctionDef):
                    if node.name not in ('__init__', 'execute', 'register_capabilities'):
                        methods.append(node.name)
                    for child in _ast.walk(node):
                        if isinstance(child, _ast.Attribute):
                            if (isinstance(child.value, _ast.Attribute)
                                    and isinstance(child.value.value, _ast.Name)
                                    and child.value.value.id == 'self'
                                    and child.value.attr == 'services'):
                                services_used.add(child.attr)
                if isinstance(node, _ast.Call):
                    func = node.func
                    if isinstance(func, _ast.Attribute) and func.attr == 'add_capability':
                        for kw in node.keywords:
                            if kw.arg == 'name' and isinstance(kw.value, _ast.Constant):
                                caps.append(kw.value.value)
            if caps:
                lines.append(f"Registered capabilities: {', '.join(caps)}")
            if methods:
                lines.append(f"Methods: {', '.join(methods[:20])}")
            if services_used:
                lines.append(f"Services used: {', '.join(sorted(services_used))}")
        except Exception:
            pass
        return '\n'.join(lines) if lines else 'Could not extract structure'

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
        services_list.append("NOTE: Do NOT use optional visualization libraries (graphviz, matplotlib, plotly). Use self.services.json or self.services.storage for data output.")
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

        # Ensure changes is a non-None list of strings
        if not isinstance(proposal.get('changes'), list):
            proposal['changes'] = []
        else:
            proposal['changes'] = [str(c) if not isinstance(c, str) else c for c in proposal['changes']]

        # Strip non-handler entries from target_functions — execute/register_capabilities
        # must never be targeted directly; the code generator only processes _handle_* methods
        _SKIP_TARGETS = {'execute', 'register_capabilities', '__init__'}
        if isinstance(proposal.get('target_functions'), list):
            proposal['target_functions'] = [
                f for f in proposal['target_functions']
                if f not in _SKIP_TARGETS
            ]

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
                # Normalize methods to list of strings
                svc_spec['methods'] = [str(m) for m in (svc_spec.get('methods') or [])]
        else:
            proposal['new_service_specs'] = {}

        # Guard other list/dict fields that LLM may return as null
        for field in ('required_services', 'required_libraries'):
            if not isinstance(proposal.get(field), list):
                proposal[field] = []

        # Normalize implementation_sketch — must be dict of {handler_name: [str, ...]}
        sketch = proposal.get('implementation_sketch')
        if not isinstance(sketch, dict):
            proposal['implementation_sketch'] = {}
        else:
            normalized_sketch = {}
            for fn, steps in sketch.items():
                if isinstance(steps, list):
                    normalized_sketch[fn] = [str(s) for s in steps if s]
                elif isinstance(steps, str) and steps:
                    # LLM returned a string instead of list — split on newlines
                    normalized_sketch[fn] = [s.strip() for s in steps.splitlines() if s.strip()]
            proposal['implementation_sketch'] = normalized_sketch

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
