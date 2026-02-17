# LLM-Driven Analysis Redesign

## Problem Solved
- **Old**: Hardcoded analysis → stuck suggesting same failing task forever
- **New**: LLM chooses what to improve with proper guardrails

## Key Changes

### 1. LLM-Driven Analysis Phase
**Location**: `improvement_loop.py` → `_analyze_system()`

**What LLM Receives**:
- List of ALL tools with their types (Tool class vs Utility script)
- List of existing tests
- Recent failures to avoid
- Structured task options

**What LLM Returns**:
```json
{
  "task_type": "create_test|fix_bug|add_feature",
  "target_file": "tools/json_tool.py",
  "test_file": "tests/unit/test_json_tool.py",
  "description": "Create tests for json_tool",
  "priority": "medium"
}
```

**Validation**:
- Checks if suggested file actually exists
- Rejects invented file paths
- Falls back to hardcoded suggestions if LLM fails

### 2. Failure Tracking & Retry Logic
**New Fields**:
- `self.failed_suggestions` - List of suggestions that failed 3+ times
- `self.retry_count` - Track attempts per suggestion

**Behavior**:
- Try each suggestion up to 3 times
- After 3 failures, mark as failed and move to next suggestion
- LLM sees recent failures and avoids them

### 3. Better Test Examples
**New Method**: `_find_similar_test(is_tool_class)`

**What It Does**:
- Searches existing tests for similar patterns
- Tool class test → finds test with `.execute()` and `result.status`
- Utility script test → finds test without `.execute()`
- Provides first 1500 chars as concrete example

**Why It Helps**:
- LLM learns from working examples
- Sees actual patterns instead of abstract templates
- Reduces invented code

### 4. Structured Context
**Analysis Prompt Includes**:
```python
## Available Tools:
[
  {"file": "tools/json_tool.py", "type": "Tool class", "has_test": true},
  {"file": "tools/analyze_llm_logs.py", "type": "Utility script", "has_test": false}
]

## Existing Tests:
["test_json_tool.py", "test_http_tool.py", ...]

## Recent Failures (avoid these):
["['tests/unit/test_analyze_llm_logs.py']"]
```

## Flow Comparison

### Old Flow (Hardcoded):
```
1. suggest_improvements() → always returns first missing test
2. LLM generates code → fails validation
3. Loop repeats → same suggestion forever
4. STUCK
```

### New Flow (LLM-Driven):
```
1. LLM analyzes → picks from available options
2. Validates file exists → rejects if invented
3. LLM generates code → fails validation
4. Retry count increments
5. After 3 failures → mark as failed
6. Next iteration → LLM sees failure, picks different task
7. PROGRESSES
```

## Benefits

1. **Autonomous Decision Making**: LLM chooses what to improve
2. **Grounded in Reality**: Can only choose from actual files
3. **Learns from Failures**: Avoids repeating failed tasks
4. **Better Examples**: Sees working tests as patterns
5. **Progressive**: Moves to next task after repeated failures

## Testing
Run self-improvement loop and verify:
- [ ] LLM suggests different tasks across iterations
- [ ] Failed suggestions are avoided after 3 attempts
- [ ] File paths are validated (no invented files)
- [ ] Similar test examples are provided
- [ ] Loop progresses instead of getting stuck

## Files Modified
- `core/improvement_loop.py`: 
  - Added `failed_suggestions` and `retry_count` tracking
  - Rewrote `_analyze_system()` with LLM + structured context
  - Added `_find_similar_test()` helper
  - Enhanced retry logic in `_run_loop()`
