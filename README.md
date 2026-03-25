# CUA — Autonomous Agent System

> **A local-first, self-evolving AI agent built for Qwen 14B via Ollama.**  
> Plans tasks, calls tools, detects capability gaps, generates new tools, and improves itself — all on your own hardware, with human approval gates at every critical step.

---

## What CUA does

CUA is an autonomous agent loop designed to run entirely offline on a local LLM. It:

- **Plans and executes** multi-step tasks as parallel DAG waves
- **Routes intelligently** via a 7-skill system with 3-signal scoring and LLM fallback
- **Calls tools natively** using function calling across 20+ tools
- **Detects capability gaps** when tools fail repeatedly and resolves them automatically
- **Generates and evolves tools** through LLM-driven pipelines with 20-gate AST validation
- **Manages dependencies** automatically — detects missing libraries and services via AST parsing
- **Self-improves** through a coordinated autonomy engine with bounded iteration and human approval gates
- **Observes everything** in a single consolidated SQLite database (`cua.db`, WAL mode)
- **Stores credentials securely** with Fernet encryption, per-tool access scoping, and TTL support
- **Connects to MCP servers** via stdlib JSON-RPC 2.0 with dynamic capability discovery

---

## Designed for local LLMs

CUA is optimised for **Qwen 14B** running via Ollama. It does not require any cloud API. All planning, tool generation, gap analysis, and self-improvement run against your local model.

Confidence thresholds are model-aware: local models (Qwen, Mistral) use `0.35`, cloud models (GPT, Claude, Gemini) use `0.5`. Tool generation uses a multi-stage Qwen pipeline rather than single-shot generation to improve reliability at 14B scale.

---

## Quick start

```bash
# 1. Install Ollama and pull the model
ollama pull qwen2.5-coder:14b

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Start the backend (port 8000)
python start.py

# 4. Start the UI (separate terminal, port 3000)
cd ui && npm install && npm start
```

Access the UI at `http://localhost:3000`  
API docs at `http://localhost:8000/docs`

**Windows users:** Use `setup.bat` for first-time setup, then `start.bat` to run.

---

## Architecture

```
User request
    ↓
Skill selector — keyword overlap + learned triggers + tool health (3-signal)
    ↓
SkillExecutionContext (32 fields) — metadata, tool guidance, I/O expectations
    ↓
ContextAwareToolSelector — reputation-weighted + circuit breaker health check
    ↓
UnifiedMemory — Jaccard search across 4 stores, injected into planner prompt
    ↓
TaskPlanner — LLM DAG generation, token-budget trimmed, memory context first
    ↓
ExecutionEngine — parallel DAG wave execution (ThreadPoolExecutor, max 4 workers, 120s/step)
    ↓
ToolOrchestrator — cached signatures, fallback on error, output validation
    ↓
CapabilityResolver — gap? reroute → MCP → API wrap → create tool
    ↓
Response
```

---

## Skills

Seven skills live in `skills/`, each with a `skill.json` and `SKILL.md`:

| Skill | Category | Preferred tools | Verification |
|-------|----------|-----------------|--------------|
| `web_research` | web | WebAccessTool, ContextSummarizerTool | source_backed |
| `computer_automation` | computer | FilesystemTool, ShellTool | side_effect_observed |
| `code_workspace` | development | CodeEditorTool, TestRunnerTool | output_validation |
| `conversation` | conversation | — | none |
| `browser_automation` | automation | BrowserAutomationTool | side_effect_observed |
| `data_operations` | data | HTTPTool, JSONTool, DatabaseQueryTool | output_validation |
| `knowledge_management` | productivity | LocalCodeSnippetLibraryTool, LocalRunNoteTool | output_validation |

Selection flow: simple greetings short-circuit early → AutoSkillDetector scores keyword overlap + learned triggers + tool health → LLM fallback if confidence < 0.35 → `conversation` skill goes direct to LLM, all others go through the full execution pipeline.

---

## Tools

### Core (always loaded)

