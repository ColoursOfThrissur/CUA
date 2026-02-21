# CUA System Architecture - Current State

## Overview
CUA is an autonomous agent system with:
- **Native Tool Calling**: Mistral function calling for automatic tool selection
- **Tool Evolution**: 6-step improvement workflow with dependency management
- **SQLite Observability**: 5 databases tracking all system activity
- **Unified UI**: 3 modes (Chat, Tools, Evolution) with real-time updates

---

## Core Flows

### 1. **Chat/Task Execution Flow (Native Tool Calling)**
```
User Request → API Server → Native Tool Calling (Mistral)
    ↓
LLM Selects Tools Automatically (OpenAI-compatible format)
    ↓
Tool Execution → Result → LLM Summary
    ↓
Natural Language Response
```

**Key Files:**
- `api/server.py` - Main entry point, native tool calling
- `planner/tool_calling.py` - Mistral function calling client
- `core/tool_orchestrator.py` - Tool execution
- `tools/capability_registry.py` - Tool registry

---

### 2. **Self-Improvement Loop Flow**
```
Start Loop → Baseline Health Check (GATE)
    ↓
Evolution Mode Check
    ├─ YES: Evolution Bridge → Evolution Controller
    └─ NO: Task Analyzer → Proposal Generator
    ↓
Code Generation (Qwen/Mistral) → Validation
    ↓
Sandbox Testing (with retry) → Risk Assessment
    ↓
Apply Changes → Verify → Track Success
```

**Key Files:**
- `core/improvement_loop.py` - Wrapper/facade
- `core/loop_controller.py` - Main loop orchestration
- `core/task_analyzer.py` - File selection & task generation
- `core/proposal_generator.py` - Code generation
- `core/sandbox_tester.py` - Isolated testing
- `updater/atomic_applier.py` - Safe file updates

**Modes:**
- **Deterministic Mode**: Task analyzer picks files based on maturity
- **Evolution Mode**: LLM proposes improvements freely

---

### 3. **Evolution Mode Flow**
```
Self-Reflector → Analyze system gaps/patterns
    ↓
LLM Generates Proposal (micro_patch/structural_upgrade/tool_extension/new_tool)
    ↓
Validation (structure, AST, risk, budget)
    ↓
Execute based on type:
    ├─ NEW_TOOL: Tool Creation Flow
    ├─ STRUCTURAL_UPGRADE: Refactoring via standard system
    ├─ TOOL_EXTENSION: Enhancement via standard system
    └─ MICRO_PATCH: Small fix via standard system
```

**Key Files:**
- `core/evolution_bridge.py` - Integration with loop controller
- `core/evolution_controller.py` - Evolution orchestration
- `core/self_reflector.py` - System analysis
- `core/proposal_types.py` - Proposal definitions
- `core/capability_graph.py` - Capability tracking
- `core/growth_budget.py` - Resource limits

---

### 4. **Tool Evolution Flow (6-Step)**
```
1. Analyze → Quality score, errors, usage
    ↓
2. Propose → LLM generates improvement spec
    ↓
3. Generate Code → LLM creates improved version
    ↓
3.5. Check Dependencies → AST parsing for missing libs/services
    ↓
4. Validate → Structure, syntax, logic checks
    ↓
5. Sandbox Test → Isolated execution
    ↓
6. Pending Approval → Human review with dependency warnings
    ↓
User Approves → Auto re-check deps → Apply changes
```

**Key Files:**
- `core/tool_evolution/flow.py` - 6-step orchestrator
- `core/tool_evolution/analyzer.py` - Tool analysis
- `core/tool_evolution/proposal_generator.py` - LLM proposals
- `core/tool_evolution/code_generator.py` - Code generation
- `core/tool_evolution/validator.py` - Validation
- `core/tool_evolution/sandbox_runner.py` - Testing
- `core/dependency_checker.py` - AST-based dependency detection
- `core/dependency_resolver.py` - Install libs, generate services
- `core/pending_evolutions_manager.py` - Approval queue
- `api/tool_evolution_api.py` - Evolution endpoints

---

### 5. **Hybrid Improvement Flow**
```
Custom Prompt → Error Prioritizer → Select Target File
    ↓
Memory Check (past attempts, success rate)
    ↓
Context Optimizer → Generate Proposal (with retry)
    ↓
Validation → Store in Memory
```

**Key Files:**
- `core/hybrid_improvement_engine.py` - RAG + memory-based improvement
- `core/error_prioritizer.py` - Error-driven targeting
- `core/improvement_memory.py` - Past attempt tracking
- `core/context_optimizer.py` - Context building

---

## Component Architecture

### **API Layer** (`api/`)
- `server.py` - FastAPI server, WebSocket/SSE events
- `improvement_api.py` - Loop control endpoints
- `pending_tools_api.py` - Tool approval workflow
- `tools_api.py` - Tool registry sync
- `scheduler_api.py` - Scheduled improvements
- `hybrid_api.py` - Hybrid engine endpoints

