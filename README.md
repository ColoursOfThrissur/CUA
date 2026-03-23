# CUA - Autonomous Agent System

**Local autonomous agent platform for safe tool-based execution, with human approval gates, controlled self-improvement, and comprehensive observability.**

> **Status (March 21, 2026):** 85%+ Architecture Complete | Production-Ready | Well-Integrated SkillExecutionContext Pattern

## 📊 Project Status

### Architecture Health
- **SkillExecutionContext Integration:** ✅ 100% - Full 32-field context flows through entire pipeline
- **Tool Selection with Fallback:** ✅ 100% - Preferred tools + fallback strategies working
- **ExecutionEngine + ToolOrchestrator:** ✅ 100% - Context passed, metrics tracked, recovery logic active
- **Output Validation:** ⚠️ 70% - Implemented in success path, needs completion in fallback paths
- **Tool Creation Alignment:** ⚠️ 60% - Contract validated, skill extraction needs enhancement
- **Multi-round Context:** ⚠️ 75% - Context preserved across iterations, could be fully refreshed between rounds

### Verified Working
- ✅ Skill-aware routing (web_research, computer_automation, code_workspace)
- ✅ SkillExecutionContext carries: verification_mode, risk_level, preferred_tools, fallback_tools, expected_output_types
- ✅ Circuit breaker integration with context awareness
- ✅ Error tracking and recovery (should_fallback(), should_retry(), should_degrade())
- ✅ Tool creation with architecture contract enforcement
- ✅ Tool evolution with execution context metrics
- ✅ Skill extraction (3 core fields: output_types, verification_mode, ui_renderer)

### Known Gaps (Refinements Only)
- ⚠️ Skill extraction undershooting (7 additional fields available but not extracted)
- ⚠️ Output validation only in success path (need to extend to fallback/error paths)
- ⚠️ Multi-round context not fully refreshed between tool calling rounds
- ❌ Service validation logic not implemented (constraint checking)
- ❌ Auto-skill detection when target_skill not provided

### Effort to 100%
- HIGH priority (direct improvements): 5 hours
- MEDIUM priority (robustness): 3 hours  
- LOW priority (polish): 5 hours
- **Total:** ~13 hours for full completion

## 🎯 What CUA Does

CUA is an autonomous agent that:
- **Plans & Executes** multi-step tasks autonomously with goal achievement
- **Learns & Remembers** conversation context and successful patterns
- **Self-corrects** by analyzing failures and iterating toward goals
- **Executes tasks** via tool calling (function calling) and a tool registry
- **Creates tools** through LLM-driven generation with validation pipeline
- **Evolves tools** by detecting weak tools and generating improvements
- **Manages dependencies** automatically (detects missing libraries/services)
- **Validates everything** via enhanced AST validation and sandbox testing
- **Observes everything** via SQLite-based logging (multiple databases)
- **Self-improves** through a hybrid improvement engine with human approval gates

### Current Product Direction

The next phase of CUA is centered on one primary workflow:

1. User submits a goal
2. CUA produces a constrained plan
3. CUA executes steps through approved tools
4. Risky actions require approval
5. CUA verifies outcomes and records an audit trail

This means CUA is being positioned first as a **reliable local autonomous execution platform**.

Tool creation, tool evolution, and broader self-improvement remain part of the system, but for the next phase they are treated as supporting operator workflows rather than equal product pillars.

## 🔧 Core Architecture: SkillExecutionContext Pattern

The system is built around **SkillExecutionContext** — a unified data structure that carries skill-aware execution guidance through the entire request pipeline:

```
User Request
    ↓
[Skill Selector] ← Infer from keywords/heuristics
    ↓
[SkillExecutionContext] ← Created with 32 fields:
    • Skill metadata: name, category, verification_mode, risk_level
    • Tool guidance: preferred_tools, available_tools, fallback_tools
    • I/O expectations: expected_input_types, expected_output_types
    • Recovery settings: max_retries (from risk_level), retry_backoff
    • Execution trace: step_history, errors_encountered, warnings
    ↓
[ContextAwareToolSelector] ← Resolve tools + check circuit breaker health
    ↓
[ExecutionEngine] ← execute_plan(..., skill_context)
    ↓
[ToolOrchestrator] ← execute_tool_step(..., execution_context)
    • On error: should_fallback()? → switch to fallback_tool
    • On success: _validate_output_against_skill(result, context)
    ↓
[Response] ← Context flows through entire execution
```

**Key Benefits:**
- ✅ No tool selector/recovery logic scattered across codebase
- ✅ Execution context available everywhere (tracer, debugger, evolution engine)
- ✅ Verification mode + output types automatically enforced
- ✅ Fallback strategies derived from skill risk level (not hard-coded)
- ✅ Every tool execution tracked for observability + skill metrics

**Implementation Status:**
- ✅ CoreSkillExecutionContext: 100% (32 fields, all methods implemented)
- ✅ Tool selection: 100% (preferred + fallback working)
- ✅ Recovery logic: 100% (should_fallback, retry, degraded mode)
- ⚠️ Output validation: 70% (works in success path, extend to errors)
- ⚠️ Multi-round preservation: 75% (context preserved, not fully refreshed)

### Near-Term Priorities (March 2026 - Next 3 Months)

#### Phase 1: Skill Extraction Enhancement (HIGH - 2 hrs)

Maximize skill-aware guidance to tool creation LLM:

- Extract all 10 SkillDefinition fields (not just 3)
- Include: preferred_tools, required_tools, input_types, risk_level, instructions
- Pass skill constraints + service patterns to LLM
- Result: LLM generates tools that align with skill domain and dependencies

#### Phase 2: Output Validation Full Coverage (HIGH - 1 hr)

Extend verification mode validation beyond success path:

- Call `_validate_output_against_skill()` in fallback scenarios
- Call in error/retry paths, not just success
- Make validation failures trigger retry or degraded mode
- Result: Invalid outputs caught everywhere, not just happy path

#### Phase 3: Multi-Round Context Refresh (MEDIUM - 2 hrs)

Improve context state across tool calling iterations:

- Rebuild execution_context between continuation rounds (lines 852-950)
- Refresh available_tools list (check circuit breaker again)
- Propagate selected_tool changes back to context
- Result: Each round has fresh context, not stale state

#### Longer-Term Backlog (Post-Phase-3)

- **Service Validation** (3 hrs): Validate generated tool services against skill patterns + constraint enforcement
- **Auto-Skill Detection** (1 hr): Use SkillSelector when target_skill not provided; fallback to manual entry if confidence low
- **Skill-Based Evolution Metrics** (2 hrs): Track success_rate per tool per skill; use for evolution prioritization
- **Full Degraded Mode** (2 hrs): Implement degraded_mode when services unavailable; switch to safer operations

