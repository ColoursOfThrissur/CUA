# Computer Use - Observe→Act→Evaluate→Adapt Architecture

## Overview

The computer use system implements a **multi-agent feedback loop** with state-driven adaptation, replacing the monolithic god-object pattern with specialized agents.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  ComputerUseController                      │
│              Orchestrates Feedback Loop                     │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   OBSERVE    │    │     ACT      │    │   EVALUATE   │
│              │───▶│              │───▶│              │
│ Capture      │    │ Execute      │    │ Verify       │
│ State        │    │ Plan         │    │ Results      │
└──────────────┘    └──────────────┘    └──────────────┘
                                                │
                                                │ Failed?
                                                ▼
                                        ┌──────────────┐
                                        │    ADAPT     │
                                        │              │
                                        │ Analyze &    │
                                        │ Replan       │
                                        └──────────────┘
                                                │
                                                │
                                                └──────▶ Loop
```

## Agent Responsibilities

### 1. PlannerAgent
**Single Responsibility**: Intent → Plan

```python
plan_result = planner.generate_plan(
    intent="Open Chrome and search for X",
    context={"screen_summary": "...", "open_windows": [...]}
)
# Returns: {"success": True, "plan": [...], "strategy": "llm_generated"}
```

**Does**:
- Parse user intent
- Generate step-by-step execution plan
- Use skill registry for reusable workflows
- Replan based on failure analysis

**Does NOT**:
- Execute steps
- Verify results
- Analyze failures

### 2. ExecutorAgent
**Single Responsibility**: Plan → Execution Trace

```python
execution_result = executor.execute_plan(
    plan=[...],
    capture_state=True
)
# Returns: {"success": bool, "trace": [...], "final_state": {...}}
```

**Does**:
- Execute plan steps sequentially
- Capture before/after state for each step
- Track execution timing
- Return detailed trace

**Does NOT**:
- Generate plans
- Verify success
- Decide what to do on failure

### 3. VerifierAgent
**Single Responsibility**: Trace → Success/Failure Analysis

```python
verification_result = verifier.verify_execution(execution_result)
# Returns: {"verified": bool, "failure_analysis": {...}, "recommendations": [...]}
```

**Does**:
- Compare before/after screenshots (screen diff)
- Detect state changes
- Classify failure reasons
- Provide actionable recommendations

**Does NOT**:
- Execute actions
- Generate plans
- Decide adaptation strategy

**Screen Diff Algorithm**:
```python
# Pixel-wise comparison
before_img = Image.open(before_path)
after_img = Image.open(after_path)
diff = np.abs(before_arr - after_arr)
similarity = 1.0 - (total_diff / max_diff)
changed = similarity < 0.95  # 5% threshold
```

### 4. CriticAgent
**Single Responsibility**: Failure → Adaptation Strategy

```python
adaptation = critic.analyze_and_adapt(
    original_plan=[...],
    execution_result={...},
    verification_result={...},
    context={...}
)
# Returns: {"adaptation_strategy": "REDETECT_ELEMENTS", "root_cause": "...", "suggested_changes": [...]}
```

**Does**:
- Determine root cause of failure
- Generate adaptation strategy
- Suggest plan modifications
- Learn from failure patterns

**Does NOT**:
- Execute plans
- Verify results
- Generate new plans (delegates to PlannerAgent)

## Feedback Loop Flow

### Cycle 1: Initial Attempt

```
1. OBSERVE
   └─ Capture: screen_summary, open_windows, active_window, resolution

2. PLAN (PlannerAgent)
   └─ Generate: [step1, step2, step3]

3. ACT (ExecutorAgent)
   └─ Execute each step with before/after state capture
   └─ Returns: execution_trace

4. EVALUATE (VerifierAgent)
   └─ Screen diff: before vs after
   └─ Classify: ELEMENT_NOT_FOUND
   └─ Recommend: ["Use detect_ui_elements", "Try alternative description"]

5. ADAPT (CriticAgent)
   └─ Root cause: ENVIRONMENT_CHANGED
   └─ Strategy: REDETECT_ELEMENTS
   └─ Changes: ["Insert detect_ui_elements before step 2"]
```

### Cycle 2: Adapted Attempt

```
1. OBSERVE (re-capture state)
   └─ Context updated with previous_failure info

2. PLAN (PlannerAgent.replan)
   └─ Generate new plan with adaptation applied
   └─ [detect_ui_elements, step1_modified, step2, step3]

