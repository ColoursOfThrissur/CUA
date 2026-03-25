"""LLM-based tool health analyzer with sequential analysis."""
import json
from pathlib import Path
from typing import Dict, List
from planner.llm_client import LLMClient

class LLMToolHealthAnalyzer:
    """Analyze tool code quality using LLM with sequential reasoning."""
    
    def __init__(self):
        self.llm = LLMClient()
        self.tools_dir = Path(__file__).parent.parent / "tools" / "experimental"
        self.cache_file = Path(__file__).parent.parent / "data" / "llm_health_cache.json"
        self._load_cache()
    
    def _load_cache(self):
        """Load cached analysis results."""
        if self.cache_file.exists():
            self.cache = json.loads(self.cache_file.read_text())
        else:
            self.cache = {}
    
    def _save_cache(self):
        """Save analysis results to cache."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps(self.cache, indent=2))
    
    def analyze_tool(self, tool_name: str, force_refresh: bool = False) -> Dict:
        """Analyze tool with sequential LLM reasoning."""
        # Cache hit: valid only if entry is < 24 hours old
        if not force_refresh and tool_name in self.cache:
            entry = self.cache[tool_name]
            try:
                import time as _time
                cached_mtime = float(entry.get("timestamp", 0))
                if _time.time() - cached_mtime < 86400:  # 24h TTL
                    return entry
            except Exception:
                pass  # fall through to re-analyse
        
        # Find tool file - check experimental dir first, then registry
        tool_file = self.tools_dir / f"{tool_name}.py"
        if not tool_file.exists():
            try:
                from core.tool_registry_manager import ToolRegistryManager
                resolved = ToolRegistryManager().resolve_source_file(tool_name)
                if resolved and resolved.exists():
                    tool_file = resolved
            except Exception:
                pass
        if not tool_file.exists():
            return {"error": "Tool file not found", "issues": [], "improvements": [], "category": "UNKNOWN"}
        
        tool_code = tool_file.read_text()
        
        # Step 1: Understand tool purpose
        purpose = self._understand_purpose(tool_name, tool_code)
        
        # Step 2: Identify code issues
        issues = self._identify_issues(tool_name, tool_code, purpose)
        
        # Step 3: Suggest improvements
        improvements = self._suggest_improvements(tool_name, tool_code, purpose, issues)
        
        # Step 4: Determine health category
        category = self._categorize_health(issues, improvements)
        
        result = {
            "tool_name": tool_name,
            "purpose": purpose,
            "issues": issues,
            "improvements": improvements,
            "category": category,
            "timestamp": __import__('time').time()  # wall-clock seconds for TTL
        }
        
        self.cache[tool_name] = result
        self._save_cache()
        
        return result
    
    def _understand_purpose(self, tool_name: str, tool_code: str) -> str:
        """Step 1: Understand what the tool is supposed to do."""
        prompt = f"""Analyze this tool and explain its intended purpose in 2-3 sentences.

Tool: {tool_name}

Code:
{tool_code[:2000]}

What is this tool supposed to do? Be concise."""
        
        return self.llm.generate_response(prompt, [])
    
    def _identify_issues(self, tool_name: str, tool_code: str, purpose: str) -> List[Dict]:
        """Step 2: Identify code quality issues."""
        prompt = f"""You are a code quality analyzer. Find REAL issues in this tool code.

Tool: {tool_name}
Purpose: {purpose}

Code:
{tool_code}

IMPORTANT CONTEXT:
- Tools inherit from BaseTool which provides: name, capabilities, _capabilities, _performance_stats, add_capability(), get_capabilities(), execute_capability()
- Tools use self._cache (with underscore) for caching - this is CORRECT
- Tools use self.services.X to access services (llm, storage, http, fs, logging, etc.) - this is CORRECT
- Tools use parameterized SQL queries (?, params) - this is CORRECT and prevents SQL injection
- Error handling with try/except and returning error dicts is CORRECT
- Using .get() on dicts with defaults is CORRECT error handling

