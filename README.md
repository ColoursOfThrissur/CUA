# CUA - Autonomous Agent System

**Local autonomous agent platform for safe tool-based execution, with human approval gates, controlled self-improvement, and comprehensive observability.**

> **Status (June 2026):** Production-Ready | Core Architecture Complete | 12 correctness/quality fixes applied across 8 components

---

## What CUA Does

CUA is a local autonomous agent that:
- **Plans & Executes** multi-step tasks with goal achievement and self-correction
- **Routes intelligently** via a skills system (7 skills, 3-signal scoring + LLM fallback)
- **Calls tools natively** via function calling (20+ tools, reputation-weighted selection)
- **Creates & evolves tools** through LLM-driven generation with validation pipelines
- **Manages dependencies** automatically (AST-based detection, pip install, service generation)
- **Validates everything** via 20-gate AST + architectural validation
- **Observes everything** via SQLite-based logging (13 databases)
- **Self-improves** through a hybrid improvement engine with human approval gates
- **Runs steps in parallel** via DAG-based wave execution (independent steps run concurrently)
- **Resolves capability gaps** automatically (local → MCP → API wrap → create tool)
- **Connects to MCP servers** via stdlib JSON-RPC 2.0 adapter with dynamic capability discovery
- **Scores tool reputation** with 4-factor composite (success rate, recency, latency, volume)
- **Stores credentials securely** with Fernet encryption, per-tool access scoping
- **Learns from history** via strategic memory (Jaccard similarity, win-rate tracking, LRU eviction)
- **Searches all memory at once** via UnifiedMemory facade (strategic plans + patterns + improvement history + conversation)
- **Evolves surgically** — tool evolution scopes rewrites to `target_functions` only, leaving rest of file untouched
- **Adapts confidence thresholds** per model — local models (Qwen/Mistral) use 0.35, cloud models (GPT/Claude/Gemini) use 0.5

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

## Architecture: SkillExecutionContext + Parallel DAG

The system is built around **SkillExecutionContext** — a unified data structure carrying skill-aware execution guidance through the entire pipeline, with **parallel wave execution** for independent steps:

```
User Request
    ↓
[Skill Selector] — 3-signal scoring: keyword overlap + learned triggers + tool health
    ↓
[SkillExecutionContext] — 32 fields:
    • Skill metadata: name, category, verification_mode, risk_level
    • Tool guidance: preferred_tools, available_tools, fallback_tools
    • I/O expectations: expected_input_types, expected_output_types
    • Recovery: max_retries (from risk_level), retry_backoff
    • Trace: step_history, errors_encountered, warnings
    ↓
[ContextAwareToolSelector] — reputation-weighted selection + circuit breaker health check
    ↓
[UnifiedMemory] — search all 4 stores: StrategicMemory + MemorySystem patterns + ImprovementMemory + conversation
    ↓
[TaskPlanner] — LLM plan generation with unified MEMORY CONTEXT block injected into prompt
    ↓
[ExecutionEngine] — parallel DAG execution:
    Wave 1: [step_1, step_2]  ← independent, run concurrently (ThreadPoolExecutor)
    Wave 2: [step_3]          ← depends on step_1 + step_2, runs after wave 1
    Wave 3: [step_4, step_5]  ← independent of each other, run concurrently
    ↓
[ToolOrchestrator] — execute_tool_step(..., execution_context)
    • On error: should_fallback()? → switch to fallback_tool
    • On success: _validate_output_against_skill(result, context)
    ↓
[CapabilityResolver] — gap detected? local → MCP → API wrap → create_tool
    ↓
[Response]
```

---

## Project Status

### Architecture Health

