"""
StepPlanner - Breaks tasks into logical incremental steps
"""
from typing import List, Dict

class StepPlanner:
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    def plan_steps(self, analysis: Dict) -> tuple[List[str], str]:
        """Break task into logical steps and detect task type
        Returns: (steps, task_type) where task_type is 'add' or 'modify'
        """
        task = analysis.get('suggestion', '').lower()
        methods = analysis.get('methods_to_modify', [])
        
        # Detect if adding new methods or modifying existing
        is_add_task = any(keyword in task for keyword in ['add', 'create', 'new method'])
        task_type = 'add' if is_add_task else 'modify'
        
        # Multi-method tasks need breakdown to fit in token limits
        if len(methods) > 1:
            steps = [f"Modify {method}() method: {task}" for method in methods]
            return (steps, task_type)
        
        # Complex tasks (long description) need breakdown
        if len(task.split()) > 20:
            prompt = self.llm_client._format_prompt(f"""Break this task into 2-3 steps.

Task: {task}
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
