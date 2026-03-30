"""
Semantic No-Op Detector - Skip patches that don't change behavior
"""
import ast
from typing import Optional

class NoOpDetector:
    def is_noop(self, original_code: str, modified_code: str) -> bool:
        """Check if modification is semantically equivalent"""
        try:
            orig_ast = ast.parse(original_code)
            mod_ast = ast.parse(modified_code)
            return ast.dump(orig_ast) == ast.dump(mod_ast)
        except:
            # If can't parse, compare normalized strings
            return self._normalize(original_code) == self._normalize(modified_code)
    
    def _normalize(self, code: str) -> str:
        """Normalize code for comparison (strip whitespace/comments)"""
        lines = []
        for line in code.split('\n'):
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                lines.append(stripped)
        return '\n'.join(lines)
