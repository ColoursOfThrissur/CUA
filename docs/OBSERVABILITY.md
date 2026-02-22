# CUA Observability System Documentation

## Overview

The CUA observability system provides comprehensive monitoring, tracing, and metrics for the autonomous agent system, with special focus on supporting the upcoming **auto-evolution** feature where the system continuously analyzes and improves its tools.

---

## Architecture

### Core Components

1. **Correlation Context** (`core/correlation_context.py`)
   - Thread-safe correlation ID management
   - Distributed tracing across all operations
   - Context managers for scoped correlation

2. **Enhanced Logging** (`core/sqlite_logging.py`)
   - SQLite-based structured logging
   - Automatic correlation ID injection
   - Multiple log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)

3. **Execution Tracking** (`core/tool_execution_logger.py`)
   - Full execution context storage
   - Parent-child execution relationships
   - Service call tracking
   - LLM usage metrics
   - Stack traces for errors

4. **Evolution Tracking** (`core/tool_evolution_logger.py`)
   - Evolution run history
   - Artifact storage (proposals, code, analysis)
   - Health before/after tracking
   - Correlation with executions

5. **Tool Creation Tracking** (`core/tool_creation_logger.py`)
   - Creation attempt logging
   - Artifact storage (specs, code, validation)
   - Success/failure tracking

6. **Metrics Aggregation** (`core/metrics_aggregator.py`)
   - Hourly tool metrics
   - System-wide metrics
   - Auto-evolution metrics (for upcoming feature)
   - Percentile calculations (p50, p95, p99)

7. **Metrics API** (`api/metrics_api.py`)
   - RESTful access to metrics
   - Tool-specific and system-wide views
   - Manual aggregation trigger

---

## Database Schema

### 1. logs.db

#### logs table
```sql
CREATE TABLE logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    correlation_id TEXT,                    -- NEW: Links to other operations
    service TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    context TEXT,                           -- JSON additional context
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
CREATE INDEX idx_correlation_id ON logs(correlation_id)
```

### 2. tool_executions.db

#### executions table
```sql
CREATE TABLE executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id TEXT,                    -- NEW: Request tracing
    parent_execution_id INTEGER,            -- NEW: Nested tool calls
    tool_name TEXT NOT NULL,
    operation TEXT NOT NULL,
    success INTEGER NOT NULL,
    error TEXT,
    error_stack_trace TEXT,                 -- NEW: Full stack trace
    execution_time_ms REAL,
    parameters TEXT,                        -- JSON input parameters
    output_data TEXT,                       -- NEW: Full output (truncated if large)
    output_size INTEGER,
    risk_score REAL,
    timestamp REAL NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_execution_id) REFERENCES executions(id)
)
CREATE INDEX idx_correlation_id ON executions(correlation_id)
CREATE INDEX idx_parent_execution_id ON executions(parent_execution_id)
```

#### execution_context table (NEW)
```sql
CREATE TABLE execution_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    correlation_id TEXT,
    service_calls TEXT,                     -- JSON array of services used
    llm_calls_count INTEGER DEFAULT 0,
    llm_tokens_used INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (execution_id) REFERENCES executions(id)
)
```

### 3. tool_evolution.db

#### evolution_runs table
```sql
CREATE TABLE evolution_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id TEXT,                    -- NEW: Request tracing
    tool_name TEXT NOT NULL,
    user_prompt TEXT,
    status TEXT NOT NULL,
    step TEXT,
    error_message TEXT,
    confidence REAL,
    health_before REAL,
    health_after REAL,                      -- NEW: Track improvement
    timestamp TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
CREATE INDEX idx_correlation_id ON evolution_runs(correlation_id)
```

#### evolution_artifacts table (NEW)
```sql
CREATE TABLE evolution_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evolution_id INTEGER NOT NULL,
    correlation_id TEXT,
    artifact_type TEXT NOT NULL,            -- proposal, code, analysis, validation, sandbox
    step TEXT NOT NULL,
    content TEXT NOT NULL,                  -- Full artifact content
    timestamp TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (evolution_id) REFERENCES evolution_runs(id)
)
```

### 4. tool_creation.db