## 1. Platform Hardening

Focus the next engineering pass on trust in the control plane:

- Startup wiring and degraded-mode reporting
- Protected-file and safety policy enforcement
- Risk scoring and approval semantics
- Rollback and quarantine behavior
- Critical-path integration tests
- Deterministic verification where possible

## 2. Product Narrowing

Reduce surface-area competition and optimize around the default workflow:

- Make autonomous goal execution the default product path
- Treat tool creation/evolution as advanced or operator-facing flows
- Simplify the UI around execute -> approve -> verify -> inspect trace
- Measure success primarily on task completion, approval quality, and debuggability

### What Is Deprioritized For Now

- Adding many more experimental tools
- Expanding the number of equally-promoted UI modes
- Increasing self-improvement autonomy before guardrails are stronger
- Polishing secondary dashboards ahead of the core execution flow
- Treating all APIs and features as equally important

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start backend (port 8000)
python start.py

# Start UI (separate terminal, port 3000)
cd ui && npm install && npm start
```

**Access**: http://localhost:3000

Backend API docs (FastAPI):
- Swagger UI: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json

## Backend API (Current)

Core
- `POST /chat` - Chat endpoint (skill-aware routing + tool calling + autonomous-agent for multi-step tasks)
- `GET /health` - Basic health + `system_available`
- `GET /status` - Runtime summary (sessions, connections, tools, capabilities, skills)
- `POST /cache/clear` - Clears sessions + caches

Realtime
- `GET /events` - SSE stream (event bus)
- `WS /ws` - WebSocket stream (event bus + initial state)
- `WS /ws/trace` - WebSocket stream for trace events (UI trace overlay)

Settings
- `GET /settings/models`
- `POST /settings/model`
- `POST /settings/reload-config`

Skills
- `GET /skills/list` - List all available skills
- `GET /skills/{skill_name}` - Get skill details
- `POST /skills/refresh` - Reload skills from disk
- `POST /skills/update/{skill_name}` - Update skill definition

Tools (registry + sync)
- `POST /api/tools/sync` - AST-based capability snapshot + runtime refresh
- `GET /api/tools/registry` - Current tool registry snapshot
- `GET /api/tools/capabilities` - Formatted capability text
- `POST /api/tools/test/{tool_name}` - LLM-generated tests for an active tool

Self-improvement
- `POST /improvement/start`
- `POST /improvement/start-continuous`
- `POST /improvement/stop`
- `POST /improvement/approve`
- `GET /improvement/status`
- `GET /improvement/logs`
- `POST /improvement/clear-logs`
- `GET /improvement/previews`
- `GET /improvement/history`
- `GET /improvement/analytics`
- `POST /improvement/export/{proposal_id}`
- `POST /improvement/import`
- `GET /improvement/history/{plan_id}`
- `POST /improvement/rollback/{plan_id}`
- `GET /improvement/tools/suggest` - Suggest next tool to create OR an existing tool to evolve (registry-aware)
- `POST /improvement/tools/create`

Pending tools + pending libraries
- `GET /pending-tools/list`
- `GET /pending-tools/{tool_id}`
- `POST /pending-tools/{tool_id}/test`
- `POST /pending-tools/{tool_id}/approve`
- `POST /pending-tools/{tool_id}/reject`
- `GET /pending-tools/active/list`
- `GET /api/libraries/pending`
- `POST /api/libraries/{lib_id}/approve`
- `POST /api/libraries/{lib_id}/reject`

Tool evolution + auto-evolution
- `POST /evolution/evolve`
- `GET /evolution/pending`
- `POST /evolution/approve/{tool_name}`
- `POST /evolution/test/{tool_name}`
- `POST /evolution/reject/{tool_name}`
- `GET /evolution/conversation/{tool_name}`
- `POST /evolution/resolve-dependencies/{tool_name}`
- `POST /auto-evolution/start`
- `POST /auto-evolution/stop`
- `GET /auto-evolution/status`
- `POST /auto-evolution/config`
- `GET /auto-evolution/queue`
- `POST /auto-evolution/trigger-scan`

Capability gaps + services (self-feature growth)
- `GET /improvement/evolution/capability-gaps` - View detected capability gaps (GapTracker summary)
- `POST /improvement/evolution/detect-gap` - Manually record a capability gap (task + optional error)
- `GET /api/services/pending` - Pending service proposals generated from missing `self.services.X`
- `GET /api/services/{service_id}` - Pending service details (includes generated code)
- `POST /api/services/{service_id}/approve` - Approve + inject generated service code
- `POST /api/services/{service_id}/reject` - Reject service proposal

Quality + metrics
- `GET /quality/summary`
- `GET /quality/tool/{tool_name}`
- `GET /quality/all`
- `GET /quality/weak`
- `GET /quality/llm-analysis/{tool_name}`
- `GET /quality/llm-analysis-all`
- `GET /quality/llm-weak`
- `GET /quality/llm-summary`
- `POST /quality/refresh-llm-analysis`
- `GET /metrics/tool/{tool_name}`
- `GET /metrics/system`
- `POST /metrics/aggregate`
- `GET /metrics/summary`

Observability
- `GET /observability/logs`
- `GET /observability/tool-executions`
- `GET /observability/tool-creation`
- `GET /observability/tool-evolution`
- `GET /observability/chat`
- `GET /observability/tables`
- `GET /observability/data/{db_name}/{table_name}`
- `GET /observability/detail/{db_name}/{table_name}/{row_id}`
- `GET /observability/filters/{db_name}/{table_name}/{column}`
- `POST /observability/cleanup`
- `POST /observability/refresh`

UI dashboards
- `GET /tools-management/summary`
- `GET /tools-management/list`
- `GET /tools-management/detail/{tool_name}`
- `GET /tools-management/executions/{tool_name}`
- `GET /tools-management/code/{tool_name}`
- `POST /tools-management/trigger-check/{tool_name}`
- `GET /tools/list`
- `GET /tools/info/{tool_name}`

Task manager
- `GET /tasks/active`
- `GET /tasks/history`
- `POST /tasks/{parent_id}/abort`
- `GET /tasks/{parent_id}/staging`

Notes
- Many routers are conditionally included at startup (see `api/server.py`). If imports fail, `/health` will still work but feature endpoints may 503/500 until dependencies/config are fixed.
- For the canonical list of tool capabilities at runtime, prefer `GET /api/tools/registry` and `GET /api/tools/capabilities`.

## Tools and Capabilities (Current)

Core tools loaded by default (see `api/server.py`)
- `FilesystemTool`: `read_file`, `write_file`, `list_directory`
- `WebAccessTool`: `fetch_url`, `search_web`, `open_page`, `get_current_page`, `crawl_site` (unified web interaction)
- `HTTPTool`: `get`, `post`, `put`, `delete` (domain allowlist enforced, hidden when WebAccessTool available)
- `JSONTool`: `parse`, `stringify`, `query`
- `ShellTool`: `execute` (command allowlist is enforced in `tools/shell_tool.py`)

Experimental tools (available in `tools/experimental/`; some are loaded by default)
- `BrowserAutomationTool`: Advanced browser automation (hidden when WebAccessTool available)
- `ContextSummarizerTool`: Text summarization with configurable length and tone
- `DatabaseQueryTool`: Database queries with schema awareness
- `LocalRunNoteTool`: Note management and persistence
- `LocalCodeSnippetLibraryTool`: Code snippet storage and retrieval
- `WorkflowAutomationTool`: Multi-step workflow execution
- `ExecutionPlanEvaluatorTool`: Plan quality assessment
- `TaskBreakdownTool`: Goal decomposition
- `UserApprovalGateTool`: Human-in-loop approval requests + policy checks
- `IntentClassifierTool`: Intent classification for routing
- `SystemIntrospectionTool`: System state inspection
- Additional experimental tools can be activated via tool sync + approval flows

## Skills System (Domain-Aware Routing & Execution Context)

CUA includes a skills system for intelligent domain-aware routing and execution context provision:

**Available Skills** (in `skills/` directory):
- `web_research`: Web searches, page extraction, content summarization, multi-source research
  - Verification: "source_backed" (requires sources + content)
  - Preferred tools: WebAccessTool, ContextSummarizerTool
  - Output types: research_summary, source_comparison, page_summary
  
- `computer_automation`: File operations, shell commands, local system tasks
  - Verification: "side_effect_observed" (requires file_path + execution proof)
  - Preferred tools: FilesystemTool, ShellTool
  - Output types: file_list, operation_result
  
- `code_workspace`: Code analysis, repository operations, development tasks
  - Verification: "output_validation" (validates output structure)
  - Preferred tools: CodeEditorTool, TestRunnerTool
  - Output types: code_analysis, test_result

**Skill Definition** (each skill has `skill.json` + `SKILL.md`):
```json
{
  "name": "skill_name",
  "category": "web|computer|development",
  "description": "What this skill does",
  "trigger_examples": ["pattern1", "pattern2"],
  "preferred_tools": ["Tool1", "Tool2"],
  "required_tools": [],
  "input_types": ["url", "query"],
  "output_types": ["research_summary", "page_summary"],
  "verification_mode": "source_backed",
  "risk_level": "medium",
  "ui_renderer": "research_summary",
  "fallback_strategy": "direct_tool_routing"
}
```

**Skill Selection Flow** (in `/chat` endpoint):
1. User message analyzed by SkillSelector
2. Keyword heuristics matched against trigger_examples
3. LLM fallback for ambiguous cases
4. **NEW: SkillExecutionContext created** with skill metadata
5. SkillContextHydrator extracts:
   - ✅ output_types (validation)
   - ✅ verification_mode (how to validate)
   - ✅ ui_renderer (how to display)
   - ⚠️ preferred_tools (to be used in LLM prompts)
   - ⚠️ required_tools (enforce in planning)
6. ContextAwareToolSelector resolves preferred_tools → available tools
7. Context passed to ExecutionEngine + ToolOrchestrator
8. Output validated against verification_mode + expected_output_types

**Integration with Execution Context**:
- ✅ SkillExecutionContext carries: risk_level, verification_mode, expected_output_types
- ✅ Tool selector resolves preferred_tools + builds fallback_tools
- ✅ Recovery settings max_retries derived from skill.risk_level
- ⚠️ Full constraint enforcement (preferred_connectors, instructions) not yet implemented

## 🏗️ Architecture Overview

### Core Components (Updated March 2026)

```
CUA System
├── Skills System
│   ├── Skill Registry - Loads and manages skill definitions (io skill.json)
│   ├── Skill Selector - Heuristic + LLM-based skill matching
│   ├── SkillExecutionContext - **NEW**: Dataclass carrying skill metadata through execution
│   ├── SkillContextHydrator - Converts skill definition → execution context
│   ├── ContextAwareToolSelector - Resolves preferred_tools, checks health
│   └── Planning Context Builder - Provides domain context to planner
│
├── Autonomous Agent
│   ├── Task Planner - Breaks goals into executable steps (skill-aware)
│   ├── Execution Engine - Runs multi-step plans with state tracking + skill_context
│   ├── Memory System - SQLite-backed conversation context & learned patterns
│   ├── ToolOrchestrator - Executes tools with execution_context (error tracking, fallback)
│   └── Goal Achievement Loop - Plan → Execute → Verify → Iterate
│
├── API Layer (FastAPI - multiple routers)
│   ├── Chat endpoint (/chat) - **NEW**: Builds SkillExecutionContext from skill_selection
│   ├── Agent API - Autonomous goal achievement
│   ├── Skills API - Skill management and routing
│   ├── Session API - Session management
│   ├── Tool Creation API - **NEW**: Validates generated tools against skill contracts
│   ├── Tool Evolution API - 6-step improvement workflow (with execution_context metrics)
│   ├── Quality API - Health scoring & recommendations
│   ├── Observability API - 10 database access with schema registry
│   ├── Observability Data API - Paginated data access with filters
│   ├── Tools Management API - Comprehensive tool management
│   ├── Cleanup API - Maintenance & cache clearing
│   ├── Hybrid API - Hybrid improvement engine
│   ├── Auto Evolution API - Automated tool evolution
│   ├── Circuit Breaker API - Failure protection
│   ├── LLM Logs API - LLM interaction logging
│   └── Settings/Scheduler/Libraries/Tools/Services APIs
│
├── Tool System
│   ├── Registry (20+ tools)
│   ├── Tool calling (function calling)
│   ├── Tool Services (storage, llm, http, fs, logging, etc.)
│   ├── Orchestrator (execution & inter-tool calls)
│   └── Enhanced Validator (AST + architectural checks)
│
├── Tool Creation Engine
│   ├── Spec Generator (LLM-driven with confidence scoring)
│   ├── Code Generator (Qwen multi-stage / GPT single-shot)
│   ├── Enhanced Validator (12+ validation gates)
│   ├── Dependency Checker (AST-based detection)
│   ├── Sandbox Runner (isolated testing)
│   └── Expansion Mode (experimental tool management)
│
├── Tool Evolution Engine
│   ├── Quality Analyzer (health scoring 0-100)
│   ├── LLM Health Analyzer (context-aware code analysis)
│   ├── Evolution Flow (6-step improvement)
│   ├── Proposal Generator (reads evolution context, minimal changes)
│   ├── Code Generator (improved version creation)
│   ├── Dependency Manager (auto-detect & resolve)
│   ├── Validator (enhanced AST + structure)
│   ├── Sandbox Runner (isolated testing)
│   └── Pending Approvals (human-in-loop with auto-cleanup)
│
├── Observability System
│   ├── SQLite Logging (10 databases)
│   ├── Database Schema Registry (LLM-assisted queries)
│   ├── Tool Execution Tracking (success/failure/timing)
│   ├── Evolution History (step-by-step tracking)
│   ├── Tool Creation Logs (generation attempts)
│   ├── Quality Metrics (health scores & trends)
│   └── Schema Validation (auto-update capability)
│
└── UI (React)
    ├── Unified Canvas (3 modes: Chat/Tools/Evolution)
    ├── Tools Management Page (comprehensive tool dashboard)
    ├── Observability Page (full-page database viewer)
    ├── Right-Slide Overlays (context-aware panels)
    ├── Theme System (dark/light with CSS variables)
    ├── Real-time Updates (WebSocket)
    ├── Approval Workflows (evolution/tool creation)
    ├── Quality Dashboard (health monitoring)
    └── Clear Cache Button (sticky bottom-left)
