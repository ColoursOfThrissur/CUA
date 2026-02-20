# CUA System Flow Diagrams

## 1. Complete System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI Server                          │
│                        (api/server.py)                          │
└────────────┬────────────────────────────────────────────────────┘
             │
             ├─── Creates ───┐
             │                │
             ▼                ▼
    ┌────────────────┐  ┌──────────────────┐
    │ CapabilityReg  │  │ ToolOrchestrator │
    │   (registry)   │  │  (orchestrator)  │
    └────────┬───────┘  └────────┬─────────┘
             │                   │
             │                   │
             ▼                   ▼
    ┌────────────────────────────────────┐
    │        ToolRegistrar               │
    │  (orchestrator + registry)         │
    └────────────────────────────────────┘
             │
             │ Used by
             ▼
    ┌────────────────────────────────────┐
    │    Pending Tools API               │
    │  (manual tool approval)            │
    └────────────────────────────────────┘
```

## 2. Tool Creation Flow (Manual Approval) ✅ WORKS

```
User Approves Tool
       │
       ▼
┌──────────────────────┐
│ Pending Tools API    │
│ (approve_tool)       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ ToolRegistrar.register_new_tool()    │
│                                      │
│ 1. Import tool module                │
│ 2. Instantiate with orchestrator +  │
│    registry injection                │
│ 3. Register with CapabilityRegistry  │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ Generated Tool Instance              │
│                                      │
│ ✅ self.orchestrator = orchestrator  │
│ ✅ self.registry = registry          │
│                                      │
│ Can call:                            │
│ - self._call_tool()                  │
│ - self._read_file()                  │
│ - self._write_file()                 │
└──────────────────────────────────────┘
```

## 3. Autonomous Tool Creation Flow ❌ BROKEN

```
Evolution Controller
       │
       ▼
┌──────────────────────────────────────┐
│ ToolCreationFlow.create_new_tool()   │
│                                      │
│ ❌ No orchestrator reference         │
│ ❌ No registry reference             │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ ToolScaffolder.scaffold()            │
│                                      │
│ Generates template with:             │
│ ✅ __init__(orchestrator, registry)  │
│ ✅ _call_tool() helper               │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ LLM fills logic                      │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ ExpansionMode.create_experimental()  │
│                                      │
│ Writes to tools/experimental/        │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ Pending Tools Manager                │
│                                      │
│ Awaits user approval                 │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ ToolRegistrar.register_new_tool()    │
│                                      │
│ ✅ Injects orchestrator + registry   │
└──────────────────────────────────────┘
```

## 4. The Broken Registry Chain ❌

```
api/server.py
    │
    │ registry = CapabilityRegistry()  ✅ Created
    │ improvement_loop = SelfImprovementLoop(...) ❌ No registry param
    │
    ▼
core/improvement_loop.py
    │
    │ self.controller = LoopController(..., registry=None) ❌ Hardcoded None
    │
    ▼
core/loop_controller.py
    │
    │ orchestrator = ToolOrchestrator()  ✅ Created
    │ self.evolution_bridge = EvolutionBridge(..., registry=registry) ⚠️ registry=None
    │
    ▼
core/evolution_bridge.py
    │
    │ self.evolution_controller = EvolutionController(..., registry=registry) ⚠️ registry=None
    │
    ▼
core/evolution_controller.py
    │
    │ self.tool_creation = ToolCreationFlow(...) ❌ No orchestrator/registry
    │
    ▼
core/tool_creation_flow.py
    │
    │ ❌ Cannot inject orchestrator/registry into generated tools
    │
    ▼
Generated Tool
    │
    │ ❌ self.orchestrator = None
    │ ❌ self.registry = None
    │
    ▼
Runtime Error when calling _call_tool()
```

## 5. The Fixed Registry Chain ✅

```
api/server.py
    │
    │ registry = CapabilityRegistry()  ✅
    │ improvement_loop = SelfImprovementLoop(..., registry=registry) ✅ ADD THIS
    │
    ▼
core/improvement_loop.py
    │
    │ self.registry = registry  ✅ ADD THIS
    │ self.controller = LoopController(..., registry=registry) ✅ FIX THIS
    │
    ▼
core/loop_controller.py
    │
    │ orchestrator = ToolOrchestrator()  ✅
    │ self.evolution_bridge = EvolutionBridge(..., registry=registry) ✅ Now has registry
    │
    ▼
core/evolution_bridge.py
    │
    │ self.evolution_controller = EvolutionController(..., registry=registry) ✅ Now has registry
    │
    ▼
core/evolution_controller.py
    │
    │ self.tool_creation = ToolCreationFlow(..., orchestrator=self.orchestrator, registry=self.registry) ✅ ADD THIS
    │
    ▼
core/tool_creation_flow.py
    │
    │ self.orchestrator = orchestrator  ✅ ADD THIS
    │ self.registry = registry  ✅ ADD THIS
    │
    ▼
ToolScaffolder.scaffold()
    │
    │ Can now pass orchestrator/registry to generated tools ✅
    │
    ▼
Generated Tool
    │
    │ ✅ self.orchestrator = orchestrator
    │ ✅ self.registry = registry
    │
    ▼
Can call _call_tool() successfully ✅
```

## 6. Tool Execution Flow (Runtime)

```
User Request
    │
    ▼
LLM Client (generate_plan)
    │
    ▼
State Machine Executor
    │
    ▼