| Component | Status | Notes |
|-----------|--------|-------|
| SkillExecutionContext (32 fields) | Complete | |
| Skill Selector (3-signal + LLM-first) | Solid | LLM fallback max_tokens=80; no stemming in `_tokenize`; no negative signal between skills |
| Task Planner (LLM → DAG) | Solid | `tools_desc` can exceed Qwen ctx for 20+ tools; `unified_context` injected late in prompt; replan doesn't pass completed outputs |
| Execution Engine (wave DAG) | Solid | Per-step timeout 120s; completed executions evicted (max 50); `resume_execution` ignores waves |
| Tool Orchestrator | Solid | `_services_cache` never invalidated on tool reload; `inspect.signature` called on every execution (not cached) |
| Circuit Breaker | Solid | `success_count` reset on CLOSED→OPEN fixed; cumulative failure count (no sliding window); not thread-safe under parallel execution |
| Strategic Memory (Jaccard + win-rate) | Solid | Dirty flag + batch write; `min_win_rate` config-driven; no time decay |
| UnifiedMemory (4-store facade) | Solid | Uses public `retrieve()` API; only searches failed improvements, not successful ones |
| Capability Resolver (5-step chain) | Solid | `_MCP_CATALOGUE` / `_API_CATALOGUE` hardcoded in file; no feedback loop when `create_tool` succeeds |
| Credential Store (Fernet) | Solid | Atomic write via tmp+replace; load errors logged; no `expires_at`/TTL |
| Autonomous Agent (goal loop) | Solid | `failed_attempts` retrieved on retry iterations; web research outcomes recorded to strategic memory |
| Parallel Execution DAG (wave-based) | Complete | |
| Recovery Logic (fallback/retry/degrade) | Complete | |
| MCP Adapter (JSON-RPC 2.0) | Complete | |
| Output Validation (all paths) | Complete | |
| Service Validation (creation + evolution) | Complete | |
| Surgical Tool Evolution (target_functions) | Complete | |
| Per-model Confidence Thresholds | Complete | |
| Edit-Block Generation (aider-style) | Complete | Creation + evolution both use `<<<< ORIGINAL / ======= / >>>>` format with fallback |

### Verified Working
- Skill-aware routing: web_research, computer_automation, code_workspace, conversation, browser_automation, data_operations, knowledge_management
- Skill selector 3-signal scoring: keyword overlap + learned triggers + live tool health
- Tool reputation 4-factor composite: 55% success, 20% recency, 15% latency, 10% volume ±5% trend
- Parallel DAG execution: independent steps run concurrently via ThreadPoolExecutor (max 4 workers, 120s per-step timeout)
- Capability resolution: local → MCP → API wrap → create_tool chain
- MCP adapter: stdlib JSON-RPC 2.0, dynamic capability discovery via `tools/list`
- Credential store: Fernet encryption, atomic writes, per-tool access scoping, graceful base64 fallback
- Strategic memory: SHA1 fingerprinting, Jaccard retrieval, 200-record LRU eviction, config-driven `min_win_rate`
- Conversational requests handled without tool routing (no false capability gaps)
- UnifiedMemory: 4-store Jaccard search via public APIs injected into TaskPlanner prompt
- Surgical tool evolution: `target_functions` scopes rewrite to named methods only
- Evolution analyzer injects top 3 recent failure messages from `tool_executions.db`
- Tool creation confidence threshold is model-aware: 0.35 for Qwen/Mistral, 0.5 for GPT/Claude/Gemini
- Multi-round tool calling: continuation rounds receive structured `[ok/err] tool.op: result_preview` blocks
- Circuit breaker: correct CLOSED→OPEN→HALF_OPEN transitions, `success_count` reset on OPEN
- Retry loop: `failed_attempts` patterns injected into planner on iteration 2+
- Web research outcomes recorded to strategic memory (no longer bypassed)
- Tool errors (`{"error": "..."}` dicts) correctly surface as failures, not silent successes

### Remaining Known Gaps

- `CircuitBreaker`: not thread-safe — `failure_count` read-modify-write races under parallel execution (no lock)
- `ToolOrchestrator._services_cache`: never invalidated when a tool is reloaded/evolved
- `TaskPlanner`: `unified_context` injected after examples in prompt — should be closer to goal for Qwen attention
- `TaskPlanner`: `tools_desc` can exceed Qwen context for 20+ tools — no token budget trimming
- `CapabilityResolver`: `_MCP_CATALOGUE` and `_API_CATALOGUE` hardcoded — should be config-driven
- `StrategicMemory`: no time decay on relevance scores — old patterns rank equal to recent ones
- `CredentialStore`: no `expires_at`/TTL support for rotating API keys
- `SkillSelector`: no stemming — "searching" doesn't match "search"

