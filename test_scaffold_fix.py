#!/usr/bin/env python3
"""Test scaffold generation fix"""

# Test the f-string fix
gap_description = "test tool"

# OLD (broken) - would fail with format specifier error
# prompt = f"""Test: {gap_description}
# Example: [{"name": "param", "type": "string"}]
# """

# NEW (fixed) - uses .format() with escaped braces
prompt = """Test: {gap_description}
Example: [{{"name": "param", "type": "string"}}]
""".format(gap_description=gap_description)

print("[OK] Prompt generation works!")
print(prompt)

# Test that the prompt contains the correct JSON
assert '{"name": "param"' in prompt
assert gap_description in prompt
print("[OK] All tests passed!")
