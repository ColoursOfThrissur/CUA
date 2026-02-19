"""
Direct LLM Test - Reproduce web_content_extractor failure
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from planner.llm_client import LLMClient
from tools.capability_registry import CapabilityRegistry
import ast

def test_code_generation():
    """Test exact scenario that failed"""
    
    # Initialize LLM
    registry = CapabilityRegistry()
    llm = LLMClient(registry=registry)
    
    # Read the actual file
    with open('tools/web_content_extractor.py', 'r') as f:
        file_content = f.read()
    
    # Extract _extract method
    tree = ast.parse(file_content)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_extract':
            extract_start = node.lineno
            extract_end = node.end_lineno
            lines = file_content.split('\n')
            extract_code = '\n'.join(lines[extract_start-1:extract_end])
            break
    
    print("=" * 80)
    print("ORIGINAL _extract METHOD (92 lines):")
    print("=" * 80)
    print(extract_code[:500] + "...")
    print()
    
    # Exact prompt from logs
    prompt = """Refactor the _extract method by extracting a helper method named '_parse_html_response' to handle HTML parsing logic.

Current method:
```python
{code}
```

Generate ONLY the new helper method. Return valid Python code with:
- Proper function definition: def _parse_html_response(self, ...):
- Complete implementation
- Proper indentation (4 spaces)
- Return statement

Format:
```python
def _parse_html_response(self, response, url):
    # implementation
    return result
```
""".format(code=extract_code)
    
    print("=" * 80)
    print("PROMPT TO LLM:")
    print("=" * 80)
    print(prompt[:500] + "...")
    print()
    
    # Call LLM
    print("=" * 80)
    print("CALLING LLM (qwen2.5-coder:14b)...")
    print("=" * 80)
    
    response = llm._call_llm(prompt, temperature=0.3, max_tokens=2048, expect_json=False)
    
    print()
    print("=" * 80)
    print("LLM RESPONSE:")
    print("=" * 80)
    print(response)
    print()
    
    # Validate response
    print("=" * 80)
    print("VALIDATION:")
    print("=" * 80)
    
    # Check for function definition
    has_def = 'def ' in response
    print(f"[OK] Contains 'def ': {has_def}")
    
    # Check for proper function name
    has_name = '_parse_html_response' in response
    print(f"[OK] Contains '_parse_html_response': {has_name}")
    
    # Try to parse as Python
    try:
        # Extract code block if wrapped in ```
        code = response
        if '```python' in code:
            code = code.split('```python')[1].split('```')[0].strip()
        elif '```' in code:
            code = code.split('```')[1].split('```')[0].strip()
        
        ast.parse(code)
        print(f"[OK] Valid Python syntax: True")
        
        # Check if it's a function
        tree = ast.parse(code)
        has_function = any(isinstance(node, ast.FunctionDef) for node in ast.walk(tree))
        print(f"[OK] Contains function definition: {has_function}")
        
        if has_function:
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    print(f"[OK] Function name: {node.name}")
                    print(f"[OK] Parameters: {[arg.arg for arg in node.args.args]}")
                    break
        
    except SyntaxError as e:
        print(f"[ERROR] Syntax Error: {e}")
        print(f"[ERROR] Valid Python syntax: False")
    
    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    test_code_generation()
