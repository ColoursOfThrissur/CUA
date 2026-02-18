# Qwen Code Generation Fix Summary

## Root Cause
The `_format_prompt()` method in `llm_client.py` was adding `\n\n```json\n` to **ALL** prompts, including code generation prompts. This confused Qwen into thinking it should output JSON instead of Python code, causing:
- Malformed responses (JSON-wrapped code)
- Truncated responses (hitting token limits while trying to format as JSON)
- Incomplete code blocks

## Test Results
Comprehensive testing (`test_qwen_limits.py`) proved:
- ✅ Qwen works perfectly with 2048 token limit
- ✅ Generates complete, valid code when prompted correctly
- ✅ Response times: 4-32s depending on complexity
- ✅ No VRAM issues with proper model unloading

## Fixes Applied

### 1. **llm_client.py** - Core Fix
- Added `expect_json` parameter to `_format_prompt()` and `_call_llm()`
- Only adds ```json hint when `expect_json=True`
- Default is `expect_json=False` for code generation

### 2. **diff_generator.py** - Code Generation
- Pass `expect_json=False` for all code generation calls
- Increased token limits: 256→512 (line edits and blocks)
- Optimized for 30-40 line code blocks

### 3. **orchestrated_code_generator.py** - Method Rewrites
- Pass `expect_json=False` for method rewrites, new files, test files
- Token limits: 1024 (methods), 1536 (tests), 2048 (new files)

### 4. **proposal_generator.py** - Self-Correction
- Pass `expect_json=False` for indentation fix prompts

### 5. **task_analyzer.py** - Analysis
- Pass `expect_json=True` for task analysis (expects JSON array)

### 6. **improvement_api.py** - Test Endpoint
- Pass `expect_json=False` for test calls

### 7. **Model Unloading** (Already Fixed)
- Added logging to `_unload_model()` in llm_client.py
- Confirmed working in loop_controller.py

## Token Limits (Optimized for RTX 3060 12GB)

| Use Case | Tokens | Rationale |
|----------|--------|-----------|
| Line edits | 512 | ~10-15 lines |
| Block inserts | 512 | ~30-40 lines |
| Method rewrites | 1024 | ~60-80 lines |
| Test files | 1536 | ~100-120 lines |
| New files | 2048 | ~150-200 lines |
| Context window | 8192 | Max for 12GB VRAM |

## Expected Results
- ✅ Qwen generates clean Python code (no JSON wrapping)
- ✅ Complete responses (no mid-line truncation)
- ✅ Proper code fences (```python ... ```)
- ✅ Faster generation (no JSON formatting overhead)
- ✅ Better validation (code parses correctly)

## Testing Recommendations
1. Run self-improvement loop
2. Monitor logs for "expect_json" parameter usage
3. Check session logs for clean Python responses
4. Verify no more "Response truncated" errors
5. Confirm code validation passes

## Rollback Plan
If issues occur, revert changes to:
- `planner/llm_client.py` (_format_prompt, _call_llm)
- `core/diff_generator.py`
- `core/orchestrated_code_generator.py`
- `core/proposal_generator.py`
- `core/task_analyzer.py`
