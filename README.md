# CUA - Autonomous Agent System

**Local autonomous agent platform for safe tool-based execution, human approval gates, controlled self-improvement, and full observability.**

> **Status (June 2026):** Production-Ready | Autonomous loop fully wired | Single consolidated DB | 20+ correctness/quality fixes applied

---

## What CUA Does

- **Plans & executes** multi-step tasks with goal achievement and self-correction
- **Routes intelligently** via a skills system (7 skills, 3-signal scoring + LLM fallback)
- **Calls tools natively** via function calling (20+ tools, reputation-weighted selection)
- **Creates & evolves tools** through LLM-driven generation with 20-gate validation
- **Manages dependencies** automatically (AST-based detection, pip install, service generation)
- **Observes everything** via a single consolidated SQLite database (`cua.db`, WAL mode)
- **Self-improves** through a hybrid improvement engine with human approval gates
- **Runs steps in parallel** via DAG-based wave execution (independent steps run concurrently)
- **Resolves capability gaps** automatically: local reroute → MCP → API wrap → create tool
- **Closes the gap loop** — resolved gaps written to `cua.db`, never re-queued on next scan
- **Connects to MCP servers** via stdlib JSON-RPC 2.0 adapter with dynamic capability discovery
- **Scores tool reputation** with 4-factor composite (success rate, recency, latency, volume)
- **Stores credentials securely** with Fernet encryption, per-tool access scoping, TTL support
- **Learns from history** via strategic memory (Jaccard similarity, win-rate tracking, LRU eviction)
- **Searches all memory at once** via UnifiedMemory facade (strategic + patterns + improvements + conversation)
- **Evolves surgically** — tool evolution scopes rewrites to `target_functions` only
- **Adapts confidence thresholds** per model — local (Qwen/Mistral) 0.35, cloud (GPT/Claude/Gemini) 0.5

---

## Quick Start

```bash
pip install -r requirements.txt

# Start backend (port 8000)
python start.py

# Start UI (separate terminal, port 3000)
cd ui && npm install && npm start
```

Access: http://localhost:3000  
API docs: http://localhost:8000/docs

---

## Architecture

```
User Request
    ↓
[Skill Selector] — 3-signal scoring: keyword overlap + learned triggers + tool health
    ↓
[SkillExecutionContext] — 32 fields: skill metadata, tool guidance, I/O expectations, recovery, trace
    ↓
[ContextAwareToolSelector] — reputation-weighted selection + circuit breaker health check
    ↓
[UnifiedMemory] — Jaccard search across 4 stores injected into planner prompt
    ↓
[TaskPlanner] — LLM plan generation, token-budget trimmed tools_desc, memory context first
    ↓
[ExecutionEngine] — parallel DAG wave execution (ThreadPoolExecutor, max 4 workers, 120s/step)
    ↓
[ToolOrchestrator] — execute with cached signatures, fallback on error, output validation
    ↓
[CapabilityResolver] — gap? reroute → MCP → API wrap → create_tool
    ↓
[Response]
```

---

## Autonomous Loop

The full self-improvement cycle runs via `CoordinatedAutonomyEngine`:

```
Chat failure → record_capability_gap (CapabilityMapper scans tools/ + tools/experimental/)
    ↓ skip if already in resolved_gaps
[GapTracker] — persist gap (requires ≥3 occurrences, confidence ≥0.7, not resolution_attempted)
    ↓
[CoordinatedAutonomyEngine.run_cycle]
    1. BaselineHealthChecker — abort if system is broken
    2. CapabilityResolver pass — reroute/MCP/API gaps marked resolved, skipped for CREATE
    3. AutoEvolutionOrchestrator.run_cycle
        a. ToolQualityAnalyzer — queue WEAK/NEEDS_IMPROVEMENT tools (min 5 uses)
        b. LLM gap analysis over failures table in cua.db
        c. Registry coverage check — skip CREATE if loaded tool already covers gap
        d. Queue CREATE (max 1 new tool per scan by default)
    4. SelfImprovementLoop — bounded improvement pass (max 3 iterations)
    5. Quality gate — pause if consecutive low-value cycles
    ↓
[_process_evolution]
    evolve_tool → pending approval → human approves → cache invalidated
    create_tool → pending approval → on success → resolved_gaps written to cua.db
                                                 → tracker.mark_resolved()
    ↓
Next cycle: gap already resolved, skipped at every gate
```

