"""Dependency resolver - installs libraries and generates services."""
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple, Optional


class DependencyResolver:
    """Resolve missing dependencies."""
    
    def __init__(self, llm_client=None):
        self.llm = llm_client
    
    def install_library(self, library: str) -> Tuple[bool, str]:
        """Install Python library via pip."""
        try:
            # Install library
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", library],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                # Add to requirements.txt
                self._add_to_requirements(library)
                return True, f"Installed {library}"
            else:
                return False, f"Failed: {result.stderr}"
        
        except subprocess.TimeoutExpired:
            return False, "Installation timeout"
        except Exception as e:
            return False, str(e)
    
    def generate_service(self, service_name: str, description: str = None) -> Tuple[bool, Optional[str]]:
        """Generate service implementation using LLM."""
        if not self.llm:
            return False, None
        
        prompt = f"""Generate a Python service class for ToolServices.

SERVICE NAME: {service_name}
DESCRIPTION: {description or f"Service for {service_name} operations"}

REQUIREMENTS:
- Class name: {service_name.title()}Service
- Simple implementation using only standard library
- Methods should be self-contained
- Return plain Python types (dict, list, str)
- No external dependencies

Example structure:
```python
class CacheService:
    def __init__(self):
        self._cache = {{}}
    
    def get(self, key: str):
        return self._cache.get(key)
    
    def set(self, key: str, value):
        self._cache[key] = value
```

Return ONLY the class definition."""

        try:
            response = self.llm._call_llm(prompt, temperature=0.2, max_tokens=800, expect_json=False)
            
            # Extract code
            code = self._extract_code(response)
            
            if code and f"class {service_name.title()}Service" in code:
                return True, code
            
            return False, None
        
        except Exception as e:
            return False, None
    
    def _add_to_requirements(self, library: str):
        """Add library to requirements.txt."""
        req_file = Path("requirements.txt")
        
        # Read existing
        if req_file.exists():
            lines = req_file.read_text().splitlines()
        else:
            lines = []
        
        # Check if already present
        if any(line.strip().startswith(library) for line in lines):
            return
        
        # Add new library
        lines.append(library)
        req_file.write_text("\n".join(lines) + "\n")
    
    def _extract_code(self, response: str) -> str:
        """Extract code from LLM response."""
        if "```python" in response:
            start = response.find("```python") + 9
            end = response.find("```", start)
            return response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            return response[start:end].strip()
        return response.strip()
