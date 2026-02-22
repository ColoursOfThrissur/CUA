# CUA System Architecture

## Overview

CUA is a self-improving autonomous agent system with native tool calling, automatic dependency management, and real-time observability.

## System Layers

### 1. API Layer (FastAPI)

**Purpose**: HTTP/WebSocket interface for all system operations

**Key Files**:
- `api/server.py` - Main server with native tool calling
- `api/tool_evolution_api.py` - Evolution workflow endpoints
- `api/quality_api.py` - Health scoring endpoints
- `api/observability_api.py` - Database query endpoints
- `api/cleanup_api.py` - Maintenance endpoints

**Endpoints**:
```
POST /chat                          # Native tool calling chat
POST /evolution/evolve              # Start tool evolution
GET  /evolution/pending             # Get pending evolutions
POST /evolution/approve/{tool}      # Approve evolution (auto re-checks deps)
POST /evolution/reject/{tool}       # Reject evolution
POST /evolution/resolve-dependencies # Install/generate/skip dependencies
GET  /quality/all                   # Get all tool health scores
GET  /quality/weak                  # Get weak tools (excludes pending)
GET  /quality/llm-weak              # Get LLM-analyzed weak tools
GET  /quality/llm-analysis/{tool}   # Get LLM health analysis
POST /quality/refresh-llm-analysis  # Refresh LLM analysis
GET  /observability/logs            # Query system logs
GET  /observability/tool-evolution  # Query evolution history
POST /observability/cleanup         # Remove stale execution logs
POST /observability/refresh         # Refresh quality metrics
GET  /observability/tables          # List all database tables
GET  /observability/data/{db}/{table} # Get paginated table data
GET  /tools/list                    # List actual tool files
GET  /tools/info/{tool}             # Get tool capabilities
GET  /tools-management/summary      # Get tool summary stats
GET  /tools-management/list         # Get all tools with health
GET  /tools-management/detail/{tool} # Get comprehensive tool details
GET  /tools-management/executions/{tool} # Get recent executions
GET  /tools-management/code/{tool}  # Get tool source code
POST /tools-management/trigger-check/{tool} # Run health check
```

### 2. Tool System

**Purpose**: Unified tool interface with service injection

**Architecture**:
```
ToolOrchestrator
    ↓
ToolRegistry (20+ tools)
    ↓
Tool Execution
    ↓
ToolServices (injected)
    ├── storage (auto-scoped)
    ├── llm (LLM calls)
    ├── http (HTTP requests)
    ├── fs (filesystem)
    ├── json (JSON ops)
    ├── logging (structured logs)
    ├── time (timestamps)
    └── ids (UUID generation)
```

**Key Files**:
- `core/tool_orchestrator.py` - Execution orchestrator
- `core/tool_services.py` - Service facade
- `tools/tool_interface.py` - Base tool class
- `tools/capability_registry.py` - Tool registry

**Tool Structure**:
```python
class MyTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.services = orchestrator.get_services(self.__class__.__name__)
        super().__init__()
    
    def register_capabilities(self):
        # Define capabilities
        pass
    
    def execute(self, operation, **kwargs):
        # Route to handlers
        pass
    
    def _handle_operation(self, **kwargs):
        # Use self.services.llm, self.services.storage, etc.
        pass
```

### 3. Native Tool Calling

**Purpose**: Automatic tool selection via Mistral function calling

**Flow**:
```
User Message
    ↓
ToolCallingClient.call_with_tools()
    ↓
Build OpenAI-compatible tool definitions
    ↓
POST /api/chat (Mistral with tools parameter)
    ↓
Model returns tool_calls or text response
    ↓
Execute selected tools via registry
    ↓
Generate natural response from results
```

**Key Files**:
- `planner/tool_calling.py` - Native function calling client
- `api/server.py` - Integration in /chat endpoint

**Tool Definition Format**:
```json
{
  "type": "function",
  "function": {
    "name": "ContextSummarizerTool_summarize_text",
    "description": "Summarize text content (Tool: ContextSummarizerTool)",
    "parameters": {
      "type": "object",
      "properties": {
        "input_text": {"type": "string", "description": "Text to summarize"},
        "summary_length": {"type": "integer", "description": "Length in words"}
      },
      "required": ["input_text"]
    }
  }
}
```

