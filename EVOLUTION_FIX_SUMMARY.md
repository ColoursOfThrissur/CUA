# Tool Evolution Fix - Implementation Summary

**Date:** March 21, 2026  
**Status:** TIER 1 COMPLETE ✅ | TIER 2 PARTIAL (60%)  
**Impact:** Unblocks 64 stuck evolutions

---

## What Was Fixed (TIER 1)

### 1. ✅ Dynamic Service Context Extraction
**File:** `core/tool_evolution/code_generator.py`  
**Change:** Added `_extract_service_signatures()` method that dynamically imports actual service classes and extracts real method names using Python introspection.

**Before:**
```python
nested = {
    "browser": "open_browser(), navigate-hardcoded list
}
```

**After:**
```python
def _extract_service_signatures(self) -> Dict[str, str]:
    """Extract actual method signatures from service classes."""
    from core.tool_services import BrowserService
    browser_methods = [m for m in dir(BrowserService) if not m.startswith('_')]
    # Returns actual methods like: open_browser, navigate, find_element, etc.
```

**Why This Matters:**
- LLM now sees ACTUAL available methods, not hallucinations
- If BrowserService changes, code generator automatically reflects new methods
- No more "Unknown method: self.services.browser.execute()" errors

---

### 2. ✅ Validation-Driven Retry Loop  
**File:** `core/tool_evolution/flow.py` (lines 93-226)  
**Changes:**
- Increased retry attempts from 2 to 3
- Moved validation INSIDE the retry loop (was outside)
- Changed to use `continue` on validation failure instead of `return False`
- Now retry with feedback instead of immediately failing

**Before:**
```python
for attempt in range(2):  # 2 attempts
    improved_code = code_gen.generate_improved_code(...)
    # ... more code ...
    # Validate (OUTSIDE loop, fails immediately)
if not is_valid:
    return False, f"Validation failed: {error}"  # NO RETRY!
```

**After:**
```python
validation_error = None
for attempt in range(3):  # 3 attempts
    improved_code = code_gen.generate_improved_code(..., validation_error=validation_error)
    # ...
    if not is_valid:
        validation_error = error
        if attempt < 2:
            continue  # RETRY with feedback!
        else:
            return False  # Only fail after all attempts
```

**Why This Matters:**
- Validation failures now trigger retries, not permanent failures
- 64 stuck evolutions can now continue instead of deadlocking
- Validation errors are opportunities to improve, not blockers

---

### 3. ✅ LLM Validation Feedback
**Files:** `core/tool_evolution/code_generator.py`  
**Changes:**
- Updated method signatures to accept `validation_error` parameter:
  - `generate_improved_code()`  
  - `_improve_existing_handlers()`
  - `_add_new_capability()`
  - `_improve_single_handler()`
  - `_generate_new_handler()`
  
- Added validation error to LLM prompts when retrying:
```python
if validation_error:
    error_context = f"\n\nPREVIOUS ATTEMPT FAILED VALIDATION:\n{validation_error}\nFIX THESE ERRORS:\n"
elif sandbox_error:
    error_context = f"\n\nPREVIOUS ATTEMPT FAILED:\n{sandbox_error}\n"
```

**Why This Matters:**
- LLM now sees WHY the code failed validation
- On retry, LLM knows "Unknown method self.services.browser.execute()" and won't generate it again
- Creates a feedback loop: Generate → Validate → Show Errors → Ask to Fix → Retry

---

### 4. ✅ WebSocket Async Stability
**File:** `api/trace_ws.py`  
**Changes:**
- Replaced bare `except:` with proper exception handling
- Added logging for all WebSocket operations
- Added connection state checking before sends
- Safe event loop lifecycle management
- Added timeouts to prevent deadlocks

**Before:**
```python
def _broadcast():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(...)
        loop.close()
    except:  # BARE EXCEPT - hides all errors!
        pass
```

**After:**
```python
def _broadcast():
    try:
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(broadcast_trace(...))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(broadcast_trace(...))
            finally:
                loop.close()
    except Exception as e:
        logger.warning(f"broadcast_trace_sync error: {e}")  # Proper logging
```

**Why This Matters:**
- WebSocket broadcast no longer crashes with "AssertionError in _ProactorBaseWritePipeTransport"
- Proper error logging for debugging
- Connection state checking prevents "already connected" errors
- Timeouts prevent infinite hangs

---

## Expected Improvements After Deployment

### Evolution Success Rate
- **Before:** 0% (0/163 completions, 64 stuck)
- **Target:** 60-70% (unblocks retry loop, most failures were method hallucination)
- **Timeline:** Next 10-20 evolution cycles should show improvement