**Key guards:**
- `enable_enhancements` defaults to `False` — healthy tools never auto-queued
- `min_usage=5` — tools with fewer than 5 executions not analyzed
- `detect_gap_from_task` requires ≥2 keyword hits — no single-word false positives
- `get_actionable_gaps` excludes `resolution_attempted=True` gaps
- LLM health cache TTL 24h — no redundant re-analysis within a day
- `resolved_gaps` table prevents re-queuing already-solved capabilities

---

## Project Status

### Architecture Health

| Component | Status | Notes |
|-----------|--------|-------|
| SkillExecutionContext (32 fields) | Complete | |
| Skill Selector (3-signal + LLM fallback) | Solid | Suffix stemming added; runner-up penalised ±0.05 |
| Task Planner (LLM → DAG) | Solid | Token budget trimming for tools_desc; memory context injected first |
| Execution Engine (wave DAG) | Solid | resume_execution wave-aware; completed outputs passed to replan |
| Tool Orchestrator | Solid | inspect.signature cached; services_cache invalidated on tool reload/approve |
| Circuit Breaker | Solid | CLOSED→OPEN→HALF_OPEN correct; success_count reset on OPEN; lock added |
| Strategic Memory | Solid | Dirty flag + batch write; config-driven min_win_rate; exponential recency decay |
| UnifiedMemory (4-store facade) | Solid | Searches both failed and successful improvements |
| Capability Resolver (5-step chain) | Solid | Config-driven catalogues; feedback loop writes to resolved_gaps |
| Credential Store (Fernet) | Solid | Atomic writes; expires_at TTL support |
| Gap Detector | Solid | ≥2 keyword hits required; CapabilityMapper scans both tool dirs |
| Gap Tracker | Solid | resolution_attempted filter; mark_resolved after queuing |
| Auto-Evolution Orchestrator | Solid | Registry coverage check before CREATE; failure scan reads cua.db |
| Coordinated Autonomy Engine | Solid | CapabilityResolver pass before CREATE queue; quality gate |
| Autonomous Loop (end-to-end) | Complete | Gap → resolve → create/evolve → resolved_gaps → skip on next scan |
| Parallel Execution DAG | Complete | |
| MCP Adapter (JSON-RPC 2.0) | Complete | |
| Surgical Tool Evolution | Complete | target_functions scopes rewrite |
| Per-model Confidence Thresholds | Complete | |
| DB Consolidation (cua.db) | Complete | Single WAL-mode file, 21 tables, all loggers redirected |
| Config Validator at startup | Complete | MCP URLs, LLM provider, port range checked |

### Remaining Known Gaps

- `CircuitBreaker`: lock added but sliding window still not implemented — cumulative failure count only
- `ImprovementMemory`: still writes to `data/improvement_memory.db` (not yet redirected to `cua.db`)
- `CapabilityResolver`: `_MCP_CATALOGUE` / `_API_CATALOGUE` config override works but defaults are static
- `SkillSelector`: no negative signal between competing skills (runner-up penalty is a partial fix)
- `TaskPlanner`: replan on retry doesn't carry completed step outputs forward

---

## Skills System

7 skills in `skills/`, each with `skill.json` + `SKILL.md`:

| Skill | Category | Preferred Tools | Verification |
|-------|----------|-----------------|--------------|
| `web_research` | web | WebAccessTool, ContextSummarizerTool | source_backed |
| `computer_automation` | computer | FilesystemTool, ShellTool | side_effect_observed |
| `code_workspace` | development | CodeEditorTool, TestRunnerTool | output_validation |
| `conversation` | conversation | — | none |
| `browser_automation` | automation | BrowserAutomationTool | side_effect_observed |
| `data_operations` | data | HTTPTool, JSONTool, DatabaseQueryTool | output_validation |
| `knowledge_management` | productivity | LocalCodeSnippetLibraryTool, LocalRunNoteTool | output_validation |

