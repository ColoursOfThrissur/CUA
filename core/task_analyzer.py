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
            blocked_tasks
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
        blocked_tasks: List[str]
    ) -> str:
        """Build analysis prompt for LLM"""
        
        if focus:
            return f"""User request: "{focus}"

## Available Tools:
{json.dumps(tools_info, indent=2)}

## Existing Tests:
{json.dumps(test_files, indent=2)}

## Your Task:
Interpret the user's request and determine the best approach.

## Output Format (JSON only):
{{
  "task_type": "create_test|modify_tool|create_tool|fix_bug",
  "target_file": "tools/exact_name.py",
  "test_file": "tests/unit/test_name.py",
  "description": "what you'll do and why",
  "priority": "high"
}}

Respond with ONLY valid JSON:"""
        
        # Autonomous mode
        blocked_section = ""
        if blocked_tasks:
            blocked_section = f"\n\n## DO NOT SUGGEST (already done or failed 3+ times):\n{json.dumps(blocked_tasks, indent=2)}\n\nCRITICAL: If you see a task in Previous Iterations with result='success', DO NOT suggest it again!\nCRITICAL: If you see the same task repeated 3+ times, DO NOT suggest it again!"
        
        return f"""Analyze this codebase and decide what improvement would add the most value.

## Available Tool Classes:
{json.dumps(tools_info, indent=2)}

## Existing Tests:
{json.dumps(test_files, indent=2)}

## Recent Failures (avoid these):
{json.dumps(failed_suggestions[-5:], indent=2) if failed_suggestions else 'None'}

## Previous Iterations:
{json.dumps(iteration_history[-5:], indent=2) if iteration_history else 'None - First iteration'}{blocked_section}

## Your Task:
You are an autonomous agent. Analyze the codebase and decide:
- What would improve system reliability?
- What would add valuable functionality?
- What issues need attention?

IMPORTANT RULES:
1. Look at Previous Iterations - if a task has result='success', DO NOT suggest it again
2. If you see the same task repeated multiple times, suggest something DIFFERENT
3. Do NOT suggest async/await features (too complex for this LLM)
4. Do NOT suggest threading/multiprocessing
5. Focus on simple, practical improvements
6. Prefer bug fixes and code quality over new features

## Output Format (JSON only):
{{
  "task_type": "create_test|fix_bug|add_feature|improve_code",
  "target_file": "exact/path/from/lists/above.py",
  "test_file": "tests/unit/test_name.py",
  "description": "specific task and why it matters",
  "priority": "low|medium|high"
}}

Respond with ONLY valid JSON:"""
    
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
