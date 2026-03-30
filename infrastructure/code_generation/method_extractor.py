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
                    if hasattr(node, 'end_lineno'):
                        end = node.end_lineno
                    else:
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
        except SyntaxError as e:
            from infrastructure.logging.logging_system import get_logger
            logger = get_logger("method_extractor")
            logger.error(f"Syntax error while extracting methods: {e}")
        except Exception as e:
            from infrastructure.logging.logging_system import get_logger
            logger = get_logger("method_extractor")
            logger.error(f"Unexpected error while extracting methods: {e}")
        
        return methods
    
    def extract_method_block(self, code: str, method_name: str) -> Optional[str]:
        """Extract complete method as text block"""
        methods = self.extract_methods(code)
        if method_name in methods:
            return methods[method_name]['code']
        return None
    
    def extract_imports(self, code: str) -> str:
        """Extract all import statements"""
        lines = code.split('\n')
        imports = []
        
        for line in lines:
            stripped = line.strip()
            try:
                if stripped.startswith('import ') or stripped.startswith('from '):
                    imports.append(line)
                elif imports and not stripped:
                    continue
                elif imports:
                    break
            except Exception as e:
                print(f"An error occurred: {e}")
        
        return '\n'.join(imports)
    
    def extract_class_definition(self, code: str) -> Optional[str]:
        """Extract class definition line and __init__"""
        try:
            tree = ast.parse(code)
            lines = code.split('\n')
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    start = node.lineno - 1
                    
                    init_end = start + 1
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                            if hasattr(item, 'end_lineno'):
                                init_end = item.end_lineno
                            else:
                                for i in range(item.lineno, len(lines)):
                                    if i > item.lineno and lines[i].strip().startswith('def '):
                                        init_end = i
                                        break
                                else:
                                    init_end = len(lines)
                            break
                    
                    return '\n'.join(lines[start:init_end])
        except (SyntaxError, TypeError) as e:
            from infrastructure.logging.logging_system import get_logger
            logger = get_logger("method_extractor")
            logger.error(f"Failed to extract class definition: {e}")
        
        return None
    
    def get_method_dependencies(self, method_name: str, code: str) -> List[str]:
        """Find methods that this method calls"""
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
        except SyntaxError as e:
            print(f'Syntax error in code: {e}')
        except Exception as e:
            print(f'An unexpected error occurred: {e}')

        return dependencies
