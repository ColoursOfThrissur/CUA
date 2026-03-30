# Tool Creation Flow - Complete Guide

## Overview
Forge's tool creation system generates different types of tools from capability gap descriptions using a multi-stage LLM pipeline with comprehensive validation.

## Flow Architecture

```
User Request → Evolution Controller → Tool Creation Orchestrator
                                              ↓
                                    ┌─────────┴─────────┐
                                    │  Spec Generator   │
                                    │  (LLM analyzes)   │
                                    └─────────┬─────────┘
                                              ↓
                                    ┌─────────┴─────────┐
                                    │  Code Generator   │
                                    │  (Qwen/Default)   │
                                    └─────────┬─────────┘
                                              ↓
                                    ┌─────────┴─────────┐
                                    │    Validator      │
                                    │  (AST checks)     │
                                    └─────────┬─────────┘
                                              ↓
                                    ┌─────────┴─────────┐
                                    │ Expansion Mode    │
                                    │ (Write to disk)   │
                                    └─────────┬─────────┘
                                              ↓
                                    ┌─────────┴─────────┐
                                    │ Sandbox Runner    │
                                    │ (Runtime tests)   │
                                    └─────────┬─────────┘
                                              ↓
                                    ┌─────────┴─────────┐
                                    │ Registry/Deploy   │
                                    └───────────────────┘
```

## Stage-by-Stage Breakdown

### 1. Evolution Controller (Entry Point)
**File**: `core/evolution_controller.py`

**What it does**:
- Receives capability gap from self-reflection system
- Validates baseline health before proceeding
- Routes to tool creation orchestrator for NEW_TOOL proposals
- Tracks creation history to avoid duplicates

**Input**: Gap description like "Need ability to manage local notes"
**Output**: Triggers tool creation flow

---

### 2. Tool Creation Orchestrator
**File**: `core/tool_creation/flow.py`

**What it does**:
- Coordinates entire creation pipeline
- Selects appropriate code generator (Qwen vs Default)
- Handles cleanup on failure
- Manages experimental namespace

**Key Decision**: Detects if LLM is Qwen model → uses multi-stage generation

---

### 3. Spec Generator (LLM Stage 1)
**File**: `core/tool_creation/spec_generator.py`

**What it does**:
- LLM analyzes gap description
- Generates tool specification with:
  - Tool name (normalized to Python identifier)
  - Domain (e.g., "note_management", "data_processing")
  - Operations (CRUD, custom actions)
  - Parameters for each operation
  - Risk level assessment
  - Dependencies

**Adaptation for Different Tools**:
```python
# CRUD Tool Spec
{
  "name": "local_note_tool",
  "domain": "note_management",
  "inputs": [
    {"operation": "create", "parameters": [{"name": "text", "type": "string"}]},
    {"operation": "get", "parameters": [{"name": "id", "type": "string"}]},
    {"operation": "list", "parameters": [{"name": "limit", "type": "integer"}]}
  ],
  "outputs": ["note_data"],
  "risk_level": 0.3
}

# API Integration Tool Spec
{
  "name": "weather_api_tool",
  "domain": "external_api",
  "inputs": [
    {"operation": "get_weather", "parameters": [{"name": "city", "type": "string"}]},
    {"operation": "get_forecast", "parameters": [{"name": "city", "type": "string"}, {"name": "days", "type": "integer"}]}
  ],
  "outputs": ["weather_data"],
  "dependencies": ["http"],
  "risk_level": 0.4
}

# LLM Processing Tool Spec
{
  "name": "text_analyzer_tool",
  "domain": "llm_processing",
  "inputs": [
    {"operation": "analyze", "parameters": [{"name": "text", "type": "string"}]},
    {"operation": "summarize", "parameters": [{"name": "text", "type": "string"}, {"name": "max_length", "type": "integer"}]}
  ],
  "outputs": ["analysis_result"],
  "dependencies": ["llm"],
  "risk_level": 0.5
}
```

