"""Qwen-style evolution code generator - preserves structure, improves handlers."""
import ast
import re
import textwrap
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class EvolutionCodeGenerator:
    """Generates improved tool code using multi-stage approach."""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def generate_improved_code(self, current_code: str, proposal: Dict[str, Any]) -> Optional[str]:
        """Generate improved code preserving structure."""
        
        # Extract class name
        class_name = self._extract_class_name(current_code)
        if not class_name:
            return None
        
        # Extract handlers to improve
        handlers = self._extract_handlers(current_code, class_name)
        if not handlers:
            logger.warning("No handlers found to improve")
            return current_code
        
        # Improve handlers one by one (like Qwen multi-stage)
        improved_code = current_code
        for handler_name, handler_code in handlers.items():
            logger.info(f"Improving handler: {handler_name}")
            improved_handler = self._improve_single_handler(
                handler_code,
                handler_name,
                proposal,
                class_name
            )
            if improved_handler:
                improved_code = self._replace_handler(
                    improved_code,
                    handler_name,
                    improved_handler,
                    class_name
                )
        
        return improved_code
    
    def _improve_single_handler(
        self,
        handler_code: str,
        handler_name: str,
        proposal: Dict[str, Any],
        class_name: str
    ) -> Optional[str]:
        """Improve a single handler method."""
        
        prompt = f"""TASK: Improve this handler method.

CURRENT CODE:
```python
{handler_code}
```

IMPROVEMENT PROPOSAL:
{proposal['description']}

CHANGES TO MAKE:
{chr(10).join(f"- {c}" for c in proposal['changes'])}

CRITICAL - AVAILABLE SERVICES (ALWAYS use self.services prefix):
- self.services.llm.generate(prompt, temperature, max_tokens) - Call LLM
- self.services.storage.save/get/list/find - Store data
- self.services.http.get/post - HTTP requests
- self.services.fs.read/write - File operations
- self.services.json.parse/stringify - JSON operations
- self.services.time.now_utc() - Timestamps
- self.services.ids.generate() - Generate IDs
- self.services.logging.info/warning/error - Log messages
- self.services.detect_language(text) - Detect language
- self.services.extract_key_points(text, style, language) - Extract key points
- self.services.sentiment_analysis(text, language) - Analyze sentiment
- self.services.generate_json_output(**kwargs) - Generate JSON

REQUIREMENTS:
- Keep method name: {handler_name}
- Keep method signature unchanged
- Preserve all parameters
- ALWAYS use self.services.X - NEVER call self.X directly for services
- Initialize any cache/state attributes in __init__ (use self._cache not self.cache)
- Only improve internal logic using AVAILABLE SERVICES above
- Add error handling if missing
- Keep under 20 lines
- Return plain dict (not ToolResult)
- DO NOT reference methods that don't exist
- DO NOT use attributes not initialized in __init__

Return ONLY the improved method definition."""
        
        for attempt in range(3):
            try:
                response = self.llm._call_llm(prompt, temperature=0.2, max_tokens=800, expect_json=False)
                improved = self._extract_method_from_response(response, handler_name)
                
                if improved and self._validate_handler(improved, handler_name):
                    return improved
                
            except Exception as e:
                logger.warning(f"Handler improvement attempt {attempt + 1} failed: {e}")
        
        return None
    
    def _extract_class_name(self, code: str) -> Optional[str]:
        """Extract class name from code."""
        match = re.search(r'class\s+(\w+)', code)
        return match.group(1) if match else None
    
    def _extract_handlers(self, code: str, class_name: str) -> Dict[str, str]:
        """Extract all handler methods from class."""
        try:
            tree = ast.parse(code)
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return {}
            
            handlers = {}
            lines = code.splitlines()
            
            for node in class_node.body:
                if isinstance(node, ast.FunctionDef):
                    # Get all methods (not just _handle_*)
                    if node.name not in ['__init__', 'register_capabilities', 'get_capabilities', 'execute']:
                        handler_code = "\n".join(lines[node.lineno - 1:node.end_lineno])
                        handlers[node.name] = handler_code
            
            return handlers
        except Exception as e:
            logger.error(f"Failed to extract handlers: {e}")
            return {}
    
    def _extract_method_from_response(self, response: str, method_name: str) -> Optional[str]:
        """Extract method from LLM response."""
        code = self._extract_python_code(response)
        if not code:
            return None
        
        code = textwrap.dedent(code).strip()
        
        try:
            tree = ast.parse(code)
            fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == method_name), None)
            if fn:
                lines = code.splitlines()
                return "\n".join(lines[fn.lineno - 1:fn.end_lineno])
        except:
            pass
        
        # Fallback: if response is just the method
        if f"def {method_name}(" in code:
            return code
        
        return None
    
    def _replace_handler(
        self,
        code: str,
        handler_name: str,
        improved_handler: str,
        class_name: str
    ) -> str:
        """Replace handler in class code."""
        try:
            tree = ast.parse(code)
            class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
            if not class_node:
                return code
            
            target = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == handler_name), None)
            if not target:
                return code
            
            # Normalize indentation
            normalized = textwrap.dedent(improved_handler).strip("\n")
            replacement_lines = ["    " + line if line else "" for line in normalized.splitlines()]
            
            lines = code.splitlines()
            start = target.lineno - 1
            end = target.end_lineno
            lines[start:end] = replacement_lines
            
            return "\n".join(lines) + "\n"
        except Exception as e:
            logger.error(f"Failed to replace handler: {e}")
            return code
    
    def _validate_handler(self, handler_code: str, expected_name: str) -> bool:
        """Validate handler code."""
        if not handler_code or len(handler_code) < 10:
            return False
        
        if f"def {expected_name}(" not in handler_code:
            return False
        
        try:
            ast.parse(handler_code)
            return True
        except:
            return False
    
    def _extract_python_code(self, response: str) -> str:
        """Extract Python code from response."""
        if "```python" in response:
            start = response.find("```python") + 9
            end = response.find("```", start)
            return response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            return response[start:end].strip()
        
        return response.strip()
