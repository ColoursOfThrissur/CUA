"""
AST Validation Layer - Verify proposals against actual code structure
"""
import ast
from pathlib import Path
from typing import List, Tuple

class ASTValidator:
    def validate_proposal(self, proposal: dict, enriched_data: dict = None) -> Tuple[bool, str]:
        """Validate proposal against actual file AST"""
        target_file = proposal.get('target_file')
        methods_affected = proposal.get('methods_affected', [])
        proposal_type = proposal.get('proposal_type', '')
        
        if not target_file or not methods_affected:
            return True, "No validation needed"
        
        try:
            with open(target_file) as f:
                tree = ast.parse(f.read())
            
            # Extract actual method names
            actual_methods = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    actual_methods.add(node.name)
            
            # For refactoring: only validate if enriched_data provides method list
            if proposal_type == 'structural_upgrade' and enriched_data:
                # Use enriched data's method list if available
                if 'all_methods' in enriched_data:
                    available_methods = enriched_data['all_methods']
                    for method in methods_affected:
                        if method not in available_methods and method not in actual_methods:
                            return False, f"Method '{method}' not found in {target_file}"
                    return True, "Validation passed"
            
            # Standard validation: methods must exist
            for method in methods_affected:
                if method not in actual_methods:
                    return False, f"Method '{method}' not found in {target_file}"
            
            # Validate proposed helper name not already used
            description = proposal.get('description', '')
            if '_' in description:
                # Extract proposed helper name
                import re
                helper_match = re.search(r'`(_[a-z_]+)`', description)
                if helper_match:
                    helper_name = helper_match.group(1)
                    if helper_name in actual_methods:
                        return False, f"Helper name '{helper_name}' already exists"
            
            # Validate methods share duplication if enriched data available
            if enriched_data and 'duplicate_blocks' in enriched_data:
                dup_methods = set()
                for block in enriched_data['duplicate_blocks']:
                    dup_methods.update(block.get('methods', []))
                
                # Skip validation if no duplication data
                if dup_methods:
                    for method in methods_affected:
                        if method not in dup_methods:
                            return False, f"Method '{method}' not in duplication cluster"
            
            return True, "Validation passed"
        
        except Exception as e:
            return False, f"Validation error: {e}"
