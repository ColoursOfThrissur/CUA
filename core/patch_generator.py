"""
Patch Generator - Creates unified diff patches from code changes
"""
import difflib
from typing import Dict, List, Optional
from pathlib import Path

class PatchGenerator:
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path)
    
    def generate_patch(self, file_path: str, old_content: str, new_content: str) -> str:
        """Generate unified diff patch"""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm=''
        )
        
        return ''.join(diff)
    
    def generate_new_file_patch(self, file_path: str, content: str) -> str:
        """Generate patch for new file creation"""
        lines = content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            [],
            lines,
            fromfile="/dev/null",
            tofile=f"b/{file_path}",
            lineterm=''
        )
        
        return ''.join(diff)
    
    def parse_llm_changes(self, llm_response: str, file_path: str) -> Optional[str]:
        """Parse LLM response and generate proper patch with validation"""
        code = self._extract_code(llm_response)
        if not code:
            return None
        
        # Basic validation
        if not self._validate_code(code):
            return None
        
        full_path = self.repo_path / file_path
        if full_path.exists():
            with open(full_path, 'r', encoding='utf-8') as f:
                old_content = f.read()
            return self.generate_patch(file_path, old_content, code)
        else:
            return self.generate_new_file_patch(file_path, code)
    
    def _validate_code(self, code: str) -> bool:
        """Validate generated code - check for diff format and dangerous patterns"""
        # Check if LLM returned diff format instead of code
        if code.startswith('---') or code.startswith('+++') or '@@' in code[:100]:
            return False
        
        # CRITICAL SECURITY PATTERNS - Block these completely
        critical_patterns = [
            ("eval(", "Code execution vulnerability"),
            ("exec(", "Code execution vulnerability"),
            ("__import__", "Dynamic import vulnerability"),
            ("compile(", "Code compilation vulnerability"),
            ("os.system", "Shell injection vulnerability"),
            ("subprocess.call", "Shell injection vulnerability"),
            ("shutil.rmtree(", "Dangerous file deletion"),
        ]
        
        for pattern, reason in critical_patterns:
            if pattern in code:
                return False
        
        # SECURITY VALIDATION PATTERNS - Check for weak security
        # Block substring matching in security-critical contexts
        if "domain in " in code or " in parsed.netloc" in code or " in url" in code:
            # Check if it's in a security validation context
            if any(keyword in code for keyword in ["_is_allowed", "validate", "check_url", "allowed_domains"]):
                return False  # Reject weak validation patterns
        
        return True
    
    def _extract_code(self, response: str) -> Optional[str]:
        """Extract code from LLM response"""
        # Look for code blocks
        if '```python' in response:
            start = response.find('```python') + 9
            end = response.find('```', start)
            if end != -1:
                return response[start:end].strip()
        
        if '```' in response:
            start = response.find('```') + 3
            newline = response.find('\n', start)
            if newline != -1:
                start = newline + 1
            end = response.find('```', start)
            if end != -1:
                return response[start:end].strip()
        
        return None
    
    def combine_patches(self, patches: List[str]) -> str:
        """Combine multiple patches into one"""
        return '\n'.join(patches)
