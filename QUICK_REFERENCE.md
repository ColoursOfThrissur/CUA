# CUA Solution - Quick Reference Guide

## 🚀 What's New?

### 1. **Auto-Evolution System** 🤖
**The Big Feature**: System automatically monitors, tests, and improves tools

**Key Files:**
- `core/auto_evolution_orchestrator.py` - Main engine
- `core/evolution_queue.py` - Priority queue
- `core/llm_test_orchestrator.py` - Test generation
- `api/auto_evolution_api.py` - Control API
- `ui/src/components/AutoEvolutionPanel.js` - UI control panel

**How to Use:**
```bash
# Via UI: Click Bot icon in header → Click "Start"
# Via API:
curl -X POST http://localhost:8000/auto-evolution/start
```

**What It Does:**
1. Scans all tools every hour
2. Analyzes health with LLM
3. Calculates priority scores
4. Queues tools needing improvement
5. Generates and runs tests
6. Waits for human approval
7. Learns from outcomes

---

### 2. **Comprehensive Observability** 📊
**The Big Feature**: Full distributed tracing and metrics

**Key Files:**
- `core/correlation_context.py` - Request tracing
- `core/metrics_aggregator.py` - Hourly metrics
- `core/llm_test_logger.py` - Test results
- `api/metrics_api.py` - Metrics API

**New Databases:**
- `llm_tests.db` - Test results and baselines
- `metrics.db` - Aggregated hourly metrics

**How to Use:**
```bash
# Get tool metrics
curl http://localhost:8000/metrics/tool/DatabaseQueryTool?hours=24

# Get system metrics
curl http://localhost:8000/metrics/system?hours=24

# Trigger aggregation
curl -X POST http://localhost:8000/metrics/aggregate
```

**What It Does:**
- Links all operations with correlation IDs
- Tracks execution context (services, LLM calls)
- Stores artifacts at each step
- Aggregates metrics hourly
- Calculates percentiles (p50, p95, p99)

---

### 3. **LLM-Based Testing** 🧪
**The Big Feature**: Automatic test generation and execution

**Key Files:**
- `core/llm_test_orchestrator.py` - Test orchestrator
- `core/llm_test_logger.py` - Test logger

**How It Works:**
1. LLM generates 5-10 realistic test cases
2. Tests execute in isolated environment
3. Output validated (LLM-based for complex results)
4. Quality score calculated (0-100)
5. Results stored in llm_tests.db

**Test Quality Score:**
```
score = (success_match × 40) + (validation_passed × 40) + (performance × 20)
```

---

### 4. **Enhanced Validation** ✅
**The Big Feature**: 12+ validation gates for code quality

**Key File:**
- `core/enhanced_code_validator.py`

**New Checks:**
- Undefined method detection
- Uninitialized attribute detection
- Code truncation detection
- Service usage pattern validation
- Architectural compliance

---

### 5. **Priority-Based Queue** 📋
**The Big Feature**: Multi-dimensional prioritization

**Key File:**
- `core/evolution_queue.py`

**Priority Formula:**
```
priority = (urgency × 0.35) + (impact × 0.30) + (feasibility × 0.20) + (timing × 0.15)
```

**Factors:**
- **Urgency**: Health score, error rate
- **Impact**: Usage frequency
- **Feasibility**: Issue clarity
- **Timing**: Recent activity

---

## 📊 Database Changes

### New Tables:

**llm_tests.db:**
```sql
-- Individual test results
CREATE TABLE llm_tests (
    correlation_id TEXT,
    tool_name TEXT,
    capability_name TEXT,
    test_name TEXT,
    passed BOOLEAN,
    quality_score INTEGER,
    output TEXT,
    validation_result TEXT
)

-- Test suite results
CREATE TABLE test_suites (
    tool_name TEXT,
    total_tests INTEGER,
    passed_tests INTEGER,
    overall_quality_score INTEGER
)

-- Baseline tracking
CREATE TABLE test_baselines (
    tool_name TEXT,
    test_name TEXT,
    baseline_output TEXT,
    baseline_quality_score INTEGER
)
```

**metrics.db:**
```sql
-- Hourly tool metrics
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

-- System-wide metrics
CREATE TABLE system_metrics_hourly (
    hour_timestamp INTEGER,
    total_tool_calls INTEGER,
    total_evolutions INTEGER,
    evolution_success_rate REAL,
    avg_response_time_ms REAL,
    unique_tools_used INTEGER
)
```

### Modified Tables:

**logs.db:**
```sql
-- Added correlation_id
ALTER TABLE logs ADD COLUMN correlation_id TEXT;
CREATE INDEX idx_correlation_id ON logs(correlation_id);
```