- `FilesystemTool` — read, write, list files and directories
- `WebAccessTool` — fetch URLs, search the web, crawl, extract links
- `HTTPTool` — GET, POST, PUT, DELETE with domain allowlist
- `JSONTool` — parse, stringify, query
- `ShellTool` — execute commands via allowlist

### Experimental (loaded at runtime from `tools/experimental/`)

- `ContextSummarizerTool` — summarise text, extract key points, sentiment, JSON output
- `DatabaseQueryTool` — query logs, analyse tool performance, find failure patterns, evolution history
- `BrowserAutomationTool` — navigate, screenshot, find elements, get page content
- `LocalCodeSnippetLibraryTool` — save, get, search, list code snippets
- `LocalRunNoteTool` — note management and persistence
- `BenchmarkRunnerTool` — run benchmark suites, add cases, execute, report
- `MCPAdapterTool` — call MCP tools, list tools, get server info (one instance per server)

### Available but not loaded by default

`WorkflowAutomationTool`, `ExecutionPlanEvaluatorTool`, `TaskBreakdownTool`, `UserApprovalGateTool`, `IntentClassifierTool`, `SystemIntrospectionTool`, `DataTransformationTool`, `DiffComparisonTool`

---

## Tool creation flow

```
User: "Create a tool for X"  — or autonomous gap triggers it
    ↓
1. Spec generation   — LLM with model-aware confidence threshold (0.35 local / 0.5 cloud)
2. Code generation   — Qwen multi-stage pipeline or single-shot for cloud models
3. Validation        — 20 AST + architecture gates (see below)
4. Dependency check  — AST-based missing libs + services detection
5. Sandbox test      — isolated execution
6. Human approval    — activate + resolved_gaps updated in cua.db
```

If the tool name already exists in the registry, the system redirects to evolution instead of creating a duplicate. If full generation fails after 3 retries, a safe scaffold is queued for evolution rather than blocking.

---

## Tool evolution flow

```
1. Analyse   — quality score 0–100 + top 3 recent failures from cua.db
2. Propose   — LLM proposes minimal fix with action_type + target_functions list
3. Generate  — rewrites only the target_functions (surgical, not full rewrite)
4. Dep check — AST parse for new imports/services
5. Validate  — 20-gate AST + CUA architecture checks
6. Sandbox   — isolated test
7. Approve   — human approves → apply + services_cache invalidated
```

Evolution is **surgical by default** — `target_functions` scopes the rewrite to only the functions that need changing, leaving the rest of the tool untouched.

---

## Validation gates (20)

AST syntax · Required methods · Execute signature · Capability registration · Parameter validation · Import validation · No mutable defaults · No relative paths · No undefined helpers · Orchestrator parameter check · Tool name assignment · Contract compliance · Undefined method detection · Uninitialized attribute detection · Code truncation detection · Service usage pattern validation · Service method existence · Capability-spec parameter matching · Hardcoded value detection · Return type validation

**Blocked in all generated tool code (AST-enforced):**

- `subprocess.*` — all variants
- `os.system`, `os.popen`, `os.execv*`, `os.spawn*`
- `eval`, `exec`, `compile`, `__import__`
- `import subprocess` / `from subprocess import *`
- `import pty`, `import pexpect`, `import fabric`, `import paramiko`

All shell access must go through `self.services.shell.execute(command)` which enforces the command allowlist.

---

## Autonomous loop

```
Chat failure → record_capability_gap
    ↓ skip if already in resolved_gaps
GapTracker — persist gap (requires ≥3 occurrences, confidence ≥0.7, ≥2 keyword hits)
    ↓
CoordinatedAutonomyEngine.run_cycle
    1. BaselineHealthChecker — abort if system is broken
    2. CapabilityResolver pass — reroute / MCP / API wrap gaps marked resolved, skip CREATE
    3. AutoEvolutionOrchestrator.run_cycle
        a. ToolQualityAnalyzer — queue WEAK/NEEDS_IMPROVEMENT tools (min 5 uses)
        b. LLM gap analysis over failures table in cua.db
        c. Registry coverage check — skip CREATE if existing tool already covers gap
        d. Queue CREATE (max 1 new tool per scan)
    4. SelfImprovementLoop — bounded pass (max 3 iterations)
    5. Quality gate — pause if consecutive low-value cycles
    ↓
_process_evolution → pending approval → human approves → resolved_gaps written to cua.db
```

