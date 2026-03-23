# Coordinated Autonomy & Tool Creation Issues

## Issues Found from Logs

### 1. **LLM Returning Empty Response for Tool Spec**
```
LLM returned empty response for tool spec
[FLOW DEBUG] Spec generation returned: False
```

**Root Cause**: The LLM is returning empty/None responses during spec generation.

**Location**: `core/tool_creation/spec_generator.py` line ~60-65

**Potential Causes**:
- LLM timeout or connection issue
- Prompt too complex or unclear
- Model not responding with valid JSON
- Temperature/token settings causing empty output

**Fix Needed**:
- Add retry logic with exponential backoff
- Simplify prompt if too complex
- Add fallback to simpler prompt format
- Log the actual LLM response before JSON extraction
- Check if `llm_client._call_llm()` is returning None vs empty string

### 2. **AsyncIO Assertion Error**
```python
Exception in callback _ProactorBaseWritePipeTransport._loop_writing(<_OverlappedF...hed result=38>)
Traceback (most recent call last):
  File "C:\Users\derik\AppData\Local\Programs\Python\Python312\Lib\asyncio\events.py", line 88, in _run
    self._context.run(self._callback, *self._args)
  File "C:\Users\derik\AppData\Local\Programs\Python\Python312\Lib\asyncio\proactor_events.py", line 382, in _loop_writing
    assert f is self._write_fut
           ^^^^^^^^^^^^^^^^^^^^
AssertionError
```

**Root Cause**: Windows-specific asyncio issue with pipe transport

**Location**: This is a Python asyncio internal issue, likely triggered by:
- `api/trace_ws.py` WebSocket broadcasting
- Coordinated autonomy engine's async loop
- Multiple concurrent async operations

**Fix Needed**:
- Wrap WebSocket broadcasts in try-except
- Use `asyncio.create_task()` with proper error handling
- Consider using `asyncio.Queue` for message passing instead of direct callbacks
- Add connection state checks before writing to WebSocket

### 3. **Tool Creation Flow Issues**

#### 3.1 No Retry on Empty LLM Response
**Location**: `core/tool_creation/spec_generator.py` line 60-65

Current code:
```python
response = llm_client._call_llm(prompt, temperature=0.3, expect_json=True)
if not response:
    logger.warning("LLM returned empty response for tool spec")
    return None
```

**Problem**: Single attempt, no retry, no fallback

**Fix Needed**:
```python
max_retries = 3
for attempt in range(max_retries):
    response = llm_client._call_llm(prompt, temperature=0.3, expect_json=True)
    if response:
        break
    if attempt < max_retries - 1:
        logger.warning(f"LLM returned empty response (attempt {attempt+1}/{max_retries}), retrying...")
        time.sleep(1)
else:
    logger.error("LLM returned empty response after all retries")
    return None
```

#### 3.2 JSON Extraction Failure Not Logged
**Location**: `core/tool_creation/spec_generator.py` line 66-69

Current code:
```python
response = llm_client._extract_json(response)
if not response:
    logger.warning("Failed to extract JSON from LLM response")
    return None
```

**Problem**: Doesn't log what the LLM actually returned

**Fix Needed**:
```python
raw_response = response
response = llm_client._extract_json(response)
if not response:
    logger.warning(f"Failed to extract JSON from LLM response. Raw response: {raw_response[:500]}")
    return None
```

### 4. **Coordinated Autonomy Engine Issues**

#### 4.1 No Error Recovery in Cycle Loop
**Location**: `core/coordinated_autonomy_engine.py` line 56-72

Current code catches exceptions but doesn't attempt recovery:
```python
except Exception as exc:
    self.last_error = str(exc)
    self.last_cycle = {
        "success": False,
        "error": str(exc),
        "finished_at": self._utc_now(),
    }
    broadcast_trace_sync("auto", f"Coordinated cycle failed: {exc}", "error", {})
```

**Problem**: 
- Continues to next cycle without analyzing failure
- No retry logic for transient failures
- No circuit breaker for repeated failures

**Fix Needed**:
- Add failure classification (transient vs permanent)
- Implement exponential backoff for transient failures
- Add circuit breaker after N consecutive failures
- Log detailed error context for debugging

