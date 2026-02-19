"""
StepPlanner - Breaks tasks into logical incremental steps
"""
from typing import List, Dict
import re

class StepPlanner:
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    def plan_steps(self, analysis: Dict) -> tuple[List[str], str]:
        """Break task into logical steps and detect task type
        Returns: (steps, task_type) where task_type is 'add' or 'modify'
        """
        task_raw = analysis.get('suggestion', '')
        task = task_raw.lower()
        methods = analysis.get('methods_to_modify', [])
        
        # Detect if adding new methods or modifying existing
        is_add_task = any(keyword in task for keyword in ['add', 'create', 'new method'])
        task_type = 'add' if is_add_task else 'modify'
        
        # Multi-method tasks need breakdown to fit in token limits.
        # Keep only explicitly mentioned methods when the task is focused.
        if len(methods) > 1:
            explicit = self._extract_explicit_methods(task_raw, methods)
            if explicit:
                filtered = [m for m in methods if m in explicit]
                if filtered:
                    methods = filtered
            steps = [f"Modify {method}() method: {task_raw}" for method in methods]
            return (steps, task_type)
        
        # Complex tasks (long description) need breakdown
        if len(task.split()) > 20:
            prompt = self.llm_client._format_prompt(f"""Break this task into 2-3 steps.

Task: {task_raw}
Methods: {', '.join(methods) if methods else 'N/A'}

Output JSON array:
["Step 1: ...", "Step 2: ..."]

Keep steps atomic.""", expect_json=True)
            
            response = self.llm_client._call_llm(prompt, temperature=0.3, max_tokens=256, expect_json=True)
            if response:
                steps = self.llm_client._extract_json(response)
                if isinstance(steps, list) and len(steps) > 1:
                    return (steps, task_type)
        
        # Simple tasks - single shot
        return ([analysis.get('suggestion', '')], task_type)

    def _extract_explicit_methods(self, task: str, candidates: List[str] = None) -> List[str]:
        patterns = [
            r"\bmodify\s+([_a-zA-Z][\w_]*)\(\)",
            r"\bmodify\s+([_a-zA-Z][\w_]*)\s+method",
            r"\brefactor\s+([_a-zA-Z][\w_]*)\(\)",
            r"\brefactor\s+([_a-zA-Z][\w_]*)\s+method",
            r"\b([_a-zA-Z][\w_]*)\(\)",
        ]
        stopwords = {
            "to", "for", "with", "from", "into", "by", "and", "or",
            "the", "a", "an", "in", "on", "of", "at", "as", "method", "function"
        }
        candidate_set = set(candidates or [])
        found: List[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, task, re.IGNORECASE):
                name = match.group(1)
                if not name:
                    continue
                lowered = name.lower()
                if lowered in stopwords:
                    continue
                if candidate_set and name not in candidate_set:
                    continue
                if name not in found:
                    found.append(name)
        return found