### Autonomy guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| No infinite tool creation | `max_new_tools_per_scan=1` + registry coverage check before CREATE |
| No duplicate gaps | `resolved_gaps` table + `resolution_attempted` filter in GapTracker |
| No runaway evolution | `enable_enhancements=False` — only WEAK/NEEDS_IMPROVEMENT tools queued |
| No low-usage churn | `min_usage=5` — tools with fewer than 5 executions never analysed |
| No false-positive gaps | ≥2 keyword hits + ≥3 occurrences + confidence ≥0.7 required |
| No unapproved code runs | Every create/evolve/improve goes through human approval gate |
| Bounded improvement | `improvement_iterations_per_cycle=3` hard cap |
| Bounded evolution | `max_evolutions_per_cycle=2` hard cap |

---

## Capability resolver

When a gap is confirmed, the resolver escalates through five steps, exiting as soon as one succeeds:

1. **Local reroute** — try next-best tool by reputation score
2. **MCP server** — check connected MCP servers for a matching capability
3. **API wrap** — wrap an external API as a new tool
4. **Create tool** — LLM-generate a new tool (requires human approval)
5. **Write to `resolved_gaps`** — gap is closed, never re-queued

---

## Observability — single database

All data lives in `data/cua.db` (WAL mode, single writer lock, 21 tables):

| Table | Contents |
|-------|----------|
| `logs` | All service logs |
| `executions` | Tool execution history and timing |
| `execution_context` | Per-execution service/LLM call metadata |
| `evolution_runs` | Evolution attempts and health delta |
| `evolution_artifacts` | Per-step evolution artifacts |
| `tool_creations` | Tool creation attempts |
| `creation_artifacts` | Per-step creation artifacts |
| `conversations` | Chat messages |
| `sessions` | Session state |
| `learned_patterns` | Skill trigger patterns |
| `failures` | Failed changes and error patterns |
| `risk_weights` | Risk scorer pattern weights |
| `improvements` | Improvement attempt outcomes |
| `plan_history` | Execution plan history |
| `improvement_metrics` | Self-improvement iteration metrics |
| `tool_metrics_hourly` | Per-tool hourly performance |
| `system_metrics_hourly` | System-wide hourly metrics |
| `auto_evolution_metrics` | Auto-evolution scan metrics |
| `resolved_gaps` | Capability gaps resolved (feedback loop) |

> **Note:** `ImprovementMemory` currently writes to a separate `data/improvement_memory.db`. Consolidation to `cua.db` is a known pending task.

---

## Available services (for tool code)

Tools access the runtime via `self.services.*`:

```python
# Storage (auto-scoped to tool)
self.services.storage.save(id, data)
self.services.storage.get(id)
self.services.storage.list(limit=10)
self.services.storage.update(id, updates)
self.services.storage.delete(id)

# LLM
self.services.llm.generate(prompt, temperature, max_tokens)

# HTTP
self.services.http.get(url)
self.services.http.post(url, data)

# Filesystem
self.services.fs.read(path)
self.services.fs.write(path, content)

# JSON
self.services.json.parse(text)
self.services.json.stringify(data)

# Shell (allowlist-enforced)
self.services.shell.execute(command)

# Logging
self.services.logging.info(message)
self.services.logging.error(message)
self.services.logging.warning(message)
self.services.logging.debug(message)

# Time and IDs
self.services.time.now_utc()
self.services.ids.generate(prefix)

# Credentials (per-tool scoped, Fernet encrypted)
self.services.credentials.get(key)
self.services.credentials.set(key, value, allowed_tools)
self.services.credentials.exists(key)
self.services.credentials.delete(key)

# Inter-tool communication
self.services.call_tool(tool_name, operation, **parameters)
self.services.list_tools()
self.services.has_capability(capability_name)
```

---

