# CUA System Testing Checklist

## Post-Fix Verification Tests

### ✅ P0 - Critical Fixes

#### 1. Test Truncated File Fix (qwen_generator.py)
**Test:** Create tool using Qwen model
```bash
# Start server
python start.py

# In another terminal
curl -X POST http://localhost:8000/improvement/create-tool \
  -H "Content-Type: application/json" \
  -d '{
    "gap_description": "Create a tool to calculate fibonacci numbers",
    "preferred_tool_name": "FibonacciTool"
  }'
```

**Expected:**
- ✅ No syntax errors
- ✅ Tool created successfully
- ✅ Multi-stage generation completes
- ✅ Skeleton and handlers generated

**Verify:**
```bash
# Check tool file exists
ls tools/experimental/FibonacciTool.py

# Check for complete class definition
grep -A 5 "def _handle_" tools/experimental/FibonacciTool.py
```

---

#### 2. Test Autonomous Agent Wiring
**Test:** Execute multi-step goal
```bash
curl -X POST http://localhost:8000/agent/goal \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "List files in current directory",
    "success_criteria": ["Files listed"],
    "max_iterations": 3,
    "session_id": "test_session_1"
  }'
```

**Expected:**
- ✅ Plan generated
- ✅ Steps executed via orchestrator
- ✅ Goal achieved
- ✅ No "Agent not initialized" error

**Verify:**
```bash
# Check execution logs
sqlite3 data/tool_executions.db "SELECT * FROM executions ORDER BY timestamp DESC LIMIT 5"
```

---

#### 3. Test Execution Engine Routing
**Test:** Execute step with orchestrator
```python
# In Python console
from core.execution_engine import ExecutionEngine
from core.task_planner import TaskStep
from tools.capability_registry import CapabilityRegistry
from core.tool_orchestrator import ToolOrchestrator

registry = CapabilityRegistry()
orchestrator = ToolOrchestrator(registry=registry)
engine = ExecutionEngine(registry, tool_orchestrator=orchestrator)

# Create test step
step = TaskStep(
    step_id="test_1",
    description="List directory",
    tool_name="FilesystemTool",
    operation="list_directory",
    parameters={"path": "."},
    dependencies=[],
    expected_output="File list"
)

# Execute
from core.execution_engine import ExecutionState, ExecutionPlan
plan = ExecutionPlan(goal="test", steps=[step], estimated_duration=5, complexity="simple")
state = ExecutionState(plan=plan)
result = engine._execute_step(step, state)

print(f"Status: {result.status}")
print(f"Output: {result.output}")
```

**Expected:**
- ✅ Step executes through orchestrator
- ✅ Result normalized correctly
- ✅ Execution logged

---

### ✅ P1 - Major Functionality Fixes

#### 4. Test Error Recovery in Agent
**Test:** Goal that fails then succeeds
```bash
curl -X POST http://localhost:8000/agent/goal \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Read a file that does not exist, then list current directory",
    "success_criteria": ["Directory listed"],
    "max_iterations": 3,
    "session_id": "test_session_2"
  }'
```

**Expected:**
- ✅ Iteration 1 fails (file not found)
- ✅ Failure analyzed with details
- ✅ Retry guidance generated
- ✅ Iteration 2 adjusts plan
- ✅ Goal achieved

**Verify:**
```bash
# Check memory system
curl http://localhost:8000/agent/memory/test_session_2
# Should show failure analysis and retry
```

---

#### 5. Test Registry Refresh
**Test:** Create tool then immediately use it
```bash
# Step 1: Create tool
curl -X POST http://localhost:8000/improvement/create-tool \
  -H "Content-Type: application/json" \
  -d '{
    "gap_description": "Create a tool to reverse strings",
    "preferred_tool_name": "StringReverseTool"
  }'

# Step 2: Immediately use in goal (no restart)
curl -X POST http://localhost:8000/agent/goal \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Use StringReverseTool to reverse the word hello",
    "success_criteria": ["String reversed"],
    "max_iterations": 2,
    "session_id": "test_session_3"
  }'
```

