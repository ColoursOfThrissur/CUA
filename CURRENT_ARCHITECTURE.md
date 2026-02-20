# CUA System Architecture - Current State

## Overview
CUA is an autonomous agent system with self-improvement capabilities, tool orchestration, and evolution modes.

---

## Core Flows

### 1. **Chat/Task Execution Flow**
```
User Request → API Server → LLM Decision (SIMPLE/COMPLEX/CHAT)
    ↓
SIMPLE: Direct tool execution (regex or capability inference)
COMPLEX: Plan generation → State machine execution
CHAT: Conversational response
    ↓
Tool Orchestrator → Parameter resolution → Tool.execute()
    ↓
Result normalization → Response to user
```

**Key Files:**
- `api/server.py` - Main entry point, chat endpoint
- `core/tool_orchestrator.py` - Central tool execution
- `core/parameter_resolution.py` - Auto-fill parameters
- `core/state_machine.py` - Multi-step plan execution

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

### 4. **Tool Creation Flow**
```
Gap Detection → Spec Generation (LLM)
    ↓
Code Generation (Qwen multi-stage / Default single-shot)
    ↓
Validation (AST, contract checks)
    ↓
Create in tools/experimental/
    ↓
Sandbox Testing → Pending Approval Queue
    ↓
User Approval → Tool Registration → Runtime Registry
```

**Key Files:**
- `core/tool_creation/flow.py` - Orchestrator
- `core/tool_creation/spec_generator.py` - Tool spec from description
- `core/tool_creation/code_generator/` - Code generation strategies
- `core/tool_creation/validator.py` - AST validation
- `core/tool_creation/sandbox_runner.py` - Isolated testing
- `core/pending_tools_manager.py` - Approval workflow
- `core/tool_registrar.py` - Dynamic registration
- `tools/capability_registry.py` - Runtime registry

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
- `tool_services.py` - Service injection (storage, LLM, HTTP, etc.)
- `secure_executor.py` - Safety validation

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

#### **Tool Creation**
- `tool_creation/flow.py` - Creation orchestrator
- `tool_creation/spec_generator.py` - Spec generation
- `tool_creation/code_generator/` - Code generation
- `tool_creation/validator.py` - Validation
- `tool_creation/sandbox_runner.py` - Testing

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
- `llm_client.py` - LLM integration (Ollama/Mistral/Qwen)
- `plan_parser.py` - Plan parsing
- `ollama_client.py` - Ollama fallback

### **Updater Layer** (`updater/`)
- `orchestrator.py` - Update orchestration
- `atomic_applier.py` - Safe file updates
- `risk_scorer.py` - Risk assessment
- `sandbox_runner.py` - Isolated testing
- `audit_logger.py` - Change tracking

### **UI Layer** (`ui/`)
- React frontend with real-time updates
- WebSocket connection for events
- Tool approval interface
- Log streaming

---

## Data Flow Patterns

### **Tool Execution**
```
Request → Orchestrator → Parameter Resolution → Tool.execute()
                ↓
        Service Injection (storage, LLM, HTTP)
                ↓
        Result Normalization → Response
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

### **Tool Creation**
```
Gap → Spec → Code → Validate → Sandbox
    ↓
Pending Queue → User Approval → Register
    ↓
Runtime Registry → Available for use
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
- Chat/task execution with tool orchestration
- Self-improvement loop (deterministic mode)
- Evolution mode with proposal generation
- Tool creation flow with approval workflow
- Hybrid improvement engine
- Real-time UI updates via WebSocket/SSE
- Conversation memory persistence
- LLM call logging
- Sandbox testing with retry

### ⚠️ **Partial**
- Tool creation orchestrator exists but registry/orchestrator injection may need verification
- Evolution mode tested but may need more real-world validation
- Hybrid engine integrated but custom prompt flow needs testing

### 🔧 **Architecture Notes**
- **Registry Chain**: Server creates registry → passed to tools → used by orchestrator
- **LLM Models**: Mistral for analysis, Qwen for code generation
- **Retry Strategy**: 3 attempts for code generation and sandbox testing
- **Event Bus**: Real-time updates to UI via WebSocket/SSE
- **Storage**: SQLite for memory, JSON for configuration

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

## Next Steps for Analysis

1. Verify registry/orchestrator injection in tool creation flow
2. Test evolution mode end-to-end
3. Validate hybrid engine with custom prompts
4. Check tool approval workflow completeness
5. Verify conversation memory integration
