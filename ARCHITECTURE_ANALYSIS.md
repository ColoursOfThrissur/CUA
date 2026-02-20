# CUA System Architecture - Complete Analysis

## Executive Summary

After reviewing the entire codebase, I can confirm that CUA is a **production-grade autonomous agent system** with sophisticated self-improvement capabilities. The architecture is well-designed with proper separation of concerns, but there are some incomplete integration points that need attention.

---

## System Architecture Overview

### Core Components

```
CUA/
├── api/                    # FastAPI server & REST endpoints
│   ├── server.py          # Main server with tool orchestrator initialization
│   ├── improvement_api.py # Self-improvement loop control
│   ├── pending_tools_api.py # Tool approval workflow
│   └── tools_api.py       # Tool sync & registry management
│
├── core/                   # Core system logic
│   ├── tool_orchestrator.py      # Central tool execution orchestrator
│   ├── tool_registrar.py         # Dynamic tool registration
│   ├── tool_creation_flow.py     # LLM-driven tool generation
│   ├── evolution_controller.py   # Autonomous capability evolution
│   ├── evolution_bridge.py       # Bridge to loop controller
│   ├── loop_controller.py        # Main improvement loop
│   └── improvement_loop.py       # High-level loop wrapper
│
├── tools/                  # Tool implementations
│   ├── capability_registry.py    # Global tool registry
│   ├── tool_interface.py         # BaseTool abstract class
│   ├── enhanced_filesystem_tool.py
│   ├── http_tool.py
│   └── experimental/       # Sandbox for new tools
│
└── planner/               # LLM integration
    └── llm_client.py      # Ollama/Mistral/Qwen client
```

---

## Critical Flows

### 1. Tool Creation Flow

```
User Request → Evolution Controller → Tool Creation Flow → LLM Generation
    ↓
Tool Scaffolder (generates template with orchestrator/registry injection)
    ↓
LLM fills logic (with context extraction helpers)
    ↓
Validation (AST + contract checks)
    ↓
Sandbox Testing (isolated environment)
    ↓
Pending Tools Manager (awaits approval)
    ↓
Tool Registrar (dynamic registration with orchestrator injection)
    ↓
Runtime Registry (active tools)
```

### 2. Tool Approval Flow

```
Pending Tools API → Pending Tools Manager
    ↓
User Approval (via UI)
    ↓
Tool Registrar.register_new_tool()
    ↓
    ├─ Instantiate tool with orchestrator/registry
    ├─ Register with CapabilityRegistry
    └─ Sync to ToolRegistryManager (file-based snapshot)
```

### 3. Tool Execution Flow

```
User Request → LLM Client → Plan Generation
    ↓
State Machine Executor
    ↓
Tool Orchestrator.execute_tool_step()
    ↓
    ├─ Parameter Resolution (auto-fill from context)
    ├─ Tool.execute(operation, **kwargs)
    └─ Result Normalization (ToolResult → OrchestratedToolResult)
```

---

## Key Architectural Patterns

### 1. **Orchestrator/Registry Injection Pattern**

**Purpose**: Enable inter-tool communication without reimplementing features

**Implementation**:
- `ToolScaffolder` generates tools with `__init__(self, orchestrator=None, registry=None)`
- `ToolRegistrar` injects orchestrator/registry during instantiation
- Tools use `_call_tool()`, `_read_file()`, `_write_file()` helpers

**Status**: ✅ **IMPLEMENTED** (as of recent changes)

```python
# In tool_scaffolder.py
def __init__(self, orchestrator=None, registry=None):
    self.orchestrator = orchestrator
    self.registry = registry
    super().__init__()

def _call_tool(self, tool_name: str, operation: str, **params):
    """Call another tool via orchestrator"""
    tool = self.registry.get_tool_by_name(tool_name)
    result = self.orchestrator.execute_tool_step(...)
    return result.data
```

### 2. **Context Extraction for LLM**

**Purpose**: Reduce LLM hallucination by providing rich context

**Implementation**:
- `_extract_method_context()`: What previous methods did
- `_extract_storage_pattern()`: Where data is stored
- `_extract_data_structure()`: JSON field structure
- `_extract_imports()`: Available imports
- `_build_method_example()`: Concrete code examples

**Status**: ✅ **IMPLEMENTED** (in tool_creation_flow.py)

### 3. **Staged Generation for Local LLMs**