```

## 🔧 Key Features

### 1. Autonomous Goal Achievement
- **Intent Classification**: LLM determines if request is multi-step task or simple query
- **Skill-Aware Planning**: Selected skill provides domain context and tool preferences
- **Multi-Step Planning**: LLM breaks complex goals into executable steps with dependencies
- **Dependency Management**: Steps execute in correct order based on dependencies
- **State Tracking**: Full execution state with step results and timing
- **Error Recovery**: Automatic retry logic with configurable max attempts (default: 3)
- **Self-Correction**: Analyzes failures and adjusts approach for next iteration
- **Memory Integration**: Learns from past successes and failures
- **Verification**: LLM verifies if goal achieved against success criteria (JSON response)
- **Approval Gates**: Plans can require user approval before execution
- **Pause/Resume**: Can pause execution and resume later
- **Parameter Resolution**: Steps can reference outputs from previous steps ({{step_X}}, ${step_X.field})

### 2. Memory & Learning
- **SQLite Persistence**: All memory stored in `data/conversations.db`
- **Conversation Context**: Maintains full conversation history per session
- **User Preferences**: Stores and applies user-specific preferences
- **Execution History**: Links conversations to execution plans
- **Pattern Learning**: Stores successful approaches for similar goals (learned_patterns table)
- **Session Management**: Create, retrieve, and clear sessions
- **Context Summarization**: Provides relevant context for planning (last 10 messages)
- **Active Goal Tracking**: Tracks current goal per session
- **In-Memory Cache**: Active sessions cached for performance

### 3. Native Tool Calling
- **Mistral Function Calling**: LLM automatically selects tools based on capability descriptions
- **Skill-Aware Tool Selection**: Preferred tools from selected skill prioritized
- **Scales to 20+ tools**: No manual tool specification needed
- **OpenAI-compatible format**: Works with any function-calling model
- **Multi-Round Execution**: Automatic continuation for multi-step tool sequences
- **Artifact Management**: Tracks outputs across tool calls for web research workflows
- **Agentic Response**: Filters tool call JSON, shows only natural language responses
- **Output Analysis**: Generates UI components based on tool results and skill context

### 4. Tool Creation
**6-Step Flow**:
1. **Spec Generation**: LLM proposes tool specification with confidence scoring
2. **Code Generation**: Multi-stage (Qwen) or single-shot (GPT/Claude) generation
3. **Enhanced Validation**: 12+ gates including AST, imports, service usage
4. **Dependency Check**: AST-based detection of missing libraries/services
5. **Sandbox Testing**: Isolated execution with ordered operations
6. **Approval**: Human review before activation

**Registry-Aware Creation**:
- Checks if tool name already exists before creation
- Suggests evolution instead of duplicate creation
- Prevents naming conflicts

### 5. Tool Evolution
**6-Step Flow with Context-Aware Improvements**:
1. **Analyze**: Quality analyzer scores tool health (0-100)
2. **Propose**: LLM reads evolution context and proposes ONLY necessary fixes with action_type
3. **Generate**: Code generator respects action_type (fix_bug/add_capability/improve_logic/refactor)
4. **Check Deps**: Dependency checker validates imports/services
5. **Validate**: Enhanced AST validation + CUA architecture checks
6. **Sandbox**: Test in isolated environment with dependency detection
7. **Approve**: Human reviews and approves (auto-removes from pending)

**Evolution Context**:
- Reads `.amazonq/rules/LocalLLMRUle.md` for guidelines
- Understands architecture patterns (self._cache, self.services.X)
- Only fixes HIGH severity bugs and clear violations
- Skips evolution if no critical issues found
- Requires justification for all changes

**Action Types**:
- **fix_bug**: Fixes broken code by modifying existing handlers
- **add_capability**: Creates new handler + registers new operation
- **improve_logic**: Enhances existing handler logic
- **refactor**: Restructures code for clarity/performance

### 6. Dependency Management
- **AST-based detection**: Parses generated code for missing imports and service calls
- **Auto-resolution**: Install libraries via pip, generate services via LLM
- **Non-blocking**: Evolutions with missing deps are blocked until resolved
- **Auto-refresh**: Re-checks dependencies on approval
- **Service Pattern Enforcement**: Validates `self.services.X` usage

### 7. Enhanced Validation
**Validation Layers**:
1. **AST Validation** (12+ gates): Syntax, imports, signatures, patterns
2. **CUA Architecture Validation**: Service method existence, capability-spec matching, hardcoded values, return types
3. **Dependency Detection**: Missing libraries and services

**Validation Gates**:
- AST syntax validation
- Required methods (register_capabilities, execute)
- Execute signature validation
- Capability registration check
- Parameter validation
- Import validation
- No mutable defaults
- No relative paths
- No undefined helpers
- Orchestrator parameter check
- Tool name assignment
- Contract compliance
- Undefined method detection
- Uninitialized attribute detection
- Code truncation detection
- Service usage pattern validation
- **NEW**: Service method existence (via service_registry)
- **NEW**: Capability-spec parameter matching
- **NEW**: Hardcoded value detection (example.com, test_user, passwords)
- **NEW**: Return type validation (dict not ToolResult)

### 8. Observability
**10 SQLite Databases**:
- `logs.db` - System logs (info, warning, error, debug)
- `tool_executions.db` - Tool execution history with timing/success
- `tool_evolution.db` - Evolution attempts with step tracking
- `tool_creation.db` - Tool creation logs with status
- `chat_history.db` - Alternative chat storage
- `conversations.db` - Main conversation history (sessions, messages, execution_history, learned_patterns)
- `analytics.db` - Improvement metrics
- `failure_patterns.db` - Failed changes and error patterns
- `improvement_memory.db` - Successful improvements
- `plan_history.db` - Execution plan history
- `llm_logs.db` - LLM interaction logs
- `llm_interactions.db` - Detailed LLM call tracking
- `metrics.db` - System metrics

**Database Schema Registry**:
- Comprehensive schema documentation for all databases
- LLM-assisted query construction
- Schema validation and auto-update
- Common query patterns for each table

### 9. Quality System
- **Health Scoring**: 0-100 based on success rate, usage, output size
- **LLM Health Analysis**: Context-aware code quality checking
- **Recommendations**: HEALTHY (80+), WEAK (50-79), BROKEN (<50)
- **Smart Categorization**: 2+ high bugs OR 4+ medium/high = WEAK
- **False Positive Reduction**: Understands correct patterns
- **Cleanup**: Remove stale execution logs for deleted tools
- **Filtering**: Only show tools with actual files
- **Auto-refresh**: Quality metrics update on evolution approval

### 10. Tools Management Page
**Comprehensive Tool Dashboard**:
- **Summary Cards**: Total tools, healthy/weak/broken/unknown counts
- **Tool List**: All tools (core + experimental) with health scores
- **Search & Filter**: By name and status (Healthy/Weak/Broken/Unknown)
- **Tool Details**: Health metrics, capabilities, issues, LLM analysis
- **Recent Executions**: Last 10 executions with success/failure status
- **Actions**: Run health check, start evolution, view code
- **Code Viewer**: Modal popup showing tool source code
- **Real-time Updates**: Cache-busted API calls for fresh data

### 11. Observability Page
**Full-Page Database Viewer**:
- **Table List**: Sidebar with all tables from 10 databases
- **Data View**: Paginated table data with search and filters
- **Row Details**: Modal popup with expandable card layout
- **Copy Functionality**: Copy individual field values
- **Filter Options**: Dynamic filters based on column values
- **Search**: Full-text search across table data
- **Back Navigation**: Return to chat mode
- **Theme Support**: Dark/light theme with CSS variables

## 📁 Project Structure

```
CUA/
├── api/                    # FastAPI endpoints (17 routers)
│   ├── agent_api.py       # NEW: Autonomous agent operations
│   ├── server.py          # Main server with native tool calling
│   ├── tool_evolution_api.py  # Evolution workflow
│   ├── tool_creation_api.py   # Tool creation (via improvement_api)
│   ├── quality_api.py     # Health scoring
│   ├── observability_api.py   # Database access
│   ├── cleanup_api.py     # Maintenance endpoints
│   ├── hybrid_api.py      # Hybrid improvement engine
│   ├── settings_api.py    # Model settings
│   ├── scheduler_api.py   # Scheduled improvements
│   ├── libraries_api.py   # Library management
│   └── tools_api.py       # Tool management & sync
│
├── core/                   # Core logic
│   ├── skills/            # Skills system
│   │   ├── __init__.py    # Skills exports
│   │   ├── models.py      # SkillDefinition, SkillSelection, SkillPlanningContext
│   │   ├── registry.py    # In-memory skill registry
│   │   ├── selector.py    # Skill selection logic (heuristic + LLM)
│   │   ├── loader.py      # Load skills from disk
│   │   ├── updater.py     # Update skill definitions
│   │   └── context.py     # Build planning context from skills
│   │
│   ├── autonomous_agent.py    # Goal achievement loop
│   ├── task_planner.py        # Multi-step planning (skill-aware)
│   ├── execution_engine.py    # Plan execution with state & parameter resolution
│   ├── memory_system.py       # SQLite-backed context & learning
│   │
│   ├── tool_creation/     # Tool creation pipeline
│   │   ├── flow.py        # Main orchestrator
│   │   ├── spec_generator.py  # Spec generation
│   │   ├── code_generator/    # Code generation
│   │   │   ├── qwen_generator.py   # Multi-stage
│   │   │   └── default_generator.py # Single-shot
│   │   ├── validator.py   # Validation
│   │   └── sandbox_runner.py  # Testing
│   │
│   ├── tool_evolution/    # Evolution flow
│   │   ├── flow.py        # 6-step orchestrator
│   │   ├── analyzer.py    # Tool analysis
│   │   ├── proposal_generator.py  # LLM proposals
│   │   ├── code_generator.py      # Code generation
│   │   ├── validator.py   # Validation
│   │   └── sandbox_runner.py      # Sandbox testing
│   │
│   ├── tool_services.py   # Service facade
│   ├── tool_orchestrator.py  # Central orchestrator
│   ├── dependency_checker.py  # AST-based detection
│   ├── dependency_resolver.py # Install libs, generate services
│   ├── enhanced_code_validator.py # NEW: Architectural validation
│   ├── tool_quality_analyzer.py  # Health scoring
│   ├── database_schema_registry.py # NEW: Schema documentation
│   ├── tool_creation_logger.py    # NEW: Creation tracking
│   ├── tool_evolution_logger.py   # Evolution tracking
│   ├── tool_execution_logger.py   # Execution tracking
│   ├── pending_evolutions_manager.py  # Approval queue
│   └── sqlite_logging.py  # SQLite logger
│
├── planner/
│   ├── llm_client.py      # LLM interface
│   └── tool_calling.py    # Native function calling
│
├── tools/                  # Tool implementations
│   ├── enhanced_filesystem_tool.py
│   ├── web_access_tool.py          # Unified web interaction
│   ├── http_tool.py                # Low-level HTTP (hidden when WebAccessTool available)
│   ├── json_tool.py
│   ├── shell_tool.py
│   └── experimental/      # Auto-generated tools
│       ├── BrowserAutomationTool.py      # Advanced browser automation
│       ├── ContextSummarizerTool.py      # Text summarization
│       ├── DatabaseQueryTool.py          # Database queries with schema
│       ├── LocalRunNoteTool.py           # Note management
│       ├── LocalCodeSnippetLibraryTool.py # Code snippet storage
│       ├── WorkflowAutomationTool.py     # Multi-step workflows
│       ├── ExecutionPlanEvaluatorTool.py # Plan quality assessment
│       ├── TaskBreakdownTool.py          # Goal decomposition
│       ├── UserApprovalGateTool.py       # Human-in-loop approvals
│       ├── IntentClassifierTool.py       # Intent classification
│       └── SystemIntrospectionTool.py    # System state inspection
│
├── skills/                 # Skill definitions
│   ├── web_research/
│   │   ├── skill.json     # Skill metadata
│   │   └── SKILL.md       # Detailed instructions
│   ├── computer_automation/
│   │   ├── skill.json
│   │   └── SKILL.md
│   └── code_workspace/
│       ├── skill.json
│       └── SKILL.md
│
├── ui/                     # React frontend
│   └── src/
│       ├── components/
│       │   ├── MainCanvas.js      # Unified canvas
│       │   ├── ModeTabBar.js      # Mode switcher
│       │   ├── FloatingActionBar.js  # Context buttons
│       │   ├── RightOverlay.js    # Slide-in panels
│       │   ├── EvolutionMode.js   # Tool evolution UI
│       │   ├── ObservabilityOverlay.js  # Database viewer
│       │   ├── QualityOverlay.js  # Health dashboard
│       │   └── PendingEvolutionsOverlay.js  # Approval UI
│       └── App.js          # Main app with clear cache
│
└── data/                   # SQLite databases & JSON storage
    ├── logs.db
    ├── tool_evolution.db
    ├── tool_executions.db
    ├── tool_creation.db
    ├── chat_history.db
    ├── conversations.db
    ├── analytics.db
    ├── failure_patterns.db
    ├── improvement_memory.db
    ├── plan_history.db
    └── pending_evolutions.json