┌──────────────────────────────────────────────────┐
│ ToolOrchestrator.execute_tool_step()             │
│                                                  │
│ 1. resolve_tool_parameters()                    │
│    - Auto-fill from context                     │
│    - Validate required params                   │
│                                                  │
│ 2. tool.execute(operation, **params)            │
│    - Compatibility layer for different sigs     │
│                                                  │
│ 3. _normalize_result()                          │
│    - ToolResult → OrchestratedToolResult        │
│    - Extract artifacts (file refs)              │
└──────────────────────────────────────────────────┘
    │
    ▼
OrchestratedToolResult
    │
    ├─ success: bool
    ├─ data: Any
    ├─ error: Optional[str]
    ├─ resolved_parameters: Dict
    ├─ missing_required: List[str]
    ├─ artifacts: List[Dict]
    └─ meta: Dict
```

## 7. Inter-Tool Communication Pattern

```
Tool A wants to read a file
    │
    ▼
┌──────────────────────────────────────┐
│ Tool A._read_file(path)              │
│                                      │
│ Calls: self._call_tool(              │
│   "FilesystemTool",                  │
│   "read_file",                       │
│   path=path                          │
│ )                                    │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ Tool A._call_tool()                  │
│                                      │
│ 1. Get tool from registry            │
│    tool = self.registry.get_tool()   │
│                                      │
│ 2. Execute via orchestrator          │
│    result = self.orchestrator        │
│      .execute_tool_step(...)         │
│                                      │
│ 3. Return data                       │
│    return result.data                │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ FilesystemTool.execute()             │
│                                      │
│ Reads file and returns ToolResult    │
└──────────┬───────────────────────────┘
           │
           ▼
File content returned to Tool A
```

## 8. Context Extraction for LLM (Reduces Hallucination)

```
LLM generates method _handle_get()
    │
    ▼
┌──────────────────────────────────────────────────┐
│ ToolCreationFlow._generate_qwen_method_step()   │
│                                                  │
│ 1. Extract context from previous methods:       │
│    - _extract_method_context()                  │
│      → "create writes to: data/contacts/..."    │
│      → "create JSON fields: id, name, email"    │
│                                                  │
│ 2. Extract storage pattern:                     │
│    - _extract_storage_pattern()                 │
│      → "self.storage_dir = 'data/contacts'"     │
│                                                  │
│ 3. Extract data structure:                      │
│    - _extract_data_structure()                  │
│      → "JSON fields: id, name, email, ..."      │
│                                                  │
│ 4. Extract imports:                             │
│    - _extract_imports()                         │
│      → "json, Path, datetime available"         │
│                                                  │
│ 5. Build concrete example:                      │
│    - _build_method_example()                    │
│      → Full working code for _handle_get()      │
└──────────────────────────────────────────────────┘
    │
    ▼
LLM receives rich context
    │
    ▼
Generates correct code (no hallucination)
```

## 9. Staged Generation for Qwen (Local LLM)

```
Stage 1: Generate Skeleton
    │
    ▼
┌──────────────────────────────────────┐
│ _build_deterministic_stage1_scaffold │
│                                      │
│ Generates:                           │
│ - Class structure                    │
│ - __init__()                         │
│ - register_capabilities()            │
│ - execute() dispatch                 │
│ - Handler stubs                      │
└──────────┬───────────────────────────┘
           │
           ▼
Stage 2: Implement Methods One-by-One
    │
    ▼
┌──────────────────────────────────────┐
│ _generate_qwen_method_step()         │
│                                      │
│ For each method:                     │
│ 1. Extract context from skeleton    │
│ 2. Generate ONLY that method         │
│ 3. Merge into skeleton               │
│ 4. Validate                          │
│ 5. Move to next method               │
└──────────┬───────────────────────────┘
           │
           ▼
Complete Tool Implementation
```

## 10. Safety Mechanisms

```
Evolution Cycle Start
    │
    ▼
┌──────────────────────────────────────┐
│ Baseline Health Check                │
│                                      │
│ - All tests pass?                    │
│ - No syntax errors?                  │
│ - No import errors?                  │
└──────────┬───────────────────────────┘
           │ ✅ Pass
           ▼
┌──────────────────────────────────────┐
│ Self-Reflection                      │
│                                      │
│ - Analyze system for improvements    │
│ - Detect duplication                 │
│ - Find long methods                  │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ LLM Proposes Evolution               │
│                                      │
│ - Generate proposal                  │
│ - Estimate risk                      │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ Controller Validates                 │
│                                      │
│ - Check growth budget                │
│ - Validate constraints               │
│ - Check file cooldown                │
└──────────┬───────────────────────────┘
           │ ✅ Approved
           ▼
┌──────────────────────────────────────┐
│ Generate Code                        │
│                                      │
│ - LLM fills logic                    │
│ - Validate syntax                    │
│ - Check contracts                    │
└──────────┬───────────────────────────┘
           │ ✅ Valid
           ▼
┌──────────────────────────────────────┐
│ Sandbox Testing                      │
│                                      │
│ - Run in isolated environment        │
│ - Execute all tests                  │
│ - Validate behavior                  │
└──────────┬───────────────────────────┘
           │ ✅ Pass
           ▼
┌──────────────────────────────────────┐
│ Apply Changes                        │
│                                      │
│ - Create backup                      │
│ - Write file                         │
│ - Verify syntax                      │
│ - Record change                      │
└──────────────────────────────────────┘
```

## Summary

**Key Insight**: The system is well-designed with proper separation of concerns, but the registry chain is incomplete. Once fixed, autonomous tool generation will work correctly with inter-tool communication.

**Fix Required**: Add 3 parameters across 3 files to complete the registry chain.

**Risk**: LOW (backward compatible, only adds optional parameters)

**Estimated Time**: 30 minutes
