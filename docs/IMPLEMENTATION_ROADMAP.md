# Implementation Roadmap

## Quick Wins (1-2 hours)

### 1. Remove Duplicate PermissionGate
**Files to modify:**
- Delete: `core/permission_gate.py`
- Update imports in: `api/server.py`, `core/secure_executor.py`
- Keep: `core/session_permissions.py` (more complete)

### 2. Create Centralized Config Manager
**New file:** `core/config_manager.py`
```python
from pydantic import BaseModel, Field
import yaml

class SecurityConfig(BaseModel):
    max_file_writes: int = 10
    max_file_size_mb: int = 1
    max_plan_steps: int = 20
    allowed_roots: list[str] = [".", "./output", "./workspace", "./temp"]
    blocked_paths: list[str] = [...]
    blocked_extensions: list[str] = [".exe", ".bat", ".cmd", ".ps1", ".sh", ".dll"]

class LLMConfig(BaseModel):
    default_model: str = "qwen"
    temperature: float = 0.7
    max_retries: int = 3
    timeout_seconds: int = 120
    
class Config(BaseModel):
    security: SecurityConfig
    llm: LLMConfig
    
def load_config() -> Config:
    with open("config.yaml") as f:
        return Config(**yaml.safe_load(f))
```

### 3. Update config.yaml
Add missing sections:
```yaml
security:
  max_file_writes: 10
  max_file_size_mb: 1
  max_plan_steps: 20
  allowed_roots: [".", "./output", "./workspace", "./temp"]
  
timeouts:
  sandbox_test: 30
  llm_request: 120
  health_check: 5
```

## Medium Effort (3-5 hours)

### 4. Dynamic Tool Schema Generation
**New file:** `core/schema_generator.py`
```python
def generate_tool_enums(registry: CapabilityRegistry):
    """Generate Pydantic enums from registered tools"""
    tools = {tool.__class__.__name__: tool for tool in registry.tools}
    operations = {}
    for cap_name in registry.get_all_capabilities():
        tool_name, op_name = cap_name.split('.')
        operations.setdefault(tool_name, []).append(op_name)
    
    return create_dynamic_enums(tools, operations)
```

### 5. Environment Variable Support
**Update:** `core/config_manager.py`
```python
import os

class Config(BaseModel):
    @classmethod
    def from_env(cls):
        config = load_config()
        # Override with env vars
        if api_url := os.getenv("CUA_API_URL"):
            config.api.url = api_url
        if max_writes := os.getenv("CUA_MAX_FILE_WRITES"):
            config.security.max_file_writes = int(max_writes)
        return config
```

### 6. Frontend Environment Config
**New file:** `ui/.env`
```
REACT_APP_API_URL=http://localhost:8000
REACT_APP_WS_URL=ws://localhost:8000/ws
```

**Update:** `ui/src/config.js`
```javascript
export const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
export const WS_URL = process.env.REACT_APP_WS_URL || 'ws://localhost:8000/ws';
```

## Larger Refactors (1-2 days)

### 7. Standardized Result Pattern
**Update:** `tools/tool_result.py`
```python
class Result[T]:
    def __init__(self, success: bool, data: T = None, error: str = None):
        self.success = success
        self.data = data
        self.error = error
    
    @classmethod
    def ok(cls, data: T) -> "Result[T]":
        return cls(True, data=data)
    
    @classmethod
    def err(cls, error: str) -> "Result[T]":
        return cls(False, error=error)
```

Apply everywhere instead of tuples/exceptions.

### 8. Hardware Auto-Detection
**New file:** `core/hardware_detector.py`
```python
import torch
import psutil

def detect_optimal_llm_config():
    if torch.cuda.is_available():
        vram = torch.cuda.get_device_properties(0).total_memory
        return {
            "num_gpu": 99,
            "num_ctx": 16384 if vram > 12e9 else 8192,
            "num_predict": 8192 if vram > 12e9 else 4096,
        }
    else:
        cpu_count = psutil.cpu_count()
        return {
            "num_gpu": 0,
            "num_thread": cpu_count,
            "num_ctx": 4096,
            "num_predict": 2048,
        }
```

### 9. Exponential Backoff for Retries
**New file:** `core/retry_strategy.py`
```python
import time
from typing import Callable, TypeVar

T = TypeVar('T')

def retry_with_backoff(func: Callable[[], T], max_retries: int = 3) -> T:
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt  # 1s, 2s, 4s
            time.sleep(wait)
```

## Testing Strategy

### Unit Tests to Add
1. `tests/unit/test_config_manager.py` - Config loading/validation
2. `tests/unit/test_schema_generator.py` - Dynamic schema generation
3. `tests/unit/test_hardware_detector.py` - Hardware detection

### Integration Tests
1. `tests/integration/test_config_override.py` - Env var overrides work
2. `tests/integration/test_dynamic_tools.py` - New tools auto-register in schema

## Migration Guide

### Step 1: Backup
```bash
git commit -am "Pre-refactor checkpoint"
```

### Step 2: Install Dependencies
```bash
pip install pydantic-settings python-dotenv
```

### Step 3: Apply Changes in Order
1. Create config_manager.py
2. Update config.yaml
3. Remove duplicate permission_gate.py
4. Update all imports
5. Run tests
6. Update frontend config

### Step 4: Verify
```bash
pytest tests/
python start.py  # Should start without errors
```

## Rollback Plan
If issues occur:
```bash
git reset --hard HEAD~1
```

All changes are backwards compatible - old code continues working during migration.