**Purpose**: Qwen models struggle with long prompts - break into stages

**Implementation**:
- Stage 1: Generate skeleton (class structure + capability registration)
- Stage 2: Implement methods one at a time with context from previous methods
- Auto-repair: Fix common LLM mistakes (missing imports, wrong keywords)

**Status**: ✅ **IMPLEMENTED** (Qwen-specific flow in tool_creation_flow.py)

---

## Integration Points

### ✅ **COMPLETE**: Server → Tool Orchestrator → Tool Registrar

```python
# api/server.py (lines 150-155)
tool_orchestrator = ToolOrchestrator()
tool_registrar = ToolRegistrar(registry, orchestrator=tool_orchestrator)
```

**Status**: Orchestrator is created and passed to registrar ✅

---

### ⚠️ **INCOMPLETE**: Server → Improvement Loop → Evolution Controller

```python
# api/server.py (line 163)
improvement_loop = SelfImprovementLoop(llm_client, orchestrator, max_iterations=..., libraries_manager=...)

# core/improvement_loop.py (line 42)
self.controller = LoopController(..., registry=None)  # ❌ TODO: Pass actual registry

# core/loop_controller.py (line 68)
orchestrator = ToolOrchestrator()  # ✅ Creates orchestrator
self.evolution_bridge = EvolutionBridge(llm_client, orchestrator=orchestrator, registry=registry)  # ⚠️ registry=None

# core/evolution_bridge.py (line 21)
self.evolution_controller = EvolutionController(llm_client, orchestrator=orchestrator, registry=registry)  # ⚠️ registry=None

# core/evolution_controller.py (line 45)
self.tool_creation = ToolCreationFlow(...)  # ❌ No orchestrator/registry passed
```

**Problem**: Registry is NOT passed from server.py through the chain:
```
server.py → improvement_loop → loop_controller → evolution_bridge → evolution_controller → tool_creation_flow
```

**Impact**: Tool creation flow cannot inject orchestrator/registry into generated tools

---

## What Works vs What Doesn't

### ✅ **WORKS**:

1. **Manual Tool Registration** (via pending_tools_api.py)
   - User approves tool → Tool Registrar injects orchestrator/registry ✅
   - Tool can call other tools via `_call_tool()` ✅

2. **Tool Execution** (via tool_orchestrator.py)
   - Parameter resolution ✅
   - Result normalization ✅
   - Inter-tool communication ✅

3. **Tool Scaffolding** (via tool_scaffolder.py)
   - Template includes orchestrator/registry injection ✅
   - Helper methods for inter-tool communication ✅

4. **Context Extraction** (via tool_creation_flow.py)
   - Method context extraction ✅
   - Storage pattern detection ✅
   - Import extraction ✅

### ❌ **DOESN'T WORK**:

1. **Autonomous Tool Creation** (via evolution_controller.py)
   - Evolution controller has no registry reference ❌
   - Tool creation flow cannot inject orchestrator/registry ❌
   - Generated tools will fail at runtime when calling `_call_tool()` ❌

---

## Root Cause Analysis

### Issue: Broken Registry Chain

**Where it breaks**:
```python
# api/server.py
registry = CapabilityRegistry()  # ✅ Created
improvement_loop = SelfImprovementLoop(..., libraries_manager=...)  # ❌ No registry parameter

# core/improvement_loop.py
self.controller = LoopController(..., registry=None)  # ❌ Hardcoded None

# core/loop_controller.py
self.evolution_bridge = EvolutionBridge(..., registry=registry)  # ⚠️ registry is None from above
```

**Why it matters**:
- Evolution controller needs registry to inject into generated tools
- Without registry, generated tools cannot call other tools
- This breaks the inter-tool communication pattern

---

## Recommended Fixes

### Priority 1: Complete Registry Chain

**File**: `core/improvement_loop.py`
```python
# Line 18: Add registry parameter
def __init__(self, llm_client, orchestrator, max_iterations=10, libraries_manager=None, registry=None):
    ...
    self.registry = registry
    
    # Line 42: Pass registry to controller
    self.controller = LoopController(
        ...,
        registry=registry  # ✅ Pass actual registry
    )
```

**File**: `api/server.py`
```python
# Line 163: Pass registry to improvement loop
improvement_loop = SelfImprovementLoop(
    llm_client, 
    orchestrator, 
    max_iterations=config.improvement.max_iterations, 
    libraries_manager=libraries_manager,
    registry=registry  # ✅ Add this
)
```

