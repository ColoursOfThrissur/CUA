# CUA Auto-Evolution System - Complete Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Observability System](#observability-system)
4. [Auto-Evolution Engine](#auto-evolution-engine)
5. [Implementation Status](#implementation-status)
6. [API Reference](#api-reference)
7. [Usage Guide](#usage-guide)
8. [Configuration](#configuration)

---

## System Overview

CUA's Auto-Evolution system continuously monitors, tests, and improves tools automatically with human-in-the-loop approval. The system combines comprehensive observability, intelligent prioritization, LLM-based testing, and strategic evolution modes.

### Key Features
- **Automatic Tool Scanning**: Hourly health checks with trend analysis
- **Multi-Dimensional Prioritization**: Urgency (35%), Impact (30%), Feasibility (20%), Timing (15%)
- **LLM Test Validation**: Generates and executes 5-10 tests per capability
- **Strategic Modes**: Reactive, Balanced, Proactive, Experimental
- **Full Observability**: Correlation IDs, metrics, artifacts, tracing
- **Human Approval**: All evolutions require user confirmation

---

## Architecture

### Core Components

```
Auto-Evolution System
├── Orchestrator (core/auto_evolution_orchestrator.py)
│   ├── Scan Loop (hourly tool health checks)
│   ├── Process Loop (execute queued evolutions)
│   └── Learning System (improve prioritization)
│
├── Evolution Queue (core/evolution_queue.py)
│   ├── Priority Calculation
│   ├── Duplicate Prevention
│   └── State Persistence
│
├── LLM Test System
│   ├── Test Orchestrator (core/llm_test_orchestrator.py)
│   ├── Test Logger (core/llm_test_logger.py)
│   └── Baseline Manager
│
├── Observability
│   ├── Correlation Context (core/correlation_context.py)
│   ├── Execution Tracking (core/tool_execution_logger.py)
│   ├── Evolution Tracking (core/tool_evolution_logger.py)
│   ├── Metrics Aggregation (core/metrics_aggregator.py)
│   └── 10 SQLite Databases
│
└── API & UI
    ├── Auto-Evolution API (api/auto_evolution_api.py)
    ├── Metrics API (api/metrics_api.py)
    └── Control Panel (ui/src/components/AutoEvolutionPanel.js)
```

---

## Observability System

### Correlation Context
Thread-safe correlation ID management for distributed tracing across all operations.

**Usage:**
```python
from core.correlation_context import CorrelationContextManager

with CorrelationContextManager() as correlation_id:
    # All logs, executions, evolutions share this ID
    logger.info("Processing request")
    result = tool.execute(operation, **params)
```

### Database Schema

#### 1. logs.db
```sql
CREATE TABLE logs (
    id INTEGER PRIMARY KEY,
    correlation_id TEXT,
    timestamp TEXT,
    service TEXT,
    level TEXT,
    message TEXT,
    context TEXT
)
```

#### 2. tool_executions.db
```sql
CREATE TABLE executions (
    id INTEGER PRIMARY KEY,
    correlation_id TEXT,
    parent_execution_id INTEGER,
    tool_name TEXT,
    operation TEXT,
    success INTEGER,
    error_stack_trace TEXT,
    execution_time_ms REAL,
    output_data TEXT,
    timestamp REAL
)

CREATE TABLE execution_context (
    execution_id INTEGER,
    service_calls TEXT,
    llm_calls_count INTEGER,
    llm_tokens_used INTEGER
)
```

#### 3. tool_evolution.db
```sql
CREATE TABLE evolution_runs (
    id INTEGER PRIMARY KEY,
    correlation_id TEXT,
    tool_name TEXT,
    status TEXT,
    health_before REAL,
    health_after REAL,
    timestamp TEXT
)

CREATE TABLE evolution_artifacts (
    evolution_id INTEGER,
    artifact_type TEXT,  -- proposal, code, analysis, validation, sandbox
    step TEXT,
    content TEXT
)
```

#### 4. llm_tests.db
```sql
CREATE TABLE llm_tests (
    id INTEGER PRIMARY KEY,
    correlation_id TEXT,
    tool_name TEXT,
    capability_name TEXT,
    test_name TEXT,
    passed BOOLEAN,
    quality_score INTEGER,
    test_case TEXT,
    output TEXT
)

CREATE TABLE test_suites (
    id INTEGER PRIMARY KEY,
    tool_name TEXT,
    total_tests INTEGER,
    passed_tests INTEGER,
    overall_quality_score INTEGER
)
```

#### 5. metrics.db
```sql
CREATE TABLE tool_metrics_hourly (
    tool_name TEXT,
    hour_timestamp INTEGER,
    total_executions INTEGER,
    successes INTEGER,
    failures INTEGER,
    avg_duration_ms REAL,
    p50_duration_ms REAL,
    p95_duration_ms REAL,
    p99_duration_ms REAL,
    error_rate_percent REAL
)
```

### Metrics Aggregation
Automatic hourly aggregation with percentile calculations (p50, p95, p99).

**Scheduler:** `core/metrics_scheduler.py` runs background job every hour.

---

## Auto-Evolution Engine

### Orchestrator Configuration
```python
{
    "mode": "balanced",              # reactive, balanced, proactive, experimental
    "scan_interval": 3600,           # 1 hour
    "max_concurrent": 2,             # Max parallel evolutions
    "min_health_threshold": 50,      # Trigger threshold
    "auto_approve_threshold": 90,    # Test score for recommendation
    "learning_enabled": True         # Learn from outcomes
}
```

### Priority Calculation
```python
priority = (urgency × 0.35) + (impact × 0.30) + (feasibility × 0.20) + (timing × 0.15)

# Urgency: Based on health score and error rate
# Impact: Based on usage count
# Feasibility: Based on issue clarity
# Timing: Based on recent activity
```

### Strategic Modes

**Reactive** (Conservative)
- Only queue if health < threshold
- Minimal changes, focus on critical issues

**Balanced** (Recommended)
- Queue if health < 70 OR (health < 85 AND urgency/impact > 60)
- Balance between stability and improvement

**Proactive** (Aggressive)
- Queue if health < 95 OR impact > 70
- Continuous optimization

**Experimental** (Testing)
- Queue everything
- Maximum improvement rate

### Workflow

```
1. Scan Phase (Every Hour)
   ├─ Get all tools
   ├─ Calculate health scores
   ├─ Query metrics for trends
   ├─ Calculate priority scores
   └─ Add to queue

2. Process Phase (Continuous)
   ├─ Get next tool from queue (highest priority)
   ├─ Check concurrent limit
   ├─ Run evolution flow (6 steps)
   ├─ Run LLM test suite
   ├─ Calculate test score (0-100)
   ├─ Recommend auto-approval if score ≥ 90
   └─ Learn from outcome

3. Approval Phase (Human)
   ├─ User reviews evolution
   ├─ Views test results
   ├─ Approves or rejects
   └─ System applies changes
```

### LLM Test System

**Test Generation:**
- 5-10 test cases per capability
- Happy path, edge cases, errors, real-world scenarios
- LLM-generated based on capability description

**Test Execution:**
- Execute each test case
- Validate output (LLM-based for complex results)
- Track performance metrics

**Quality Scoring:**
```python
test_quality = (success_match × 40) + (validation_passed × 40) + (performance × 20)
suite_score = (avg_quality × 70) + (pass_rate × 30)
```

---

## Implementation Status

### ✅ Phase 1 Complete (Foundation)
- Correlation context system
- Enhanced logging with correlation IDs
- Execution tracking with full context
- Evolution tracking with artifacts
- Metrics aggregation system
- LLM test orchestrator
- LLM test logger
- Evolution queue manager

### ✅ Phase 2 Complete (Core Engine)
- Auto-evolution orchestrator
- Auto-evolution API
- Auto-evolution UI panel
- Server integration
- Header button integration

### ⏳ Phase 3 (Enhancement)
- Notification system
- Analytics dashboard
- Learning system refinement
- Advanced health metrics

---

## API Reference

### Auto-Evolution API

#### POST /auto-evolution/start
Start the auto-evolution engine.

**Response:**
```json
{"success": true, "message": "Auto-evolution started"}
```

#### POST /auto-evolution/stop
Stop the auto-evolution engine.

#### GET /auto-evolution/status
Get current status.

**Response:**
```json
{
  "running": true,
  "mode": "balanced",
  "queue_size": 3,
  "in_progress": 1,
  "config": {...}
}
```

#### POST /auto-evolution/config
Update configuration.

**Request:**
```json
{
  "mode": "proactive",
  "scan_interval": 1800,
  "max_concurrent": 3
}
```

#### GET /auto-evolution/queue
View evolution queue.

**Response:**
```json
{
  "queue": [
    {
      "tool_name": "DatabaseQueryTool",
      "priority_score": 87.25,
      "reason": "Critical health score (45/100)",
      "status": "queued"
    }
  ]
}
```

#### POST /auto-evolution/trigger-scan
Manually trigger tool health scan.

### Metrics API

#### GET /metrics/tool/{tool_name}?hours=24
Get tool-specific metrics.

#### GET /metrics/system?hours=24
Get system-wide metrics.

#### POST /metrics/aggregate
Manually trigger metrics aggregation.

#### GET /metrics/summary
Get latest metrics summary.

---

## Usage Guide

### Starting Auto-Evolution

**Via UI:**
1. Click Bot icon in header
2. Click "Start" button
3. Configure settings if needed
4. Monitor queue and status

**Via API:**
```bash
curl -X POST http://localhost:8000/auto-evolution/start
```

### Configuring Modes

**Balanced Mode (Recommended):**
```bash
curl -X POST http://localhost:8000/auto-evolution/config \
  -H "Content-Type: application/json" \
  -d '{"mode": "balanced", "scan_interval": 3600}'
```

**Proactive Mode (Aggressive):**
```bash
curl -X POST http://localhost:8000/auto-evolution/config \
  -H "Content-Type: application/json" \
  -d '{"mode": "proactive", "max_concurrent": 3}'
```

### Monitoring

**Check Status:**
```bash
curl http://localhost:8000/auto-evolution/status
```

**View Queue:**
```bash
curl http://localhost:8000/auto-evolution/queue
```

**View Metrics:**
```bash
curl http://localhost:8000/metrics/summary
```

### Approving Evolutions

1. Evolution appears in "Pending Evolutions" overlay
2. Review changes, test results, and health improvement
3. Click "Approve" to apply or "Reject" to discard
4. System automatically removes from pending queue

---

## Configuration

### Auto-Evolution Config
**File:** `config/auto_evolution.json`

```json
{
  "enabled": false,
  "strategy_mode": "balanced",
  "scan_interval": 3600,
  "max_pending_evolutions": 5,
  "cooldown_period": 300,
  "tool_filters": {
    "include_core": true,
    "include_experimental": true,
    "exclude_recent": true,
    "recent_threshold_days": 7
  },
  "llm_testing": {
    "enabled": true,
    "tests_per_capability": 5,
    "quality_threshold": 70,
    "use_llm_validation": true
  },
  "notifications": {
    "evolution_ready": true,
    "critical_failures": true,
    "daily_summary": true
  }
}
```

### Environment Variables
```bash
OLLAMA_URL=http://localhost:11434
MODEL=mistral:latest
CORS_ALLOW_ORIGINS=http://localhost:3000
```

---

## Best Practices

### 1. Start with Balanced Mode
Begin with balanced mode to understand system behavior before switching to proactive.

### 2. Monitor Queue Size
Keep queue size under 10 to avoid overwhelming approval process.

### 3. Review Test Results
Always review LLM test results before approving evolutions.

### 4. Use Correlation IDs
Track issues using correlation IDs across logs, executions, and evolutions.

### 5. Regular Metrics Review
Check metrics dashboard weekly to identify trends.

---

## Troubleshooting

### Issue: Orchestrator not starting
**Solution:** Check logs for initialization errors, ensure all dependencies are installed.

### Issue: No tools being queued
**Solution:** Lower `min_health_threshold` or switch to proactive mode.

### Issue: Tests failing
**Solution:** Review test cases, adjust `quality_threshold`, or disable LLM validation temporarily.

### Issue: High queue size
**Solution:** Increase `max_concurrent` or approve/reject pending evolutions faster.

---

## Performance Considerations

- **Scan Interval:** 1 hour recommended, adjust based on tool count
- **Max Concurrent:** 2-3 recommended, higher may impact system performance
- **Database Size:** Implement retention policies for logs and metrics
- **LLM Calls:** Test generation uses LLM, monitor token usage

---

## Future Enhancements

### Short-term
- Notification badges in UI
- Quick actions in Tools Management
- Analytics dashboard with charts

### Medium-term
- ML-based priority learning
- Predictive evolution triggers
- A/B testing for evolutions

### Long-term
- Distributed tracing with flame graphs
- Anomaly detection with ML
- Advanced visualization

---

## Files Reference

### Core Components
- `core/auto_evolution_orchestrator.py` - Main engine (200 lines)
- `core/evolution_queue.py` - Priority queue (150 lines)
- `core/llm_test_orchestrator.py` - Test generation (250 lines)
- `core/llm_test_logger.py` - Test logging (150 lines)
- `core/correlation_context.py` - Tracing (100 lines)
- `core/metrics_aggregator.py` - Metrics (200 lines)

### API
- `api/auto_evolution_api.py` - Control endpoints (80 lines)
- `api/metrics_api.py` - Metrics endpoints (100 lines)

### UI
- `ui/src/components/AutoEvolutionPanel.js` - Control panel (150 lines)
- `ui/src/components/AutoEvolutionPanel.css` - Styles (250 lines)

**Total:** ~1,630 lines of production code

---

## Success Metrics

✅ **System Running:** Auto-evolution orchestrator operational
✅ **Tools Scanned:** Hourly health checks executing
✅ **Evolutions Queued:** Priority-based queue management
✅ **Tests Passing:** LLM test validation working
✅ **Approvals Working:** Human-in-the-loop functional
✅ **Observability:** Full tracing and metrics
✅ **UI Functional:** Control panel operational

**Target:** 80% evolution success rate, 15+ point average health improvement

---

This documentation provides everything needed to understand, configure, and operate the CUA Auto-Evolution system!