#### tool_creations table
```sql
CREATE TABLE tool_creations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id TEXT,                    -- NEW: Request tracing
    tool_name TEXT NOT NULL,
    user_prompt TEXT,
    status TEXT NOT NULL,
    step TEXT,
    error_message TEXT,
    code_size INTEGER,
    capabilities_count INTEGER,
    timestamp REAL NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
CREATE INDEX idx_correlation_id ON tool_creations(correlation_id)
```

#### creation_artifacts table (NEW)
```sql
CREATE TABLE creation_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creation_id INTEGER NOT NULL,
    correlation_id TEXT,
    artifact_type TEXT NOT NULL,            -- spec, code, validation, sandbox
    step TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp REAL NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (creation_id) REFERENCES tool_creations(id)
)
```

### 5. metrics.db (NEW)

#### tool_metrics_hourly table
```sql
CREATE TABLE tool_metrics_hourly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    hour_timestamp INTEGER NOT NULL,
    total_executions INTEGER NOT NULL,
    successes INTEGER NOT NULL,
    failures INTEGER NOT NULL,
    avg_duration_ms REAL,
    p50_duration_ms REAL,
    p95_duration_ms REAL,
    p99_duration_ms REAL,
    error_rate_percent REAL,
    avg_output_size INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tool_name, hour_timestamp)
)
```

#### system_metrics_hourly table
```sql
CREATE TABLE system_metrics_hourly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hour_timestamp INTEGER NOT NULL UNIQUE,
    total_chat_requests INTEGER DEFAULT 0,
    total_tool_calls INTEGER NOT NULL,
    total_evolutions INTEGER DEFAULT 0,
    evolution_success_rate REAL DEFAULT 0,
    avg_response_time_ms REAL,
    unique_tools_used INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

#### auto_evolution_metrics table (for upcoming feature)
```sql
CREATE TABLE auto_evolution_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hour_timestamp INTEGER NOT NULL,
    tools_analyzed INTEGER DEFAULT 0,
    evolutions_triggered INTEGER DEFAULT 0,
    evolutions_pending INTEGER DEFAULT 0,
    evolutions_approved INTEGER DEFAULT 0,
    evolutions_rejected INTEGER DEFAULT 0,
    avg_health_improvement REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(hour_timestamp)
)
```

---

## API Endpoints

### Metrics API

#### GET /metrics/tool/{tool_name}
Get metrics for a specific tool.

**Query Parameters:**
- `hours` (int, default=24): Hours of data to retrieve (1-168)

**Response:**
```json
{
  "tool_name": "ContextSummarizerTool",
  "hours": 24,
  "metrics": [
    {
      "hour_timestamp": 1708531200,
      "total_executions": 45,
      "successes": 43,
      "failures": 2,
      "avg_duration_ms": 234.5,
      "p50_duration_ms": 210.0,
      "p95_duration_ms": 450.0,
      "p99_duration_ms": 520.0,
      "error_rate_percent": 4.44
    }
  ],
  "count": 24
}
```

#### GET /metrics/system
Get system-wide metrics.

**Query Parameters:**
- `hours` (int, default=24): Hours of data to retrieve

**Response:**
```json
{
  "hours": 24,
  "metrics": [
    {
      "hour_timestamp": 1708531200,
      "total_tool_calls": 234,
      "total_evolutions": 5,
      "evolution_success_rate": 80.0,
      "avg_response_time_ms": 456.7,
      "unique_tools_used": 12
    }
  ],
  "count": 24
}
```

#### POST /metrics/aggregate
Manually trigger metrics aggregation.

**Response:**
```json
{
  "status": "success",
  "message": "Metrics aggregation completed"
}
```

#### GET /metrics/summary
Get summary of latest metrics.

**Response:**
```json
{
  "latest_system_metrics": { ... },
  "top_tools_24h": [
    {"tool_name": "ContextSummarizerTool", "total": 145},
    {"tool_name": "DatabaseQueryTool", "total": 89}
  ]
}
```

---

## Usage Examples

### 1. Tracing a Request

```python
from core.correlation_context import CorrelationContextManager

