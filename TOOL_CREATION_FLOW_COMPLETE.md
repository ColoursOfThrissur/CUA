# Complete Tool Creation Flow - All Files

## Flow Overview: UI → API → Core → Validation → Approval → Registration

---

## 1. USER INTERFACE LAYER

### Files to Check:
- `ui/src/components/ToolCreation.jsx` (or similar)
- `ui/src/api/toolsApi.js` (or similar)
- UI makes POST request to `/improvement/tools/create`

**Status:** NOT CHECKED YET

---

## 2. API LAYER

### `api/improvement_api.py`
**Endpoint:** `POST /improvement/tools/create`
**Line:** 442-520
**What it does:**
1. Receives description + optional tool_name from UI
2. Creates CapabilityGraph, ExpansionMode, ToolCreationOrchestrator
3. Calls `tool_creation.create_tool(description, llm_client, tool_name)`
4. If successful, validates tool contract
5. Adds to PendingToolsManager for approval
6. Returns pending_tool_id to UI

**Dependencies:**
- `core.tool_creation.flow.ToolCreationOrchestrator`
- `core.capability_graph.CapabilityGraph`
- `core.expansion_mode.ExpansionMode`
- `loop_instance.llm_client`
- `loop_instance.pending_tools_manager`

**Status:** ✅ CHECKED - Aligned with thin tool architecture

---

## 3. TOOL CREATION ORCHESTRATION

### `core/tool_creation/flow.py`
**Class:** `ToolCreationOrchestrator`
**Method:** `create_new_tool(gap_description, llm_client, preferred_tool_name)`
**Lines:** 28-95

**Flow Steps:**
1. Log capability gap
2. Call SpecGenerator.propose_tool_spec()
3. Call QwenCodeGenerator.generate() or DefaultCodeGenerator.generate()
4. Call ToolValidator.validate()
5. Call ExpansionMode.create_experimental_tool()
6. Call SandboxRunner.run_sandbox()
7. Return success/failure

**Dependencies:**
- `core.tool_creation.spec_generator.SpecGenerator`
- `core.tool_creation.code_generator.QwenCodeGenerator`
- `core.tool_creation.code_generator.DefaultCodeGenerator`
- `core.tool_creation.validator.ToolValidator`
- `core.tool_creation.sandbox_runner.SandboxRunner`
- `core.expansion_mode.ExpansionMode`

**Status:** ✅ CHECKED - Removed scaffolding, passes None as template

---

## 4. SPEC GENERATION

### `core/tool_creation/spec_generator.py`
**Class:** `SpecGenerator`
**Method:** `propose_tool_spec(gap_description, llm_client, preferred_tool_name)`
**Lines:** 16-115

**What it does:**
1. Builds prompt asking LLM for tool spec
2. Calls `llm_client._call_llm()` with expect_json=True
3. Extracts JSON from response
4. Normalizes tool name, inputs (operations), outputs, dependencies
5. Creates CapabilityNode
6. Returns spec dict with operations

**Output Format:**
```python
{
    'name': 'ToolName',
    'domain': 'Domain',
    'inputs': [
        {
            'operation': 'op_name',
            'parameters': [
                {'name': 'param', 'type': 'string', 'description': '...', 'required': True}
            ]
        }
    ],
    'outputs': [...],
    'dependencies': [...],
    'risk_level': 0.0,
    'node': CapabilityNode(...)
}
```

**Status:** ✅ CHECKED - Generates proper spec with operations

---

## 5. CODE GENERATION

### `core/tool_creation/code_generator/base.py`
**Class:** `BaseCodeGenerator` (ABC)
**Method:** `generate(template, tool_spec)` (abstract)

**Status:** ✅ CHECKED - Base interface

### `core/tool_creation/code_generator/qwen_generator.py`
**Class:** `QwenCodeGenerator`
**Method:** `generate(template, tool_spec)`
**Lines:** 17-49

**Multi-Stage Process:**

#### Stage 1: Skeleton Generation
**Method:** `_generate_stage1_skeleton()`
**Lines:** 51-125

**Sub-stages:**
- **1a:** `_generate_base_skeleton()` - Creates base class structure
  - Imports, class definition, __init__, empty register_capabilities, empty execute
  - ~30 lines of code
  