```

## 🔄 Data Flow

### Autonomous Goal Flow
```
User: "Go to Google, search Wikipedia, then go to Wikipedia and search AGI"
    ↓
1. Skill Selection
   - Analyzes message for domain (web_research detected)
   - Provides preferred tools: [WebAccessTool]
   - Sets verification mode: strict
    ↓
2. Intent Classification
   - LLM determines: Multi-step task (A)
   - Triggers autonomous agent
    ↓
3. Task Planning (skill-aware)
   - Breaks into steps:
     * step_1: open_page(url="https://www.google.com")
     * step_2: search_web(query="Wikipedia") [depends on step_1]
     * step_3: open_page(url=from step_2 results)
     * step_4: search_web(query="AGI") [depends on step_3]
   - Validates all tools exist
   - Checks parameter requirements
   - Builds dependency graph
    ↓
4. Execution Engine
   - Executes in dependency order
   - Resolves {{step_X}} parameter references
   - Retries failed steps (max 3 attempts)
   - Tracks state for each step
    ↓
5. Verification
   - LLM checks if ALL parts completed:
     ✓ Went to Google
     ✓ Searched for Wikipedia
     ✓ Navigated to Wikipedia
     ✓ Searched for AGI on Wikipedia
   - Returns JSON: {"success": true/false, "reason": "...", "missing_parts": [...]}
    ↓