**Expected:**
- ✅ Tool created
- ✅ Registry refreshed before planning
- ✅ New tool available in plan
- ✅ No "Unknown tool" error

---

#### 6. Test Dependency Auto-Resolution
**Test:** Create tool requiring external library
```bash
curl -X POST http://localhost:8000/improvement/create-tool \
  -H "Content-Type: application/json" \
  -d '{
    "gap_description": "Create a tool to make HTTP requests using the requests library",
    "preferred_tool_name": "HTTPClientTool"
  }'
```

**Expected:**
- ✅ Missing library detected (requests)
- ✅ Library installed automatically
- ✅ requirements.txt updated
- ✅ Tool created successfully

**Verify:**
```bash
# Check if requests installed
pip show requests

# Check requirements.txt
grep "requests" requirements.txt

# Check creation logs
sqlite3 data/tool_creation.db "SELECT * FROM creation_logs WHERE tool_name='HTTPClientTool'"
```

---

#### 7. Test LLM Verification Parsing
**Test:** Goal with partial completion
```bash
curl -X POST http://localhost:8000/agent/goal \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Open Google and search for AI and take screenshot",
    "success_criteria": [
      "Google opened",
      "Search performed",
      "Screenshot taken"
    ],
    "max_iterations": 2,
    "session_id": "test_session_4"
  }'
```

**Expected:**
- ✅ Verification uses JSON response
- ✅ Correctly identifies missing parts
- ✅ No false positives from keyword matching
- ✅ Detailed missing_parts list

**Verify:**
```bash
# Check verification details
curl http://localhost:8000/agent/memory/test_session_4
# Should show structured verification result
```

---

### ✅ P2 - Quality & Reliability Fixes

#### 8. Test Evolution Backup & Rollback
**Test:** Evolution with backup creation
```bash
# Step 1: Start evolution
curl -X POST http://localhost:8000/evolution/start \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "ContextSummarizerTool",
    "user_prompt": "Improve error handling"
  }'

# Step 2: Check backup created
ls -la data/tool_backups/ | grep ContextSummarizerTool

# Step 3: Reject evolution (if needed)
curl -X POST http://localhost:8000/evolution/reject \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "ContextSummarizerTool"
  }'

# Step 4: Verify rollback
diff tools/experimental/ContextSummarizerTool.py data/tool_backups/ContextSummarizerTool_*.py.bak
```

**Expected:**
- ✅ Backup created before evolution
- ✅ Backup has timestamp
- ✅ Rollback restores original
- ✅ No broken code left

---

#### 9. Test Parameter Resolution Validation
**Test:** Plan with step references
```python
# In Python console
from core.execution_engine import ExecutionEngine, ExecutionState, StepResult, StepStatus
from core.task_planner import ExecutionPlan, TaskStep

# Create mock state with completed step
plan = ExecutionPlan(goal="test", steps=[], estimated_duration=5, complexity="simple")
state = ExecutionState(plan=plan)

# Add completed step with output
state.step_results["step_1"] = StepResult(
    step_id="step_1",
    status=StepStatus.COMPLETED,
    output={"url": "https://google.com", "status": "success"}
)

# Test parameter resolution
engine = ExecutionEngine(None)

# Valid reference
params1 = {"target": "$step.step_1.url"}
resolved1 = engine._resolve_parameters(params1, state)
print(f"Resolved: {resolved1}")  # Should be {"target": "https://google.com"}

# Invalid field
params2 = {"target": "$step.step_1.invalid_field"}
try:
    resolved2 = engine._resolve_parameters(params2, state)
except ValueError as e:
    print(f"Error (expected): {e}")  # Should list available fields

# Missing step
params3 = {"target": "$step.step_999.url"}
try:
    resolved3 = engine._resolve_parameters(params3, state)
except ValueError as e:
    print(f"Error (expected): {e}")  # Should say step not found
```

