"""Test tool calling JSON parsing"""

# Simulate the parsing logic
def test_parse_multiple_json():
    # This is what the LLM returned
    content = """```json
{
  "name": "BrowserAutomationTool_open_and_navigate",
  "arguments": {
    "url": "https://www.google.com"
  }
}
{
  "name": "BrowserAutomationTool_find_element",
  "arguments": {
    "selector": "input[name='q']"
  }
}
{
  "name": "BrowserAutomationTool_take_screenshot",
  "arguments": {
    "filename": "screenshot.png"
  }
}
```"""
    
    # Strip markdown
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        if len(lines) > 2:
            stripped = "\n".join(lines[1:-1]).strip()
    
    print("Stripped content:")
    print(stripped)
    print("\n" + "="*50 + "\n")
    
    # Parse multiple JSON objects
    import json
    calls = []
    for line in stripped.split("\n"):
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
                if "name" in parsed and "arguments" in parsed:
                    calls.append({"function": parsed})
                    print(f"Parsed: {parsed['name']}")
            except Exception as e:
                print(f"Failed to parse line: {line[:50]}... Error: {e}")
    
    print(f"\nTotal tool calls extracted: {len(calls)}")
    return calls

if __name__ == "__main__":
    result = test_parse_multiple_json()
    print("\nFinal result:")
    for i, call in enumerate(result, 1):
        func = call["function"]
        print(f"{i}. {func['name']} with args: {func['arguments']}")
