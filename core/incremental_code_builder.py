"""
IncrementalCodeBuilder - Accumulates code changes step by step with LLM merge
"""
import ast
from typing import Dict, List, Optional

class IncrementalCodeBuilder:
    def __init__(self, original_code: str, llm_client=None):
        self.original_code = original_code
        self.current_code = original_code
        self.steps_completed = []
        self.step_changes = []
        self.llm_client = llm_client
    
    def add_step(self, step_description: str, new_code: str):
        """Add a step's code changes"""
        self.steps_completed.append(step_description)
        self.step_changes.append({
            'step': step_description,
            'code': new_code
        })
    
    def merge_all_changes(self) -> Optional[str]:
        """Merge all step changes incrementally"""
        if not self.llm_client:
            if self.step_changes:
                return self.step_changes[-1]['code']
            return self.original_code
        
        if len(self.step_changes) == 0:
            return self.original_code
        
        if len(self.step_changes) == 1:
            return self.step_changes[0]['code']
        
        # Multiple steps - merge incrementally
        # Start with first step's result
        merged = self.step_changes[0]['code']
        
        # For each subsequent step, extract the changed method and integrate
        from core.method_extractor import MethodExtractor
        from core.code_integrator import CodeIntegrator
        extractor = MethodExtractor()
        integrator = CodeIntegrator()
        
        for i in range(1, len(self.step_changes)):
            step_code = self.step_changes[i]['code']
            
            # Extract methods from this step
            step_methods = extractor.extract_methods(step_code)
            merged_methods = extractor.extract_methods(merged)
            
            # Find which method changed in this step
            changed_methods = {}
            for method_name, method_info in step_methods.items():
                if method_name in merged_methods:
                    # Method exists - check if changed
                    if method_info['code'] != merged_methods[method_name]['code']:
                        changed_methods[method_name] = method_info['code']
                else:
                    # New method
                    changed_methods[method_name] = method_info['code']
            
            # Integrate changed methods into merged code
            if changed_methods:
                merged = integrator.integrate_methods(merged, changed_methods)
                if not self._is_structurally_valid_python(merged):
                    return None
        
        if not self._is_structurally_valid_python(merged):
            return None
        return merged

    def _is_structurally_valid_python(self, code: str) -> bool:
        """Fast structural gate to prevent propagating malformed merges."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not node.body:
                    return False
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    return False
        return True
    
    def _extract_code(self, response: str) -> Optional[str]:
        """Extract code from LLM response"""
        if '```python' in response:
            start = response.find('```python') + 9
            end = response.find('```', start)
            if end != -1:
                return response[start:end].strip()
        
        if '```' in response:
            start = response.find('```') + 3
            end = response.find('```', start)
            if end != -1:
                return response[start:end].strip()
        
        return None
    
    def get_complete_code(self) -> str:
        """Get final accumulated code"""
        return self.current_code
    
    def get_progress(self) -> Dict:
        """Get build progress"""
        return {
            'steps_completed': len(self.steps_completed),
            'current_size': len(self.current_code),
            'original_size': len(self.original_code)
        }
    
    def rollback_last_step(self):
        """Rollback last step if it failed"""
        if self.step_changes:
            self.step_changes.pop()
            self.steps_completed.pop()