---

## Skills System

7 skills in `skills/` directory, each with `skill.json` + `SKILL.md`:

| Skill | Category | Preferred Tools | Verification |
|-------|----------|-----------------|--------------|
| `web_research` | web | WebAccessTool, ContextSummarizerTool | source_backed |
| `computer_automation` | computer | FilesystemTool, ShellTool | side_effect_observed |
| `code_workspace` | development | CodeEditorTool, TestRunnerTool | output_validation |
| `conversation` | conversation | — | none |
| `browser_automation` | automation | BrowserAutomationTool | side_effect_observed |
| `data_operations` | data | HTTPTool, JSONTool, DatabaseQueryTool | output_validation |
| `knowledge_management` | productivity | LocalCodeSnippetLibraryTool, LocalRunNoteTool | output_validation |

**Skill Selection Flow:**
1. Simple greeting/farewell → early return (no skill needed)
2. AutoSkillDetector: 3-signal scoring (keyword overlap +0.55, learned triggers +0.20, tool health +0.10)
3. LLM fallback if confidence < 0.35
4. `conversation` skill → direct LLM response, no tool calling
5. Other skills → SkillExecutionContext built → ContextAwareToolSelector (reputation-weighted) → ExecutionEngine

---

## Tools

### Core Tools (always loaded)
- `FilesystemTool`: `read_file`, `write_file`, `list_directory`, `list_files`
- `WebAccessTool`: `fetch_url`, `search_web`, `open_page`, `get_current_page`, `crawl_site`, `extract_links`, `extract_search_results`
- `HTTPTool`: `get`, `post`, `put`, `delete` (domain allowlist enforced; hidden when WebAccessTool available)
- `JSONTool`: `parse`, `stringify`, `query`
- `ShellTool`: `execute` (command allowlist enforced)

### Experimental Tools (loaded at runtime)
- `ContextSummarizerTool`: `summarize_text`, `extract_key_points`, `sentiment_analysis`, `generate_json_output`
- `DatabaseQueryTool`: `query_logs`, `analyze_tool_performance`, `find_failure_patterns`, `get_evolution_history`
- `BrowserAutomationTool`: `open_and_navigate`, `take_screenshot`, `find_element`, `get_page_content`
- `LocalCodeSnippetLibraryTool`: `save_snippet`, `get_snippet`, `search`, `list_popular`
- `LocalRunNoteTool`: note management and persistence
- `BenchmarkRunnerTool`: `run_benchmark_suite`, `add_benchmark_case`, `execute`, `run_suite`, `run`, `add_case`
- `MCPAdapterTool`: `call_tool`, `list_tools`, `get_server_info` (one instance per configured MCP server)

### Additional Experimental (available, not loaded by default)
- `WorkflowAutomationTool`, `ExecutionPlanEvaluatorTool`, `TaskBreakdownTool`
- `UserApprovalGateTool`, `IntentClassifierTool`, `SystemIntrospectionTool`

---

## Chat Request Flow

```
User Message
    ↓
Simple greeting? → Early return (no skill, no tools)
    ↓
AutoSkillDetector (3-signal scoring + LLM fallback)
    ↓
conversation skill? → LLM direct response
    ↓
Intent: multi-step (A) or simple (B)?
    ↓
[A] AutonomousAgent          [B] Native Tool Calling
    TaskPlanner                   ToolCallingClient
    ExecutionEngine               Multi-round (max 3)
    Verify + Iterate              Output Analysis
    ↓                             ↓
Natural language response (tool call JSON filtered out)
```

---

## Autonomous Agent Flow