**Fallback Logic**: If LLM doesn't provide structured operations, defaults to generic CRUD operations.

---

### 4. Code Generator (LLM Stage 2)
**Files**: 
- `core/tool_creation/code_generator/qwen_generator.py` (multi-stage)
- `core/tool_creation/code_generator/default_generator.py` (single-shot)

#### Qwen Generator (Multi-Stage Approach)
**Why**: Local Qwen models are accurate up to ~200 lines, so we break generation into stages.

**Stage 1: Skeleton Generation**
```python
# Step 1a: Generate base class structure
class LocalNoteTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.services = orchestrator.get_services(self.__class__.__name__)
        super().__init__()
    
    def register_capabilities(self):
        pass  # Will add next
    
    def execute(self, operation: str, **kwargs):
        raise ValueError(f"Unsupported operation: {operation}")

# Step 1b: Add capabilities ONE AT A TIME (keeps each LLM call small)
# For each operation in spec:
#   - Add ToolCapability registration
#   - Add operation routing in execute()
#   - Add handler stub
```

**Stage 2: Handler Implementation**
```python
# For each handler stub, generate implementation ONE BY ONE
# Example for _handle_create:
def _handle_create(self, **kwargs):
    note_id = kwargs.get('note_id') or self.services.ids.generate()
    text = kwargs.get('text')
    if not text:
        raise ValueError("Missing required parameter: text")
    
    data = {"note_id": note_id, "text": text}
    return self.services.storage.save(note_id, data)
```

**Adaptation by Tool Type**:

**CRUD Tool** → Uses `self.services.storage.*`
```python
def _handle_create(self, **kwargs):
    item_id = kwargs.get('id') or self.services.ids.generate()
    return self.services.storage.save(item_id, dict(kwargs))

def _handle_get(self, **kwargs):
    return self.services.storage.get(kwargs['id'])

def _handle_list(self, **kwargs):
    return self.services.storage.list(limit=kwargs.get('limit', 10))
```

**HTTP API Tool** → Uses `self.services.http.*`
```python
def _handle_get_weather(self, **kwargs):
    city = kwargs.get('city')
    url = f"https://api.weather.com/v1/current?city={city}"
    return self.services.http.get(url)

def _handle_get_forecast(self, **kwargs):
    city = kwargs.get('city')
    days = kwargs.get('days', 7)
    url = f"https://api.weather.com/v1/forecast?city={city}&days={days}"
    return self.services.http.get(url)
```

**LLM Processing Tool** → Uses `self.services.llm.*`
```python
def _handle_analyze(self, **kwargs):
    text = kwargs.get('text')
    prompt = f"Analyze the following text: {text}"
    result = self.services.llm.generate(prompt, temperature=0.3)
    return {"analysis": result}

def _handle_summarize(self, **kwargs):
    text = kwargs.get('text')
    max_length = kwargs.get('max_length', 100)
    prompt = f"Summarize in {max_length} words: {text}"
    return {"summary": self.services.llm.generate(prompt, 0.3)}
```

**Composite Tool** → Uses `self.services.call_tool()`
```python
def _handle_weather_report(self, **kwargs):
    city = kwargs.get('city')
    
    # Call weather API tool
    weather = self.services.call_tool(
        'weather_api_tool', 
        'get_weather', 
        city=city
    )
    
    # Call LLM tool to format
    report = self.services.call_tool(
        'text_formatter_tool',
        'format',
        data=weather,
        style='friendly'
    )
    
    return report
```

#### Default Generator (Single-Shot)
**Why**: Cloud LLMs (GPT-4, Claude) can handle full tool generation in one call.

**Approach**: Provides complete contract + spec → generates entire tool code at once.

---

### 5. Validator (AST-Based Checks)
**File**: `core/tool_creation/validator.py`

**What it does**: Comprehensive validation using Python AST parsing:

**Structural Checks**:
- ✅ Class name matches spec
- ✅ Inherits from BaseTool
- ✅ Has `__init__(self, orchestrator=None)`
- ✅ Has `register_capabilities()`
- ✅ Has `execute(self, operation, **kwargs)`

**Capability Checks**:
- ✅ Calls `self.add_capability()` for each operation
- ✅ ToolCapability has all required fields
- ✅ Parameters use correct ParameterType enums
- ✅ Handler methods exist for all capabilities

**Safety Checks**:
- ✅ No mutable default arguments
- ✅ No relative `./` paths (must use `data/`)
- ✅ No undefined helper method calls
- ✅ No direct `self.capabilities` assignment
- ✅ Correct import statements

**Contract Checks**:
- ✅ Handlers return plain dict (not ToolResult)
- ✅ Uses `self.services.*` for operations
- ✅ Raises ValueError for validation errors

**Why This Matters**: Catches 90% of generation errors before runtime.

---

### 6. Expansion Mode (Disk Write)
**File**: `core/expansion_mode.py`

**What it does**:
- Writes generated code to `tools/experimental/{tool_name}.py`
- Creates test template in `tests/experimental/test_{tool_name}.py`
- Manages experimental → stable promotion

**Experimental Namespace**: New tools start here, isolated from production tools.

---

### 7. Sandbox Runner (Runtime Validation)
**File**: `core/tool_creation/sandbox_runner.py`

**What it does**: Executes generated tool in isolated environment with:

**Setup**:
- Creates temporary directory
- Instantiates tool with real orchestrator
- Provides real services (storage, LLM, HTTP)

**Smoke Tests**:
- Discovers all capabilities
- Builds test parameters based on operation types
- Executes operations in logical order (create → get → list)
- Validates results

**Parameter Generation by Type**:
```python
# INTEGER parameters
if "priority" in name: → 2
if "version" in name: → 1
if "limit" in name: → 10

# STRING parameters
if "code" in name: → "print('demo')"
if "language" in name: → "python"
if "name" in name: → "Demo name"
if "url" in name: → "https://example.com"

# BOOLEAN parameters → True
# LIST parameters → ["demo", "test"]
# DICT parameters → {"source": "sandbox"}
```

**Persistence Verification**: If tool creates items, verifies they can be retrieved.

**Why This Matters**: Catches runtime errors, service integration issues, and logic bugs.

---

### 8. Registry & Deployment
**What happens**:
- Tool registered as experimental in capability graph
- Available for use immediately
- Tracked for promotion to stable after N successful cycles

---

## How Generation Adapts to Different Tool Types

### Type Detection
The system infers tool type from:
1. **Domain** in spec (e.g., "note_management", "external_api", "llm_processing")
2. **Dependencies** (e.g., ["http"], ["llm"], ["storage"])
3. **Operation names** (e.g., "get_weather" → API, "analyze" → LLM)

### Service Selection
Code generator includes appropriate service calls:

| Tool Type | Primary Services | Example Operations |
|-----------|-----------------|-------------------|
| CRUD/Storage | `storage.*` | save, get, list, update, delete |
| HTTP API | `http.*` | get, post, put, delete |
| LLM Processing | `llm.*` | generate, analyze, summarize |
| Composite | `call_tool()` | Multi-tool workflows |
| File Operations | `filesystem.*` | read, write, list_files |
| Time-based | `time.*` | schedule, timestamp |

### Pattern Templates
Generator uses patterns based on operation names:

**Pattern: CRUD**
```python
# Detected by: create/get/list/update/delete operations
def _handle_{operation}(self, **kwargs):
    item_id = kwargs.get('id') or self.services.ids.generate()
    return self.services.storage.{operation}(item_id, data)
```

**Pattern: HTTP Request**
```python
# Detected by: URL parameters, "fetch"/"request" in operation name
def _handle_{operation}(self, **kwargs):
    url = kwargs.get('url')
    return self.services.http.get(url)
```

