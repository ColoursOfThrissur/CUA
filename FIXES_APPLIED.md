# Fixes Applied to Prevent Type Mismatch Issues

## Issue
BenchmarkRunnerTool had bug: `'dict' object has no attribute 'strip'`
- Root cause: `self.services.shell.execute()` returns ToolResult/dict, not string
- Tool code assumed string return type

## Fixes Applied

### 1. Fixed BenchmarkRunnerTool (tools/experimental/BenchmarkRunnerTool.py)
- Added proper result extraction from ToolResult object
- Handles both ToolResult.data and dict formats
- Converts to string before calling .strip()

### 2. Added Fallback Registry Refresh (api/server.py line 185-203)
- When tool not found, automatically calls refresh_runtime_registry_from_files()
- Added fuzzy matching for tool names (e.g., BenchmarkTool → BenchmarkRunnerTool)
- Prevents "Tool not found" errors when LLM uses slightly wrong names

### 3. Fixed Skill Trigger Examples (skills/computer_automation/skill.json)
- Added benchmark-related triggers: "run benchmark suite", "add benchmark case", "list benchmark cases"
- Ensures skill selector matches benchmark requests to computer_automation skill
- Makes BenchmarkRunnerTool available in preferred_tools list

### 4. Added Debug Logging (planner/tool_calling.py)
- Logs tool definitions being sent to LLM
- Logs BenchmarkRunnerTool operations specifically
- Helps diagnose context issues

## Prevention Strategy for Future

To prevent similar issues in future tool creations, update service documentation in:
- `core/tool_creation/spec_generator.py` line 59
- `core/tool_creation/code_generator/qwen_generator.py` (if exists)

Change from:
```python
'shell': 'execute(command, args=[])'
```

To:
```python
'shell': 'execute(command, args=[]) -> Returns ToolResult. Access output via result.data'
```

This tells the LLM that services return ToolResult objects, not raw strings.