```
Goal submitted
    ↓
UnifiedMemory.search_for_planning() → inject ranked MEMORY CONTEXT (4 stores) into prompt
    ↓
TaskPlanner → multi-step plan (skill-aware, dependency graph)
    ↓
requires_approval? → surface plan to UI, wait for "go ahead"
    ↓
ExecutionEngine → parallel DAG execution:
    _build_execution_waves() → group independent steps into waves
    Wave N: independent steps → ThreadPoolExecutor (max 4 workers)
    Wave N+1: dependent steps → run after wave N completes
    • Resolves {{step_X}} parameter references
    • Retries failed steps (max 3, skill-context backoff)
    ↓
LLM Verification → {"success": true/false, "missing_parts": [...]}
    ↓
Iterate (max 3) or complete → StrategicMemory.record() outcome
```

---

## Tool Creation Flow

```
User: "Create a tool for X"
    ↓
1. Spec Generation (LLM + confidence scoring)
2. Code Generation (Qwen multi-stage or GPT single-shot)
3. Enhanced Validation (20 gates: AST, architecture, service usage)
4. Dependency Check (AST-based: missing libs + services)
5. Sandbox Test (isolated execution)
6. Human Approval → activate
```

Registry-aware: if tool name already exists, returns "already exists" and suggests evolution instead.
Confidence threshold is model-aware: reads `min_confidence` from `config/model_capabilities.json` per model pattern (0.35 local, 0.5 cloud).

---

## Tool Evolution Flow

```
1. Analyze (quality score 0-100 + top 3 recent failures from tool_executions.db injected)
2. Propose (LLM reads evolution context, proposes minimal fix with action_type + target_functions list)
3. Generate (scopes rewrite to target_functions only; falls back to all handlers if not found)
4. Check Dependencies (AST parse)
5. Validate (enhanced AST + CUA architecture checks)
6. Sandbox Test
7. Human Approval → apply + remove from pending
```

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

## Validation Gates (20)

1. AST syntax
2. Required methods (`register_capabilities`, `execute`)
3. Execute signature
4. Capability registration
5. Parameter validation
6. Import validation
7. No mutable defaults
8. No relative paths
9. No undefined helpers
10. Orchestrator parameter check
11. Tool name assignment
12. Contract compliance
13. Undefined method detection
14. Uninitialized attribute detection
15. Code truncation detection
16. Service usage pattern validation
17. Service method existence (via service_registry)
18. Capability-spec parameter matching
19. Hardcoded value detection
20. Return type validation (dict, not ToolResult)

---

## Observability (13 SQLite Databases)

| Database | Contents |
|----------|----------|
| `logs.db` | System logs |
| `tool_executions.db` | Execution history with timing |
| `tool_evolution.db` | Evolution attempts + steps |
| `tool_creation.db` | Tool generation logs |
| `tool_creation_logs.db` | Creation tracking |
| `tool_execution_logs.db` | Detailed execution logs |
| `chat_history.db` | Chat storage |
| `conversations.db` | Sessions, messages, learned_patterns |
| `analytics.db` | Improvement metrics |
| `failure_patterns.db` | Failed changes + error patterns |
| `improvement_memory.db` | Successful improvements |
| `plan_history.db` | Execution plan history |
| `llm_logs.db` / `llm_interactions.db` | LLM call tracking |
| `metrics.db` | System metrics |

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
- `GET /health` — health + `system_available`
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
- `GET /improvement/tools/suggest?skip=N` — cycles through suggestions
- `POST /improvement/tools/create`
- `GET /improvement/history`, `GET /improvement/analytics`, `GET /improvement/previews`
- `POST /improvement/rollback/{plan_id}`

### Tool Evolution
- `POST /evolution/evolve`, `GET /evolution/pending`
- `POST /evolution/approve/{tool_name}`, `POST /evolution/reject/{tool_name}`
- `POST /evolution/test/{tool_name}`, `GET /evolution/conversation/{tool_name}`
- `POST /evolution/resolve-dependencies/{tool_name}`

### Auto-Evolution
- `POST /auto-evolution/start`, `POST /auto-evolution/stop`, `GET /auto-evolution/status`
- `POST /auto-evolution/config`, `GET /auto-evolution/queue`, `POST /auto-evolution/trigger-scan`

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
- `POST /observability/cleanup`, `POST /observability/refresh`

