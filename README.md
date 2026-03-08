# CUA - Autonomous Agent System

**Self-improving AI agent with native tool calling, automatic dependency management, real-time evolution, and comprehensive observability.**

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
- `POST /chat` - Chat endpoint (intent classification + tool calling + autonomous-agent fallback when available)
- `GET /health` - Basic health + `system_available`
- `GET /status` - Runtime summary (sessions, connections, tools, capabilities)
- `POST /cache/clear` - Clears sessions + caches

Realtime
- `GET /events` - SSE stream (event bus)
- `WS /ws` - WebSocket stream (event bus + initial state)
- `WS /ws/trace` - WebSocket stream for trace events (UI trace overlay)

Settings
- `GET /settings/models`
- `POST /settings/model`
- `POST /settings/reload-config`

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
- `HTTPTool`: `get`, `post`, `put`, `delete` (domain allowlist is enforced in `tools/http_tool.py`)
- `JSONTool`: `parse`, `stringify`, `query`
- `ShellTool`: `execute` (command allowlist is enforced in `tools/shell_tool.py`)

Experimental tools (available in `tools/experimental/`; some are loaded by default)
- `BrowserAutomationTool`
- `ContextSummarizerTool`
- `DatabaseQueryTool`
- `LocalRunNoteTool`
- additional experimental tools exist and can be activated/loaded via the tool sync + approval flows

## 🏗️ Architecture Overview

### Core Components

```
CUA System
├── Autonomous Agent (NEW)
│   ├── Task Planner - Breaks goals into executable steps
│   ├── Execution Engine - Runs multi-step plans with state tracking
│   ├── Memory System - Conversation context & learned patterns
│   └── Goal Achievement Loop - Plan → Execute → Verify → Iterate
│
├── API Layer (FastAPI - multiple routers)
│   ├── Agent API (NEW) - Autonomous goal achievement
│   ├── Chat endpoint (/chat) - Native tool calling with agentic response
│   ├── Tool Creation API - LLM-driven tool generation
│   ├── Tool Evolution API - 6-step improvement workflow
│   ├── Quality API - Health scoring & recommendations
│   ├── Observability API - 10 database access with schema registry
│   ├── Observability Data API - Paginated data access with filters
│   ├── Tools Management API - Comprehensive tool management
│   ├── Cleanup API - Maintenance & cache clearing
│   ├── Hybrid API - hybrid improvement engine
│   └── Settings/Scheduler/Libraries/Tools APIs
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

### 1. Autonomous Goal Achievement (NEW)
- **Multi-Step Planning**: LLM breaks complex goals into executable steps
- **Dependency Management**: Steps execute in correct order based on dependencies
- **State Tracking**: Full execution state with step results and timing
- **Error Recovery**: Automatic retry logic with configurable max attempts
- **Self-Correction**: Analyzes failures and adjusts approach for next iteration
- **Memory Integration**: Learns from past successes and failures
- **Verification**: LLM verifies if goal achieved against success criteria
- **Pause/Resume**: Can pause execution and resume later

### 2. Memory & Learning (NEW)
- **Conversation Context**: Maintains full conversation history per session
- **User Preferences**: Stores and applies user-specific preferences
- **Execution History**: Links conversations to execution plans
- **Pattern Learning**: Stores successful approaches for similar goals
- **Session Management**: Create, retrieve, and clear sessions
- **Context Summarization**: Provides relevant context for planning

### 3. Native Tool Calling
- **Mistral Function Calling**: LLM automatically selects tools based on capability descriptions
- **Scales to 20+ tools**: No manual tool specification needed
- **OpenAI-compatible format**: Works with any function-calling model
- **Agentic Response**: Filters tool call JSON, shows only natural language responses

### 4. Tool Creation
**6-Step Flow**:
1. **Spec Generation**: LLM proposes tool specification with confidence scoring
2. **Code Generation**: Multi-stage (Qwen) or single-shot (GPT/Claude) generation
3. **Enhanced Validation**: 12+ gates including AST, imports, service usage
4. **Dependency Check**: AST-based detection of missing libraries/services
5. **Sandbox Testing**: Isolated execution with ordered operations
6. **Approval**: Human review before activation

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
- `conversations.db` - Main conversation history
- `analytics.db` - Improvement metrics
- `failure_patterns.db` - Failed changes and error patterns
- `improvement_memory.db` - Successful improvements
- `plan_history.db` - Execution plan history

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
│   ├── autonomous_agent.py    # NEW: Goal achievement loop
│   ├── task_planner.py        # NEW: Multi-step planning
│   ├── execution_engine.py    # NEW: Plan execution with state
│   ├── memory_system.py       # NEW: Context & learning
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
│   ├── http_tool.py
│   ├── json_tool.py
│   ├── shell_tool.py
│   └── experimental/      # Auto-generated tools
│       ├── ContextSummarizerTool.py  # Text summarization
│       ├── DatabaseQueryTool.py      # Database queries with schema
│       └── LocalRunNoteTool.py       # Note management
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

### Autonomous Goal Flow (NEW)
```
User: "Analyze sales data and create report"
    ↓
1. Plan (break into steps: fetch data, analyze, generate report)
    ↓
2. Execute (run each step with dependencies)
    ↓
3. Verify (check if goal achieved)
    ↓
4. Iterate (if failed, adjust and retry)
    ↓
Goal Achieved → Store success pattern
```

### Chat Request Flow
```
User Message
    ↓
Native Tool Calling (Mistral)
    ↓
Tool Selection (automatic)
    ↓
Tool Execution (via registry)
    ↓
Result → LLM Summary (includes all data fields)
    ↓
Natural Response (filters out tool call JSON)
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
- Output Size: 20 points
- Error Rate: -10 points

**Recommendations**:
- **HEALTHY** (80-100): No action needed
- **WEAK** (50-79): Consider evolution
- **BROKEN** (0-49): Quarantine or fix

## 🚦 Status

**Working**:
- ✅ Autonomous goal achievement (multi-step planning & execution)
- ✅ Memory system (conversation context & learned patterns)
- ✅ Self-correction (failure analysis & iteration)
- ✅ Native tool calling (20+ tools)
- ✅ Tool creation (6-step flow with validation)
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

**In Progress**:
- 🔄 Auto-evolution triggers (scheduled improvements)

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

## 📄 License

MIT License - See LICENSE file

## 🙏 Acknowledgments

- **Ollama**: Local LLM hosting (any compatible model)
- **FastAPI**: Backend framework
- **React**: Frontend framework
- **Qwen / Mistral / etc.**: Local models (configurable)