- **1b:** `_add_capability_to_skeleton()` - Adds each capability incrementally
  - For each operation: adds ToolCapability, execute branch, handler stub
  - ~20 lines per operation
  - Provides FULL current code + exact additions needed

#### Stage 2: Handler Implementation
**Method:** `_generate_stage2_handlers()`
**Lines:** 127-145

**Process:**
- Extracts handler names from skeleton
- For each handler, calls `_generate_single_handler()`
- Provides current stub, operation details, available services
- Implements logic using self.services
- ~20 lines per handler

**Key Methods:**
- `_extract_handler_names()` - Gets list of _handle_* methods
- `_generate_single_handler()` - Implements one handler
- `_extract_method()` - Gets current method code
- `_replace_method()` - Merges new implementation

**Status:** ✅ CHECKED - Multi-stage incremental generation with self-contained prompts

### `core/tool_creation/code_generator/default_generator.py`
**Class:** `DefaultCodeGenerator`
**Method:** `generate(template, tool_spec)`
**Lines:** 15-44

**What it does:**
- Single-shot generation for non-Qwen models
- Builds complete prompt with spec, contract, requirements
- Calls LLM with validation loop (3 attempts)
- Returns complete code

**Status:** ✅ CHECKED - Single-shot approach for standard LLMs

---

## 6. CODE VALIDATION

### `core/tool_creation/validator.py`
**Class:** `ToolValidator`
**Method:** `validate(code, tool_spec)`
**Lines:** 13-86

**Validation Checks:**
1. Parse AST (syntax check)
2. Find expected class
3. Check required methods exist (register_capabilities, execute)
4. Validate execute signature (operation, **kwargs or parameters)
5. Validate capabilities registration (add_capability with 2 args)
6. Validate Parameter and ToolCapability objects
7. Check __init__ accepts orchestrator parameter
8. No mutable default arguments
9. No ./ relative paths
10. No undefined helper methods
11. Required imports present
12. No isinstance with ParameterType enums

**Status:** ✅ CHECKED - Validates thin tool contracts

---

## 7. FILE CREATION

### `core/expansion_mode.py`
**Class:** `ExpansionMode`
**Method:** `create_experimental_tool(tool_name, code)`
**Lines:** 17-36

**What it does:**
1. Checks if expansion enabled
2. Checks if tool already exists
3. Writes code to `tools/experimental/{tool_name}.py`
4. Generates test file in `tests/experimental/test_{tool_name}.py`
5. Returns success/failure

**Test Template:**
- Creates basic test with orchestrator
- Tests tool instantiation
- Tests capability registration

**Status:** ✅ CHECKED - Updated for thin tool architecture

---

## 8. SANDBOX TESTING

### `core/tool_creation/sandbox_runner.py`
**Class:** `SandboxRunner`
**Method:** `run_sandbox(tool_name)`
**Lines:** 19-48

**Process:**
1. Load tool class from file
2. **Create ToolOrchestrator BEFORE chdir** (important for LLMLogger paths)
3. Create temp directory
4. Change to temp directory
5. Create data/ subdirectory
6. Instantiate tool with orchestrator
7. Run smoke tests on all capabilities
8. Restore original directory

**Method:** `_run_smoke_tests(tool_instance, orchestrator)`
**Lines:** 66-135

**What it tests:**
- Tool has capabilities
- Builds test parameters for each operation
- Executes each operation via orchestrator
- Checks for success
- Verifies persistence (if CRUD operations)

**Status:** ✅ CHECKED - Creates orchestrator before chdir, tests with services

---

## 9. ORCHESTRATOR & SERVICES

### `core/tool_orchestrator.py`
**Class:** `ToolOrchestrator`
**Method:** `get_services(tool_name)`
**Lines:** 34-42

**What it does:**
- Lazy-loads LLM client if not provided
- Creates ToolServices with storage_broker and llm_client
- Caches services per tool name

**Method:** `execute_tool_step(tool, tool_name, operation, parameters, context)`
**Lines:** 44-130

**What it does:**
- Resolves parameters
- Validates parameters
- Executes tool operation
- Wraps plain dict returns in ToolResult
- Handles exceptions

**Status:** ✅ CHECKED - Provides services to tools

### `core/tool_services.py`
**Class:** `ToolServices`

**Provides:**
- storage: save, get, list, update, delete
- llm: generate
- http: get, post, put, delete
- fs: read, write, list
- json: parse, stringify, query
- shell: execute
- ids: generate
- time: now_utc