# In API endpoint
with CorrelationContextManager() as correlation_id:
    # All logs, executions, evolutions will have this correlation_id
    logger.info("Processing request")
    result = tool.execute(operation, **params)
    evolution_logger.log_run(tool_name, status="success")
```

### 2. Logging with Context

```python
from core.sqlite_logging import get_logger

logger = get_logger("my_service")
logger.info("Operation started", user_id="123", operation="summarize")
logger.error("Operation failed", error_type="ValidationError", details={...})
```

### 3. Tracking Tool Execution

```python
from core.tool_execution_logger import get_execution_logger

logger = get_execution_logger()
execution_id = logger.log_execution(
    tool_name="ContextSummarizerTool",
    operation="summarize_text",
    success=True,
    error=None,
    execution_time_ms=234.5,
    parameters={"input_text": "...", "summary_length": 100},
    output_data={"summary": "...", "tone": "neutral"},
    service_calls=["llm", "storage"],
    llm_calls_count=1,
    llm_tokens_used=450
)
```

### 4. Storing Evolution Artifacts

```python
from core.tool_evolution_logger import get_evolution_logger

logger = get_evolution_logger()

# Log evolution run
evolution_id = logger.log_run(
    tool_name="DatabaseQueryTool",
    user_prompt=None,
    status="in_progress",
    step="analysis",
    health_before=56.95
)

# Store artifacts at each step
logger.log_artifact(evolution_id, "analysis", "analyze", analysis_results)
logger.log_artifact(evolution_id, "proposal", "propose", proposal_json)
logger.log_artifact(evolution_id, "code", "generate", generated_code)
logger.log_artifact(evolution_id, "validation", "validate", validation_results)
logger.log_artifact(evolution_id, "sandbox", "test", sandbox_output)
```

### 5. Querying by Correlation ID

```sql
-- Find all related operations for a request
SELECT 'log' as type, * FROM logs WHERE correlation_id = 'abc-123'
UNION ALL
SELECT 'execution' as type, * FROM executions WHERE correlation_id = 'abc-123'
UNION ALL
SELECT 'evolution' as type, * FROM evolution_runs WHERE correlation_id = 'abc-123'
ORDER BY timestamp;
```

---

## Auto-Evolution Support

The observability system is designed to support the upcoming auto-evolution feature:

### Key Metrics for Auto-Evolution

1. **Tool Health Trends**
   - Success rate over time
   - Error rate changes
   - Performance degradation

2. **Evolution Effectiveness**
   - Health improvement after evolution
   - Success rate of evolutions
   - Time to approval

3. **System Load**
   - Number of pending evolutions
   - Tools awaiting analysis
   - Approval queue depth

### Auto-Evolution Workflow Observability

```
1. Health Check Run
   ├─ Log: "Auto-evolution health check started"
   ├─ Metric: tools_analyzed++
   └─ Correlation ID: auto-evo-{timestamp}

2. Tool Analysis
   ├─ Log: "Analyzing tool X"
   ├─ Execution: health_check operation
   └─ Artifact: analysis results

3. Evolution Triggered
   ├─ Log: "Evolution triggered for tool X"
   ├─ Metric: evolutions_triggered++
   ├─ Evolution Run: status=in_progress
   └─ Artifacts: proposal, code, validation

4. Pending Approval
   ├─ Log: "Evolution pending approval"
   ├─ Metric: evolutions_pending++
   └─ Notification: User approval needed

5. User Approval
   ├─ Log: "Evolution approved by user"
   ├─ Metric: evolutions_approved++
   ├─ Evolution Run: status=success, health_after=X
   └─ Metric: avg_health_improvement updated

6. Next Tool
   └─ Repeat from step 2
```

### Queries for Auto-Evolution Dashboard

```sql
-- Tools needing evolution (declining health)
SELECT tool_name, 
       AVG(CASE WHEN hour_timestamp > (strftime('%s', 'now') - 86400) 
           THEN error_rate_percent END) as recent_error_rate,
       AVG(CASE WHEN hour_timestamp <= (strftime('%s', 'now') - 86400) 
           THEN error_rate_percent END) as previous_error_rate
FROM tool_metrics_hourly
GROUP BY tool_name
HAVING recent_error_rate > previous_error_rate * 1.2;