**Expected:**
- ✅ Valid references resolve correctly
- ✅ Invalid fields show available fields
- ✅ Missing steps show clear error
- ✅ Type mismatches explained

---

#### 10. Test Error Recovery Config
**Test:** Verify error recovery initialized
```python
# In Python console
from core.execution_engine import ExecutionEngine
from tools.capability_registry import CapabilityRegistry

registry = CapabilityRegistry()
engine = ExecutionEngine(registry)

# Check error recovery exists
print(f"Error recovery: {engine.error_recovery}")
print(f"Max retries: {engine.error_recovery.config.max_retries}")
print(f"Strategy: {engine.error_recovery.config.strategy}")
```

**Expected:**
- ✅ Error recovery initialized
- ✅ Config values correct
- ✅ Strategy set to RETRY

---

## Integration Tests

### Test 1: End-to-End Tool Creation
```bash
# Create tool with dependencies → Use in goal
curl -X POST http://localhost:8000/improvement/create-tool \
  -H "Content-Type: application/json" \
  -d '{
    "gap_description": "Create a tool to fetch weather data from an API",
    "preferred_tool_name": "WeatherTool"
  }'

# Wait for creation to complete, then use it
curl -X POST http://localhost:8000/agent/goal \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Use WeatherTool to get weather for New York",
    "success_criteria": ["Weather data retrieved"],
    "max_iterations": 2,
    "session_id": "test_integration_1"
  }'
```

**Expected:**
- ✅ Tool created with dependencies
- ✅ Registry refreshed
- ✅ Tool available in plan
- ✅ Goal executed successfully

---

### Test 2: Evolution with Failure Recovery
```bash
# Evolve tool → Fail sandbox → Retry → Success
curl -X POST http://localhost:8000/evolution/start \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "DatabaseQueryTool",
    "user_prompt": "Add support for complex queries"
  }'

# Monitor evolution progress
curl http://localhost:8000/evolution/status/DatabaseQueryTool
```

**Expected:**
- ✅ Backup created
- ✅ First attempt may fail sandbox
- ✅ Retry with error feedback
- ✅ Second attempt succeeds
- ✅ Pending approval created

---

### Test 3: Multi-Iteration Goal Achievement
```bash
# Complex goal requiring multiple iterations
curl -X POST http://localhost:8000/agent/goal \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Open Google, search for Wikipedia, navigate to Wikipedia, search for Artificial Intelligence, take screenshot",
    "success_criteria": [
      "Google opened",
      "Wikipedia searched",
      "Wikipedia page opened",
      "AI article found",
      "Screenshot captured"
    ],
    "max_iterations": 5,
    "session_id": "test_integration_3"
  }'
```

**Expected:**
- ✅ Plan generated with all steps
- ✅ Steps execute in order
- ✅ Failures analyzed
- ✅ Plan adjusted on retry
- ✅ All criteria met

---

## Performance Tests

### Test 1: Registry Refresh Overhead
```python
import time
from tools.capability_registry import CapabilityRegistry

registry = CapabilityRegistry()

# Measure refresh time
start = time.time()
registry.refresh()
end = time.time()

print(f"Refresh time: {(end - start) * 1000:.2f}ms")
# Should be < 20ms
```

### Test 2: Dependency Check Overhead
```python
import time
from core.dependency_checker import DependencyChecker

checker = DependencyChecker()

code = """
import requests
from bs4 import BeautifulSoup

class TestTool:
    def execute(self):
        self.services.http.get("url")
"""

start = time.time()
report = checker.check_code(code)
end = time.time()

print(f"Check time: {(end - start) * 1000:.2f}ms")
# Should be < 100ms
```