**Selection flow:**
1. Simple greeting/farewell → early return
2. AutoSkillDetector: keyword overlap + learned triggers + tool health
3. LLM fallback if confidence < 0.35
4. `conversation` → direct LLM response
5. Other → SkillExecutionContext → ContextAwareToolSelector → ExecutionEngine

---

## Tools

### Core (always loaded)
- `FilesystemTool` — read_file, write_file, list_directory, list_files
- `WebAccessTool` — fetch_url, search_web, open_page, crawl_site, extract_links, extract_search_results
- `HTTPTool` — get, post, put, delete (domain allowlist; hidden when WebAccessTool available)
- `JSONTool` — parse, stringify, query
- `ShellTool` — execute (command allowlist)

### Experimental (loaded at runtime)
- `ContextSummarizerTool` — summarize_text, extract_key_points, sentiment_analysis, generate_json_output
- `DatabaseQueryTool` — query_logs, analyze_tool_performance, find_failure_patterns, get_evolution_history
- `BrowserAutomationTool` — open_and_navigate, take_screenshot, find_element, get_page_content
- `LocalCodeSnippetLibraryTool` — save_snippet, get_snippet, search, list_popular
- `LocalRunNoteTool` — note management and persistence
- `BenchmarkRunnerTool` — run_benchmark_suite, add_benchmark_case, execute, run_suite
- `MCPAdapterTool` — call_tool, list_tools, get_server_info (one instance per MCP server)

### Available, not loaded by default
- `WorkflowAutomationTool`, `ExecutionPlanEvaluatorTool`, `TaskBreakdownTool`
- `UserApprovalGateTool`, `IntentClassifierTool`, `SystemIntrospectionTool`
- `DataTransformationTool`, `DiffComparisonTool`

---

## Tool Creation Flow

```
User: "Create a tool for X"  (or autonomous gap triggers it)
    ↓
1. Spec Generation — LLM + model-aware confidence threshold (0.35 local / 0.5 cloud)
2. Code Generation — Qwen multi-stage or GPT single-shot
3. Enhanced Validation — 20 AST + architecture gates
4. Dependency Check — AST-based missing libs + services
5. Sandbox Test — isolated execution
6. Human Approval → activate + resolved_gaps updated
```

Registry-aware: existing tool name → returns "already exists", redirects to evolution.

---

## Tool Evolution Flow

```
1. Analyze — quality score 0-100 + top 3 recent failures from cua.db injected
2. Propose — LLM proposes minimal fix with action_type + target_functions list
3. Generate — scopes rewrite to target_functions only
4. Check Dependencies — AST parse
5. Validate — 20-gate AST + CUA architecture checks
6. Sandbox Test
7. Human Approval → apply + services_cache invalidated
```

---

## Validation Gates (20)

AST syntax · Required methods · Execute signature · Capability registration · Parameter validation · Import validation · No mutable defaults · No relative paths · No undefined helpers · Orchestrator parameter check · Tool name assignment · Contract compliance · Undefined method detection · Uninitialized attribute detection · Code truncation detection · Service usage pattern validation · Service method existence · Capability-spec parameter matching · Hardcoded value detection · Return type validation

**Blocked in generated tool code (AST-enforced):**
- `subprocess.*` — all variants (run, call, Popen, check_output, check_call)
- `os.system`, `os.popen`, `os.execv*`, `os.spawn*`
- `eval`, `exec`, `compile`, `__import__`
- `import subprocess` / `from subprocess import *` — blocked at import level
- `import pty`, `import pexpect`, `import fabric`, `import paramiko`

All shell access must go through `self.services.shell.execute()` which enforces the command allowlist.

---

## Observability — Single Database

All data lives in `data/cua.db` (WAL mode, single writer lock):