### 4. Evolution Engine

**Purpose**: Automated tool improvement with human approval

**6-Step Flow with Context-Aware Improvements**:
```
1. ANALYZE
   - Quality analyzer scores tool (0-100)
   - LLM health analyzer checks code quality
   - Extracts current code, errors, usage stats
   - Generates analysis summary

2. PROPOSE
   - Reads evolution context from .amazonq/rules/LocalLLMRUle.md
   - Understands architecture patterns (self._cache, self.services.X)
   - LLM generates improvement specification
   - ONLY proposes fixes for HIGH severity bugs
   - Skips if no critical issues found
   - Requires justification for changes

3. GENERATE CODE
   - Code generator creates minimal improved version
   - Preserves structure, improves handlers
   - Uses available services list

3.5. CHECK DEPENDENCIES
   - AST parser extracts imports and self.services.X calls
   - Checks against installed libraries and AVAILABLE_SERVICES
   - Stores missing deps in proposal

4. VALIDATE
   - AST validation (syntax)
   - Structure validation (class, methods)
   - Logic validation (no breaking changes)

5. SANDBOX TEST
   - Import in isolated environment
   - Instantiate tool
   - Execute sample operations
   - Catch exceptions

6. PENDING APPROVAL
   - Store in pending_evolutions.json
   - Display in UI with dependency warnings
   - Human reviews and approves/rejects
```

**Key Files**:
- `core/tool_evolution/flow.py` - Orchestrator
- `core/tool_evolution/analyzer.py` - Tool analysis
- `core/tool_evolution/proposal_generator.py` - Context-aware proposals
- `core/tool_evolution/code_generator.py` - Code generation
- `core/tool_evolution/validator.py` - Validation
- `core/tool_evolution/sandbox_runner.py` - Sandbox testing
- `core/pending_evolutions_manager.py` - Approval queue
- `core/llm_tool_health_analyzer.py` - LLM-based health analysis

### 5. Dependency Management

**Purpose**: Prevent broken code from missing libraries/services

**Detection** (AST-based):
```python
# DependencyChecker parses code
tree = ast.parse(code)

# Extract imports
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        # Check if installed
        
# Extract service calls
for node in ast.walk(tree):
    if isinstance(node, ast.Attribute):
        # Check if self.services.X exists
```

**Resolution**:
```
Missing Library
    ↓
subprocess.run(["pip", "install", library])
    ↓
Add to requirements.txt

Missing Service
    ↓
LLM generates service class
    ↓
Add to ToolServices
    ↓
Update AVAILABLE_SERVICES
```

**Auto-Refresh**:
- On approval, re-run dependency check
- If resolved since creation, proceed
- If still missing, block with error

**Key Files**:
- `core/dependency_checker.py` - AST-based detection
- `core/dependency_resolver.py` - Installation & generation
- `api/tool_evolution_api.py` - Auto re-check on approval

### 6. Observability System

**Purpose**: Complete visibility into system operations

**5 SQLite Databases**:

1. **logs.db** (System Logs)
   - Table: `logs`
   - Fields: id, timestamp, service, level, message, context
   - Use: All application logs

2. **tool_executions.db** (Execution History)
   - Table: `executions`
   - Fields: id, tool_name, operation, status, duration, timestamp
   - Use: Track tool usage and performance

3. **tool_evolution.db** (Evolution Tracking)
   - Table: `evolution_runs`
   - Fields: id, tool_name, user_prompt, status, step, error_message, confidence, health_before, timestamp
   - Use: Track evolution attempts with step-by-step details

4. **tool_creation.db** (Creation Logs)
   - Table: `creation_runs`
   - Fields: id, tool_name, status, step, error_message, timestamp
   - Use: Track tool generation

5. **chat_history.db** (Conversations)
   - Table: `messages`
   - Fields: id, session_id, role, content, timestamp
   - Use: Conversation history

**Key Files**:
- `core/sqlite_logging.py` - Base logger
- `core/tool_evolution_logger.py` - Evolution tracking
- `core/tool_execution_logger.py` - Execution tracking
- `core/chat_history_logger.py` - Chat logging
- `api/observability_api.py` - Query endpoints

### 7. Quality System

**Purpose**: Health scoring and recommendations