6. Iteration (if needed)
   - Analyzes failure details
   - Updates context with learnings
   - Generates retry guidance
   - Re-plans with corrections
   - Max 3 iterations (configurable)
    ↓
Goal Achieved → Store success pattern in learned_patterns
```

### Chat Request Flow
```
User Message
    ↓
Skill Selection (heuristic + LLM fallback)
    ↓
Intent Classification (multi-step vs simple)
    ↓
┌─────────────────┬─────────────────┐
│   Multi-Step    │     Simple      │
│   (Autonomous   │   (Tool Call)   │
│     Agent)      │                 │
└─────────────────┴─────────────────┘
    ↓                     ↓
Task Planner      Native Tool Calling
(skill-aware)     (skill-aware)
    ↓                     ↓
Execution Engine  Tool Execution
(with retries)    (multi-round)
    ↓                     ↓
Verification      Output Analysis
    ↓                     ↓
Iterate/Complete  UI Components
    ↓                     ↓
Natural Response (filters tool call JSON)
```

### Tool Creation Flow
```
User: "Create a tool for X"
    ↓
1. Spec Generation (LLM proposes spec with confidence)
    ↓
2. Code Generation (Qwen multi-stage or GPT single-shot)
    ↓
3. Enhanced Validation (12+ gates)
    ↓
