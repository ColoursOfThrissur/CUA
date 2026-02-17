# Hardcoded Issues & Improvements Needed

## 🔴 Critical Issues

### 1. **Duplicate Permission Gate Classes**
- **Files**: `core/permission_gate.py` AND `core/session_permissions.py`
- **Issue**: Two different implementations of PermissionGate with same functionality
- **Impact**: Confusion, potential bugs from using wrong one
- **Fix**: Consolidate into single `core/session_permissions.py`

### 2. **Hardcoded File Limits**
```python
# Scattered across multiple files:
max_file_writes: 10          # permission_gate.py, session_permissions.py
max_file_size: 1024 * 1024   # permission_gate.py, session_permissions.py, immutable_brain_stem.py
max_steps: 20                # plan_validator.py
```
- **Issue**: Same values duplicated, not configurable
- **Fix**: Move to `config.yaml` with single source of truth

### 3. **Hardcoded Allowed Paths**
```python
# immutable_brain_stem.py
_ALLOWED_ROOTS = (".", "./output", "./workspace", "./temp")

# enhanced_filesystem_tool.py
allowed_roots = [".", "./output", "./workspace"]
```
- **Issue**: Different defaults, not synchronized
- **Fix**: Single config source, environment-aware paths

### 4. **Hardcoded Tool/Operation Enums**
```python
# plan_schema.py
class ToolName(str, Enum):
    FILESYSTEM_TOOL = "filesystem_tool"  # Only one tool!

class OperationName(str, Enum):
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    LIST_DIRECTORY = "list_directory"
```
- **Issue**: Schema breaks when adding new tools (HTTP, JSON, Shell already exist!)
- **Fix**: Dynamic schema generation from CapabilityRegistry

## 🟡 Medium Priority

### 5. **Hardcoded Model Configuration**
```python
# llm_client.py
options = {
    "num_predict": 8192,
    "num_ctx": 16384,
    "num_gpu": 99,
    "num_thread": 8,
}
```
- **Issue**: Hardware-specific settings hardcoded
- **Fix**: Auto-detect GPU/CPU, make configurable per model

### 6. **Hardcoded Retry Logic**
```python
# llm_client.py
max_retries: int = 3
```
- **Issue**: Fixed retry count
- **Fix**: Configurable with exponential backoff

### 7. **Hardcoded Timeout Values**
```python
# sandbox_tester.py (implied)
timeout=30  # self_evolution.py

# llm_client.py
timeout=120

# start.py
time.sleep(2)
timeout=5
```
- **Issue**: Magic numbers scattered everywhere
- **Fix**: Centralized timeout config

### 8. **Hardcoded API Endpoints**
```python
# UI App.js
'http://localhost:8000/...'  # Hardcoded in 20+ places
```
- **Issue**: Can't change port/host without editing code
- **Fix**: Environment variable `REACT_APP_API_URL`

### 9. **Session ID Generation**
```python
# App.js
Math.random().toString(36).substr(2, 9)
```
- **Issue**: Weak, collision-prone
- **Fix**: Use crypto.randomUUID() or backend-generated

## 🟢 Low Priority

### 10. **Hardcoded Log Paths**
```python
# Implied in logging_system.py
logs/llm/
logs/cua_api.log
```
- **Issue**: Not configurable
- **Fix**: Config-based log directory

### 11. **Hardcoded Backup Naming**
```python
# self_evolution.py
f"{capability_name}_v{version}.py"
```
- **Issue**: Simple naming, no timestamp
- **Fix**: Include timestamp for better tracking

### 12. **Hardcoded WebSocket Reconnect**
```python
// App.js
setTimeout(connect, 3000)  // 3 second reconnect
```
- **Issue**: Fixed delay
- **Fix**: Exponential backoff

## 📋 Architectural Issues

### 13. **Missing Tool Registration**
- **Issue**: HTTP, JSON, Shell tools exist but NOT in plan_schema.py enums
- **Impact**: LLM can't generate plans using these tools
- **Fix**: Dynamic schema from registry

### 14. **Inconsistent Error Handling**
- **Issue**: Some functions return tuples, some throw exceptions, some return Result objects
- **Fix**: Standardize on Result pattern everywhere

### 15. **No Configuration Validation**
- **Issue**: config.yaml loaded but not validated
- **Fix**: Pydantic schema for config validation

### 16. **Hardcoded Database Paths**
```python
# Implied in various files
data/analytics.db
data/conversations.db
data/plan_history.db
```
- **Issue**: Not configurable
- **Fix**: Config-based with path validation

## 🎯 Recommended Action Plan

### Phase 1: Configuration Consolidation
1. Create `core/config_manager.py` with Pydantic validation
2. Move all hardcoded values to `config.yaml`
3. Add environment variable overrides

### Phase 2: Code Deduplication
1. Remove duplicate PermissionGate
2. Consolidate path validation logic
3. Standardize error handling

### Phase 3: Dynamic Schema
1. Generate plan_schema enums from CapabilityRegistry
2. Auto-update when tools registered
3. LLM prompt includes all available tools

### Phase 4: Environment Awareness
1. Auto-detect hardware capabilities
2. Adjust LLM settings based on available VRAM
3. Graceful degradation for limited resources
