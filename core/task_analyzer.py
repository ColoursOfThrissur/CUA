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
    
    def analyze_and_propose_tasks(
        self, 
        focus: Optional[str] = None,
        failed_suggestions: List[str] = None,
        iteration_history: List[Dict] = None
    ) -> List[Dict]:
        """
        Analyze system and propose multiple tasks (batch mode)
        Returns: List of task dicts
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
        
        # Build prompt for batch mode
        prompt_text = self._build_batch_analysis_prompt(
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
                metadata={"phase": "analysis_batch", "temperature": temperature, "focus": focus, "repeated_count": repeated_count}
            )
            
            if not response:
                return []
            
            # Extract JSON array
            tasks_raw = self.llm_client._extract_json(response)
            if not tasks_raw:
                return []
            
            # Handle both array and single object
            if isinstance(tasks_raw, list):
                tasks = tasks_raw
            else:
                tasks = [tasks_raw]
            
            # Validate and interpret each task
            result_tasks = []
            for task in tasks:
                if 'target_file' not in task:
                    continue
                
                # Check blocked files
                target_file = task.get('target_file', '')
                if self._is_blocked(target_file, blocked_tasks):
                    continue
                
                interpreted = self._interpret_task(task, focus)
                if interpreted:
                    result_tasks.append(interpreted)
            
            return result_tasks
            
        except Exception as e:
            self.llm_logger.log_error(str(e), {"phase": "analysis_batch", "focus": focus})
            return []
    
    def _is_blocked(self, target_file: str, blocked_tasks: List[str]) -> bool:
        """Check if file is blocked"""
        for blocked in blocked_tasks:
            if '(' in blocked:
                blocked_file = blocked.split('(')[0].strip()
            else:
                blocked_file = blocked.strip()
            if target_file == blocked_file:
                return True
        return False
    
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
    
    def _build_batch_analysis_prompt(
        self,
        tools_info: List[Dict],
        test_files: List[str],
        focus: Optional[str],
        failed_suggestions: List[str],
        iteration_history: List[Dict],
        blocked_tasks: List[str],
        static_issues: List[Dict] = None
    ) -> str:
        """Build batch analysis prompt requesting array of tasks"""
        
        # Format static issues if available
        issues_section = ""
        if static_issues:
            issues_section = "\n\n## Concrete Issues Found by Static Analysis:\n"
            for i, issue in enumerate(static_issues, 1):
                issues_section += f"{i}. **{issue['file']}:{issue['line']}** [{issue['severity'].upper()}]\n"
                issues_section += f"   - {issue['code']}: {issue['message']}\n"
        
        blocked_section = ""
        if blocked_tasks:
            blocked_section = f"\n\n## DO NOT SUGGEST (already done or failed 3+ times):\n{json.dumps(blocked_tasks, indent=2)}"
        
        code_snippets = self._get_code_snippets(tools_info)
        
        return f"""Analyze this codebase and identify 3-5 improvements ordered by priority.

## Available Tool Classes with Code Preview:
{code_snippets}{issues_section}

## Existing Tests:
{json.dumps(test_files, indent=2)}

## Previous Iterations:
{json.dumps(iteration_history[-5:], indent=2) if iteration_history else 'None - First iteration'}{blocked_section}

## Your Task:
Analyze the CODE SNIPPETS and STATIC ANALYSIS ISSUES to identify 3-5 SPECIFIC improvements:
1. **PRIORITY**: Fix issues found by static analysis first
2. Security vulnerabilities (SQL injection, XSS, path traversal, SSRF)
3. Missing error handling or validation
4. Code quality issues

IMPORTANT:
- Return an ARRAY of 3-5 tasks ordered by priority (highest first)
- Each task should target a DIFFERENT file
- Be SPECIFIC about the exact issue in the code
- Do NOT suggest tasks from blocked list

## Output Format (JSON array only):
[
  {{
    "task_type": "fix_bug|improve_code|add_validation",
    "target_file": "exact/path/from/lists/above.py",
    "test_file": "tests/unit/test_name.py",
    "description": "SPECIFIC issue and fix",
    "priority": "high|medium|low"
  }},
  {{
    "task_type": "fix_bug",
    "target_file": "different/file.py",
    "test_file": "tests/unit/test_file.py",
    "description": "Another specific issue",
    "priority": "high"
  }}
]

Respond with ONLY a valid JSON array:"""
    
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
        if not target:
            return None
        
        # Normalize path separators for current OS
        import os
        target = target.replace('/', os.sep).replace('\\', os.sep)
        
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