## UI modes

1. **Chat** — conversational interface, native tool calling, agentic responses
2. **Tools mode** — tool creation, capability spec, sandbox testing, approval workflow
3. **Evolution mode** — tool selection, evolution workflow, pending approvals, capability gaps, auto-evolution, pending services
4. **Autonomy mode** — Agent Cockpit: live cycle pipeline, thought stream (WebSocket), gap kanban, cycle history, start/stop/run-cycle controls, pending approvals banner, evolution queue strip
5. **Tools management** — health dashboard, search/filter, LLM analysis, code viewer
6. **Observability** — full-page database viewer, paginated data, row details, column filters

---

## Security model

**Shell access** — `ShellTool` enforces a command allowlist. Generated code cannot bypass this because `subprocess.*`, `os.system`, `eval`, `exec`, and all SSH/PTY libraries are blocked at the AST validation stage before any code is accepted.

**Human approval gates** — no generated code runs without explicit approval:
- Tool creation → `pending_tools` queue → human approves → registered
- Tool evolution → `pending_evolutions` queue → human approves → applied
- Self-improvement patches → `UpdateGate` → PENDING → human approves → `AtomicApplier`

**Sandbox isolation** — all generated code executes in an isolated sandbox before queuing for approval.

**Protected files** — `immutable_brain_stem` blocks modification of core system files regardless of LLM output.

**Credential isolation** — Fernet-encrypted store with per-tool access scoping. A tool can only read credentials it was explicitly granted.

**Input limits** — `/chat` enforces a 50KB max payload. Correlation IDs on all requests for audit tracing.

---

## Failure handling

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
If gap detected: GapDetector → GapTracker (≥3 occurrences, confidence ≥0.7)
    ↓
Next autonomy cycle: CapabilityResolver → reroute / MCP / API wrap / create tool
```

Circuit breaker states per tool: `CLOSED` (normal) → `OPEN` (failing, skip) → `HALF_OPEN` (probe recovery)

---

## Project structure

```
CUA/
├── api/                          # FastAPI routers (30+ files)
│   ├── server.py                 # Main server + /chat endpoint
│   ├── bootstrap.py              # Runtime init + router wiring
│   ├── chat_helpers.py           # Chat handler, gap recording, tool execution
│   └── *_api.py                  # Feature routers
│
├── core/                         # Core logic (80+ modules)
│   ├── skills/                   # Skill system
│   │   ├── selector.py           # 3-signal scoring + LLM fallback
│   │   ├── execution_context.py  # SkillExecutionContext (32 fields)
│   │   ├── context_hydrator.py   # Skill → execution context
│   │   └── tool_selector.py      # ContextAwareToolSelector
│   ├── tool_creation/            # 6-step creation pipeline
│   ├── tool_evolution/           # 6-step evolution pipeline
│   ├── autonomous_agent.py
│   ├── task_planner.py           # Token-budget trimming, memory context first
│   ├── execution_engine.py       # Parallel DAG wave execution
│   ├── tool_orchestrator.py      # Cached signatures, services_cache invalidation
│   ├── strategic_memory.py       # Jaccard + win-rate + recency decay
│   ├── unified_memory.py         # 4-store search facade
│   ├── capability_resolver.py    # 5-step resolution chain
│   ├── capability_mapper.py      # Scans tools/ + tools/experimental/
│   ├── gap_detector.py           # ≥2 keyword hits, LLM gap analysis
│   ├── gap_tracker.py            # Persistence, resolution_attempted filter
│   ├── auto_evolution_orchestrator.py
│   ├── coordinated_autonomy_engine.py
│   ├── credential_store.py       # Fernet encryption, TTL support
│   ├── circuit_breaker.py        # Thread-safe CLOSED→OPEN→HALF_OPEN
│   ├── cua_db.py                 # Single WAL-mode SQLite, 21 tables
│   └── config_manager.py         # Config + startup validator
│
├── tools/                        # Tool implementations
│   ├── enhanced_filesystem_tool.py
│   ├── web_access_tool.py
│   ├── http_tool.py
│   ├── json_tool.py
│   ├── shell_tool.py
│   └── experimental/             # Runtime-loaded tools
│
├── skills/                       # 7 skill definitions
│
├── planner/
│   ├── llm_client.py
│   └── tool_calling.py           # Native function calling, multi-round
│
├── updater/                      # Self-improvement update pipeline
│   ├── orchestrator.py
│   ├── risk_scorer.py
│   ├── sandbox_runner.py
│   ├── update_gate.py
│   ├── atomic_applier.py
│   └── audit_logger.py
│
├── ui/src/components/            # React UI (50+ components)
│
├── config.yaml                   # MCP servers, resolver catalogues, improvement settings
├── config/model_capabilities.json
├── requirements.txt
└── data/
    ├── cua.db                    # Single consolidated database (WAL)
    ├── capability_gaps.json
    ├── strategic_memory.json
    ├── credentials.enc
    └── pending_*.json