| Table | Contents |
|-------|----------|
| `logs` | All service logs |
| `executions` | Tool execution history + timing |
| `execution_context` | Per-execution service/LLM call metadata |
| `evolution_runs` | Evolution attempts + health delta |
| `evolution_artifacts` | Per-step evolution artifacts |
| `tool_creations` | Tool creation attempts |
| `creation_artifacts` | Per-step creation artifacts |
| `conversations` | Chat messages |
| `sessions` | Session state |
| `learned_patterns` | Skill trigger patterns |
| `failures` | Failed changes + error patterns |
| `risk_weights` | Risk scorer pattern weights |
| `improvements` | Improvement attempt outcomes |
| `plan_history` | Execution plan history |
| `improvement_metrics` | Self-improvement iteration metrics |
| `tool_metrics_hourly` | Per-tool hourly performance |
| `system_metrics_hourly` | System-wide hourly metrics |
| `auto_evolution_metrics` | Auto-evolution scan metrics |
| `resolved_gaps` | Capability gaps resolved (feedback loop) |

---

## Update Pipeline (Self-Improvement)

```
Proposed change
    ↓
IdempotencyChecker → reject duplicates
RiskScorer → score by files changed + diff size
UpdateGate → APPROVED / PENDING / REJECTED
    ↓
PENDING → human approval required
APPROVED → SandboxRunner → AtomicApplier → AuditLogger
```

---

## Safety Features

- Sandbox testing for all generated code
- Human approval gates for evolution, creation, and risky updates
- Risk scoring before any self-modification
- Protected files blocked from modification (`immutable_brain_stem`)
- 20-gate AST + architectural validation
- Circuit breaker per tool with reputation scoring
- Rollback support (backups before changes)
- Service pattern enforcement (`self.services.X` only)
- Idempotency checking (no duplicate changes)
- Input size limit (50KB max on /chat)
- Correlation context on all requests
- Fernet-encrypted credential store (per-tool scoping, TTL support)
- MCP server connections validated before capability registration
- Config validator at startup (MCP URLs, LLM provider, port range)
- Gap detection requires ≥2 keyword hits + ≥3 occurrences + confidence ≥0.7

---

## Available Services (for tool code)

```python
self.services.storage.save(id, data)
self.services.storage.get(id)
self.services.storage.list(limit=10)
self.services.storage.update(id, updates)
self.services.storage.delete(id)

self.services.llm.generate(prompt, temperature, max_tokens)
self.services.http.get(url)
self.services.http.post(url, data)
self.services.fs.read(path)
self.services.fs.write(path, content)
self.services.json.parse(text)
self.services.json.stringify(data)
self.services.shell.execute(command)
self.services.logging.info(message)
self.services.time.now_utc()
self.services.ids.generate(prefix)

# Credential store (per-tool scoped)
self.services.credentials.get(key)
self.services.credentials.set(key, value, allowed_tools)
self.services.credentials.exists(key)
self.services.credentials.delete(key)

self.services.call_tool(tool_name, operation, **parameters)
self.services.list_tools()
self.services.has_capability(capability_name)
```

---

## Backend API

### Core
- `POST /chat` — skill-aware routing + tool calling + autonomous agent
- `GET /health` — health + system_available
- `GET /status` — sessions, tools, capabilities, skills
- `POST /cache/clear` — clear sessions + caches

### Realtime
- `GET /events` — SSE stream
- `WS /ws` — WebSocket (event bus + initial state)
- `WS /ws/trace` — trace events

### Skills
- `GET /skills/list`, `GET /skills/{skill_name}`, `POST /skills/refresh`, `POST /skills/update/{skill_name}`

### Tools
- `POST /api/tools/sync`, `GET /api/tools/registry`, `GET /api/tools/capabilities`, `POST /api/tools/test/{tool_name}`

### Self-Improvement
- `POST /improvement/start`, `POST /improvement/start-continuous`, `POST /improvement/stop`
- `POST /improvement/approve`, `GET /improvement/status`, `GET /improvement/logs`
- `GET /improvement/tools/suggest?skip=N`, `POST /improvement/tools/create`
- `GET /improvement/history`, `GET /improvement/analytics`, `GET /improvement/previews`
- `POST /improvement/rollback/{plan_id}`

### Tool Evolution
- `POST /evolution/evolve`, `GET /evolution/pending`
- `POST /evolution/approve/{tool_name}`, `POST /evolution/reject/{tool_name}`
- `POST /evolution/test/{tool_name}`, `GET /evolution/conversation/{tool_name}`
- `POST /evolution/resolve-dependencies/{tool_name}`