ONLY report issues if:
1. BUGS - Actual code errors you can verify (wrong variable name that doesn't exist, calling undefined method, missing required parameter)
2. ARCHITECTURE - Clear violations (using self.X instead of self.services.X for service calls, implementing service logic directly)
3. PERFORMANCE - Obvious inefficiencies (no caching when needed, N+1 queries, loading entire files unnecessarily)
4. MAINTAINABILITY - Significant problems (no error handling at all, extremely complex logic, missing critical validation)

DO NOT report:
- Issues that are already handled correctly in the code
- Style preferences or minor improvements
- Hypothetical edge cases that are already covered
- Things that could be better but work fine

Return ONLY a JSON array of REAL issues:
[
  {{"category": "BUGS", "severity": "HIGH", "description": "Calls undefined method self.foo() that doesn't exist", "line_hint": "line 120"}}
]

If no REAL issues found, return: []"""
        
        response = self.llm.generate_response(prompt, [])
        
        try:
            # Extract JSON from response
            start = response.find('[')
            end = response.rfind(']') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except:
            pass
        
        return []
    
    def _extract_tool_structure(self, tool_code: str) -> str:
        """Extract registered capabilities, operations, and services used from tool code."""
        import ast as _ast
        lines = []
        try:
            tree = _ast.parse(tool_code)
            # Registered capability names
            caps = []
            services_used = set()
            methods = []
            for node in _ast.walk(tree):
                if isinstance(node, _ast.FunctionDef):
                    if node.name not in ('__init__', 'execute', 'register_capabilities'):
                        methods.append(node.name)
                    # Detect self.services.X usage
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

    def _suggest_improvements(self, tool_name: str, tool_code: str, purpose: str, issues: List[Dict]) -> List[Dict]:
        """Step 3: Suggest functional improvements grounded in the actual tool code."""
        structure = self._extract_tool_structure(tool_code)
        prompt = f"""You are a feature enhancement advisor reviewing actual tool code.

Tool: {tool_name}
Purpose: {purpose}

Tool structure:
{structure}

Code:
{tool_code}

Existing issues already found: {json.dumps(issues)}

Based on the ACTUAL CODE and registered capabilities above, suggest specific improvements that are:
- Grounded in what this tool specifically does (not generic advice)
- Additions or enhancements to the existing operations this tool already has
- Realistic given the tool's current architecture and services it already uses

DO NOT suggest:
- Generic improvements like "add batch processing" unless the tool already has single-item operations that would clearly benefit
- Things already present in the code
- Fixes for the issues listed above (those are separate)

Return ONLY a JSON array (max 3 items):
[
  {{"type": "NEW_CAPABILITY", "priority": "HIGH", "description": "<specific to this tool's existing operations>"}}
]

If no meaningful improvements exist for this specific tool, return: []"""
        
        response = self.llm.generate_response(prompt, [])
        
        try:
            start = response.find('[')
            end = response.rfind(']') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except:
            pass
        
        return []
    
    def _categorize_health(self, issues: List[Dict], improvements: List[Dict]) -> str:
        """Step 4: Categorize tool health."""
        high_severity_bugs = sum(1 for i in issues if i.get('severity') == 'HIGH' and i.get('category') == 'BUGS')
        medium_high_issues = sum(1 for i in issues if i.get('severity') in ['HIGH', 'MEDIUM'])
        total_issues = len(issues)
        
        if high_severity_bugs >= 2 or medium_high_issues >= 4:
            return "WEAK"
        elif high_severity_bugs == 1 or total_issues >= 3:
            return "NEEDS_IMPROVEMENT"
        elif total_issues > 0:
            return "HEALTHY_WITH_MINOR_ISSUES"
        else:
            return "HEALTHY"
    
    def analyze_all_tools(self, force_refresh: bool = False) -> Dict[str, Dict]:
        """Analyze all tools in experimental directory."""
        results = {}
        
        if not self.tools_dir.exists():
            return results
        
        for tool_file in self.tools_dir.glob("*.py"):
            if tool_file.name.startswith("__"):
                continue
            
            tool_name = tool_file.stem
            try:
                results[tool_name] = self.analyze_tool(tool_name, force_refresh)
            except Exception as e:
                results[tool_name] = {
                    "tool_name": tool_name,
                    "error": str(e),
                    "category": "ERROR"
                }
        
        return results
    
    def get_weak_tools(self, force_refresh: bool = False) -> List[Dict]:
        """Get tools categorized as WEAK."""
        all_results = self.analyze_all_tools(force_refresh)
        return [
            result for result in all_results.values()
            if result.get('category') == 'WEAK'
        ]
    
    def get_summary(self, force_refresh: bool = False) -> Dict:
        """Get summary of all tool health."""
        all_results = self.analyze_all_tools(force_refresh)
        
        categories = {}
        for result in all_results.values():
            cat = result.get('category', 'UNKNOWN')
            categories[cat] = categories.get(cat, 0) + 1
        
        return {
            "total_tools": len(all_results),
            "categories": categories,
            "weak_tools": [r['tool_name'] for r in all_results.values() if r.get('category') == 'WEAK'],
            "needs_improvement": [r['tool_name'] for r in all_results.values() if r.get('category') == 'NEEDS_IMPROVEMENT']
        }