3. ACT (ExecutorAgent)
   └─ Execute adapted plan

4. EVALUATE (VerifierAgent)
   └─ Screen diff: 8.5% change detected
   └─ State changes: ["window_changed", "mouse_moved"]
   └─ Verified: TRUE

SUCCESS → Exit loop
```

## Root Cause Classification

| Root Cause | Trigger | Adaptation Strategy |
|------------|---------|---------------------|
| **ENVIRONMENT_CHANGED** | Element not found, screen different | REDETECT_ELEMENTS |
| **TIMING_ISSUE** | Timeout, action too fast | RETRY_WITH_DELAY |
| **MISSING_PREREQUISITE** | Window not focused, state not met | ADD_PREREQUISITE |
| **WRONG_TARGET** | Out of bounds, incorrect coordinates | ALTERNATIVE_APPROACH |
| **NO_EFFECT** | Screen unchanged after action | VERIFY_STATE |
| **TOOL_LIMITATION** | Permission denied, capability missing | ABORT |

## Adaptation Strategies

### RETRY_WITH_DELAY
```python
# Add delays before failed step
modified_plan.insert(failed_step - 1, {
    "tool": "InputAutomationTool",
    "operation": "press_key",
    "params": {"key": "sleep", "duration": 1.0}
})
```

### REDETECT_ELEMENTS
```python
# Insert fresh UI detection
modified_plan.insert(failed_step - 1, {
    "tool": "ScreenPerceptionTool",
    "operation": "detect_ui_elements",
    "params": {"element_types": ["button", "icon", "text"]}
})
```

### ADD_PREREQUISITE
```python
# Insert missing setup step
modified_plan.insert(failed_step - 1, {
    "tool": "SystemControlTool",
    "operation": "focus_window",
    "params": {"title": "target_window"}
})
```

### ALTERNATIVE_APPROACH
```python
# Replace failed step with different method
# Example: click → smart_click
modified_plan[failed_step] = {
    "tool": "InputAutomationTool",
    "operation": "smart_click",  # Uses vision detection
    "params": {"target": "OK button"}
}
```

## State Tracking

### Execution State (per step)
```python
{
    "step": 1,
    "tool": "SystemControlTool",
    "operation": "launch_application",
    "params": {"name": "notepad"},
    "result": {"success": True, "pid": 1234},
    "before_state": {
        "screenshot_path": "output/before_1.png",
        "screenshot_hash": "abc123...",
        "active_window": "Desktop",
        "mouse_position": {"x": 100, "y": 200},
        "timestamp": 1234567890.123
    },
    "after_state": {
        "screenshot_path": "output/after_1.png",
        "screenshot_hash": "def456...",
        "active_window": "Notepad",
        "mouse_position": {"x": 100, "y": 200},
        "timestamp": 1234567890.456
    }
}
```

### Workflow State (global)
```python
{
    "current_intent": "Open Chrome and search for X",
    "cycle_history": [
        {
            "cycle": 1,
            "success": False,
            "plan": [...],
            "execution": {...},
            "verification": {...},
            "adaptation": {...},
            "cycle_time": 2.5
        },
        {
            "cycle": 2,
            "success": True,
            "plan": [...],
            "execution": {...},
            "verification": {...},
            "cycle_time": 3.1
        }
    ]
}
```

## Screen Diff Verification

### Algorithm
```python
def _compute_screen_diff(before_state, after_state):
    before_img = Image.open(before_state["screenshot_path"])
    after_img = Image.open(after_state["screenshot_path"])
    
    # Convert to numpy arrays
    before_arr = np.array(before_img)
    after_arr = np.array(after_img)
    
    # Pixel-wise difference
    diff = np.abs(before_arr.astype(float) - after_arr.astype(float))
    total_diff = np.sum(diff)
    max_diff = before_arr.size * 255
    
    # Similarity score
    similarity = 1.0 - (total_diff / max_diff)
    
    return {
        "changed": similarity < 0.95,  # 5% threshold
        "similarity": round(similarity, 3),
        "diff_percentage": round((1.0 - similarity) * 100, 2)
    }
