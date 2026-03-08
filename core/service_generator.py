"""
Service Generator - Auto-generates missing service methods
"""
import json
from pathlib import Path
from planner.llm_client import LLMClient

class ServiceGenerator:
    def __init__(self):
        self.llm = LLMClient()
        
    def generate_service_method(self, service_name: str, method_name: str, context: str = "") -> dict:
        """Generate a service method implementation"""
        
        prompt = f"""Generate a Python service method for the CUA tool system.

Service: {service_name}
Method: {method_name}
Context: {context if context else "No additional context"}

Requirements:
1. Method should be a standalone function that can be added to a service class
2. Use appropriate error handling
3. Return meaningful results
4. Follow Python best practices
5. Include docstring

Example service method structure:
```python
def method_name(self, param1, param2=None):
    \"\"\"Method description\"\"\"
    try:
        # Implementation
        result = ...
        return result
    except Exception as e:
        raise RuntimeError(f"Error in method_name: {{e}}")
```

Generate ONLY the method code, no class definition, no imports.
"""
        
        try:
            code = self.llm.generate(prompt, temperature=0.3, max_tokens=1000)
            
            # Clean up code
            code = code.strip()
            if code.startswith("```python"):
                code = code[9:]
            if code.startswith("```"):
                code = code[3:]
            if code.endswith("```"):
                code = code[:-3]
            code = code.strip()
            
            return {
                "success": True,
                "code": code,
                "service_name": service_name,
                "method_name": method_name
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "service_name": service_name,
                "method_name": method_name
            }
    
    def generate_full_service(self, service_name: str, methods: list, context: str = "") -> dict:
        """Generate a complete service class"""
        
        methods_str = ", ".join(methods)
        prompt = f"""Generate a Python service class for the CUA tool system.

Service Name: {service_name}
Required Methods: {methods_str}
Context: {context if context else "No additional context"}

Requirements:
1. Create a service class named {service_name.capitalize()}Service
2. Implement all required methods: {methods_str}
3. Use appropriate error handling
4. Follow CUA service patterns
5. Include docstrings

Example service structure:
```python
class BrowserService:
    \"\"\"Browser automation service\"\"\"
    
    def __init__(self):
        self.driver = None
    
    def execute(self, command, **kwargs):
        \"\"\"Execute browser command\"\"\"
        try:
            # Implementation
            return result
        except Exception as e:
            raise RuntimeError(f"Browser error: {{e}}")
```

Generate the complete service class code.
"""
        
        try:
            code = self.llm.generate(prompt, temperature=0.3, max_tokens=2000)
            
            # Clean up code
            code = code.strip()
            if code.startswith("```python"):
                code = code[9:]
            if code.startswith("```"):
                code = code[3:]
            if code.endswith("```"):
                code = code[:-3]
            code = code.strip()
            
            return {
                "success": True,
                "code": code,
                "service_name": service_name,
                "methods": methods
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "service_name": service_name,
                "methods": methods
            }