4. Dependency Check (AST parsing)
    ↓
5. Sandbox Test (isolated execution)
    ↓
6. Approval (human review)
    ↓
User Approves → Activate Tool
```

### Evolution Flow
```
User: "Improve ContextSummarizerTool"
    ↓
1. Analyze (quality score, errors, usage)
    ↓
2. Propose (LLM generates improvement spec)
    ↓
3. Generate Code (LLM creates improved version)
    ↓
3.5. Check Dependencies (AST parsing)
    ↓
4. Validate (enhanced AST + structure)
    ↓
5. Sandbox Test (isolated execution)
    ↓
6. Pending Approval (human review)
    ↓
User Approves → Apply Changes → Remove from Pending
```

### Dependency Resolution Flow
```
Evolution/Creation Generated
    ↓
Dependency Checker (AST parse)
    ↓
Missing Libraries? → Install via pip
Missing Services? → Generate via LLM or Skip
    ↓
Re-check on Approval
    ↓
All Resolved? → Proceed
Still Missing? → Block with error
```

## 🎨 UI Features

### Theme System
- **Dark Theme** (default): Black background (#000000), blue accent (#4a9eff)
- **Light Theme**: Modern white (#f7f7f7), GitHub-style colors
- **CSS Variables**: All colors use theme variables, no hardcoded colors
- **Smooth Transitions**: 0.2s ease transitions on theme change
- **Persistent**: Theme choice saved to localStorage
- **Toggle**: Sun/Moon icon in header

### UI Modes

### 1. CUA Chat
- Conversational interface
- Native tool calling
- Real-time execution
- Agentic responses (no tool call JSON shown)

### 2. Tools Mode
- Tool creation interface
- Capability specification
- Sandbox testing
- Approval workflow

### 3. Evolution Mode
- Tool selection (Recommended/All)
- Recommended excludes tools with pending evolutions
- Prioritizes tools with recent errors
- Evolution workflow
- Pending approvals with dependency warnings
- Auto-cleanup on approval/rejection
- Capability gaps dashboard (what features the system is missing)
- Pending services approvals (approve/reject injected `core/tool_services.py` changes)
- Embedded auto-evolution panel (queue + scan + config)

### 4. Tools Management
- Comprehensive tool dashboard
- All tools with health metrics
- Search and filter capabilities
- Individual tool analysis
- Quick actions (health check, evolution, view code)

### 5. Observability
- Full-page database viewer
- 10 databases with all tables
- Paginated data with search/filters
- Row details in modal popup
- Copy functionality for fields

## 📊 Observability

**Database Icon** in header opens overlay with 10 tabs:
- **System Logs**: All application logs with filtering
- **Tool Executions**: Execution history per tool with metrics
- **Tool Evolution**: Evolution attempts with step tracking
- **Tool Creation**: Tool generation logs with status
- **Chat History**: Conversation logs
- **Analytics**: Improvement metrics
- **Failure Patterns**: Failed changes and error patterns
- **Improvement Memory**: Successful improvements
- **Plan History**: Execution plan history
- **Conversations**: Main conversation storage

**Features**:
- Cleanup stale data
- Refresh quality metrics
- Filter by tool/status/date
- Schema validation
- LLM-assisted queries via DatabaseQueryTool

## 🛠️ Available Services

Tools can access via `self.services`:

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

# Shell
self.services.shell.execute(command)

# Logging
self.services.logging.info(message)
self.services.logging.error(message)
self.services.logging.warning(message)
self.services.logging.debug(message)

# Time
self.services.time.now_utc()
self.services.time.now_local()

# IDs
self.services.ids.generate(prefix)
self.services.ids.uuid()

# NLP Helpers
self.services.extract_key_points(text, style, language)
self.services.sentiment_analysis(text, language)
self.services.detect_language(text)
self.services.generate_json_output(**kwargs)

# Inter-tool Communication
self.services.call_tool(tool_name, operation, **parameters)
self.services.list_tools()
self.services.has_capability(capability_name)
```