#### 4.2 Quality Gate Pausing Too Aggressively
**Location**: `core/coordinated_autonomy_engine.py` line 62-68

```python
if self.last_cycle.get("quality_gate", {}).get("should_pause"):
    self.paused_reason = self.last_cycle["quality_gate"].get("reason")
    broadcast_trace_sync(...)
    self.running = False
    break
```

**Problem**: Stops entire coordinated autonomy on low-value cycles

**Fix Needed**:
- Make pause threshold configurable
- Add "degraded mode" instead of full stop
- Allow manual override to continue despite low value
- Add notification instead of auto-pause

### 5. **Architecture Issues with New Creation/Evolution Process**

#### 5.1 Service Resolution Happens Too Late
**Location**: `core/tool_creation/flow.py` line 150-180

Services are resolved AFTER code generation, causing validation failures.

**Fix Needed**:
- Move service resolution to spec generation phase
- Pass available services to code generator
- Block creation early if critical services missing

#### 5.2 Sandbox Retry Logic Doesn't Update Spec
**Location**: `core/tool_creation/flow.py` line 280-320

Retries regenerate code but don't update the tool_spec with learned corrections.

**Fix Needed**:
```python
# After each retry, update spec with corrections
tool_spec['_previous_errors'] = tool_spec.get('_previous_errors', [])
tool_spec['_previous_errors'].append({
    'attempt': attempt,
    'error': error_msg,
    'validation_error': validation_error
})
```

#### 5.3 No Validation of LLM Client State
**Location**: Multiple files

Code assumes `llm_client` is always available and working.

**Fix Needed**:
- Add health check before expensive operations
- Implement fallback to cached/default specs
- Add circuit breaker for LLM calls

## Recommended Fixes Priority

### High Priority (Blocking Issues)
1. **Fix LLM empty response** - Add retry logic + logging
2. **Fix AsyncIO assertion** - Wrap WebSocket broadcasts in error handling
3. **Add LLM health check** - Validate client before operations

### Medium Priority (Quality Issues)
4. **Improve error recovery** - Add retry logic to coordinated autonomy
5. **Better logging** - Log raw LLM responses for debugging
6. **Service resolution timing** - Move to spec generation phase

### Low Priority (Enhancements)
7. **Quality gate tuning** - Make thresholds configurable
8. **Spec learning** - Update spec with retry learnings
9. **Circuit breaker** - Add for repeated LLM failures

## Testing Recommendations

### Unit Tests Needed
1. `test_spec_generator_empty_response()` - Test retry logic
2. `test_spec_generator_invalid_json()` - Test JSON extraction
3. `test_coordinated_autonomy_failure_recovery()` - Test error handling
4. `test_tool_creation_service_resolution()` - Test service timing

### Integration Tests Needed
1. `test_full_tool_creation_with_llm_failure()` - End-to-end with failures
2. `test_coordinated_autonomy_cycle()` - Full cycle with mocked components
3. `test_websocket_broadcast_error_handling()` - WebSocket error scenarios

## Architecture Recommendations

### 1. Separate LLM Client Health Monitoring
Create `core/llm_health_monitor.py`:
- Track success/failure rates
- Implement circuit breaker
- Provide health status API
- Auto-retry with backoff

### 2. Improve Observability
- Add structured logging with correlation IDs
- Track LLM call latency and success rates
- Add metrics for tool creation success/failure
- Dashboard for coordinated autonomy health

### 3. Graceful Degradation
- Cache last successful specs
- Provide manual override for quality gates
- Allow partial success (some tools created, some failed)
- Continue with reduced functionality instead of full stop

## Code Changes Needed

### File: `core/tool_creation/spec_generator.py`
- Add retry logic (lines 60-70)
- Log raw LLM responses (line 66)
- Add LLM health check (line 55)

### File: `core/coordinated_autonomy_engine.py`
- Add failure classification (line 56)
- Implement circuit breaker (line 40)
- Make quality gate configurable (line 62)

### File: `api/trace_ws.py`
- Wrap broadcasts in try-except
- Check connection state before writing
- Use asyncio.Queue for message passing

### File: `core/tool_creation/flow.py`
- Move service resolution earlier (line 150)
- Update spec with retry learnings (line 290)
- Add LLM health check (line 100)