**tool_executions.db:**
```sql
-- Added correlation_id, parent_execution_id, error_stack_trace, output_data
ALTER TABLE executions ADD COLUMN correlation_id TEXT;
ALTER TABLE executions ADD COLUMN parent_execution_id INTEGER;
ALTER TABLE executions ADD COLUMN error_stack_trace TEXT;
ALTER TABLE executions ADD COLUMN output_data TEXT;

-- New table for execution context
CREATE TABLE execution_context (
    execution_id INTEGER,
    service_calls TEXT,
    llm_calls_count INTEGER,
    llm_tokens_used INTEGER
)
```

**tool_evolution.db:**
```sql
-- Added correlation_id, health_before, health_after
ALTER TABLE evolution_runs ADD COLUMN correlation_id TEXT;
ALTER TABLE evolution_runs ADD COLUMN health_before REAL;
ALTER TABLE evolution_runs ADD COLUMN health_after REAL;

-- New table for artifacts
CREATE TABLE evolution_artifacts (
    evolution_id INTEGER,
    artifact_type TEXT,  -- proposal, code, analysis, validation, sandbox
    step TEXT,
    content TEXT
)
```

---

## 🎯 API Endpoints

### Auto-Evolution API:
```bash
POST   /auto-evolution/start          # Start engine
POST   /auto-evolution/stop           # Stop engine
GET    /auto-evolution/status         # Get status
POST   /auto-evolution/config         # Update config
GET    /auto-evolution/queue          # View queue
POST   /auto-evolution/trigger-scan   # Manual scan
```

### Metrics API:
```bash
GET    /metrics/tool/{tool_name}?hours=24   # Tool metrics
GET    /metrics/system?hours=24             # System metrics
POST   /metrics/aggregate                   # Manual aggregation
GET    /metrics/summary                     # Latest summary
```

---

## 🎨 UI Changes

### New Components:
1. **AutoEvolutionPanel.js** - Control panel for auto-evolution
   - Start/Stop controls
   - Real-time status
   - Queue visualization
   - Configuration management
   - Scan progress tracking

2. **Header.js** - Added Bot icon
   - Opens AutoEvolutionPanel
   - Shows running status

### Modified Components:
1. **App.js** - Integrated AutoEvolutionPanel
2. **PendingEvolutionsOverlay.js** - Enhanced with test results

---

## 🔧 Configuration

### Auto-Evolution Config:
```javascript
{
  mode: "balanced",              // reactive, balanced, proactive, experimental
  scan_interval: 3600,           // 1 hour (in seconds)
  max_concurrent: 2,             // Max parallel evolutions
  min_health_threshold: 50,      // Trigger threshold
  auto_approve_threshold: 90,    // Test score for recommendation
  learning_enabled: true,        // Learn from outcomes
  enable_enhancements: true      // Queue healthy tools with improvements
}
```

### Strategic Modes:

**Reactive** (Conservative):
- Only queue if health < threshold
- Minimal changes

**Balanced** (Recommended):
- Queue if health < 70 OR (health < 85 AND urgency/impact > 60)
- Balance stability and improvement

**Proactive** (Aggressive):
- Queue if health < 95 OR impact > 70
- Continuous optimization

**Experimental** (Testing):
- Queue everything
- Maximum improvement rate

---

## 📈 Metrics & Monitoring

### Key Metrics:

**Tool Health:**
- Success rate over time
- Error rate changes
- Performance trends (p50, p95, p99)
- Usage frequency

**Evolution Effectiveness:**
- Health improvement (before → after)
- Test pass rate
- Evolution success rate
- Time to approval

**System Load:**
- Total tool calls per hour
- Unique tools used
- Average response time
- Evolution queue size

### Accessing Metrics:

**Via UI:**
- Tools Management Page → Health metrics
- Observability Overlay → metrics.db

**Via API:**
```bash
# Tool-specific metrics
curl http://localhost:8000/metrics/tool/DatabaseQueryTool?hours=24

# System-wide metrics
curl http://localhost:8000/metrics/system?hours=24

# Latest summary
curl http://localhost:8000/metrics/summary
```

---

## 🔄 Typical Workflows

### 1. Start Auto-Evolution:
```
1. Click Bot icon in header
2. Click "Start" button
3. System begins hourly scans
4. Tools get queued based on priority
5. Evolutions run automatically
6. Approve in Pending Evolutions overlay
```

### 2. Manual Tool Scan:
```
1. Click Bot icon in header
2. Click "Scan Now" button
3. Watch progress bar
4. Review queued tools
5. Wait for evolutions to complete
6. Approve or reject
```

### 3. Review Metrics:
```
1. Go to Tools Management Page
2. View health scores for all tools
3. Click tool for detailed metrics
4. Check recent executions
5. View LLM analysis
```

### 4. Trace a Request:
```
1. Note correlation_id from response
2. Open Observability Overlay
3. Search logs.db for correlation_id
4. Search tool_executions.db for correlation_id
5. Search tool_evolution.db for correlation_id
6. View complete request flow
```

---

## 🎓 Best Practices

### 1. Use Correlation Context:
```python
from core.correlation_context import CorrelationContextManager

with CorrelationContextManager() as correlation_id:
    # All operations share this ID
    logger.info("Processing request")
    result = tool.execute(operation, **params)
```