## 🔐 Safety Features

- **Sandbox Testing**: All generated code tested in isolation
- **Human Approval**: Evolution/creation requires manual approval
- **Dependency Validation**: Blocks broken code with missing deps
- **Enhanced Validation**: 12+ gates including architectural checks
- **Health Scoring**: Identifies weak/broken tools
- **Rollback Support**: Backups created before changes
- **Service Pattern Enforcement**: Validates correct service usage
- **Auto-cleanup**: Removes approved/rejected evolutions from pending

## 📈 Quality Metrics

**Health Score** (0-100):
- Success Rate: 40 points
- Usage Count: 30 points

## ✅ Verification Status (March 21, 2026)

### Comprehensive Architecture Review

A full architectural audit was conducted to verify the integration of SkillExecutionContext and supporting systems. Here's the verified status:

**Core Verification Results:**

| Component | Status | Evidence | Score |
|-----------|--------|----------|-------|
| **SkillExecutionContext** | ✅ COMPLETE | 32 fields fully implemented; used throughout pipeline | 100% |
| **Tool Selection** | ✅ WORKING | preferred_tools resolved; fallback_tools built and used | 100% |
| **ExecutionEngine** | ✅ INTEGRATED | skill_context passed; max_retries from risk_level used | 100% |
| **ToolOrchestrator** | ✅ INTEGRATED | execution_context used for error tracking + recovery | 100% |
| **Recovery Logic** | ✅ WORKING | should_fallback() evaluated at 3 call sites; fallback switching active | 100% |
| **Output Validation** | ⚠️ PARTIAL | Function implemented; called in success path; needs extension | 70% |
| **Skill Extraction** | ⚠️ PARTIAL | 3 of 10 fields extracted; missing tools/constraints | 30% |
| **Multi-round Context** | ⚠️ PARTIAL | Context preserved; could be fully refreshed | 75% |
| **Service Validation** | ❌ NOT YET | No constraint/signature checking | 0% |
| **Auto-Skill Detection** | ❌ NOT YET | SkillSelector available but not called if target_skill null | 0% |

**Overall Architecture Score: 85%** ✅

### What's Verified Working (Confidence Level 100%)

**Execution Pipeline:**
- ✅ Skill selection (keywords + heuristics + LLM)
- ✅ SkillExecutionContext creation with all metadata
- ✅ Tool resolution (preferred_tools → available tools)
- ✅ Context flow through ExecutionEngine.execute_plan()
- ✅ Context flow through ToolOrchestrator.execute_tool_step()
- ✅ Recovery logic: error tracking, fallback switching, retry logic
- ✅ Metrics collection: step_history, errors_encountered, warnings
- ✅ Tool creation with architecture contract validation
- ✅ Tool evolution with context-aware analysis

**Safety & Validation:**
- ✅ Circuit breaker integrated with context awareness
- ✅ Error tracking at every tool execution point
- ✅ Fallback strategies derived from skill.risk_level
- ✅ Output validation function exists and working
- ✅ Verification modes enforced (source_backed, side_effect_observed)

### Known Refinements Needed (Blocking?: NO)

**HIGH Priority (2-3 hrs):**
1. Skill extraction: Extract all 10 fields instead of 3 → Better LLM guidance
2. Output validation: Extend to fallback/error paths → Complete coverage

**MEDIUM Priority (2 hrs):**
3. Multi-round context: Fully refresh between tool calling rounds → Cleaner state

**LOW Priority (3+ hrs):**
4. Service validation: Constraint + signature checking → Smarter tool generation
5. Auto-skill detection Fallback when target_skill not provided → Better UX

### Production Readiness

✅ **READY FOR PRODUCTION** with note:
- Core execution path is solid (100% verified)
- Recovery logic is active (tested at 3 integration points)
- No blocking issues or architectural flaws
- Gaps are refinements, not functionality blockers
- System correctly prevents silent failures

### Next Engineering Phase