```

### Interpretation
- **similarity > 0.95**: No significant change (action likely failed)
- **0.90 < similarity < 0.95**: Minor change (partial success)
- **similarity < 0.90**: Significant change (likely success)

## Failure Pattern Learning

### Pattern Storage
```python
{
    "failure_reason": "ELEMENT_NOT_FOUND",
    "root_cause": "ENVIRONMENT_CHANGED",
    "strategy": {"type": "REDETECT_ELEMENTS", "confidence": 0.9},
    "context": {"active_window": "Chrome", "screen_summary": "..."},
    "timestamp": 1234567890.123
}
```

### Trend Analysis
```python
trends = critic.analyze_failure_trends()
# Returns:
{
    "trends": {
        "failure_reasons": {
            "ELEMENT_NOT_FOUND": 15,
            "WINDOW_NOT_FOCUSED": 8,
            "TIMEOUT": 3
        },
        "adaptation_strategies": {
            "REDETECT_ELEMENTS": 12,
            "ADD_PREREQUISITE": 7,
            "RETRY_WITH_DELAY": 4
        }
    },
    "insights": [
        "Most common failure: ELEMENT_NOT_FOUND (15 occurrences)",
        "Most used strategy: REDETECT_ELEMENTS (12 times)"
    ],
    "total_failures": 26
}
```

## Usage Examples

### Simple Task
```python
controller = ComputerUseController(orchestrator=orchestrator)

result = controller.execute("automate_task", 
    intent="Take a screenshot and save it"
)

# Result:
{
    "success": True,
    "cycles": 1,
    "final_result": {
        "plan": [...],
        "execution": {...},
        "verification": {"verified": True, "confidence": 0.9}
    }
}
```

### Complex Task with Adaptation
```python
result = controller.execute("automate_task",
    intent="Open Chrome, navigate to google.com, and search for 'AI agents'"
)

# Result:
{
    "success": True,
    "cycles": 2,  # Failed once, adapted, succeeded
    "cycle_history": [
        {
            "cycle": 1,
            "success": False,
            "adaptation": {
                "root_cause": "WINDOW_NOT_FOCUSED",
                "strategy": "ADD_PREREQUISITE"
            }
        },
        {
            "cycle": 2,
            "success": True,
            "verification": {"verified": True}
        }
    ]
}
```

### Get Failure Insights
```python
insights = controller.execute("get_failure_insights")

# Result:
{
    "success": True,
    "trends": {...},
    "insights": [
        "Most common failure: ELEMENT_NOT_FOUND (15 occurrences)",
        "Most used strategy: REDETECT_ELEMENTS (12 times)"
    ],
    "recent_patterns": [...]
}
```

## Key Differences from Old Architecture

| Aspect | Old (God Object) | New (Multi-Agent) |
|--------|------------------|-------------------|
| **Planning** | Controller does everything | PlannerAgent (single responsibility) |
| **Execution** | Inline in controller | ExecutorAgent with state capture |
| **Verification** | `return True` | VerifierAgent with screen diff |
| **Adaptation** | Retry same plan | CriticAgent analyzes + PlannerAgent replans |
| **State** | In-memory dict | Before/after state per step |
| **Feedback** | None | Full Observe→Act→Evaluate→Adapt loop |
| **Learning** | None | Failure pattern tracking + trend analysis |

## Performance Characteristics

| Metric | Value |
|--------|-------|
| **Cycle overhead** | ~0.5s (state capture + analysis) |
| **Screen diff time** | ~0.1s per comparison |
| **Adaptation time** | ~1-2s (LLM replan) |
| **Max cycles** | 2 (configurable) |
| **State storage** | ~2MB per cycle (screenshots) |

## Future Enhancements

1. **Skill Registry Integration**: PlannerAgent uses learned skills instead of raw steps
2. **Semantic Element Matching**: Replace substring matching with embeddings
3. **Parallel Execution**: ExecutorAgent runs independent steps in parallel
4. **Persistent Memory**: Store successful plans in database for reuse
5. **Multi-Monitor Support**: Screen diff per monitor
6. **Recording Mode**: Generate automation scripts from user actions

## Summary

The refactored architecture transforms computer use from a **tool-driven system** into a **state-driven feedback system**:

✅ **Separation of Concerns**: 4 agents, each with single responsibility  
✅ **State-Driven**: Before/after state capture for every step  
✅ **Intelligent Adaptation**: Root cause analysis + strategy generation  
✅ **Screen Diff Verification**: Pixel-wise comparison, not blind trust  
✅ **Failure Learning**: Pattern tracking + trend analysis  
✅ **Feedback Loop**: Observe→Act→Evaluate→Adapt  

The system now **adapts** instead of just **retrying**.
