"""
Method Extractor - Extract individual methods/functions from Python files
"""
import ast
from typing import Dict, List, Optional

class MethodExtractor:
    def extract_methods(self, code: str) -> Dict[str, Dict]:
        """Extract all methods with their line ranges and code"""
        methods = {}
        
        try:
            tree = ast.parse(code)
            lines = code.split('\n')
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    start = node.lineno - 1
                    # Better fallback: find next function or end of file
                    if hasattr(node, 'end_lineno'):
                        end = node.end_lineno
                    else:
                        # Fallback: scan for next def or class
                        end = len(lines)
                        for i in range(start + 1, len(lines)):
                            if lines[i].strip().startswith('def ') or lines[i].strip().startswith('class '):
                                end = i
                                break
                    
                    method_code = '\n'.join(lines[start:end])
                    
                    methods[node.name] = {
                        'code': method_code,
                        'start_line': start,
                        'end_line': end,
                        'is_private': node.name.startswith('_'),
                        'args': [arg.arg for arg in node.args.args]
                    }
        except Exception as e:
            from core.logging_system import get_logger
            logger = get_logger("method_extractor")
            logger.error(f"Failed to extract methods: {e}")
        
        return methods
    
    def extract_imports(self, code: str) -> str:
        """Extract all import statements"""
        lines = code.split('\n')
        imports = []
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('import ') or stripped.startswith('from '):
                imports.append(line)
            elif imports and not stripped:
                continue
            elif imports:
                break
        
        return '\n'.join(imports)
    
    def extract_class_definition(self, code: str) -> Optional[str]:
        """Extract class definition line and __init__"""
        try:
            tree = ast.parse(code)
            lines = code.split('\n')
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    start = node.lineno - 1
                    
                    # Find __init__ if exists
                    init_end = start + 1
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                            if hasattr(item, 'end_lineno'):
                                init_end = item.end_lineno
                            else:
                                # Fallback: scan for next def
                                for i in range(item.lineno, len(lines)):
                                    if i > item.lineno and lines[i].strip().startswith('def '):
                                        init_end = i
                                        break
                                else:
                                    init_end = len(lines)
                            break
                    
                    return '\n'.join(lines[start:init_end])
        except Exception as e:
            from core.logging_system import get_logger
            logger = get_logger("method_extractor")
            logger.error(f"Failed to extract class definition: {e}")
        
        return None
    
    def get_method_dependencies(self, method_name: str, code: str) -> List[str]:
        """Find which other methods this method calls"""
        dependencies = []
        
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == method_name:
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            if isinstance(child.func, ast.Attribute):
                                if isinstance(child.func.value, ast.Name) and child.func.value.id == 'self':
                                    dependencies.append(child.func.attr)
        except:
            pass
        
        return dependencies