-- Evolution success rate by tool
SELECT tool_name,
       COUNT(*) as total_evolutions,
       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successes,
       AVG(health_after - health_before) as avg_improvement
FROM evolution_runs
WHERE health_after IS NOT NULL
GROUP BY tool_name;

-- Pending evolutions queue
SELECT tool_name, timestamp, step
FROM evolution_runs
WHERE status = 'pending_approval'
ORDER BY timestamp;
```

---

## Implementation Status

### ✅ Completed (Phase 1 - Foundation)

1. **Correlation Context System**
   - Thread-safe correlation ID management
   - Context managers for scoped correlation
   - Middleware integration in FastAPI

2. **Enhanced Logging**
   - Correlation ID in all logs
   - Structured logging with context
   - Console output with correlation ID

3. **Execution Tracking**
   - Correlation ID in executions
   - Parent-child execution relationships
   - Full execution context storage
   - Service call tracking
   - Stack traces for errors

4. **Evolution Tracking**
   - Correlation ID in evolution runs
   - Artifact storage system
   - Health before/after tracking

5. **Tool Creation Tracking**
   - Correlation ID in creations
   - Artifact storage system

6. **Metrics Aggregation**
   - Hourly tool metrics
   - System-wide metrics
   - Auto-evolution metrics schema
   - Percentile calculations

7. **Metrics API**
   - Tool-specific metrics endpoint
   - System metrics endpoint
   - Manual aggregation trigger
   - Metrics summary endpoint

### 🔄 In Progress (Phase 2 - Integration)

1. **Update Evolution Flow**
   - Integrate artifact logging at each step
   - Update health_after on completion
   - Track service calls during evolution

2. **Update Tool Creation Flow**
   - Integrate artifact logging
   - Track validation details
   - Store sandbox output

3. **Update Tool Orchestrator**
   - Track parent-child executions
   - Log service calls
   - Count LLM usage

4. **Metrics Scheduler**
   - Background job for hourly aggregation
   - APScheduler integration
   - Error handling and retry

### ⏳ Pending (Phase 3 - UI & Advanced Features)

1. **Metrics Dashboard UI**
   - Charts for tool metrics
   - System health overview
   - Auto-evolution status
   - Real-time updates via WebSocket

2. **Correlation Viewer UI**
   - Trace view for requests
   - Timeline visualization
   - Artifact viewer

3. **Advanced Querying**
   - Cross-database queries
   - Saved query templates
   - Query builder UI

4. **Real-time Monitoring**
   - WebSocket for live metrics
   - Active operations view
   - Alert system

5. **Anomaly Detection**
   - Baseline calculation
   - Deviation detection
   - Automatic alerts

6. **Data Retention**
   - Automatic cleanup jobs
   - Archival system
   - Configurable retention policies

---

## Migration Guide

### Updating Existing Code

#### 1. Evolution Flow

**Before:**
```python
logger.log_run(tool_name, user_prompt, "success", step="complete")
```

**After:**
```python
evolution_id = logger.log_run(tool_name, user_prompt, "in_progress", step="analysis", health_before=health_score)

# Store artifacts at each step
logger.log_artifact(evolution_id, "analysis", "analyze", analysis_results)
logger.log_artifact(evolution_id, "proposal", "propose", proposal)
logger.log_artifact(evolution_id, "code", "generate", code)

# Update with final status and health
logger.log_run(tool_name, user_prompt, "success", step="complete", health_after=new_health_score)
```

#### 2. Tool Execution

**Before:**
```python
logger.log_execution(tool_name, operation, success, error, exec_time, params, output)
```

**After:**
```python
execution_id = logger.log_execution(
    tool_name, operation, success, error, exec_time, params, output,
    parent_execution_id=parent_id,  # If nested call
    service_calls=["llm", "storage"],
    llm_calls_count=1,
    llm_tokens_used=450
)
```

#### 3. Using Correlation Context

**In API endpoints:**
```python
from core.correlation_context import CorrelationContextManager