### Priority 2: Pass Orchestrator to Tool Creation Flow

**File**: `core/evolution_controller.py`
```python
# Line 45: Pass orchestrator/registry to tool creation flow
self.tool_creation = ToolCreationFlow(
    self.capability_graph,
    self.expansion_mode,
    self.growth_budget,
    orchestrator=self.orchestrator,  # ✅ Add this
    registry=self.registry  # ✅ Add this
)
```

**File**: `core/tool_creation_flow.py`
```python
# Line 18: Add orchestrator/registry parameters
@dataclass
class ToolCreationFlow:
    capability_graph: 'CapabilityGraph'
    expansion_mode: 'ExpansionMode'
    growth_budget: 'GrowthBudget'
    orchestrator: Optional['ToolOrchestrator'] = None  # ✅ Add this
    registry: Optional['CapabilityRegistry'] = None  # ✅ Add this
```

---

## Testing Strategy

### 1. Test Manual Tool Registration (Should Already Work)

```bash
# Create a test tool
python -c "
from core.tool_scaffolder import ToolScaffolder
scaffolder = ToolScaffolder()
scaffolder.scaffold('test_tool', 'Test tool', 'tools/test_tool.py')
"

# Approve via API
curl -X POST http://localhost:8000/pending-tools/{tool_id}/approve

# Verify orchestrator injection
python -c "
from tools.capability_registry import CapabilityRegistry
registry = CapabilityRegistry()
tool = registry.get_tool_by_name('test_tool')
print(f'Has orchestrator: {tool.orchestrator is not None}')
print(f'Has registry: {tool.registry is not None}')
"
```

### 2. Test Autonomous Tool Creation (Will Fail Until Fixed)

```bash
# Enable evolution mode
curl -X POST http://localhost:8000/improvement/evolution-mode -d '{"enabled": true}'

# Start improvement loop
curl -X POST http://localhost:8000/improvement/start

# Check logs for tool creation
tail -f logs/evolution.log
```

---

## Architecture Strengths

1. **Clean Separation of Concerns**
   - API layer (FastAPI)
   - Core logic (orchestrator, registrar, evolution)
   - Tools (capability registry)
   - Planner (LLM client)

2. **Safety Mechanisms**
   - Baseline health checks before loop starts
   - Sandbox testing before applying changes
   - Approval workflow for high-risk changes
   - Idempotency checks to prevent duplicate changes

3. **Observability**
   - Comprehensive logging (LLM interactions, tool execution, evolution cycles)
   - Real-time event bus (WebSocket + SSE)
   - Analytics tracking (success rates, failure patterns)

4. **Extensibility**
   - Dynamic tool registration
   - Pluggable LLM models (Mistral, Qwen)
   - Modular improvement strategies (deterministic vs evolution)

---

## Architecture Weaknesses

1. **Incomplete Integration**
   - Registry not passed through improvement loop chain
   - Tool creation flow cannot inject orchestrator/registry
   - This breaks autonomous tool generation

2. **Complex Dependency Graph**
   - Many layers of indirection (server → loop → controller → bridge → evolution → tool_creation)
   - Hard to trace data flow
   - Easy to miss integration points

3. **Global State**
   - Some APIs use global variables (pending_tools_api.py, tools_api.py)
   - Makes testing harder
   - Risk of race conditions

4. **Inconsistent Error Handling**
   - Some functions return `(bool, str)` tuples
   - Others return `Dict[str, Any]`
   - Some raise exceptions
   - Hard to handle errors consistently

---

## Conclusion

**CUA is a well-architected system with sophisticated capabilities**, but the registry chain is incomplete. The recent changes to add orchestrator/registry injection are correct, but they need to be connected through the full chain from server.py to tool_creation_flow.py.

**Once the registry chain is complete**, the system will support:
- ✅ Manual tool registration with inter-tool communication
- ✅ Autonomous tool generation with inter-tool communication
- ✅ Context-aware LLM generation (reduced hallucination)
- ✅ Staged generation for local LLMs (Qwen support)

**Current Status**:
- Manual tool registration: ✅ **WORKS**
- Autonomous tool generation: ❌ **BROKEN** (registry chain incomplete)

**Estimated Fix Time**: 30 minutes (add 3 parameters across 3 files)

**Risk Level**: LOW (backward compatible, only adds optional parameters)