### Auto-Evolution + Coordinated Autonomy
- `POST /auto-evolution/start`, `POST /auto-evolution/stop`, `GET /auto-evolution/status`
- `POST /auto-evolution/config`, `GET /auto-evolution/queue`, `POST /auto-evolution/trigger-scan`
- `POST /auto-evolution/coordinated/start`, `POST /auto-evolution/coordinated/stop`
- `POST /auto-evolution/coordinated/run-cycle`, `GET /auto-evolution/coordinated/status`
- `POST /auto-evolution/coordinated/config`

### Pending Approvals
- `GET /pending-tools/list`, `POST /pending-tools/{tool_id}/approve`, `POST /pending-tools/{tool_id}/reject`
- `GET /api/libraries/pending`, `POST /api/libraries/{lib_id}/approve`
- `GET /api/services/pending`, `POST /api/services/{service_id}/approve`
- `GET /pending-skills/list`, `POST /pending-skills/{skill_id}/approve`

### Capability Gaps
- `GET /improvement/evolution/capability-gaps`
- `POST /improvement/evolution/detect-gap`

### Quality + Metrics
- `GET /quality/summary`, `GET /quality/all`, `GET /quality/weak`
- `GET /quality/tool/{tool_name}`, `GET /quality/llm-analysis/{tool_name}`
- `GET /metrics/tool/{tool_name}`, `GET /metrics/system`, `GET /metrics/summary`

### Observability
- `GET /observability/tables`, `GET /observability/data/{db_name}/{table_name}`
- `GET /observability/detail/{db_name}/{table_name}/{row_id}`
- `GET /observability/filters/{db_name}/{table_name}/{column}`

### Tools Management
- `GET /tools-management/summary`, `GET /tools-management/list`
- `GET /tools-management/detail/{tool_name}`, `GET /tools-management/code/{tool_name}`
- `POST /tools-management/trigger-check/{tool_name}`

### Circuit Breaker + Reputation
- `GET /circuit-breaker/status`
- `GET /circuit-breaker/reputation` — composite scores for all tools
- `GET /circuit-breaker/tool/{name}` — per-tool status + reputation

### MCP
- `GET /mcp/status` — connected servers + health
- `GET /mcp/tools` — all discovered MCP capabilities

### Credentials
- `GET /credentials/list`, `POST /credentials/set`, `DELETE /credentials/{key}`
- `GET /credentials/{key}/exists`, `PATCH /credentials/{key}/scope`

### Strategic Memory + Tasks
- `GET /agent/strategic-memory` — stats + top 10 patterns by win-rate
- `GET /tasks/active`, `GET /tasks/history`, `POST /tasks/{parent_id}/abort`

### Settings
- `GET /settings/models`, `POST /settings/model`, `POST /settings/reload-config`

---

## Project Structure