### Tools Management
- `GET /tools-management/summary`, `GET /tools-management/list`
- `GET /tools-management/detail/{tool_name}`, `GET /tools-management/code/{tool_name}`
- `POST /tools-management/trigger-check/{tool_name}`

### Circuit Breaker + Reputation
- `GET /circuit-breaker/status`
- `GET /circuit-breaker/reputation` — composite reputation scores for all tools
- `GET /circuit-breaker/tool/{name}` — per-tool status + reputation

### MCP
- `GET /mcp/status` — connected servers + health
- `GET /mcp/tools` — all discovered MCP capabilities

### Credentials
- `GET /credentials/list` — list credential keys (values never returned)
- `POST /credentials/set` — store encrypted credential
- `DELETE /credentials/{key}` — remove credential
- `GET /credentials/{key}/exists` — check existence
- `PATCH /credentials/{key}/scope` — update allowed tools

### Strategic Memory
- `GET /agent/strategic-memory` — stats + top 10 patterns by win-rate

### Other
- `GET /tasks/active`, `GET /tasks/history`, `POST /tasks/{parent_id}/abort`
- `GET /settings/models`, `POST /settings/model`, `POST /settings/reload-config`

---

## Project Structure

```
CUA/
├── api/                    # FastAPI routers (30+ files)
│   ├── server.py           # Main server + /chat endpoint
│   ├── bootstrap.py        # Runtime init + router wiring
│   ├── mcp_api.py          # MCP status + tools endpoints
│   ├── credentials_api.py  # Credential CRUD endpoints
│   ├── agent_api.py        # Strategic memory endpoint
│   └── *_api.py            # Feature routers
│
├── core/                   # Core logic (80+ modules)
│   ├── skills/             # Skill system
│   │   ├── models.py       # SkillDefinition, SkillSelection
│   │   ├── registry.py     # In-memory skill registry + ToolReputation
│   │   ├── selector.py     # 3-signal skill scoring + LLM fallback
│   │   ├── execution_context.py  # SkillExecutionContext (32 fields)
│   │   ├── context_hydrator.py   # Skill → execution context
│   │   └── tool_selector.py      # ContextAwareToolSelector (reputation-weighted)
│   ├── tool_creation/      # 6-step creation pipeline
│   ├── tool_evolution/     # 6-step evolution pipeline
│   ├── autonomous_agent.py
│   ├── task_planner.py
│   ├── execution_engine.py      # Parallel DAG wave execution
│   ├── memory_system.py
│   ├── tool_orchestrator.py
│   ├── strategic_memory.py      # Jaccard plan retrieval + win-rate LRU
│   ├── unified_memory.py        # 4-store search facade — singleton via get_unified_memory()
│   ├── capability_resolver.py   # 3-step gap resolution chain
│   ├── credential_store.py      # Fernet-encrypted credential store
│   ├── gap_detector.py          # Capability gap detection
│   ├── gap_tracker.py           # Gap persistence + resolution tracking
│   ├── auto_skill_detection.py  # AutoSkillDetector
│   ├── circuit_breaker.py
│   ├── config_manager.py        # Config + MCPServerConfig
│   └── enhanced_code_validator.py
│
├── core/services/
│   └── credential_service.py    # Per-tool scoped credential access
│
├── tools/                  # Tool implementations
│   ├── enhanced_filesystem_tool.py
│   ├── web_access_tool.py
│   ├── http_tool.py
│   ├── json_tool.py
│   ├── shell_tool.py
│   └── experimental/       # 15 experimental tools
│       └── MCPAdapterTool.py    # JSON-RPC 2.0 MCP client
│
├── skills/                 # Skill definitions (7 skills)
│   ├── web_research/
│   ├── computer_automation/
│   ├── code_workspace/
│   ├── conversation/
│   ├── browser_automation/
│   ├── data_operations/
│   └── knowledge_management/
│
├── planner/
│   ├── llm_client.py
│   └── tool_calling.py     # Native function calling
│
├── updater/                # Self-improvement update pipeline
│   ├── orchestrator.py     # Full update pipeline
│   ├── risk_scorer.py
│   ├── sandbox_runner.py
│   ├── update_gate.py
│   ├── atomic_applier.py
│   └── audit_logger.py
│
├── ui/src/components/      # React UI (50+ components)
│
└── data/                   # SQLite databases + JSON state
    ├── strategic_memory.json
    └── credentials.enc
```

