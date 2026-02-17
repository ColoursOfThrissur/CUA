"""
Task Analyzer - Analyzes codebase and determines next improvement task
"""
import json
import re
from typing import Optional, Dict, List
from pathlib import Path

class TaskAnalyzer:
    def __init__(self, llm_client, system_analyzer, llm_logger):
        self.llm_client = llm_client
        self.analyzer = system_analyzer
        self.llm_logger = llm_logger
        self.static_analyzer = None
        
        # Try to import static analyzer
        try:
            from tools.static_analyzer import StaticAnalyzer
            self.static_analyzer = StaticAnalyzer()
        except ImportError:
            pass
    
    def analyze_and_propose_task(
        self, 
        focus: Optional[str] = None,
        failed_suggestions: List[str] = None,
        iteration_history: List[Dict] = None
    ) -> Optional[Dict]:
        """
        Analyze system and propose next task
        Returns: {
            'issue': str,
            'suggestion': str,
            'priority': str,
            'files_affected': [str],
            'target_tool': Optional[str],
            'user_override': bool
        }
        """
        context = self.analyzer.get_codebase_context()
        test_files = context['test_coverage']['test_files']
        
        # Build tool information with capabilities
        tools_info = self._get_tools_info(test_files)
        
        # Get static analysis issues if available
        static_issues = []
        if self.static_analyzer:
            try:
                static_issues = self.static_analyzer.get_top_issues(max_issues=3)
            except Exception:
                pass
        
        # Detect repeated suggestions
        repeated_count = self._count_repeated_tasks(iteration_history or [])
        blocked_tasks = self._extract_blocked_tasks(iteration_history or [])
        
        # Build prompt
        prompt_text = self._build_analysis_prompt(
            tools_info, 
            test_files, 
            focus,
            failed_suggestions or [],
            iteration_history or [],
            blocked_tasks,
            static_issues
        )
        
        prompt = self.llm_client._format_prompt(prompt_text)
        
        # Increase temperature if stuck in loop
        temperature = 0.7 if repeated_count >= 3 else 0.3
        
        try:
            response = self.llm_client._call_llm(prompt, temperature=temperature)
            
            self.llm_logger.log_interaction(
                prompt=prompt,
                response=response or "<empty>",
                metadata={"phase": "analysis", "temperature": temperature, "focus": focus, "repeated_count": repeated_count}
            )
            
            if not response:
                return None
            
            # Extract and validate JSON
            analysis = self.llm_client._extract_json(response)
            if not analysis or 'target_file' not in analysis:
                return None
            
            # ENFORCE blocked files - reject if LLM suggests blocked file
            target_file = analysis.get('target_file', '')
            if blocked_tasks:
                # Check exact file match
                for blocked in blocked_tasks:
                    # Extract file path from blocked string
                    if '(' in blocked:
                        blocked_file = blocked.split('(')[0].strip()
                    else:
                        blocked_file = blocked.strip()
                    
                    if target_file == blocked_file:
                        # LLM ignored block - force different file
                        available_files = [t['file'] for t in tools_info if t['file'] != target_file]
                        if available_files:
                            analysis['target_file'] = available_files[0]
                            analysis['description'] = f"Review code quality in {available_files[0]}"
                            self.llm_logger.log_interaction(
                                prompt="blocked_file_override",
                                response=f"Redirected from {target_file} to {available_files[0]}",
                                metadata={"phase": "analysis", "blocked": blocked_file}
                            )
                        break
            
            # Interpret task and build result
            return self._interpret_task(analysis, focus)
            
        except Exception as e:
            self.llm_logger.log_error(str(e), {"phase": "analysis", "focus": focus})
            return None
    
    def _get_tools_info(self, test_files: List[str]) -> List[Dict]:
        """Extract tool information with class names and operations"""
        tools_info = []
        tools_dir = self.analyzer.repo_path / "tools"
        
        if not tools_dir.exists():
            return tools_info
        
        for tool_file in tools_dir.glob("*.py"):
            if tool_file.name.startswith("_"):
                continue
            
            content = self.analyzer.get_file_content(f"tools/{tool_file.name}")
            is_tool_class = content and 'class ' in content and 'def execute(' in content
            
            if not is_tool_class:
                continue
            
            has_test = f"test_{tool_file.stem}.py" in test_files
            
            # Extract class name
            class_match = re.search(r'class (\w+)', content)
            class_name = class_match.group(1) if class_match else "Unknown"
            
            # Extract operations - look for if operation == "execute" pattern
            ops = re.findall(r'operation\s*==\s*["\']([\w_]+)["\']', content)
            if not ops:
                # Fallback: dict-style "operation":
                ops = re.findall(r'["\']([\w_]+)["\']\s*:', content)
            operations = list(set(ops[:5]))
            
            tools_info.append({
                "file": f"tools/{tool_file.name}",
                "class": class_name,
                "operations": operations,
                "has_test": has_test
            })
        
        return tools_info
    
    def _count_repeated_tasks(self, iteration_history: List[Dict]) -> int:
        """Count how many times the same file was targeted recently"""
        if len(iteration_history) < 2:
            return 0
        
        recent_files = [h.get('file', '') for h in iteration_history[-5:]]
        if not recent_files:
            return 0
        
        # Count most common file
        from collections import Counter
        counts = Counter(recent_files)
        return max(counts.values()) if counts else 0
    
    def _extract_blocked_tasks(self, iteration_history: List[Dict]) -> List[str]:
        """Extract files that succeeded or were repeated 3+ times"""
        blocked = []
        file_counts = {}
        
        for h in iteration_history:
            file = h.get('file', '')
            result = h.get('result', '')
            
            # Block successful files
            if result == 'success' and file:
                blocked.append(f"{file} (already succeeded)")
            
            # Count file repetitions
            file_counts[file] = file_counts.get(file, 0) + 1
        
        # Block files repeated 3+ times
        for file, count in file_counts.items():
            if count >= 3 and file:
                blocked.append(f"{file} (failed {count} times - too complex for LLM)")
        
        return list(set(blocked))
    
    def _build_analysis_prompt(
        self,
        tools_info: List[Dict],
        test_files: List[str],
        focus: Optional[str],
        failed_suggestions: List[str],
        iteration_history: List[Dict],
        blocked_tasks: List[str],
        static_issues: List[Dict] = None
    ) -> str:
        """Build analysis prompt for LLM with code snippets"""
        
        # Format static issues if available
        issues_section = ""
        if static_issues:
            issues_section = "\n\n## Concrete Issues Found by Static Analysis:\n"
            for i, issue in enumerate(static_issues, 1):
                issues_section += f"{i}. **{issue['file']}:{issue['line']}** [{issue['severity'].upper()}]\n"
                issues_section += f"   - {issue['code']}: {issue['message']}\n"
        
        if focus:
            # User-directed mode - show code snippets
            code_snippets = self._get_code_snippets(tools_info)
            return f"""User request: "{focus}"

## Available Tools with Code Preview:
{code_snippets}{issues_section}

## Existing Tests:
{json.dumps(test_files, indent=2)}

## Your Task:
Interpret the user's request and determine the best approach.
Look at the code snippets and static analysis issues to identify SPECIFIC problems:
- Missing error handling
- Hardcoded values that should be configurable
- Security vulnerabilities (SQL injection, path traversal, etc.)
- Performance issues (inefficient loops, memory leaks)
- Missing validation

## Output Format (JSON only):
{{
  "task_type": "create_test|modify_tool|create_tool|fix_bug",
  "target_file": "tools/exact_name.py",
  "test_file": "tests/unit/test_name.py",
  "description": "SPECIFIC issue found and how to fix it",
  "priority": "high"
}}

Respond with ONLY valid JSON:"""
        
        # Autonomous mode with code analysis
        blocked_section = ""
        if blocked_tasks:
            blocked_section = f"\n\n## DO NOT SUGGEST (already done or failed 3+ times):\n{json.dumps(blocked_tasks, indent=2)}\n\nCRITICAL: If you see a task in Previous Iterations with result='success', DO NOT suggest it again!\nCRITICAL: If you see the same task repeated 3+ times, DO NOT suggest it again!"
        
        code_snippets = self._get_code_snippets(tools_info)
        
        return f"""Analyze this codebase and decide what improvement would add the most value.

## Available Tool Classes with Code Preview:
{code_snippets}{issues_section}

## Existing Tests:
{json.dumps(test_files, indent=2)}

## Recent Failures (avoid these):
{json.dumps(failed_suggestions[-5:], indent=2) if failed_suggestions else 'None'}

## Previous Iterations:
{json.dumps(iteration_history[-5:], indent=2) if iteration_history else 'None - First iteration'}{blocked_section}

## Your Task:
Analyze the CODE SNIPPETS and STATIC ANALYSIS ISSUES above to identify SPECIFIC problems:
1. **PRIORITY**: Fix issues found by static analysis first (concrete, actionable)
2. Security vulnerabilities (SQL injection, XSS, path traversal, SSRF)
3. Missing error handling or validation
4. Hardcoded values that should be in config
5. Performance issues (inefficient algorithms, memory leaks)
6. Code quality issues (duplicated code, complex logic)

IMPORTANT RULES:
1. Look at Previous Iterations - if a task has result='success', DO NOT suggest it again
2. If you see the same task repeated multiple times, suggest something DIFFERENT
3. Be SPECIFIC - mention the exact issue you found in the code
4. Do NOT suggest async/await features (too complex)
5. Do NOT suggest threading/multiprocessing
6. Focus on simple, practical improvements

## Output Format (JSON only):
{{
  "task_type": "fix_bug|improve_code|add_validation",
  "target_file": "exact/path/from/lists/above.py",
  "test_file": "tests/unit/test_name.py",
  "description": "SPECIFIC issue: [describe exact problem in code] - Fix: [how to fix it]",
  "priority": "low|medium|high"
}}

Respond with ONLY valid JSON:"""
    
    def _get_code_snippets(self, tools_info: List[Dict]) -> str:
        """Get code snippets from tools for LLM analysis"""
        snippets = []
        
        for tool in tools_info:
            file_path = tool['file']
            content = self.analyzer.get_file_content(file_path)
            
            if not content:
                continue
            
            # Extract key methods (first 30 lines of each class)
            lines = content.split('\n')
            class_start = None
            
            for i, line in enumerate(lines):
                if 'class ' in line:
                    class_start = i
                    break
            
            if class_start is not None:
                # Get first 30 lines of class
                snippet_lines = lines[class_start:min(class_start + 30, len(lines))]
                snippet = '\n'.join(snippet_lines)
                
                snippets.append(f"""### {file_path}
```python
{snippet}
... (truncated)
```
""")
        
        return '\n'.join(snippets) if snippets else "No code available"
    
    def _interpret_task(self, analysis: Dict, focus: Optional[str]) -> Optional[Dict]:
        """Interpret LLM response and determine files to modify"""
        
        target = analysis.get('target_file')
        task_type = analysis.get('task_type', 'create_test')
        
        # Validate target exists
        if not (self.analyzer.repo_path / target).exists():
            return None
        
        result = {
            "issue": analysis.get('description', focus or 'Improvement needed'),
            "suggestion": analysis.get('description', focus or 'Improvement needed'),
            "priority": analysis.get('priority', 'high' if focus else 'medium'),
            "user_override": bool(focus)
        }
        
        # Interpret task intent
        description_lower = analysis.get('description', '').lower()
        mentions_test = any(word in description_lower for word in ['test', 'testing', 'coverage'])
        has_test_file = bool(analysis.get('test_file'))
        
        if task_type == 'create_test':
            # Creating new test file
            test_file = analysis.get('test_file', f"tests/unit/test_{target.split('/')[-1]}")
            result['files_affected'] = [test_file]
            result['target_tool'] = target
        elif task_type in ['add_feature', 'improve_code'] and mentions_test and not has_test_file:
            # Only create test if explicitly about testing AND no test_file provided
            test_file = f"tests/unit/test_{target.split('/')[-1]}"
            result['files_affected'] = [test_file]
            result['target_tool'] = target
        elif task_type in ['modify_tool', 'fix_bug', 'create_tool', 'add_feature', 'improve_code']:
            # Modifying/creating tool file - this is the default for add_feature
            result['files_affected'] = [target]
        else:
            # Default: modify target
            result['files_affected'] = [target]
        
        return result