**Health Score Calculation** (0-100):
```python
score = 0

# Success rate (40 points)
if executions > 0:
    score += (successes / executions) * 40

# Usage (30 points)
if executions >= 10:
    score += 30
elif executions >= 5:
    score += 20
elif executions >= 1:
    score += 10

# Output size (20 points)
if avg_output_size > 100:
    score += 20
elif avg_output_size > 50:
    score += 10

# Error penalty (10 points)
if error_rate > 0.5:
    score -= 10
```

**Recommendations**:
- **HEALTHY** (80-100): No action
- **WEAK** (50-79): Consider evolution
- **BROKEN** (0-49): Quarantine or fix

**Key Files**:
- `core/tool_quality_analyzer.py` - Health scoring
- `api/quality_api.py` - Quality endpoints
- `api/cleanup_api.py` - Cleanup stale data

### 8. UI Layer (React)

**Purpose**: Unified interface with 5 modes

**Architecture**:
```
App.js
    ↓
Header (mode switcher, tools management, observability, theme toggle)
    ↓
MainCanvas (renders mode-specific content)
    ├── CUA Chat (ChatPanel)
    ├── Tools Mode (ToolModeChat)
    ├── Evolution Mode (EvolutionMode)
    ├── Tools Management (ToolsManagementPage)
    └── Observability (ObservabilityPage)
    ↓
FloatingActionBar (context-sensitive buttons)
    ↓
RightOverlay (slide-in panels)
    ├── ObservabilityOverlay (10 database tabs)
    ├── QualityOverlay (health dashboard)
    ├── PendingEvolutionsOverlay (approval UI)
    └── Other overlays
```

**Key Components**:
- `ui/src/App.js` - Main app with state management and theme
- `ui/src/components/MainCanvas.js` - Unified canvas
- `ui/src/components/ModeTabBar.js` - Mode switcher
- `ui/src/components/FloatingActionBar.js` - Context buttons
- `ui/src/components/RightOverlay.js` - Slide-in panel
- `ui/src/components/EvolutionMode.js` - Evolution UI
- `ui/src/components/ToolsManagementPage.js` - Tool dashboard
- `ui/src/components/ObservabilityPage.js` - Full-page database viewer
- `ui/src/components/ObservabilityOverlay.js` - Database overlay
- `ui/src/components/QualityOverlay.js` - Health dashboard
- `ui/src/components/PendingEvolutionsOverlay.js` - Approval UI