```
CUA/
├── api/                         # FastAPI routers (30+ files)
│   ├── server.py                # Main server + /chat endpoint
│   ├── bootstrap.py             # Runtime init + router wiring
│   ├── chat_helpers.py          # Chat handler, gap recording, tool execution
│   └── *_api.py                 # Feature routers
│
├── core/                        # Core logic (80+ modules)
│   ├── skills/                  # Skill system
│   │   ├── selector.py          # 3-signal scoring + LLM fallback + stemming
│   │   ├── execution_context.py # SkillExecutionContext (32 fields)
│   │   ├── context_hydrator.py  # Skill → execution context
│   │   └── tool_selector.py     # ContextAwareToolSelector (reputation-weighted)
│   ├── tool_creation/           # 6-step creation pipeline
│   ├── tool_evolution/          # 6-step evolution pipeline
│   ├── autonomous_agent.py
│   ├── task_planner.py          # Token-budget trimming, memory context first
│   ├── execution_engine.py      # Parallel DAG wave execution, wave-aware resume
│   ├── tool_orchestrator.py     # Cached signatures, services_cache invalidation
│   ├── strategic_memory.py      # Jaccard + win-rate + recency decay
│   ├── unified_memory.py        # 4-store search facade
│   ├── capability_resolver.py   # 5-step resolution chain, config-driven catalogues
│   ├── capability_mapper.py     # Scans tools/ + tools/experimental/
│   ├── gap_detector.py          # ≥2 keyword hits, LLM gap analysis
│   ├── gap_tracker.py           # Persistence, resolution_attempted filter
│   ├── auto_evolution_orchestrator.py  # Scan + queue, cua.db failure read
│   ├── coordinated_autonomy_engine.py  # Full cycle: health → resolve → evolve → improve
│   ├── credential_store.py      # Fernet encryption, TTL support
│   ├── circuit_breaker.py       # Thread-safe, CLOSED→OPEN→HALF_OPEN
│   ├── cua_db.py                # Single WAL-mode SQLite, 21 tables
│   └── config_manager.py        # Config + startup validator
│
├── tools/                       # Tool implementations
│   ├── enhanced_filesystem_tool.py
│   ├── web_access_tool.py
│   ├── http_tool.py
│   ├── json_tool.py
│   ├── shell_tool.py
│   └── experimental/            # 15 experimental tools
│
├── skills/                      # Skill definitions (7 skills)
│
├── planner/
│   ├── llm_client.py
│   └── tool_calling.py          # Native function calling, multi-round
│
├── updater/                     # Self-improvement update pipeline
│   ├── orchestrator.py
│   ├── risk_scorer.py
│   ├── sandbox_runner.py
│   ├── update_gate.py
│   ├── atomic_applier.py
│   └── audit_logger.py
│
├── ui/src/components/           # React UI (50+ components)
│
└── data/
    ├── cua.db                   # Single consolidated database (WAL)
    ├── capability_gaps.json     # Gap tracker state
    ├── strategic_memory.json    # Strategic memory state
    ├── credentials.enc          # Encrypted credential store
    └── pending_*.json           # Pending approval queues
```

---

## UI Modes

1. **Chat** — conversational interface, native tool calling, agentic responses
2. **Tools Mode** — tool creation, capability spec, sandbox testing, approval workflow
3. **Evolution Mode** — tool selection, evolution workflow, pending approvals, capability gaps, auto-evolution, pending services
4. **Autonomy Mode** — Agent Cockpit: live cycle pipeline, thought stream (WS), gap kanban, cycle history, start/stop/run-cycle controls, pending approvals banner, evolution queue strip
5. **Tools Management** — health dashboard, search/filter, LLM analysis, code viewer
6. **Observability** — full-page database viewer, paginated data, row details, column filters

---

## Configuration