### **Core Layer** (`core/`)

#### **Orchestration**
- `tool_orchestrator.py` - Central tool execution
- `tool_registrar.py` - Dynamic tool registration
- `tool_services.py` - Service facade (storage, llm, http, fs, logging, etc.)
- `secure_executor.py` - Safety validation

#### **Dependency Management**
- `dependency_checker.py` - AST-based detection of missing imports/services
- `dependency_resolver.py` - Install libraries via pip, generate services via LLM

#### **Observability**
- `sqlite_logging.py` - SQLite logger (logs.db)
- `tool_evolution_logger.py` - Evolution tracking (tool_evolution.db)
- `tool_execution_logger.py` - Execution history (tool_executions.db)
- `tool_creation_logger.py` - Creation logs (tool_creation.db)
- `chat_history_logger.py` - Chat history (chat_history.db)
- `tool_quality_analyzer.py` - Health scoring (0-100)

#### **Self-Improvement**
- `improvement_loop.py` - Loop facade
- `loop_controller.py` - Main loop logic
- `task_analyzer.py` - Task selection
- `proposal_generator.py` - Code generation
- `sandbox_tester.py` - Testing
- `hybrid_improvement_engine.py` - RAG-based improvement

#### **Evolution System**
- `evolution_bridge.py` - Integration bridge
- `evolution_controller.py` - Evolution orchestration
- `self_reflector.py` - System analysis
- `capability_graph.py` - Capability tracking
- `growth_budget.py` - Resource limits
- `expansion_mode.py` - Experimental tool management

#### **Tool Evolution**
- `tool_evolution/flow.py` - 6-step evolution orchestrator
- `tool_evolution/analyzer.py` - Tool analysis with quality scoring
- `tool_evolution/proposal_generator.py` - LLM-based improvement proposals
- `tool_evolution/code_generator.py` - Code generation with service awareness
- `tool_evolution/validator.py` - AST and structure validation
- `tool_evolution/sandbox_runner.py` - Isolated testing

#### **Safety & Validation**
- `immutable_brain_stem.py` - Core safety rules
- `baseline_health_checker.py` - Pre-loop validation
- `failure_classifier.py` - Error classification
- `ast_validator.py` - AST validation
- `idempotency_checker.py` - Duplicate prevention
- `interface_protector.py` - API stability

#### **Memory & Analytics**
- `conversation_memory.py` - Chat history (SQLite)
- `improvement_memory.py` - Past attempts (SQLite)
- `improvement_analytics.py` - Success metrics
- `plan_history.py` - Execution history
- `llm_logger.py` - LLM call logging

#### **Utilities**
- `config_manager.py` - Configuration
- `event_bus.py` - Real-time events
- `storage_broker.py` - File abstraction
- `parameter_resolution.py` - Auto-fill params
- `validation_service.py` - Input validation

### **Tools Layer** (`tools/`)
- `capability_registry.py` - Runtime tool registry
- `tool_interface.py` - BaseTool abstract class
- `enhanced_filesystem_tool.py` - File operations
- `http_tool.py` - HTTP requests
- `json_tool.py` - JSON operations
- `shell_tool.py` - Shell commands
- `web_content_extractor.py` - Web scraping
- `experimental/` - Pending approval tools

### **Planner Layer** (`planner/`)
- `llm_client.py` - LLM integration (Ollama/Mistral)
- `tool_calling.py` - Native function calling (Mistral)
- `plan_parser.py` - Plan parsing
- `ollama_client.py` - Ollama fallback

### **Updater Layer** (`updater/`)
- `orchestrator.py` - Update orchestration
- `atomic_applier.py` - Safe file updates
- `risk_scorer.py` - Risk assessment
- `sandbox_runner.py` - Isolated testing
- `audit_logger.py` - Change tracking

### **UI Layer** (`ui/`)
- **Unified Canvas**: 3 modes (CUA Chat, Tools, Evolution)
- **Mode Tabs**: Carousel-style switcher with glass morphism
- **Floating Action Bar**: Context-sensitive buttons per mode
- **Right Overlays**: Slide-in panels with gradient backdrop
- **Observability**: Database viewer with 5 tabs
- **Quality Dashboard**: Health scores and recommendations
- **Pending Evolutions**: Approval UI with dependency warnings
- **Real-time Updates**: WebSocket for live data

---

## Data Flow Patterns

### **Native Tool Calling**
```
User Message → ToolCallingClient
    ↓
Build OpenAI-compatible tool definitions from registry
    ↓
Mistral /api/chat with tools parameter
    ↓
LLM returns tool_calls or text response
    ↓
Execute selected tools → Return results
```

### **Self-Improvement**
```
Loop Start → Baseline Check → Task Selection
    ↓
Code Generation (with context) → Validation
    ↓
Sandbox Test (with retry) → Apply → Verify
    ↓
Track Success → Analytics → Next Iteration
```

