# CUA - Autonomous Agent System

**Self-improving AI agent with native tool calling, automatic dependency management, real-time evolution, and comprehensive observability.**

## 🎯 What CUA Does

CUA is an autonomous agent that:
- **Executes tasks** using 20+ tools via Mistral's native function calling
- **Creates tools** through LLM-driven generation with validation pipeline
- **Evolves tools** by detecting weak tools and generating improvements
- **Manages dependencies** automatically (detects missing libraries/services)
- **Validates everything** via enhanced AST validation and sandbox testing
- **Observes everything** via SQLite-based logging across 10 databases
- **Self-improves** through hybrid improvement engine with 80% success rate

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

## 🏗️ Architecture Overview

### Core Components

```
CUA System
├── API Layer (FastAPI - 15 routers)
│   ├── Chat endpoint (/chat) - Native tool calling with agentic response
│   ├── Tool Creation API - LLM-driven tool generation
│   ├── Tool Evolution API - 6-step improvement workflow
│   ├── Quality API - Health scoring & recommendations
│   ├── Observability API - 10 database access with schema registry
│   ├── Cleanup API - Maintenance & cache clearing
│   ├── Hybrid API - 80% success improvement engine
│   └── Settings/Scheduler/Libraries/Tools APIs
│
├── Tool System
│   ├── Registry (20+ tools)
│   ├── Native Function Calling (Mistral)
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
│   ├── Evolution Flow (6-step improvement)
│   ├── Proposal Generator (LLM-driven specs)
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
    ├── Right-Slide Overlays (context-aware panels)
    ├── Real-time Updates (WebSocket)
    ├── Approval Workflows (evolution/tool creation)
    ├── Quality Dashboard (health monitoring)
    └── Clear Cache Button (sticky bottom-left)
```

## 🔧 Key Features

### 1. Native Tool Calling
- **Mistral Function Calling**: LLM automatically selects tools based on capability descriptions
- **Scales to 20+ tools**: No manual tool specification needed
- **OpenAI-compatible format**: Works with any function-calling model
- **Agentic Response**: Filters tool call JSON, shows only natural language responses

### 2. Tool Creation
**6-Step Flow**:
1. **Spec Generation**: LLM proposes tool specification with confidence scoring
2. **Code Generation**: Multi-stage (Qwen) or single-shot (GPT/Claude) generation
3. **Enhanced Validation**: 12+ gates including AST, imports, service usage
4. **Dependency Check**: AST-based detection of missing libraries/services
5. **Sandbox Testing**: Isolated execution with ordered operations
6. **Approval**: Human review before activation

### 3. Tool Evolution
**6-Step Flow**:
1. **Analyze**: Quality analyzer scores tool health (0-100)
2. **Propose**: LLM generates improvement spec
3. **Generate**: Code generator creates improved version
4. **Check Deps**: Dependency checker validates imports/services
5. **Validate**: Enhanced AST validation + structure checks
6. **Sandbox**: Test in isolated environment
7. **Approve**: Human reviews and approves (auto-removes from pending)

### 4. Dependency Management
- **AST-based detection**: Parses generated code for missing imports and service calls
- **Auto-resolution**: Install libraries via pip, generate services via LLM
- **Non-blocking**: Evolutions with missing deps are blocked until resolved
- **Auto-refresh**: Re-checks dependencies on approval
- **Service Pattern Enforcement**: Validates `self.services.X` usage

### 5. Enhanced Validation
**12+ Validation Gates**:
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
- **NEW**: Undefined method detection
- **NEW**: Uninitialized attribute detection
- **NEW**: Code truncation detection
- **NEW**: Service usage pattern validation

### 6. Observability
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

### 7. Quality System
- **Health Scoring**: 0-100 based on success rate, usage, output size
- **Recommendations**: HEALTHY (80+), WEAK (50-79), BROKEN (<50)
- **Cleanup**: Remove stale execution logs for deleted tools
- **Filtering**: Only show tools with actual files
- **Auto-refresh**: Quality metrics update on evolution approval

## 📁 Project Structure

```
CUA/
├── api/                    # FastAPI endpoints (15 routers)
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

## 🎨 UI Modes

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
- Evolution workflow
- Pending approvals with dependency warnings
- Auto-cleanup on approval/rejection

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
- ✅ Native tool calling (20+ tools)
- ✅ Tool creation (6-step flow with validation)
- ✅ Tool evolution (6-step flow with auto-cleanup)
- ✅ Dependency management (auto-detect & resolve)
- ✅ Enhanced validation (12+ gates)
- ✅ SQLite observability (10 databases)
- ✅ Database schema registry (LLM-assisted)
- ✅ Quality scoring & recommendations
- ✅ Unified UI with 3 modes
- ✅ Real-time updates (WebSocket)
- ✅ Approval workflows with auto-cleanup
- ✅ Cache clearing (UI button + API endpoint)
- ✅ Agentic chat responses (filters tool calls)

**In Progress**:
- 🔄 LLM-based health checking (input/output validation)
- 🔄 Auto-evolution triggers (scheduled improvements)

## 📝 Configuration

**Environment Variables**:
- `OLLAMA_URL`: Ollama server URL (default: http://localhost:11434)
- `MODEL`: LLM model (default: mistral:latest)
- `CORS_ALLOW_ORIGINS`: Allowed origins (default: http://localhost:3000)

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

- **Mistral AI**: Native function calling
- **Ollama**: Local LLM hosting
- **FastAPI**: Backend framework
- **React**: Frontend framework
- **Qwen**: Code generation model