```

---

## Configuration

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `CUA_API_URL` | `http://localhost:8000` | Backend base URL |
| `CORS_ALLOW_ORIGINS` | `http://localhost:3000` | Allowed CORS origins |
| `REACT_APP_API_URL` | — | Frontend → backend URL |
| `REACT_APP_WS_URL` | — | Frontend WebSocket URL |
| `CUA_RELOAD_MODE` | — | Set to `1` to disable coordinated autonomy (use with `uvicorn --reload`) |

**Config files:**
- `config.yaml` — MCP servers, capability_resolver catalogues, improvement settings
- `config/model_capabilities.json` — per-model strategy, max_lines, min_confidence
- `requirements.txt` — Python dependencies
- `ui/package.json` — frontend dependencies

---

## Testing

```bash
pytest -q
```

- `tests/unit/` — unit tests per component
- `tests/integration/` — full pipeline tests
- `tests/smoke/` — boot and approval flow
- `tests/experimental/` — per experimental tool

On Windows, `tmpdir` and `cacheprovider` are disabled in `pytest.ini`. A local `tmp_path` fixture is in `tests/conftest.py`.

---

## Known gaps and limitations

| Area | Issue |
|------|-------|
| `CircuitBreaker` | Uses cumulative failure count, not a sliding window — transient failures permanently degrade tool reputation |
| `ImprovementMemory` | Still writes to `data/improvement_memory.db` instead of `cua.db` |
| `CapabilityResolver` | `_MCP_CATALOGUE` / `_API_CATALOGUE` config override works but defaults are static |
| `SkillSelector` | No strong negative signal between competing skills |
| `TaskPlanner` | Replan on retry doesn't carry completed step outputs forward |
| Parallel execution | `max_workers=4` was tuned for cloud LLMs — reduce to 1–2 for single-GPU local setups |
| Strategic memory | Jaccard similarity is keyword-based, not semantic — consider replacing with a local embedding model (e.g. `nomic-embed-text` via Ollama) |

---

## Contributing

1. Pass `SkillExecutionContext` wherever execution happens
2. Track steps with `execution_context.add_step()`
3. Track errors with `execution_context.add_error()`
4. New services → add to `core/tool_services.py` and `AVAILABLE_SERVICES` in `core/dependency_checker.py`
5. New DB tables → add schema to `core/cua_db.py` (`_create_all_tables`) and `core/database_schema_registry.py`
6. New MCP servers → add `MCPServerConfig` entry to `config.yaml` under `mcp_servers`
7. Parallel-safe tools → no shared mutable state; `_execute_step` is called from threads

---

## Documentation

- `docs/ARCHITECTURE.md` — architecture deep-dive
- `docs/SYSTEM_ARCHITECTURE.md` — system overview
- `docs/OBSERVABILITY.md` — observability guide
- `docs/AUTO_EVOLUTION_IMPLEMENTATION.md` — auto-evolution guide
- `CURRENT_STATE.md` — live status of all components
- `ACTIONABLE_RECOMMENDATIONS.md` — prioritised improvement backlog
- API reference: `http://localhost:8000/docs`

---

## License

MIT License — see LICENSE file