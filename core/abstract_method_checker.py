"""
Abstract Method Checker - Prevent breaking abstract methods
"""
import ast
from pathlib import Path
from typing import Set

class AbstractMethodChecker:
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path)
    
    def get_abstract_methods(self, file_path: str) -> Set[str]:
        """Extract abstract method names from file"""
        full_path = self.repo_path / file_path
        if not full_path.exists():
            return set()
        
        try:
            code = full_path.read_text(encoding='utf-8')
            tree = ast.parse(code)
            
            abstract_methods = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            # Check for @abstractmethod decorator
                            for decorator in item.decorator_list:
                                if isinstance(decorator, ast.Name) and decorator.id == 'abstractmethod':
                                    abstract_methods.add(item.name)
                                elif isinstance(decorator, ast.Attribute) and decorator.attr == 'abstractmethod':
                                    abstract_methods.add(item.name)
            
            return abstract_methods
        except:
            return set()
    
    def is_abstract_method(self, file_path: str, method_name: str) -> bool:
        """Check if method is abstract"""
        abstract_methods = self.get_abstract_methods(file_path)
        return method_name in abstract_methods
