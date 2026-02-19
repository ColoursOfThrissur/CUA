"""
Dependency Analyzer - Build import graph and calculate blast radius
"""
import ast
from pathlib import Path
from typing import Dict, Set, List
from collections import defaultdict

class DependencyAnalyzer:
    """Analyze code dependencies and calculate change impact"""
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path)
        self.import_graph = defaultdict(set)  # file -> set of files it imports
        self.reverse_graph = defaultdict(set)  # file -> set of files that import it
        self.core_modules = {
            'core/immutable_brain_stem.py',
            'core/orchestrated_code_generator.py',
            'core/proposal_generator.py',
            'core/secure_executor.py',
            'tools/capability_registry.py',
            'updater/orchestrator.py',
            'api/server.py'
        }
        self._build_graph()
    
    def _build_graph(self):
        """Build import dependency graph"""
        # Scan all Python files
        for py_file in self.repo_path.rglob('*.py'):
            if 'venv' in str(py_file) or '__pycache__' in str(py_file):
                continue
            
            rel_path = str(py_file.relative_to(self.repo_path)).replace('\\', '/')
            imports = self._extract_imports(py_file)
            
            for imp in imports:
                self.import_graph[rel_path].add(imp)
                self.reverse_graph[imp].add(rel_path)
    
    def _extract_imports(self, file_path: Path) -> Set[str]:
        """Extract import statements from file"""
        imports = set()
        
        try:
            code = file_path.read_text(encoding='utf-8')
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(self._resolve_import(alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(self._resolve_import(node.module))
        except:
            pass
        
        return imports
    
    def _resolve_import(self, module_name: str) -> str:
        """Convert module name to file path"""
        # Convert core.config_manager -> core/config_manager.py
        parts = module_name.split('.')
        
        # Check if it's a local import
        if parts[0] in ['core', 'tools', 'updater', 'planner', 'api']:
            return '/'.join(parts) + '.py'
        
        return module_name
    
    def calculate_blast_radius(self, file_path: str) -> Dict:
        """Calculate impact of changing a file"""
        normalized = file_path.replace('\\', '/')
        
        # Direct dependents
        direct = self.reverse_graph.get(normalized, set())
        
        # Transitive dependents (BFS)
        transitive = set()
        queue = list(direct)
        visited = set(direct)
        
        while queue:
            current = queue.pop(0)
            dependents = self.reverse_graph.get(current, set())
            
            for dep in dependents:
                if dep not in visited:
                    visited.add(dep)
                    transitive.add(dep)
                    queue.append(dep)
        
        # Check if core module
        is_core = normalized in self.core_modules
        
        # Calculate risk multiplier
        total_affected = len(direct) + len(transitive)
        if is_core:
            risk_multiplier = 2.0
        elif total_affected > 10:
            risk_multiplier = 1.5
        elif total_affected > 5:
            risk_multiplier = 1.2
        else:
            risk_multiplier = 1.0
        
        return {
            'file': normalized,
            'is_core_module': is_core,
            'direct_dependents': list(direct),
            'transitive_dependents': list(transitive),
            'total_affected': total_affected,
            'risk_multiplier': risk_multiplier
        }
    
    def get_dependency_chain(self, file_path: str) -> List[str]:
        """Get full dependency chain for a file"""
        normalized = file_path.replace('\\', '/')
        chain = []
        
        # BFS to find all dependencies
        queue = [normalized]
        visited = {normalized}
        
        while queue:
            current = queue.pop(0)
            deps = self.import_graph.get(current, set())
            
            for dep in deps:
                if dep not in visited:
                    visited.add(dep)
                    chain.append(dep)
                    queue.append(dep)
        
        return chain
    
    def is_circular_dependency(self, file_path: str) -> bool:
        """Check if file has circular dependencies"""
        normalized = file_path.replace('\\', '/')
        
        def has_cycle(node, visited, rec_stack):
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in self.import_graph.get(node, set()):
                if neighbor not in visited:
                    if has_cycle(neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        return has_cycle(normalized, set(), set())
