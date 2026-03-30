"""
Code Integrator - Merge modified methods back into original file
"""
from typing import Dict, List, Optional

class CodeIntegrator:
    def is_complete_method(self, code: str) -> bool:
        """Validate method is complete with def + body"""
        if not code or not code.strip():
            return False
        
        lines = [l for l in code.split('\n') if l.strip()]
        if not lines:
            return False
        
        # Must start with def
        if not lines[0].strip().startswith('def '):
            return False
        
        # Must have body (more than just signature)
        if len(lines) < 2:
            return False
        
        # For __init__, allow imports and blank lines
        if '__init__' in lines[0]:
            return True
        
        # Check for proper indentation in body (skip blank lines)
        if lines[0].strip().startswith('def '):
            sig_indent = len(lines[0]) - len(lines[0].lstrip())
            # Find first non-empty body line
            for i in range(1, len(lines)):
                if lines[i].strip():
                    body_indent = len(lines[i]) - len(lines[i].lstrip())
                    if body_indent <= sig_indent:
                        return False
                    break
        
        return True
    
    def integrate_methods(self, original_code: str, modified_methods: Dict[str, str]) -> str:
        """Replace methods using AST when possible, fallback to string replacement"""
        from infrastructure.code_generation.method_extractor import MethodExtractor
        from infrastructure.logging.logging_system import get_logger
        logger = get_logger("code_integrator")
        
        # Try AST-based integration first
        try:
            import ast
            result = self._integrate_with_ast(original_code, modified_methods)
            if result:
                logger.info("Used AST-based integration")
                return result
        except Exception as e:
            logger.info(f"AST integration failed: {e}, using string-based")
        
        # Fallback to string-based
        extractor = MethodExtractor()
        
        # Get all methods with line positions
        all_methods = extractor.extract_methods(original_code)
        lines = original_code.split('\n')
        
        # Collect missing imports from all modified methods
        missing_imports = self._detect_missing_imports(original_code, modified_methods)
        if missing_imports:
            logger.info(f"Adding missing imports: {missing_imports}")
            lines = self._add_imports(lines, missing_imports)
            # Re-extract methods after adding imports (line numbers shifted)
            original_code = '\n'.join(lines)
            all_methods = extractor.extract_methods(original_code)
        
        # Sort by start line descending to avoid index shifts
        methods_to_replace = sorted(
            [(name, all_methods[name]) for name in modified_methods.keys() if name in all_methods],
            key=lambda x: x[1]['start_line'],
            reverse=True
        )
        
        # Replace each method from bottom to top
        for method_name, method_info in methods_to_replace:
            new_method = modified_methods[method_name]
            
            start = method_info['start_line']
            end = method_info['end_line']
            
            # Get original method indentation from first line
            original_indent = self._get_indentation(lines[start])
            
            # Normalize: strip all indentation, then apply fresh indent
            new_lines = new_method.split('\n')
            indented_lines = []
            for line in new_lines:
                if line.strip():  # Non-empty line
                    # Strip existing indent and apply original indent
                    indented_lines.append(original_indent + line.lstrip())
                else:  # Empty line
                    indented_lines.append('')
            
            lines[start:end] = indented_lines
            
            logger.info(f"Replaced method {method_name}: lines {start}-{end}")
        
        return '\n'.join(lines)

    def verify_expected_methods(self, code: str, expected_methods: List[str]) -> bool:
        """Verify expected method names exist and file is parseable."""
        try:
            import ast
            tree = ast.parse(code)
        except Exception:
            return False

        if not expected_methods:
            return True
        found = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        return all(method in found for method in expected_methods if method)
    
    def _get_indentation(self, line: str) -> str:
        """Get indentation from line"""
        return line[:len(line) - len(line.lstrip())]
    
    def _integrate_with_ast(self, original_code: str, modified_methods: Dict[str, str]) -> Optional[str]:
        """Use AST to replace method bodies only - preserves decorators/signatures"""
        import ast
        
        try:
            tree = ast.parse(original_code)
        except:
            return None
        
        class_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_node = node
                break
        
        if not class_node:
            return None
        
        # Parse modified methods and extract bodies
        modified_bodies = {}
        for method_name, method_code in modified_methods.items():
            try:
                method_tree = ast.parse(method_code)
                if method_tree.body and isinstance(method_tree.body[0], ast.FunctionDef):
                    method_node = method_tree.body[0]
                    if not method_node.body:
                        return None
                    # Store only the body
                    modified_bodies[method_name] = method_node.body
                else:
                    return None
            except:
                return None
        
        # Replace only method bodies (keep decorators, signature, docstring)
        for node in class_node.body:
            if isinstance(node, ast.FunctionDef) and node.name in modified_bodies:
                node.body = modified_bodies[node.name]
        
        return ast.unparse(tree)
    def _apply_indentation(self, code: str, base_indent: str) -> List[str]:
        """Apply base indentation - only used for add_new_methods"""
        lines = code.split('\n')
        if not lines:
            return []
        
        # Find minimum indentation (excluding empty lines)
        min_indent = float('inf')
        for line in lines:
            if line.strip():
                indent_len = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent_len)
        
        if min_indent == float('inf'):
            min_indent = 0
        
        # Apply base indent while preserving relative indentation
        result = []
        for line in lines:
            if line.strip():
                relative_indent = len(line) - len(line.lstrip()) - min_indent
                result.append(base_indent + ' ' * relative_indent + line.lstrip())
            else:
                result.append('')
        
        return result
    
    def add_new_methods(self, original_code: str, new_methods: Dict[str, str], insert_before: str = None) -> str:
        """Add new methods to class"""
        lines = original_code.split('\n')
        
        # Find insertion point (before specified method or before last line of class)
        insert_line = self._find_class_end(lines)
        
        if insert_before:
            from infrastructure.code_generation.method_extractor import MethodExtractor
            extractor = MethodExtractor()
            methods = extractor.extract_methods(original_code)
            
            if insert_before in methods:
                insert_line = methods[insert_before]['start_line']
        
        # Get class indentation
        class_indent = self._find_class_indentation(lines)
        method_indent = class_indent + '    '
        
        # Insert new methods
        for method_name, method_code in new_methods.items():
            # Apply proper indentation
            method_lines = self._apply_indentation(method_code, method_indent)
            lines[insert_line:insert_line] = method_lines + ['']
            insert_line += len(method_lines) + 1
        
        return '\n'.join(lines)
    
    def _find_class_end(self, lines: List[str]) -> int:
        """Find last line of class body (before closing or EOF)"""
        # Scan backwards for last non-empty, non-comment line with class indentation
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if line and not line.startswith('#'):
                return i + 1
        return len(lines)
    
    def _find_class_indentation(self, lines: List[str]) -> str:
        """Find class definition indentation"""
        for line in lines:
            if line.strip().startswith('class '):
                return self._get_indentation(line)
        return ''
    
    def _detect_missing_imports(self, original_code: str, modified_methods: Dict[str, str]) -> List[str]:
        """Detect imports used in methods but missing from module"""
        import re
        
        # Common imports to check
        import_patterns = {
            'time': r'\btime\.',
            'datetime': r'\b(datetime\.|timedelta)',
            'json': r'\bjson\.',
            'os': r'\bos\.',
            'sys': r'\bsys\.',
            'logging': r'\blogging\.',
        }
        
        missing = []
        for module, pattern in import_patterns.items():
            # Check if used in any modified method
            used = any(re.search(pattern, code) for code in modified_methods.values())
            if used:
                # Check if already imported
                if f'import {module}' not in original_code:
                    missing.append(f'import {module}')
        
        return missing
    
    def _add_imports(self, lines: List[str], imports: List[str]) -> List[str]:
        """Add imports after existing imports or at top"""
        # Find last import line
        last_import_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith(('import ', 'from ')):
                last_import_idx = i
        
        # Insert after last import or at top (after docstring)
        insert_idx = last_import_idx + 1 if last_import_idx >= 0 else 0
        
        # Skip docstring if at top
        if insert_idx == 0:
            for i, line in enumerate(lines[:10]):
                if '"""' in line or "'''" in line:
                    # Find closing docstring
                    for j in range(i + 1, min(i + 20, len(lines))):
                        if '"""' in lines[j] or "'''" in lines[j]:
                            insert_idx = j + 1
                            break
                    break
        
        # Insert imports
        for imp in reversed(imports):
            lines.insert(insert_idx, imp)
        
        return lines