**Styling**:
- Theme system with CSS variables in `ui/src/styles/theme.css`
- Dark theme (default): Black background (#000000), blue accent (#4a9eff)
- Light theme: Modern white (#f7f7f7), GitHub-style colors
- No hardcoded colors, all use CSS variables
- Smooth theme transitions

### 9. LLM Integration

**Purpose**: Unified LLM interface

**Clients**:
- `planner/llm_client.py` - Standard LLM calls
- `planner/tool_calling.py` - Native function calling

**Usage**:
```python
# Standard generation
response = llm_client.generate_response(prompt, history)

# Native tool calling
success, tool_calls, text = tool_caller.call_with_tools(message, history)
```

## Data Flow Diagrams

### Chat Request
```
User: "summarize this text: [content]"
    ↓
POST /chat
    ↓
ToolCallingClient.call_with_tools()
    ↓
Mistral returns: tool_calls=[{function: {name: "summarize_text", arguments: {...}}}]
    ↓
registry.execute_capability("summarize_text", **arguments)
    ↓
ContextSummarizerTool._handle_summarize_text()
    ↓
self.services.llm.generate(prompt)
    ↓
Return result
    ↓
LLM generates natural response
    ↓
Response to user
```

### Evolution Request
```
User: "Improve ContextSummarizerTool"
    ↓
POST /evolution/evolve
    ↓
ToolEvolutionOrchestrator.evolve_tool()
    ↓
1. Analyzer.analyze_tool() → health score, issues
2. ProposalGenerator.generate_proposal() → improvement spec
3. CodeGenerator.generate_improved_code() → new code
3.5. DependencyChecker.check_code() → missing deps
4. Validator.validate() → syntax, structure
5. SandboxRunner.test_improved_tool() → isolated test
6. PendingEvolutionsManager.add_pending_evolution() → approval queue
    ↓
UI shows pending evolution with dependency warnings
    ↓
User clicks "Approve"
    ↓
POST /evolution/approve/{tool}
    ↓
Re-check dependencies (auto-refresh)
    ↓
If resolved: Apply changes
If missing: Block with error
```

### Dependency Resolution
```
Evolution generates code with self.services.logging.info()
    ↓
DependencyChecker.check_code()
    ↓
AST parse: finds self.services.logging
    ↓
Check AVAILABLE_SERVICES: {'storage', 'llm', 'http', ...}
    ↓
'logging' not in set → missing_services=['logging']
    ↓
Store in proposal.dependencies
    ↓
Developer adds LoggingService to ToolServices
    ↓
Update AVAILABLE_SERVICES.add('logging')
    ↓
User clicks "Approve"
    ↓
Auto re-check: 'logging' now in AVAILABLE_SERVICES
    ↓
No missing deps → Proceed with approval
```

## Key Design Patterns

### 1. Service Injection
Tools receive services via orchestrator, not direct imports:
```python
# Bad
import requests
response = requests.get(url)

# Good
response = self.services.http.get(url)
```

### 2. Auto-Scoped Storage
Each tool gets isolated storage directory:
```python
# Automatically scoped to tool name
self.services.storage.save("item-1", data)
# Saves to: data/contextsummarizer/item-1.json
```

### 3. Thin Tools
Tools delegate to services, minimal logic:
```python
def _handle_operation(self, **kwargs):
    # Validate
    # Call service
    # Return result
    pass
```

### 4. Human-in-Loop
All evolutions require approval:
```python
# Generate → Validate → Sandbox → Pending → Approve
```

### 5. Auto-Refresh
Dependencies re-checked on approval:
```python
# Stored at creation time
proposal['dependencies'] = {'missing_services': ['logging']}

# Re-checked at approval time
report = checker.check_code(improved_code)
# If resolved, proceed
```

## Configuration

### Available Services
Defined in `core/dependency_checker.py`:
```python
AVAILABLE_SERVICES = {
    'storage', 'time', 'ids', 'llm', 'http', 'json', 
    'shell', 'fs', 'logging',
    'extract_key_points', 'sentiment_analysis', 
    'detect_language', 'generate_json_output',
    'call_tool', 'list_tools', 'has_capability'
}
```

### Standard Library Modules
Don't need installation:
```python
STDLIB_MODULES = {
    'json', 'os', 'sys', 'time', 'datetime', 'pathlib', 're', 
    'typing', 'collections', 'itertools', 'functools', 'math', 
    'random', 'uuid', 'logging', 'traceback', 'inspect', 'ast', 
    'dataclasses', 'enum'
}
```

## Extension Points

### Adding New Service
1. Create service class in `core/tool_services.py`
2. Add to `ToolServices.__init__()`
3. Add to `AVAILABLE_SERVICES` in `core/dependency_checker.py`
4. Update code generator prompt in `core/tool_evolution/code_generator.py`

### Adding New Tool
1. Create tool file in `tools/` or `tools/experimental/`
2. Inherit from `BaseTool`
3. Register capabilities
4. Use `self.services` for operations
5. Register in `api/server.py` or via tool creation flow

### Adding New Database
1. Create logger in `core/` (e.g., `my_logger.py`)
2. Define table schema
3. Add query endpoint in `api/observability_api.py`
4. Add tab in `ui/src/components/ObservabilityOverlay.js`

## Performance Considerations

- **SQLite**: Fast for reads, single-writer for writes
- **Tool Calling**: ~1-2s per LLM call
- **Evolution**: ~10-30s for full cycle
- **Dependency Check**: <100ms (AST parsing)
- **WebSocket**: Real-time updates, minimal overhead

## Security

- **Sandbox Testing**: Isolated execution before approval
- **Human Approval**: Required for all evolutions
- **Dependency Validation**: Blocks unknown imports
- **Service Isolation**: Tools can't access system directly
- **Filesystem Restrictions**: Allowed roots only

## Future Enhancements

1. **Auto-Evolution Triggers**: Scheduled improvements
2. **Multi-Model Support**: Different models for different tasks
3. **Distributed Execution**: Scale across multiple nodes
4. **Version Control**: Git integration for tool changes
