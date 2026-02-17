"""
Test orchestrated code generation
"""
import sys
sys.path.insert(0, '.')

from core.orchestrated_code_generator import OrchestratedCodeGenerator
from core.system_analyzer import SystemAnalyzer
from planner.llm_client import LLMClient

# Initialize
llm = LLMClient(model="mistral")
analyzer = SystemAnalyzer()
generator = OrchestratedCodeGenerator(llm, analyzer)

# Test: Modify http_tool to add PUT/DELETE methods
user_request = "Add PUT and DELETE HTTP methods to the http tool"
target_file = "tools/http_tool.py"

print(f"Testing orchestrated generation...")
print(f"Request: {user_request}")
print(f"Target: {target_file}")
print("-" * 60)

success, code, error = generator.generate_code(user_request, target_file)

if success:
    print("SUCCESS!")
    print(f"Generated {len(code)} characters of code")
    print("\nFirst 500 chars:")
    print(code[:500])
    print("\nLast 500 chars:")
    print(code[-500:])
else:
    print(f"FAILED: {error}")
