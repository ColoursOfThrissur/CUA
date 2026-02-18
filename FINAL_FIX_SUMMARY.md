# Final Fix Summary - Qwen Code Generation

## Root Cause
`_format_prompt()` had `expect_json=True` as default, causing ALL prompts (including code generation) to get `\n\n```json\n` appended. This confused Qwen into generating JSON-wrapped code or entire files instead of clean Python code blocks.

## Critical Fix
**planner/llm_client.py line 169:**
```python
# BEFORE (WRONG):
def _format_prompt(self, content: str, expect_json: bool = True) -> str:

# AFTER (CORRECT):
def _format_prompt(self, content: str, expect_json: bool = False) -> str:
```

## Test Results
✅ **test_cua_flow.py** - Both tests passed:
- Block Insert: 13 lines, 62 tokens, 11.5s - VALID
- Method Rewrite: 12 lines, 123 tokens, 3.9s - VALID

## All Files Modified

### 1. planner/llm_client.py
- Changed `expect_json` default from `True` to `False`
- Added `expect_json` parameter to `_format_prompt()` and `_call_llm()`
- Enhanced logging: full prompt/response, metadata (expect_json, token counts, endings)
- Added debug logging for call parameters

### 2. core/diff_generator.py
- Pass `expect_json=False` for all code generation
- Token limits: 512 for line edits and block inserts
- Enhanced validation logging with code previews
- Better error messages showing what was generated

### 3. core/orchestrated_code_generator.py
- Pass `expect_json=False` for method rewrites, new files, test files
- Token limits: 1024 (methods), 1536 (tests), 2048 (new files)

### 4. core/proposal_generator.py
- Pass `expect_json=False` for self-correction prompts

### 5. core/task_analyzer.py
- Pass `expect_json=True` for task analysis (expects JSON array)

### 6. api/improvement_api.py
- Pass `expect_json=False` for test calls

## Logging Improvements

### Before:
- Truncated to 500 chars (confusing for debugging)
- No metadata about expect_json flag
- No token counts

### After:
- Full prompt and response logged
- Metadata includes:
  - `expect_json` flag (critical for debugging)
  - `max_tokens` setting
  - Token counts (prompt and generated)
  - Prompt/response endings (last 100 chars)
  - Full lengths
- Debug logging for:
  - LLM call parameters
  - Validation failures with code previews
  - Truncation detection with full response

## Expected Behavior After Fix

### Code Generation (expect_json=False):
```
Prompt: "Add code block...\n\nOutput ONLY the code block:"
Response: "```python\n    code here\n```"
```

### Task Analysis (expect_json=True):
```
Prompt: "Analyze codebase...\n\n```json\n"
Response: "[{\"task_type\": \"fix_bug\", ...}]"
```

## Verification Steps
1. Restart CUA system
2. Check logs for `expect_json=False` in code generation calls
3. Verify responses are clean Python (no JSON wrapping)
4. Confirm validation passes (3-20 lines for blocks)
5. Check no "Response truncated" errors

## Rollback
If issues occur, revert:
```bash
git checkout HEAD -- planner/llm_client.py core/diff_generator.py core/orchestrated_code_generator.py core/proposal_generator.py core/task_analyzer.py api/improvement_api.py
```

## Performance Metrics (from test)
- Block insert: ~12s, ~60 tokens
- Method rewrite: ~4s, ~120 tokens
- No truncation, complete code
- Validation passes on first attempt
