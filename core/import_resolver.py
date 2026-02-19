"""
Import Resolver - Detect and add missing imports
"""
import ast
import re
from typing import List, Set

class ImportResolver:
    # Common stdlib modules
    STDLIB_MODULES = {
        'time', 'datetime', 'json', 'os', 'sys', 'logging', 're', 'pathlib',
        'subprocess', 'shutil', 'collections', 'itertools', 'functools',
        'typing', 'dataclasses', 'enum', 'abc', 'asyncio'
    }
    
    def detect_missing(self, original_code: str, new_code: str) -> List[str]:
        """Detect imports used in new code but missing from original"""
        used_names = self._extract_names(new_code)
        existing_imports = self._extract_imports(original_code)
        
        missing = []
        for name in used_names:
            if name in self.STDLIB_MODULES and name not in existing_imports:
                missing.append(f"import {name}")
        
        return missing
    
    def _extract_names(self, code: str) -> Set[str]:
        """Extract module names used in code"""
        names = set()
        # Pattern: module.something
        for match in re.finditer(r'\b(\w+)\.', code):
            names.add(match.group(1))
        return names
    
    def _extract_imports(self, code: str) -> Set[str]:
        """Extract already imported modules"""
        imports = set()
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module.split('.')[0])
        except:
            pass
        return imports