### **Tool Evolution**
```
Analyze Tool → Propose Changes → Generate Code
    ↓
Check Dependencies (AST) → Validate → Sandbox
    ↓
Pending Approval → Re-check Deps on Approval
    ↓
Apply Changes → Update Registry
```

### **Dependency Resolution**
```
Evolution Generated → DependencyChecker (AST parse)
    ↓
Missing Libraries? → Install via pip + add to requirements.txt
Missing Services? → Generate via LLM or Skip
    ↓
Re-check on Approval → All Resolved? → Proceed
```

---

## Key Integration Points

1. **Server → Improvement Loop**
   - `server.py` creates `SelfImprovementLoop`
   - Loop uses `LoopController` internally
   - Controller has `EvolutionBridge` for evolution mode

2. **Loop Controller → Evolution**
   - `loop_controller.py` checks `evolution_bridge.should_use_evolution()`
   - If true, runs `evolution_bridge.run_evolution_cycle()`
   - Evolution controller uses standard proposal generator

3. **Evolution → Tool Creation**
   - `evolution_controller.py` has `ToolCreationOrchestrator`
   - For NEW_TOOL proposals, delegates to tool creation flow
   - Other proposals use standard improvement system

4. **Tool Orchestrator → Tools**
   - All tool execution goes through `ToolOrchestrator`
   - Injects services via `ToolServices`
   - Normalizes results to `OrchestratedToolResult`

5. **Pending Tools → Registration**
   - `pending_tools_manager.py` manages approval queue
   - `tool_registrar.py` dynamically imports and registers
   - `capability_registry.py` tracks runtime capabilities

---

## Safety Mechanisms

1. **Baseline Health Check** - Pre-loop validation
2. **Sandbox Testing** - Isolated execution before apply
3. **Risk Scoring** - Approval workflow for high-risk changes
4. **Idempotency Check** - Prevent duplicate changes
5. **Interface Protection** - Preserve public APIs
6. **Failure Classification** - Smart error handling
7. **Growth Budget** - Resource limits for evolution
8. **File Cooldown** - Prevent repeated failures

---

## Current State Summary

### ✅ **Working**
- Native tool calling (Mistral function calling)
- Tool evolution (6-step flow with dependency management)
- SQLite observability (5 databases)
- Quality scoring and recommendations
- Unified UI with 3 modes
- Real-time updates via WebSocket
- Approval workflows with dependency warnings
- Auto dependency re-check on approval
- Service facade with logging support

### 🔄 **In Progress**
- LLM-based health checking (input/output validation)
- Auto-evolution triggers (scheduled improvements)
- Service generation via LLM (for missing services)

### 🔧 **Architecture Notes**
- **Native Tool Calling**: Mistral automatically selects tools via function calling
- **Dependency Management**: AST-based detection, auto-install libraries, LLM-generated services
- **Observability**: 5 SQLite databases track all system activity
- **Service Facade**: Tools access storage, llm, http, fs, json, logging via self.services
- **Auto Refresh**: Dependencies re-checked on approval to detect newly added services
- **Health Scoring**: 0-100 based on success rate, usage, output size
- **Event Bus**: Real-time updates to UI via WebSocket
- **Storage**: SQLite for logs/history, JSON for pending approvals

---

## Flow Diagram Summary

```
┌─────────────────────────────────────────────────────────────┐
│                        API Server                            │
│  (FastAPI + WebSocket/SSE)                                  │
└────────────┬────────────────────────────────────────────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌─────────┐    ┌──────────────┐
│  Chat   │    │ Improvement  │
│  Flow   │    │    Loop      │
└────┬────┘    └──────┬───────┘
     │                │
     ▼                ▼
┌─────────────┐  ┌──────────────────┐
│    Tool     │  │  Loop Controller │
│ Orchestrator│  │  (with Evolution │
└─────┬───────┘  │     Bridge)      │
      │          └────────┬─────────┘
      │                   │
      ▼                   ▼
┌──────────────┐   ┌─────────────────┐
│  Capability  │   │   Evolution     │
│   Registry   │   │   Controller    │
└──────────────┘   └────────┬────────┘
                            │
                   ┌────────┴────────┐
                   │                 │
                   ▼                 ▼
            ┌──────────────┐  ┌─────────────┐
            │ Tool Creation│  │  Standard   │
            │     Flow     │  │ Improvement │
            └──────────────┘  └─────────────┘
```

---

## Available Services (via self.services)

```python
# Storage (auto-scoped to tool)
self.services.storage.save(id, data)
self.services.storage.get(id)
self.services.storage.list(limit=10)

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

# Logging
self.services.logging.info(message)
self.services.logging.error(message)
self.services.logging.warning(message)

# Time
self.services.time.now_utc()

# IDs
self.services.ids.generate(prefix)

# NLP Helpers
self.services.extract_key_points(text)
self.services.sentiment_analysis(text)
self.services.detect_language(text)
self.services.generate_json_output(**kwargs)
```