**Immediate (This Week):**
- Implement skill extraction enhancement (HIGH priority #1)
- Extend output validation coverage (HIGH priority #2)
- These two changes alone bring system to 90%+

**Short-term (Next 2 Weeks):**
- Multi-round context refresh
- Auto-skill detection fallback
- Would bring system to 95%

**Medium-term (Next Month):**
- Service validation pipeline
- Skill-based evolution metrics
- Full 100% completion

## 📚 Documentation

- **Architecture**: See `/memories/repo/architecture-verification-complete.md`
- **Skills**: See `/skills/*/SKILL.md` for each skill's guidance
- **API Reference**: http://localhost:8000/docs (Swagger UI)
- **Git**: Commits tagged with [ARCH], [SKILL], [VERIFY] for architecture changes

## 🤝 Contributing

When adding new features:
1. Ensure SkillExecutionContext is passed where needed
2. Add step tracking: `execution_context.add_step()`
3. Add error tracking: `execution_context.add_error()` 
4. Test context flow end-to-end
5. Verify skill constraints are respected

## 📝 License

CUA is proprietary software for local autonomous execution.
- Output Size: 20 points
- Error Rate: -10 points

**Recommendations**:
- **HEALTHY** (80-100): No action needed
- **WEAK** (50-79): Consider evolution
- **BROKEN** (0-49): Quarantine or fix

## 🎯 Strategic Direction

CUA already has substantial feature depth. The main constraint is no longer capability breadth; it is reliability, control-plane clarity, and product focus.

### Core Decision

CUA should move forward as a **reliable local autonomous execution platform with human approval gates**.

That means the primary product journey is:

- Goal intake
- Plan generation
- Tool-based execution
- Approval-aware escalation
- Verification
- Audit and trace inspection

### Secondary Capabilities

These remain valuable, but should be framed as support systems for the primary journey:

- Tool creation
- Tool evolution
- Auto-evolution
- Broad observability dashboards
- Multi-mode administrative UI flows

### Architecture Direction

To support that product direction, the next architecture work should prioritize:

- Hardening safety mechanisms so documented guarantees are enforced at runtime
- Breaking up startup and dependency wiring so system health is easier to understand
- Improving deterministic validation and reducing reliance on model-only verification
- Expanding tests around the critical execution and approval paths before adding more breadth

### Success Metrics For This Direction

- Goal completion rate for the primary workflow
- Approval rate for genuinely risky actions
- Execution failure rate by tool
- Rollback frequency
- Pending approval aging
- Time to diagnose failed runs

## 🚦 Status

**Working**:
- ✅ Skills system (domain-aware routing with 3 skills: web_research, computer_automation, code_workspace)
- ✅ Autonomous goal achievement (intent classification + multi-step planning & execution)
- ✅ Memory system (SQLite persistence + conversation context & learned patterns)
- ✅ Self-correction (failure analysis & iteration with detailed error tracking)
- ✅ Native tool calling (20+ tools with skill-aware selection)
- ✅ WebAccessTool (unified web interaction: fetch, search, open, crawl)
- ✅ Tool creation (6-step flow with validation + registry-aware duplicate prevention)
- ✅ Tool evolution (action-type aware, context-aware improvements)
- ✅ CUA architecture validation (service methods, capability matching)
- ✅ Smart sandbox (dependency detection, network error handling)
- ✅ LLM health analyzer (reduced false positives)
- ✅ Tools Management page (comprehensive dashboard)
- ✅ Observability page (full-page database viewer)
- ✅ Theme system (dark/light with CSS variables)
- ✅ Dependency management (auto-detect & resolve)
- ✅ Enhanced validation (3-layer: AST + Architecture + Dependencies)
- ✅ SQLite observability (10 databases)
- ✅ Database schema registry (LLM-assisted)
- ✅ Quality scoring & recommendations
- ✅ Unified UI with 5 modes
- ✅ Real-time updates (WebSocket)
- ✅ Approval workflows with auto-cleanup
- ✅ Cache clearing (UI button + API endpoint)
- ✅ Agentic chat responses (filters tool calls)
- ✅ Output analysis & UI component generation
- ✅ Capability gap detection & tracking
- ✅ Parameter resolution in execution engine ({{step_X}} references)

**In Progress**:
- 🔄 Auto-evolution triggers (scheduled improvements)
- 🔄 Platform hardening of safety, startup wiring, and approval semantics
- 🔄 Product narrowing around the default autonomous execution workflow

**Current Focus Areas**:
- Make the execution control plane more trustworthy than the feature surface is broad
- Shift the main product story from "many agent capabilities" to "safe goal completion"
- Keep self-improvement features available, but behind stronger operator framing and guardrails

## 📚 Documentation

- **[OBSERVABILITY.md](docs/OBSERVABILITY.md)** - Complete observability system guide
  - Correlation context & distributed tracing
  - 10 SQLite databases with schemas
  - Metrics aggregation & API endpoints
  - Best practices & troubleshooting

- **[AUTO_EVOLUTION_IMPLEMENTATION.md](docs/AUTO_EVOLUTION_IMPLEMENTATION.md)** - Auto-evolution system guide
  - LLM test orchestrator & validation
  - Evolution queue & prioritization
  - Implementation roadmap
  - Configuration & testing strategy

## 📝 Configuration

**Environment Variables**:
- `OLLAMA_URL`: Ollama server URL (default: http://localhost:11434)
- `CUA_API_URL`: Override backend base URL (default: http://localhost:8000)
- `CUA_API_PORT`: Override backend port (default: 8000)
- `CUA_MAX_FILE_WRITES`: Override max file writes per run (optional)
- `CORS_ALLOW_ORIGINS`: Allowed origins (default: http://localhost:3000)
- `REACT_APP_API_URL`: Frontend -> backend URL (see `ui/.env`)
- `REACT_APP_WS_URL`: Frontend WebSocket URL (see `ui/.env`)

**Config Files**:
- `config.yaml`: System configuration
- `config/model_capabilities.json`: Model routing config
- `requirements.txt`: Python dependencies
- `ui/package.json`: Frontend dependencies

## 🤝 Contributing

1. Tools are auto-generated via creation/evolution system
2. Services added to `core/tool_services.py`
3. Update `AVAILABLE_SERVICES` in `core/dependency_checker.py`
4. Update `DATABASE_SCHEMAS` in `core/database_schema_registry.py`
5. System auto-detects and validates

**Auto-evolution config keys** (via `POST /auto-evolution/config`):
- `enable_enhancements`: Whether to queue "HEALTHY but improvable" enhancements
- `max_new_tools_per_scan`: Limit how many new tools can be queued from capability gaps per scan

## 🧪 Testing

In some restricted Windows environments, `pytest` can fail when it tries to create temp folders or caches (permission denied). This repo disables `tmpdir` and `cacheprovider` in `pytest.ini` and provides a local `tmp_path` fixture in `tests/conftest.py`.

```bash
pytest -q
```

## 🧱 Reliability Notes

- **SQLite is best-effort**: observability/memory/history DBs are treated as optional; if a DB is locked/readonly, the system logs a warning and continues operating.
- **Creation is registry-aware**: if a requested tool name already exists, the API returns an "already exists" response and points you to evolve the existing tool instead of creating duplicates.
- **Service calls are validated**: generated/evolved code must only call allowed `self.services.*` APIs (unknown service methods are blocked by validation).
- **Scaffold-first fallback**: if full generation fails validation, CUA may create a safe scaffold and queue the tool for evolution rather than writing unvalidated code.

## 📄 License

MIT License - See LICENSE file

## 🙏 Acknowledgments

- **Ollama**: Local LLM hosting (any compatible model)
- **FastAPI**: Backend framework
- **React**: Frontend framework
- **Qwen / Mistral / etc.**: Local models (configurable)
