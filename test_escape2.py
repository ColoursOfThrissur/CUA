import ast

print("=== ESCAPING LAYERS ===")
print()

# Layer 1: What Python needs to parse correctly
print("1. FINAL PYTHON CODE (what ast.parse needs):")
final = r'safe_id = item_id.strip().replace("/", "_").replace("\\", "_")'
print(f"   {final}")
ast.parse(final)
print("   OK Valid")
print()

# Layer 2: What the f-string needs to produce
print("2. F-STRING OUTPUT (what f-string must produce):")
print(r'   safe_id = item_id.strip().replace("/", "_").replace("\\", "_")')
print()

# Layer 3: What we write in the f-string
print("3. F-STRING SOURCE (what we write in code):")
print(r'   In f-string: replace("\\\\", "_")')
print(r'   Because: \\\\ in f-string -> \\ in output')
print()

# Test it
test_template = f'safe_id = item_id.strip().replace("/", "_").replace("\\\\", "_")'
print("4. TEST:")
print(f"   Generated: {test_template}")
try:
    ast.parse(test_template)
    print("   OK Valid Python")
except SyntaxError as e:
    print(f"   ERROR Invalid: {e}")