**Environment Variables:**
- `OLLAMA_URL` — Ollama server URL (default: http://localhost:11434)
- `CUA_API_URL` — Backend base URL (default: http://localhost:8000)
- `CORS_ALLOW_ORIGINS` — Allowed origins (default: http://localhost:3000)
- `REACT_APP_API_URL` — Frontend → backend URL
- `REACT_APP_WS_URL` — Frontend WebSocket URL
- `CUA_RELOAD_MODE` — Set to `1` to disable coordinated autonomy (use with uvicorn --reload)

**Config Files:**
- `config.yaml` — System config: MCP servers, capability_resolver catalogues, improvement settings
- `config/model_capabilities.json` — Per-model: strategy, max_lines, min_confidence
- `requirements.txt` — Python dependencies
- `ui/package.json` — Frontend dependencies

---

## Testing

```bash
pytest -q
```

On Windows, `tmpdir` and `cacheprovider` are disabled in `pytest.ini`. A local `tmp_path` fixture is in `tests/conftest.py`.

- `tests/unit/` — unit tests per component
- `tests/integration/` — full pipeline tests
- `tests/smoke/` — boot + approval flow
- `tests/experimental/` — per experimental tool

---

## Reliability Notes

- `cua.db` is the single source of truth — WAL mode, module-level write lock, best-effort (logs warning and continues on lock)
- Tool creation is registry-aware — existing names redirect to evolution
- Service calls validated — only `self.services.*` APIs pass the 20-gate validator
- Scaffold-first fallback — if full generation fails, a safe scaffold is queued for evolution
- Parallel execution is thread-safe — `_execute_step` reads shared state, never mutates mid-wave
- Credential store falls back to base64 obfuscation if `cryptography` is not installed
- Coordinated autonomy is blocked in reload mode (`CUA_RELOAD_MODE=1`) to prevent concurrent cycle conflicts

---

## Security Model

**Shell access** — `ShellTool` enforces a command allowlist. Generated tool code cannot bypass this:
- `subprocess.*`, `os.system`, `os.popen`, `os.exec*`, `os.spawn*` → blocked by AST validator
- `eval`, `exec`, `compile`, `__import__` → blocked by AST validator
- `import subprocess` / `from subprocess import *` → blocked at import statement level
- `import pty`, `import pexpect`, `import fabric`, `import paramiko` → blocked at import level
- All shell access in tool code must use `self.services.shell.execute(command)` which routes through the allowlist

**Human approval gates** — no generated code runs without explicit approval:
- Tool creation → `pending_tools` queue → human approves → registered
- Tool evolution → `pending_evolutions` queue → human approves → applied
- Self-improvement patches → `UpdateGate` → PENDING → human approves → `AtomicApplier`

**Sandbox isolation** — all generated code is executed in an isolated sandbox before queuing for approval.

**Protected files** — `immutable_brain_stem` blocks modification of core system files regardless of what the LLM proposes.

**Input limits** — `/chat` enforces a 50KB max payload. Correlation IDs on all requests for audit tracing.

**Credential isolation** — Fernet-encrypted store with per-tool access scoping. A tool can only read credentials it was explicitly granted access to.

---

## Failure Handling Model

```
Tool execution fails
    ↓
CircuitBreaker records failure (CLOSED → OPEN after threshold)
    ↓
ToolOrchestrator fallback: retry with next-best tool by reputation score
    ↓
ExecutionEngine: step marked failed, replan triggered
    ↓
TaskPlanner replan: completed step outputs passed forward, failed step retried with context
    ↓
If gap detected: GapDetector → GapTracker (≥3 occurrences, conf ≥0.7)
    ↓
Next autonomy cycle: CapabilityResolver → reroute/MCP/API/create_tool
```

**Per-tool circuit breaker states:** `CLOSED` (normal) → `OPEN` (failing, skip tool) → `HALF_OPEN` (probe recovery)

**Evolution failures** — if code generation fails all 3 retries, a safe scaffold is queued instead. The original tool is never modified until human approval.

---

## Autonomy Guarantees

| Guarantee | Mechanism |
|-----------|----------|
| No infinite tool creation | `max_new_tools_per_scan=1` + registry coverage check before CREATE |
| No duplicate gaps | `resolved_gaps` table + `resolution_attempted` filter in `GapTracker` |
| No runaway evolution | `enable_enhancements=False` — only WEAK/NEEDS_IMPROVEMENT tools queued |
| No low-usage tool churn | `min_usage=5` — tools with <5 executions never analyzed |
| No false-positive gaps | ≥2 keyword hits + ≥3 occurrences + confidence ≥0.7 required |
| No unapproved code runs | Every create/evolve/improve goes through human approval gate |
| No permanent pause on idle | `pause_on_low_value=False` — idle cycles (nothing to improve) are normal |
| Bounded improvement passes | `improvement_iterations_per_cycle=3` hard cap per cycle |
| Bounded evolution per cycle | `max_evolutions_per_cycle=2` hard cap per cycle |

---

## Contributing

1. Pass `SkillExecutionContext` where execution happens
2. Track steps: `execution_context.add_step()`
3. Track errors: `execution_context.add_error()`
4. New services → add to `core/tool_services.py` + `AVAILABLE_SERVICES` in `core/dependency_checker.py`
5. New DB tables → add schema to `core/cua_db.py` (`_create_all_tables`) + `core/database_schema_registry.py`
6. New MCP servers → add `MCPServerConfig` entry to `config.yaml` under `mcp_servers`
7. Parallel-safe tools → no shared mutable state; `_execute_step` is called from threads

---

## Documentation

- `docs/ARCHITECTURE.md` — architecture deep-dive
- `docs/SYSTEM_ARCHITECTURE.md` — system architecture
- `docs/OBSERVABILITY.md` — observability system guide
- `docs/AUTO_EVOLUTION_IMPLEMENTATION.md` — auto-evolution guide
- API reference: http://localhost:8000/docs

---

## License

MIT License — See LICENSE file