### Test 3: Backup Creation Overhead
```python
import time
from pathlib import Path
from core.tool_evolution.flow import ToolEvolutionOrchestrator

# Mock orchestrator
class MockOrchestrator:
    def _create_backup(self, tool_name, tool_path):
        from pathlib import Path
        import shutil
        from datetime import datetime
        
        tool_file = Path(tool_path)
        backup_dir = Path("data/tool_backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{tool_name}_{timestamp}.py.bak"
        backup_path = backup_dir / backup_name
        
        start = time.time()
        shutil.copy2(tool_file, backup_path)
        end = time.time()
        
        return (end - start) * 1000

orch = MockOrchestrator()
backup_time = orch._create_backup("TestTool", "tools/experimental/ContextSummarizerTool.py")
print(f"Backup time: {backup_time:.2f}ms")
# Should be < 10ms
```

---

## Regression Tests

### Test 1: Existing Tools Still Work
```bash
# Test core tools
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "List files in current directory",
    "session_id": "regression_1"
  }'
```

**Expected:**
- ✅ FilesystemTool works
- ✅ No errors
- ✅ Response generated

### Test 2: Existing Evolution Flow Works
```bash
# Test evolution without new features
curl -X POST http://localhost:8000/evolution/start \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "LocalRunNoteTool",
    "user_prompt": "Improve documentation"
  }'
```

**Expected:**
- ✅ Evolution starts
- ✅ Backup created (new feature)
- ✅ Analysis completes
- ✅ Proposal generated
- ✅ Pending approval created

### Test 3: Chat Mode Still Works
```bash
# Test regular chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the capital of France?",
    "session_id": "regression_3"
  }'
```

**Expected:**
- ✅ LLM responds
- ✅ No tool calling
- ✅ Conversation mode works

---

## Checklist Summary

### Critical (P0) - Must Pass
- [ ] Qwen generator completes without errors
- [ ] Autonomous agent executes plans
- [ ] Execution engine uses orchestrator

### Major (P1) - Should Pass
- [ ] Error recovery analyzes failures
- [ ] Registry refreshes before planning
- [ ] Dependencies auto-install
- [ ] Verification uses JSON parsing

### Quality (P2) - Nice to Have
- [ ] Backups created before evolution
- [ ] Parameter resolution validates
- [ ] Error recovery config initialized

### Integration - End-to-End
- [ ] Tool creation → immediate use works
- [ ] Evolution with retry succeeds
- [ ] Multi-iteration goals achieve

### Performance - Acceptable Overhead
- [ ] Registry refresh < 20ms
- [ ] Dependency check < 100ms
- [ ] Backup creation < 10ms

### Regression - No Breaking Changes
- [ ] Existing tools work
- [ ] Existing evolution works
- [ ] Chat mode works

---

## Test Results Template

```markdown
## Test Run: [Date]

### Environment
- OS: [Windows/Linux/Mac]
- Python: [Version]
- CUA Version: v1.0 (Post-Fix)

### P0 Tests
- [ ] ✅ Qwen generator: PASS
- [ ] ✅ Agent wiring: PASS
- [ ] ✅ Orchestrator routing: PASS

### P1 Tests
- [ ] ✅ Error recovery: PASS
- [ ] ✅ Registry refresh: PASS
- [ ] ✅ Dependency resolution: PASS
- [ ] ✅ Verification parsing: PASS

### P2 Tests
- [ ] ✅ Backup/rollback: PASS
- [ ] ✅ Parameter validation: PASS
- [ ] ✅ Error recovery config: PASS

### Integration Tests
- [ ] ✅ End-to-end creation: PASS
- [ ] ✅ Evolution retry: PASS
- [ ] ✅ Multi-iteration goal: PASS

### Performance Tests
- [ ] ✅ Registry refresh: 12ms (< 20ms) ✓
- [ ] ✅ Dependency check: 45ms (< 100ms) ✓
- [ ] ✅ Backup creation: 6ms (< 10ms) ✓

### Regression Tests
- [ ] ✅ Existing tools: PASS
- [ ] ✅ Existing evolution: PASS
- [ ] ✅ Chat mode: PASS

### Overall Status
✅ ALL TESTS PASSED

### Notes
[Any observations or issues]
```

---

**Last Updated:** 2024
**Version:** CUA v1.0 (Post-Fix)