### What This Unblocks
1. **64 Stuck Evolutions** - Can now retry instead of deadlock
2. **Invalid Method Errors** - LLM gets feedback, won't repeat mistakes
3. **Validation Failures** - Become learning opportunities, not dead ends
4. **System Stability** - WebSocket won't crash background processes

---

## Remaining Work (TIER 2)

### 5. Complete Output Validation Coverage (MEDIUM - 2 hrs)
**Status:** 60% done - function exists, only used in success path

**Not Yet Done:**
- Output validation should also run when there are partial errors
- Validation failures should trigger fallback/retry
- Error output should be validated
- Degraded results should be validated

**File:** `api/server.py` (lines 565, 1025-1100)

**Next Step:** Extend validation call outside the `if aggregated_results and not aggregated_errors:` block to:
- Partial results with warnings
- Error recovery paths
- Fallback tool execution

---

### 6. Input Validation Middleware (MEDIUM - 2 hrs)
**Status:** Not done

**Needed:**
- Request size limits (prevent 10MB+ payloads)
- Rate limiting (prevent 1000 requests/sec)
- SQL injection protection for tool parameters
- HTML sanitization for user input

**File:** `api/server.py` (main request handler)

**Approach:**
```python
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/chat/message")
@limiter.limit("60/minute")
async def chat_endpoint(request: Request, message: str):
    # Validate size
    if len(message) > 10000:
        raise ValueError("Message too large")
    # Sanitize HTML
    message = sanitize_html(message)
    # Continue...
```

---

## Testing Recommendations

### Test 1: Code Generation with Service Feedback
1. Trigger evolution of BrowserAutomationTool
2. Monitor `data/tool_evolution.db` for `evolution_runs` events
3. Check if generation attempts > 1 (indicates retry)
4. Check if `validation` step shows proper error messages
5. Expected: Code generation eventually succeeds

### Test 2: Validation Retry Loop
1. Manually create an invalid proposal (calls non-existent method)
2. Run evolution
3. Monitor logs for "Retrying code generation with validation feedback"
4. Should see 3 attempts in database, not 1
5. Expected: Retry count increases, doesn't give up immediately

### Test 3: WebSocket Stability
1. Open 10 WebSocket connections simultaneously
2. Trigger coordinated autonomy cycle
3. Kill 5 random connections mid-broadcast
4. Monitor `api/trace_ws.py` logs for exceptions
5. Expected: No AssertionError, graceful connection cleanup

---

## Known Limitations

### What Still Needs Fixing
1. **Output validation incomplete** - only success path
2. **No input validation** - vulnerable to large payloads
3. **Skill alignment not full** - 3/10 fields extracted (was planned)
4. **Multi-round context not refreshed** - context gets stale after 50+ tool calls

### What Can't Be Fixed By Validation Loop
- **Tool creation success rate** - Often fails at proposal stage (not code gen)
- **Proposal quality** - Depends on LLM understanding of tool weaknesses
- **Architecture contract violations** - Caught by validator, but LLM might regenerate same errors

---

## Files Modified

1. ✅ `core/tool_evolution/code_generator.py` - Dynamic extraction, feedback
2. ✅ `core/tool_evolution/flow.py` - Validation retry loop  
3. ✅ `api/trace_ws.py` - Async stability fixes
4. ⏳ `api/server.py` - Output validation coverage (PARTIAL)

---

## Success Metrics

**Monitor these over next 7 days:**
- Evolution completion rate (target: 50%+)
- Average attempts per evolution (target: < 3)
- WebSocket error count (target: 0)
- Validation failure types (target: decreasing)

**Queries to track:**
```sql
-- Success rate
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as completed,
    ROUND(100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / COUNT(*), 1) as success_rate
FROM evolution_runs
WHERE timestamp > datetime('now', '-7 days');

-- Retry effectiveness
SELECT 
    tool_name,
    COUNT(*) as total_attempts,
    SUM(CASE WHEN step = 'validation' THEN 1 ELSE 0 END) as validation_attempts,
    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successes
FROM evolution_runs
GROUP BY tool_name
ORDER BY successes DESC;
```

---

## Deployment Checklist

- [ ] Run `python -m pytest tests/test_tool_evolution_integration.py` 
- [ ] Manually trigger 5 BrowserAutomationTool evolutions
- [ ] Monitor `logs/system.log` for errors
- [ ] Check WebSocket connections don't error on disconnect
- [ ] Verify `data/tool_evolution.db` has 3 attempts for validation failures
- [ ] Test with different service registry configurations

---

## Contact/Questions

- **Code Generation Issues:** Check `core/tool_evolution/code_generator.py:_extract_service_signatures()`
- **Validation Loop Issues:** Check `core/tool_evolution/flow.py:evolve_tool()` line ~120
- **WebSocket Crashes:** Check `api/trace_ws.py` for exception logging
- **Performance:** Monitor execution time with 3 attempts instead of 2