@router.post("/evolve")
async def evolve_tool(tool_name: str):
    with CorrelationContextManager() as correlation_id:
        # All operations will share this correlation_id
        result = evolution_orchestrator.evolve(tool_name)
        return {"correlation_id": correlation_id, "result": result}
```

**In background jobs:**
```python
from core.correlation_context import CorrelationContext

def auto_evolution_job():
    correlation_id = CorrelationContext.generate_id()
    CorrelationContext.set_id(correlation_id)
    
    # Run evolution
    # ...
    
    CorrelationContext.clear()
```

---

## Best Practices

### 1. Always Use Correlation Context

```python
# ✅ Good
with CorrelationContextManager() as corr_id:
    process_request()

# ❌ Bad
process_request()  # No correlation tracking
```

### 2. Store Artifacts at Each Step

```python
# ✅ Good
evolution_id = logger.log_run(...)
logger.log_artifact(evolution_id, "analysis", "analyze", results)
logger.log_artifact(evolution_id, "proposal", "propose", proposal)

# ❌ Bad
logger.log_run(...)  # No artifacts stored
```

### 3. Track Service Calls

```python
# ✅ Good
service_calls = []
result = self.services.llm.generate(...)
service_calls.append("llm")
logger.log_execution(..., service_calls=service_calls)

# ❌ Bad
logger.log_execution(...)  # No service tracking
```

### 4. Log Errors with Context

```python
# ✅ Good
try:
    result = operation()
except Exception as e:
    logger.error("Operation failed", 
                 error_type=type(e).__name__,
                 error_message=str(e),
                 operation="summarize")

# ❌ Bad
logger.error(str(e))  # No context
```

---

## Performance Considerations

### 1. Artifact Storage

- Artifacts are stored as TEXT in SQLite
- Large artifacts (>10KB) should be truncated
- Consider compression for very large artifacts

### 2. Metrics Aggregation

- Run hourly to avoid performance impact
- Use background job (APScheduler)
- Aggregate only last hour, not full history

### 3. Query Optimization

- All correlation_id columns are indexed
- Use LIMIT when querying large tables
- Consider pagination for UI

### 4. Database Size

- Implement retention policies
- Archive old data to compressed files
- Monitor database growth

---

## Troubleshooting

### Issue: Correlation ID not appearing in logs

**Solution:** Ensure correlation context is set before logging:
```python
with CorrelationContextManager():
    logger.info("This will have correlation_id")
```

### Issue: Metrics not updating

**Solution:** Manually trigger aggregation:
```bash
curl -X POST http://localhost:8000/metrics/aggregate
```

### Issue: Missing artifacts

**Solution:** Check that log_artifact is called at each step:
```python
evolution_id = logger.log_run(...)
logger.log_artifact(evolution_id, artifact_type, step, content)
```

### Issue: Database locked errors

**Solution:** Use connection pooling or reduce concurrent writes:
```python
with sqlite3.connect(db_path, timeout=30) as conn:
    # Operations
```

---

## Future Enhancements

### Short-term (1-2 weeks)

1. Complete integration with evolution/creation flows
2. Add metrics scheduler
3. Build basic metrics dashboard UI
4. Add correlation viewer

### Medium-term (1 month)

5. Implement real-time monitoring
6. Add anomaly detection
7. Build advanced query interface
8. Add data retention policies

### Long-term (2-3 months)

9. Distributed tracing with flame graphs
10. Performance profiling integration
11. Machine learning for anomaly detection
12. Advanced visualization (Sankey, network graphs)

---

## Conclusion

The enhanced observability system provides:

✅ **Complete request tracing** via correlation IDs
✅ **Full context storage** for debugging
✅ **Metrics aggregation** for trends
✅ **Auto-evolution support** with dedicated metrics
✅ **Scalable architecture** for future growth

This foundation enables the auto-evolution feature to:
- Track which tools need improvement
- Monitor evolution effectiveness
- Measure system health over time
- Provide visibility into the continuous improvement process

---

## Contact & Support

For questions or issues with the observability system:
1. Check this documentation
2. Review the troubleshooting section
3. Examine correlation IDs in logs
4. Query metrics for patterns

**Remember:** Observability is not just about collecting data—it's about understanding your system's behavior and making informed decisions.