---

## UI Modes

1. **Chat** — conversational interface, native tool calling, agentic responses
2. **Tools Mode** — tool creation, capability spec, sandbox testing, approval workflow
3. **Evolution Mode** — tool selection, evolution workflow, pending approvals, capability gaps, auto-evolution panel, pending services
4. **Tools Management** — health dashboard, search/filter, LLM analysis, code viewer
5. **Observability** — full-page database viewer, paginated data, row details, filters

---

## Safety Features

- Sandbox testing for all generated code
- Human approval gates for evolution, creation, and risky updates
- Risk scoring (files changed + diff size) before any self-modification
- Protected files blocked from modification (immutable_brain_stem)
- AST + architectural validation (20 gates)
- Circuit breaker per tool (failure protection) with reputation scoring
- Rollback support (backups before changes)
- Service pattern enforcement (`self.services.X` only)
- Idempotency checking (no duplicate changes)
- Input size limit (10MB max on /chat)
- Correlation context on all requests
- Fernet-encrypted credential store (per-tool access scoping)
- MCP server connections validated before capability registration

---

## Configuration

**Environment Variables:**
- `OLLAMA_URL` — Ollama server URL (default: http://localhost:11434)
- `CUA_API_URL` — Backend base URL (default: http://localhost:8000)
- `CORS_ALLOW_ORIGINS` — Allowed origins (default: http://localhost:3000)
- `REACT_APP_API_URL` — Frontend → backend URL
- `REACT_APP_WS_URL` — Frontend WebSocket URL

**Config Files:**
- `config.yaml` — System configuration (includes `mcp_servers` list)
- `config/model_capabilities.json` — Model routing config: `strategy`, `max_lines`, `min_confidence` per model pattern
- `requirements.txt` — Python dependencies
- `ui/package.json` — Frontend dependencies

---

## Testing

```bash
pytest -q
```

On Windows, `tmpdir` and `cacheprovider` are disabled in `pytest.ini`. A local `tmp_path` fixture is provided in `tests/conftest.py`.

Test structure:
- `tests/unit/` — unit tests per component
- `tests/integration/` — full pipeline tests
- `tests/smoke/` — boot + approval flow
- `tests/experimental/` — per experimental tool

---

## Reliability Notes

- SQLite databases are best-effort — if locked/readonly, system logs a warning and continues
- Tool creation is registry-aware — existing tool names return "already exists" and redirect to evolution
- Service calls are validated — only allowed `self.services.*` APIs pass validation
- Scaffold-first fallback — if full generation fails, a safe scaffold is created and queued for evolution
- Auto-evolution config keys: `enable_enhancements`, `max_new_tools_per_scan`
- Parallel execution is thread-safe — `_execute_step` reads shared state but never mutates it mid-wave
- Credential store falls back to base64 obfuscation if `cryptography` package is not installed

---

## Contributing

When adding features:
1. Pass SkillExecutionContext where execution happens
2. Track steps: `execution_context.add_step()`
3. Track errors: `execution_context.add_error()`
4. New services → add to `core/tool_services.py` + `AVAILABLE_SERVICES` in `core/dependency_checker.py`
5. New databases → add schema to `core/database_schema_registry.py`
6. New MCP servers → add `MCPServerConfig` entry to `config.yaml` under `mcp_servers`
7. Parallel-safe tools → ensure no shared mutable state; `_execute_step` is called from threads

---

## Documentation

- `docs/OBSERVABILITY.md` — full observability system guide
- `docs/AUTO_EVOLUTION_IMPLEMENTATION.md` — auto-evolution guide
- `docs/ARCHITECTURE.md` — architecture deep-dive
- `docs/SYSTEM_ARCHITECTURE.md` — system architecture
- API reference: http://localhost:8000/docs

---

## License

MIT License — See LICENSE file
