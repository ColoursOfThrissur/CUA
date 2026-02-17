"""
Code Integrator - Merge modified methods back into original file
"""
from typing import Dict, List

class CodeIntegrator:
    def integrate_methods(self, original_code: str, modified_methods: Dict[str, str]) -> str:
        """Replace methods in original code with modified versions"""
        lines = original_code.split('\n')
        
        from core.method_extractor import MethodExtractor
        extractor = MethodExtractor()
        
        # Get original method positions
        original_methods = extractor.extract_methods(original_code)
        
        # Sort by start line descending to avoid index corruption
        sorted_methods = sorted(
            [(name, info) for name, info in original_methods.items() if name in modified_methods],
            key=lambda x: x[1]['start_line'],
            reverse=True
        )
        
        # Replace each modified method from bottom to top
        for method_name, method_info in sorted_methods:
            new_code = modified_methods[method_name]
            start = method_info['start_line']
            end = method_info['end_line']
            
            # Preserve indentation
            original_indent = self._get_indentation(lines[start])
            new_lines = self._apply_indentation(new_code, original_indent)
            
            # Replace lines
            lines[start:end] = new_lines
        
        return '\n'.join(lines)
    
    def _get_indentation(self, line: str) -> str:
        """Get indentation from line"""
        return line[:len(line) - len(line.lstrip())]
    
    def _apply_indentation(self, code: str, base_indent: str) -> List[str]:
        """Apply base indentation to code block"""
        lines = code.split('\n')
        result = []
        
        for line in lines:
            if line.strip():  # Non-empty line
                # Get relative indentation
                line_indent = self._get_indentation(line)
                # Apply base + relative
                result.append(base_indent + line.lstrip())
            else:
                result.append(line)
        
        return result
    
    def add_new_methods(self, original_code: str, new_methods: Dict[str, str], insert_before: str = None) -> str:
        """Add new methods to class"""
        lines = original_code.split('\n')
        
        # Find insertion point (before specified method or before last line of class)
        insert_line = self._find_class_end(lines)
        
        if insert_before:
            from core.method_extractor import MethodExtractor
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
