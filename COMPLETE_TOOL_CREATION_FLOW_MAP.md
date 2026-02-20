# COMPLETE TOOL CREATION FLOW - ALL FILES MAPPED

## FLOW STAGES

### 1. UI LAYER (User Initiates)
- **ui/src/components/PendingToolsPanel.js** - Displays pending tools, approve/reject buttons
- **ui/src/App.js** - Main React app, handles API calls
- **ui/src/GlobalState.js** - Global state management
- **ui/src/config.js** - API endpoint configuration

### 2. API ENTRY POINT (HTTP Request)
- **api/server.py** - FastAPI server initialization, mounts all routers
- **api/improvement_api.py** - POST `/improvement/tools/create` endpoint - CREATES TOOL
- **api/pending_tools_api.py** - POST `/pending-tools/{tool_id}/approve` - APPROVES TOOL

### 3. TOOL CREATION ORCHESTRATION
- **core/tool_creation/flow.py** - ToolCreationOrchestrator - main orchestrator
- **core/tool_creation/spec_generator.py** - SpecGenerator - generates tool spec from description
- **core/tool_creation/code_generator/** - Code generation strategies
  - **qwen_generator.py** - Multi-stage LLM generation for Qwen
  - **default_generator.py** - Single-shot generation for other models
- **core/tool_creation/validator.py** - AST-based validation of generated code
- **core/tool_creation/sandbox_runner.py** - Sandbox testing of generated tool

### 4. CAPABILITY & GRAPH MANAGEMENT
- **core/capability_graph.py** - CapabilityGraph - validates tool registration
- **core/capability_mapper.py** - CapabilityMapper - builds capability graph from existing tools
- **core/gap_detector.py** - GapDetector - detects missing capabilities
- **core/gap_tracker.py** - GapTracker - tracks capability gaps

### 5. EXPANSION MODE (Tool File Creation)
- **core/expansion_mode.py** - ExpansionMode - creates experimental tool files
- **core/tool_scaffolder.py** - ToolScaffolder - OLD template system (unused by new flow)

### 6. PENDING TOOLS MANAGEMENT
- **core/pending_tools_manager.py** - PendingToolsManager - manages pending queue
  - `add_pending_tool()` - Adds tool to pending queue
  - `validate_tool_metadata()` - Validates metadata contract
  - `validate_tool_file_contract()` - Validates tool file contract (AST checks)
  - `approve_tool()` - Marks tool as approved
  - `reject_tool()` - Rejects and deletes tool files

### 7. TOOL REGISTRATION (Approval Flow)
- **core/tool_registrar.py** - ToolRegistrar - dynamically registers tools
  - `register_new_tool()` - Imports module, instantiates tool, registers with registry
  - `_resolve_tool_class()` - Finds BaseTool subclass in module
- **tools/capability_registry.py** - CapabilityRegistry - central capability registry
  - `register_tool()` - Registers tool and capabilities
  - `unregister_tool()` - Removes tool and capabilities
- **core/tool_registry_manager.py** - ToolRegistryManager - manages tool_registry.json
- **tools/capability_extractor.py** - CapabilityExtractor - extracts capabilities from tool files (AST)

### 8. TOOL ORCHESTRATION (Runtime)
- **core/tool_orchestrator.py** - ToolOrchestrator - executes tool operations
- **core/tool_services.py** - ToolServices - provides services to tools
  - StorageService - data persistence
  - TimeService - timestamps
  - IdService - ID generation
  - LLMService, HTTPService, FileSystemService, JSONService, ShellService

### 9. SERVICE LAYER
- **core/services/llm_service.py** - LLMService - LLM operations
- **core/services/http_service.py** - HTTPService - HTTP requests
- **core/services/filesystem_service.py** - FileSystemService - file operations
- **core/services/json_service.py** - JSONService - JSON operations
- **core/services/shell_service.py** - ShellService - shell commands

### 10. LLM CLIENT
- **planner/llm_client.py** - LLMClient - calls LLM API
  - `_call_llm()` - Makes LLM API call
  - `_extract_json()` - Extracts JSON from response
  - `get_llm_client()` - Returns global instance

### 11. TOOL BASE CLASSES
- **tools/tool_interface.py** - BaseTool - base class for all tools
- **tools/tool_capability.py** - ToolCapability, Parameter, SafetyLevel
- **tools/tool_result.py** - ToolResult, ResultStatus

### 12. STORAGE & PERSISTENCE
- **core/storage_broker.py** - StorageBroker - file system abstraction
- **data/pending_tools.json** - Pending tools storage
- **data/tool_registry.json** - Tool registry storage

### 13. VALIDATION & SAFETY
- **core/immutable_brain_stem.py** - BrainStem - safety validation
- **core/validation_service.py** - ValidationService
- **core/ast_validator.py** - AST validation
- **core/behavior_validator.py** - Behavior validation

### 14. LOGGING & MONITORING
- **core/llm_logger.py** - LLMLogger - logs LLM calls
- **core/logging_system.py** - Logging system
- **logs/llm/** - LLM session logs

### 15. LEGACY/UNUSED FILES (Still in codebase)
- **core/tool_creation_flow.py** - OLD wrapper that delegates to new flow
- **core/tool_generation_orchestrator.py** - OLD orchestrator
- **core/tool_generation_context.py** - OLD context
- **core/tool_scaffolder.py** - OLD template system

## ERROR-PRONE AREAS

### Contract Validation Failures
- **pending_tools_manager.py** lines 60-200 - validate_tool_file_contract()
  - AST parsing errors
  - Missing execute() method
  - Missing register_capabilities()
  - Missing add_capability() calls
  - Undefined helper method calls
  - isinstance(ParameterType.X) usage
  - Storage path mismatches
  - Missing directory creation

### Capability Extraction Failures
- **capability_extractor.py** lines 20-300 - extract_from_file()
  - No class definition found
  - Missing register_capabilities()
  - No ToolCapability definitions
  - Handler validation failures

### Registration Failures
- **tool_registrar.py** lines 20-100 - register_new_tool()
  - Module import errors
  - No BaseTool subclass found
  - Tool instantiation errors (orchestrator/registry injection)
  - Capability registration errors

### Post-Registration Validation Failures
- **pending_tools_api.py** lines 40-80 - _post_register_contract_check()
  - execute() signature validation
  - get_capabilities() failures
  - Required parameters with defaults
  - Missing capability handlers

### Code Generation Failures
- **qwen_generator.py** - Multi-stage generation
  - Stage 1a: Base skeleton generation
  - Stage 1b: Capability addition (incremental)
  - Stage 2: Handler implementation (one-by-one)
  - Syntax errors, incomplete code, missing imports

### Sandbox Testing Failures
- **sandbox_runner.py** - Sandbox execution
  - Orchestrator creation timing (must be BEFORE chdir)
  - LLMLogger path resolution
  - Tool instantiation errors
  - Smoke test failures

## COMPLETE EXECUTION FLOW

1. User clicks "Create Tool" in UI → **PendingToolsPanel.js**
2. POST request to `/improvement/tools/create` → **improvement_api.py**
3. Creates CapabilityGraph, ExpansionMode, ToolCreationOrchestrator → **flow.py**
4. Generates spec from description → **spec_generator.py** → **llm_client.py**
5. Generates code (multi-stage for Qwen) → **qwen_generator.py** → **llm_client.py**
6. Validates generated code (AST) → **validator.py**
7. Creates tool file in tools/experimental/ → **expansion_mode.py**
8. Runs sandbox tests → **sandbox_runner.py** → **tool_orchestrator.py**
9. Validates tool file contract → **pending_tools_manager.py** validate_tool_file_contract()
10. Adds to pending queue → **pending_tools_manager.py** add_pending_tool()
11. Saves to data/pending_tools.json → **storage_broker.py**
12. Returns pending_tool_id to UI → **improvement_api.py**
13. UI displays in pending tools panel → **PendingToolsPanel.js**

14. User clicks "Approve" → **PendingToolsPanel.js**
15. POST request to `/pending-tools/{tool_id}/approve` → **pending_tools_api.py**
16. Gets tool metadata → **pending_tools_manager.py** get_tool()
17. Validates tool file contract AGAIN → **pending_tools_manager.py** validate_tool_file_contract()
18. Extracts capabilities → **capability_extractor.py** extract_from_file()
19. Registers tool dynamically → **tool_registrar.py** register_new_tool()
20. Imports module → Python importlib
21. Resolves tool class → **tool_registrar.py** _resolve_tool_class()
22. Instantiates tool with orchestrator → **tool_interface.py** BaseTool.__init__()
23. Registers with capability registry → **capability_registry.py** register_tool()
24. Runs post-registration checks → **pending_tools_api.py** _post_register_contract_check()
25. Marks as approved → **pending_tools_manager.py** approve_tool()
26. Updates tool registry JSON → **tool_registry_manager.py** update_tool()
27. Returns success to UI → **pending_tools_api.py**
28. UI removes from pending panel → **PendingToolsPanel.js**

## FILES NOT YET CHECKED FOR ERRORS

- **api/server.py** - Server initialization, router mounting
- **core/evolution_bridge.py** - Evolution mode bridge
- **core/improvement_loop.py** - Main improvement loop
- **core/hybrid_improvement_engine.py** - Hybrid engine
- **core/storage_broker.py** - Storage abstraction
- **core/immutable_brain_stem.py** - Safety validation
- **planner/ollama_client.py** - Ollama client fallback
- **updater/** - All updater files
- **ui/src/App.js** - Main React app
- **ui/src/GlobalState.js** - State management

## CRITICAL INTEGRATION POINTS

1. **improvement_api.py** ↔ **flow.py** - Tool creation initiation
2. **flow.py** ↔ **qwen_generator.py** - Code generation
3. **flow.py** ↔ **sandbox_runner.py** - Sandbox testing
4. **flow.py** ↔ **pending_tools_manager.py** - Pending queue
5. **pending_tools_api.py** ↔ **tool_registrar.py** - Tool registration
6. **tool_registrar.py** ↔ **capability_registry.py** - Capability registration
7. **tool_registrar.py** ↔ **capability_extractor.py** - Capability extraction
8. **sandbox_runner.py** ↔ **tool_orchestrator.py** - Tool execution
9. **tool_orchestrator.py** ↔ **tool_services.py** - Service injection
10. **All generators** ↔ **llm_client.py** - LLM calls

## NEXT STEPS

1. Read and verify **api/server.py** - understand initialization
2. Read and verify **core/storage_broker.py** - understand storage
3. Read and verify **core/immutable_brain_stem.py** - understand safety
4. Read and verify **ui/src/App.js** - understand UI flow
5. Read and verify **planner/ollama_client.py** - understand LLM fallback
6. Trace actual error logs to find failure points
7. Test each integration point individually
