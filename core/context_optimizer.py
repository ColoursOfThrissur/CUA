"""
Context Optimizer - Intelligently selects relevant code context for LLM
"""
import ast
from pathlib import Path
from typing import List, Dict, Set

class ContextOptimizer:
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.max_context_size = 8000  # tokens
    
    def get_optimized_context(self, target_file: str, error_context: Dict = None) -> Dict:
        """Get optimized context for a target file"""
        target_path = Path(target_file)
        
        context = {
            'target_file': {
                'path': str(target_path),
                'content': self._read_file(target_path),
                'summary': self._get_file_summary(target_path)
            },
            'dependencies': [],
            'related_files': [],
            'error_context': error_context or {}
        }
        
        # Get direct dependencies
        dependencies = self._get_dependencies(target_path)
        for dep in dependencies[:3]:  # Limit to top 3
            dep_path = self._resolve_import(dep, target_path)
            if dep_path and dep_path.exists():
                context['dependencies'].append({
                    'path': str(dep_path),
                    'summary': self._get_file_summary(dep_path)
                })
        
        # Get related files (same directory)
        related = self._get_related_files(target_path, limit=2)
        for rel_path in related:
            context['related_files'].append({
                'path': str(rel_path),
                'summary': self._get_file_summary(rel_path)
            })
        
        return context
    
    def _read_file(self, file_path: Path) -> str:
        """Read file content"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return ""
    
    def _get_file_summary(self, file_path: Path) -> Dict:
        """Get summary of file structure"""
        try:
            content = self._read_file(file_path)
            tree = ast.parse(content)
            
            classes = []
            functions = []
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                    classes.append({
                        'name': node.name,
                        'methods': methods[:5]  # Limit methods
                    })
                elif isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                    functions.append(node.name)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        imports.extend([alias.name for alias in node.names])
                    else:
                        imports.append(node.module)
            
            return {
                'classes': classes[:5],  # Top 5 classes
                'functions': functions[:10],  # Top 10 functions
                'imports': list(set(imports))[:10],  # Top 10 unique imports
                'lines': len(content.split('\n'))
            }
        except Exception:
            return {
                'classes': [],
                'functions': [],
                'imports': [],
                'lines': 0
            }
    
    def _get_dependencies(self, file_path: Path) -> List[str]:
        """Extract import dependencies from file"""
        try:
            content = self._read_file(file_path)
            tree = ast.parse(content)
            
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend([alias.name for alias in node.names])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
            
            # Filter to project imports only
            project_imports = []
            for imp in imports:
                if not imp.startswith(('os', 'sys', 'json', 'typing', 're', 'pathlib')):
                    project_imports.append(imp)
            
            return project_imports
        except Exception:
            return []
    
    def _resolve_import(self, import_name: str, from_file: Path) -> Path:
        """Resolve import to file path"""
        # Convert import to path
        parts = import_name.split('.')
        
        # Try relative to project root
        potential_path = self.project_root / '/'.join(parts)
        if potential_path.with_suffix('.py').exists():
            return potential_path.with_suffix('.py')
        
        # Try as package
        potential_init = potential_path / '__init__.py'
        if potential_init.exists():
            return potential_init
        
        return None
    
    def _get_related_files(self, file_path: Path, limit: int = 2) -> List[Path]:
        """Get related files in same directory"""
        related = []
        parent = file_path.parent
        
        for py_file in parent.glob('*.py'):
            if py_file != file_path and py_file.name != '__init__.py':
                related.append(py_file)
                if len(related) >= limit:
                    break
        
        return related
    
    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation (1 token ≈ 4 chars)"""
        return len(text) // 4