### 2. Store Artifacts:
```python
evolution_id = logger.log_run(...)
logger.log_artifact(evolution_id, "analysis", "analyze", results)
logger.log_artifact(evolution_id, "proposal", "propose", proposal)
logger.log_artifact(evolution_id, "code", "generate", code)
```

### 3. Track Service Calls:
```python
service_calls = []
result = self.services.llm.generate(...)
service_calls.append("llm")
logger.log_execution(..., service_calls=service_calls)
```

### 4. Start with Balanced Mode:
- Begin with balanced mode
- Monitor queue size
- Adjust based on needs
- Switch to proactive for rapid improvement

### 5. Review Test Results:
- Always check test scores before approving
- Look for patterns in failures
- Update baselines as needed
- Monitor regression

---

## 🚨 Troubleshooting

### Issue: Orchestrator not starting
**Solution:**
```bash
# Check logs
tail -f logs/system.log

# Verify dependencies
pip install -r requirements.txt

# Check LLM client
curl http://localhost:11434/api/tags
```

### Issue: No tools being queued
**Solution:**
```bash
# Lower threshold or switch mode
curl -X POST http://localhost:8000/auto-evolution/config \
  -H "Content-Type: application/json" \
  -d '{"mode": "proactive", "min_health_threshold": 70}'

# Manual scan
curl -X POST http://localhost:8000/auto-evolution/trigger-scan
```

### Issue: Tests failing
**Solution:**
- Review test cases in llm_tests.db
- Check tool implementation
- Verify service availability
- Update baselines if behavior changed

### Issue: Metrics not updating
**Solution:**
```bash
# Manual aggregation
curl -X POST http://localhost:8000/metrics/aggregate

# Check scheduler
# Verify MetricsScheduler is running in server.py
```

---

## 📚 Documentation

### Main Docs:
- `SOLUTION_ANALYSIS.md` - Comprehensive analysis (this file's companion)
- `docs/AUTO_EVOLUTION_COMPLETE.md` - Auto-evolution guide
- `docs/OBSERVABILITY.md` - Observability system
- `docs/AUTO_EVOLUTION_IMPLEMENTATION.md` - Implementation details
- `README.md` - System overview

### Code Comments:
- All new files have comprehensive docstrings
- Complex functions have inline comments
- Database schemas documented in code

---

## 🎯 Quick Commands

### Start System:
```bash
# Backend
python start.py

# UI (separate terminal)
cd ui && npm start
```

### Auto-Evolution:
```bash
# Start
curl -X POST http://localhost:8000/auto-evolution/start

# Stop
curl -X POST http://localhost:8000/auto-evolution/stop

# Status
curl http://localhost:8000/auto-evolution/status

# Manual scan
curl -X POST http://localhost:8000/auto-evolution/trigger-scan
```

### Metrics:
```bash
# Tool metrics
curl http://localhost:8000/metrics/tool/DatabaseQueryTool?hours=24

# System metrics
curl http://localhost:8000/metrics/system?hours=24

# Aggregate
curl -X POST http://localhost:8000/metrics/aggregate
```

### Database Queries:
```bash
# View logs with correlation ID
sqlite3 data/logs.db "SELECT * FROM logs WHERE correlation_id='abc-123'"

# View tool metrics
sqlite3 data/metrics.db "SELECT * FROM tool_metrics_hourly WHERE tool_name='DatabaseQueryTool' ORDER BY hour_timestamp DESC LIMIT 24"

# View test results
sqlite3 data/llm_tests.db "SELECT * FROM test_suites WHERE tool_name='DatabaseQueryTool' ORDER BY timestamp DESC LIMIT 10"
```

---

## ✅ Checklist for New Features

When adding new features, ensure:

- [ ] Use CorrelationContext for tracing
- [ ] Log to appropriate database
- [ ] Store artifacts if applicable
- [ ] Track service calls
- [ ] Add API endpoint if needed
- [ ] Update UI if user-facing
- [ ] Add tests
- [ ] Update documentation
- [ ] Follow CSS variable pattern for colors
- [ ] Use existing services via self.services

---

## 🎉 Summary

**What Changed:**
- ✅ Auto-evolution system (2,500+ lines)
- ✅ Comprehensive observability (1,000+ lines)
- ✅ LLM-based testing (600+ lines)
- ✅ Enhanced validation (200+ lines)
- ✅ Priority-based queue (150+ lines)
- ✅ Metrics aggregation (250+ lines)
- ✅ UI control panel (250+ lines)

**What It Enables:**
- 🤖 Automatic tool improvement
- 📊 Full request tracing
- 🧪 Intelligent testing
- 📈 Comprehensive metrics
- 🎯 Strategic evolution modes
- 👁️ Complete observability

**Production Ready:** ✅

---

**Last Updated:** February 22, 2026
**Quick Reference Version:** 1.0