**Status:** NOT CHECKED YET

---

## 10. LLM CLIENT & LOGGING

### `planner/llm_client.py`
**Class:** `LLMClient`
**Method:** `_call_llm(prompt, temperature, max_tokens, expect_json)`
**Lines:** 467-540

**What it does:**
- Calls Ollama API
- Logs interaction via LLMLogger
- Returns response or None

**Function:** `get_llm_client(registry)`
**Lines:** 18-23

**What it does:**
- Returns global LLM client instance
- Creates new instance if not exists

**Status:** ✅ CHECKED - Logs to LLMLogger

### `core/llm_logger.py`
**Class:** `LLMLogger`
**Method:** `__init__(log_dir, max_session_size_mb)`
**Lines:** 10-19

**What it does:**
- **Uses .resolve() to get absolute path** (fixed for sandbox)
- Creates log directory
- Creates session and error log files

**Status:** ✅ CHECKED - Uses absolute paths

---

## 11. PENDING TOOLS MANAGEMENT

### `core/pending_tools_manager.py`
**Class:** `PendingToolsManager`

**Methods to check:**
- `add_pending_tool(tool_data)` - Adds tool to pending queue
- `get_pending_list()` - Returns list for UI
- `get_tool(tool_id)` - Gets tool details
- `approve_tool(tool_id)` - Marks as approved
- `reject_tool(tool_id, reason)` - Removes tool
- `validate_tool_file_contract(tool_file)` - Validates tool file

**Status:** NOT CHECKED YET

---

## 12. TOOL REGISTRATION

### `api/pending_tools_api.py`
**Endpoint:** `POST /pending-tools/{tool_id}/approve`
**Lines:** 95-157

**Process:**
1. Get tool from PendingToolsManager
2. Validate tool file contract
3. Extract capabilities
4. Register tool via ToolRegistrar
5. Run post-registration contract check
6. Update tool registry
7. Return success

**Dependencies:**
- `PendingToolsManager`
- `ToolRegistrar`
- `ToolRegistryManager`
- `CapabilityExtractor`

**Status:** ✅ CHECKED - Approval flow

### Files to check:
- `core/tool_registrar.py` - ToolRegistrar class
- `core/tool_registry_manager.py` - ToolRegistryManager class
- `tools/capability_extractor.py` - CapabilityExtractor class

**Status:** NOT CHECKED YET

---

## 13. SUPPORTING FILES

### Files to check:
- `core/capability_graph.py` - CapabilityGraph class
- `core/storage_broker.py` - get_storage_broker function
- `core/parameter_resolution.py` - resolve_tool_parameters function
- `core/validation_service.py` - ValidationService class
- `tools/tool_interface.py` - BaseTool class
- `tools/tool_result.py` - ToolResult, ResultStatus
- `tools/tool_capability.py` - ToolCapability, Parameter, ParameterType, SafetyLevel

**Status:** NOT CHECKED YET

---

## SUMMARY OF WHAT'S BEEN CHECKED

✅ **API Layer:** improvement_api.py
✅ **Flow:** tool_creation/flow.py
✅ **Spec Generation:** tool_creation/spec_generator.py
✅ **Code Generation:** qwen_generator.py, default_generator.py, base.py
✅ **Validation:** tool_creation/validator.py
✅ **File Creation:** expansion_mode.py
✅ **Sandbox:** tool_creation/sandbox_runner.py
✅ **Orchestrator:** tool_orchestrator.py
✅ **LLM Client:** llm_client.py
✅ **LLM Logger:** llm_logger.py
✅ **Approval API:** pending_tools_api.py

## WHAT STILL NEEDS CHECKING

❌ **UI Layer:** React components
❌ **Tool Services:** tool_services.py and all service implementations
❌ **Pending Tools Manager:** pending_tools_manager.py
❌ **Tool Registrar:** tool_registrar.py
❌ **Registry Manager:** tool_registry_manager.py
❌ **Capability Extractor:** capability_extractor.py
❌ **Supporting Core Files:** capability_graph, storage_broker, parameter_resolution, validation_service
❌ **Tool Base Classes:** tool_interface, tool_result, tool_capability

---

## NEXT STEPS

1. Check all "NOT CHECKED YET" files
2. Verify they align with thin tool architecture
3. Update any that still use old patterns
4. Document complete flow with all file interactions
