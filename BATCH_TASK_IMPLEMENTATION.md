# Batch Task Processing Implementation

## Problem
LLM was returning arrays of multiple tasks `[{}, {}, {}]` but code expected single task object `{}`. This caused:
- JSON extraction failures
- "No improvements needed" loop
- Wasted LLM analysis (re-analyzing same codebase 10 times)

## Solution: Hybrid Batch Processing
LLM analyzes once and returns 3-5 prioritized tasks → System processes them one-by-one

## Changes Made

### 1. loop_controller.py
**Added task queue management:**
```python
self.task_queue = []  # Queue of tasks from LLM
self.task_attempts = {}  # Track attempts per task (max 3)
```

**Modified run_loop():**
- Check if task_queue is empty
- If empty: Call `analyze_and_propose_tasks()` to get batch of 3-5 tasks
- Pop first task from queue
- Check if task failed 3 times → skip and move to next
- Process task with existing pipeline (proposal → sandbox → apply)
- Track attempts per task using hash of files_affected

### 2. task_analyzer.py
**Added new method:**
```python
def analyze_and_propose_tasks() -> List[Dict]:
    """Returns array of 3-5 tasks instead of single task"""
```

**New prompt:**
```python
def _build_batch_analysis_prompt():
    """Explicitly requests JSON array of 3-5 tasks"""
```

**Key prompt changes:**
- "Analyze this codebase and identify 3-5 improvements ordered by priority"
- "Return an ARRAY of 3-5 tasks ordered by priority (highest first)"
- "Each task should target a DIFFERENT file"
- Output format shows array: `[{task1}, {task2}, {task3}]`

**Added helper:**
```python
def _is_blocked(target_file, blocked_tasks) -> bool:
    """Check if file is in blocked list"""
```

## Benefits

### Efficiency
- **Before**: 10 LLM calls analyzing same codebase
- **After**: 1 LLM call → 5 tasks queued

### Progress
- **Before**: Stuck suggesting same task 10 times
- **After**: Task 1 fails 3 times → automatically move to task 2

### Token Usage
- **Before**: ~500K tokens (10 full analyses)
- **After**: ~100K tokens (1 analysis + 5 code generations)

### Safety Maintained
- Each task still gets individual:
  - Proposal generation
  - Sandbox testing
  - Git commit
  - Rollback capability
- Circuit breaker still works (5 consecutive failures)

## How It Works

```
Iteration 1:
  ├─ Queue empty → Analyze codebase
  ├─ LLM returns: [task1, task2, task3, task4, task5]
  ├─ Queue: [task1, task2, task3, task4, task5]
  ├─ Pop task1 → Process → Success ✓
  └─ Commit changes

Iteration 2:
  ├─ Queue has tasks → Skip analysis
  ├─ Pop task2 → Process → Sandbox fail ✗
  └─ task2 attempts: 1

Iteration 3:
  ├─ Queue has tasks → Skip analysis
  ├─ Pop task2 → Process → Sandbox fail ✗
  └─ task2 attempts: 2

Iteration 4:
  ├─ Queue has tasks → Skip analysis
  ├─ Pop task2 → Process → Sandbox fail ✗
  └─ task2 attempts: 3 (max reached)

Iteration 5:
  ├─ Queue has tasks → Skip analysis
  ├─ Pop task2 → Check attempts (3) → Skip task2
  ├─ Pop task3 → Process → Success ✓
  └─ Commit changes

Iteration 6:
  ├─ Queue empty → Analyze codebase again
  └─ Get new batch of tasks...
```

## Backward Compatibility
- Old `analyze_and_propose_task()` method removed
- All calls now use `analyze_and_propose_tasks()` (returns list)
- Existing pipeline unchanged (still processes one task at a time)
- Git commits still individual per task
- Rollback still works per task

## Testing
Run the self-improvement loop and verify:
1. LLM returns array of 3-5 tasks
2. Tasks are processed sequentially
3. Failed tasks are retried up to 3 times
4. After 3 failures, system moves to next task
5. When queue empty, new batch is requested
6. Each successful task creates individual git commit

## Configuration
No config changes needed. System automatically:
- Requests 3-5 tasks per batch
- Limits to max 5 tasks per batch
- Retries each task max 3 times
- Maintains existing max_iterations limit
