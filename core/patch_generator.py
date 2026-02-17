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
        
        # Check dangerous patterns
        dangerous = [
            "eval(", "exec(", "__import__", "compile(",
            "os.system", "subprocess.call",
            "shutil.rmtree(", ".unlink(", ".rmdir(",
            "open(", "Path(", "file.write",
            # Security validation patterns
            "domain in ",  # Substring matching in security checks
            " in parsed.netloc",  # SSRF vulnerability pattern
            " in url",  # Weak URL validation
        ]
        
        # Block definitely dangerous operations
        blocked = [
            "eval(", "exec(", "__import__", "compile(", 
            "os.system", "subprocess.call", "shutil.rmtree(",
            "domain in ", " in parsed.netloc"  # Prevent SSRF patterns
        ]
        return not any(d in code for d in blocked)
    
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