**Pattern: LLM Processing**
```python
# Detected by: "analyze"/"summarize"/"generate" in operation name
def _handle_{operation}(self, **kwargs):
    text = kwargs.get('text')
    prompt = f"Process: {text}"
    return {"result": self.services.llm.generate(prompt, 0.3)}
```

**Pattern: Inter-Tool Communication**
```python
# Detected by: dependencies in spec
def _handle_{operation}(self, **kwargs):
    # Call dependency tool
    result = self.services.call_tool('other_tool', 'operation', **params)
    # Process result
    return processed_result
```

---

## Example: Complete Flow for Note Tool

**1. Gap Description**: "Need ability to manage local notes with tags"

**2. Spec Generated**:
```json
{
  "name": "local_note_tool",
  "domain": "note_management",
  "inputs": [
    {"operation": "create", "parameters": [
      {"name": "text", "type": "string", "required": true},
      {"name": "tags", "type": "list", "required": false}
    ]},
    {"operation": "get", "parameters": [
      {"name": "note_id", "type": "string", "required": true}
    ]},
    {"operation": "list", "parameters": [
      {"name": "limit", "type": "integer", "required": false, "default": 10}
    ]}
  ],
  "risk_level": 0.3
}
```

**3. Code Generated** (Qwen multi-stage):
- Stage 1a: Base class with __init__, register_capabilities, execute
- Stage 1b: Add create capability + stub
- Stage 1b: Add get capability + stub
- Stage 1b: Add list capability + stub
- Stage 2: Implement _handle_create (uses storage.save)
- Stage 2: Implement _handle_get (uses storage.get)
- Stage 2: Implement _handle_list (uses storage.list)

**4. Validation**: AST checks pass (all methods exist, correct signatures, uses services)

**5. Sandbox Test**:
- Create note with text="Test" → Success
- Get note by ID → Returns created note
- List notes → Returns list with created note

**6. Deployed**: Available as `local_note_tool` in experimental namespace

---

## Key Advantages

1. **Adaptive**: Generates different code patterns based on tool type
2. **Safe**: Multi-layer validation (AST + runtime)
3. **Accurate**: Multi-stage keeps LLM calls under 200 lines
4. **Composable**: Tools can call other tools via services
5. **Testable**: Automatic sandbox validation
6. **Isolated**: Experimental namespace prevents production impact

---

## Extending the System

### Adding New Tool Patterns

**1. Add pattern detection in spec_generator.py**:
```python
if "database" in gap_description.lower():
    spec["domain"] = "database_operations"
    spec["dependencies"] = ["database"]
```

**2. Add service method in tool_services.py**:
```python
def query_database(self, query: str):
    # Database service implementation
    pass
```

**3. Add pattern template in qwen_generator.py**:
```python
if "database" in tool_spec["domain"]:
    pattern = """
def _handle_{operation}(self, **kwargs):
    query = kwargs.get('query')
    return self.services.query_database(query)
"""
```

**4. Add validation in validator.py** (if needed):
```python
if "database" in spec["domain"]:
    # Validate SQL injection protection
    pass
```

### Tool Type Examples

**Already Supported**:
- ✅ CRUD/Storage tools
- ✅ HTTP API tools
- ✅ LLM processing tools
- ✅ Composite tools (inter-tool communication)

**Easy to Add**:
- 🔄 Database query tools
- 🔄 File processing tools
- 🔄 Scheduled/cron tools
- 🔄 WebSocket tools
- 🔄 Email/notification tools

---

## Summary

The tool creation flow is a **production-ready pipeline** that:
1. Analyzes capability gaps with LLM
2. Generates tool specifications
3. Creates code using multi-stage generation (Qwen) or single-shot (cloud LLMs)
4. Validates with AST parsing + runtime tests
5. Deploys to experimental namespace
6. Adapts generation patterns based on tool type (CRUD, API, LLM, composite)

The system is **extensible** - new tool types can be added by defining patterns and service methods.
