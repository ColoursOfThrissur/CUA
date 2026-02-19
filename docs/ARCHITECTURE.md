# CUA Self-Improvement Architecture

## System Overview
Autonomous agent system with hybrid self-improvement engine combining RAG + Agent-Based + Memory architecture. Uses Qwen 14B for small-block modifications with deterministic policy enforcement.

---

## System Architecture

### Frontend (React + Glassmorphism UI)
- **Modern Design**: Glassmorphism with animated gradient backgrounds, no borders
- **Components**: Chat panel, Agent control, Combined tools panel, History
- **Features**: Voice input, toast notifications, collapsible sections, keyboard shortcuts
- **Icons**: Lucide React icons throughout
- **Real-time**: WebSocket connection to backend API

### Backend (FastAPI)
- **Main API** (`api/server.py`): Agent control, chat, tools, history
- **Hybrid API** (`api/hybrid_api.py`): Self-improvement stats, priority files, memory, error analysis
- **WebSocket**: Real-time agent status and log streaming
- **Lazy Loading**: Components initialized on-demand to avoid circular dependencies

### Core Systems

#### 1. Safety & Execution
- **ImmutableBrainStem**: Read-only safety validation for all operations
- **InterfaceProtector**: Prevents breaking abstract classes
- **SandboxRunner**: Isolated test execution with failure classification
- **AtomicApplier**: Safe file modifications with rollback support

#### 2. Tool System
- **ToolRegistry**: Dynamic tool discovery and registration
- **ToolInterface**: Base class for all tools (file, shell, search, etc.)
- **ToolResult**: Standardized success/error responses
- **Built-in Tools**: File operations, shell execution, web search, code analysis
- **WebContentExtractor**: Structured HTML parsing from web pages (capability expansion test)

#### 3. LLM Integration
- **Qwen 14B**: Primary model for code generation and analysis
- **LLMClient**: Unified interface for model interactions
- **Prompt Engineering**: Zero-indent formatting for 14B model stability
- **Token Optimization**: Context optimizer reduces usage by ~70%
- **Session Logging**: All LLM interactions logged to `logs/llm_sessions/` with 10MB rotation

#### 4. Hybrid Improvement Engine (80% Success Rate)
**Architecture**: RAG + Agent-Based + Memory

**Components**:
- **ImprovementMemory** (`core/improvement_memory.py`): SQLite database tracking all improvement attempts with outcomes, errors, test results, metrics
- **ErrorPrioritizer** (`core/error_prioritizer.py`): Analyzes logs to identify files with most errors, extracts patterns, prioritizes targets
- **TestValidator** (`core/test_validator.py`): Runs pytest, syntax checks, validates changes before applying
- **ContextOptimizer** (`core/context_optimizer.py`): Intelligently selects relevant code context, extracts summaries, resolves dependencies
- **HybridImprovementEngine** (`core/hybrid_improvement_engine.py`): Main orchestrator combining all components with iterative refinement (max 3 attempts)

**Workflow**:
1. Error analysis identifies priority files
2. Context optimizer gathers relevant code (70% token reduction)
3. Memory system checks past attempts to avoid repeating failures
4. LLM generates improvement proposal
5. Test validator checks syntax and runs tests
6. If validation fails, iterate with error feedback (max 3 attempts)
7. Record outcome in memory for future learning

**Success Rate**: 80% (vs 50% with standard loop)

#### 5. Evolution Controller (Autonomous Capability Engine)
**Purpose**: Autonomous code evolution with controlled freedom

**Components**:
- **EvolutionController** (`core/evolution_controller.py`): Main orchestrator
- **SelfReflector** (`core/self_reflector.py`): Strategic system analysis
- **InsightEnricher** (`core/insight_enricher.py`): Converts metrics to concrete structural facts
- **CapabilityGraph** (`core/capability_graph.py`): Tracks tool capabilities
- **GrowthBudget** (`core/growth_budget.py`): Controls evolution rate
- **ASTValidator** (`core/ast_validator.py`): Validates proposals against actual code

**Workflow**:
1. **Baseline Gate**: Health check (syntax, imports, tests)
2. **Self-Reflection**: Analyze system for improvements
   - Detect long methods (>80 lines)
   - Find code duplication patterns
   - Identify capability gaps
   - Detect missing abstractions
3. **Proposal Generation**: LLM proposes evolution
   - Types: micro_patch, structural_upgrade, tool_extension, new_tool
   - Constraints: Single file, max 3 methods, no interface changes
   - Validation: AST checks, structural constraints, risk scoring
4. **Execution**: Uses standard improvement system
   - Extracts actual method code (prevents hallucination)
   - Passes to ProposalGenerator with real code context
   - Applies via AtomicApplier
5. **Growth Budget**: Increments cycle counter

**Key Fix (2025-02-19)**: Evolution controller now extracts actual method code before refactoring to prevent LLM hallucination. Previously, LLM only saw method names/line counts and would generate code referencing non-existent attributes.

#### 6. Standard Improvement Loop
- **ImprovementLoop** (`core/improvement_loop.py`): Fallback system, tries hybrid engine first
- **LoopController** (`core/loop_controller.py`): Main loop orchestration
- **TaskAnalyzer** (`core/task_analyzer.py`): File selection and feature suggestion
- **ProposalGenerator** (`core/proposal_generator.py`): Code generation with validation
- **FeatureTracker** (`core/feature_tracker.py`): Maturity levels and cooldown management

#### 7. Code Generation Pipeline
**Components**:
- **OrchestratedCodeGenerator** (`core/orchestrated_code_generator.py`): Main code generation orchestrator
- **StepPlanner** (`core/step_planner.py`): Breaks tasks into steps
- **IncrementalCodeBuilder** (`core/incremental_code_builder.py`): Builds code step-by-step
- **OutputValidator** (`core/output_validator.py`): Validates generated code structure
- **PatchGenerator** (`core/patch_generator.py`): Creates FILE_REPLACE patches

**Workflow**:
1. **Step Planning**: Break task into 1-3 steps
2. **Code Generation**: 
   - Single-shot for 1 step
   - Incremental for multiple steps
   - Strategy: insert (new method) or rewrite (modify existing)
3. **Validation**: OutputValidator checks structure
   - Uses `ast.walk()` to find functions inside classes (fixed 2025-02-19)
   - Validates method signatures, return types
4. **Patch Creation**: PatchGenerator creates FILE_REPLACE format
5. **Application**: AtomicApplier writes complete file to disk

**Key Fixes (2025-02-19)**:
- **Method Name Extraction**: Improved regex patterns with blacklist for common words
- **Silent Fallback Bug**: Removed dangerous fallback that silently modified wrong method
- **Refactoring Prompt**: Fixed contradictory instructions, now explicitly requests BOTH methods
- **Token Limit**: Increased max_tokens from 3072 to 4096 for refactoring tasks
- **Output Validator**: Fixed to use `ast.walk()` instead of `tree.body` to find functions inside classes

---

## Standard Improvement Pipeline (5 Stages)

### Stage 0: Baseline Gate
**Component**: `BaselineHealthChecker`
- Runs syntax check, import check, baseline tests
- Skips 10 known broken tests
- **STOPS loop if baseline fails** (no blind retries)

### Stage 1: File Selection
**Component**: `TaskAnalyzer._analyze_stage1_discovery()`

**Mode A - Autonomous** (no user intent):
- Deterministic selection (NO LLM)
- Picks highest score from maturity ranking
- Filters: cooldown, blocked files, protected interfaces

**Mode B - Intent-Driven** (user provides goal):
- LLM for semantic mapping only
- Maps user intent → relevant file
- Metadata consistency guard (rejects fabricated reasoning)

**Constraints**:
- 3-iteration cooldown per file
- Skip files modified in last 3 iterations
- Protected interfaces blocked

### Stage 2: Feature Suggestion
**Component**: `TaskAnalyzer._analyze_stage2_implementation()`

**Early Risk Estimation**:
- Blast radius analysis (dependency graph)
- Failure history check
- Skips if early_risk > 0.7

**LLM Constraints**:
- 6 allowed categories: input_validation, error_handling, logging, security, timeout_handling, parameter_validation
- Forbidden: caching (unless heavy I/O), async, performance, refactoring
- Max 80 lines, single method only

**Validation Gates**:
1. Output validator (category, max_lines, no async/caching)
2. Sanity check (feature relevance for tool type)
3. Repetition guard (reject if category used 2+ times)
4. Duplicate interaction prevention (>70% similarity)
5. Method existence check
6. Abstract method safety (blocks @abstractmethod)
7. Constructor restriction (only logging/parameter_validation)

### Stage 3: Code Generation
**Component**: `ProposalGenerator`

**Protected Interface Check**:
- Blocks: tool_interface.py, tool_result.py, immutable_brain_stem.py

**Generation**:
- Single-shot for simple tasks
- Multi-step for complex (incremental merge)

**Validation**:
1. Syntax (AST parse)
2. Security (no eval/exec, SQL injection, SSRF)
3. Semantic (CodeCritic - hard fails on empty methods, placeholders)
4. Behavioral drift detection
5. Output validator (single method, valid Python)

**Integrations**:
- Body-only AST replacement (preserves decorators/signatures)
- Import resolver (auto-adds missing stdlib imports)
- No-op detector (skips if AST identical)

### Stage 4: Sandbox Testing
**Component**: `SandboxRunner`

**Failure Classification**:
- Baseline failure → STOP LOOP (fatal)
- Syntax error → Regenerate
- Integration error → Retry merge
- Test regression → Reject
- Environment error → Retry once

**Tests**:
- Baseline test (original code)
- Coverage delta check (rejects if drops >2%)
- Proposal test (modified code)
- Skips 10 known broken tests

### Stage 5: Apply
**Component**: `AtomicApplier`

**Guards**:
1. Staleness check (file unchanged since snapshot)
2. No-op detection (skip if no semantic change)
3. Import resolution (add missing imports)
4. Idempotency check (prevent duplicate changes)

**Rollback**: Git-based or manual .bak files

---

## Component Details

### Safety Layer
- **ImmutableBrainStem**: Validates all operations (read-only)
- **InterfaceProtector**: Prevents breaking abstract classes
- **FailureClassifier**: Smart retry logic (5 failure types)
- **BaselineHealthChecker**: Pre-loop gate

### Analysis Layer
- **DependencyAnalyzer**: Blast radius (import graph)
- **FailureLearner**: SQLite-based failure history (temporal decay)
- **CodeCritic**: Semantic validation (hard fails vs warnings)
- **BehaviorValidator**: Detects API drift
- **ErrorPrioritizer**: Log analysis for error-driven improvements
- **ContextOptimizer**: Smart context selection with 70% token reduction

### Tracking Layer
- **FeatureTracker**: Maturity levels, cooldown, category coverage
- **FeatureGapAnalyzer**: Priority categories per file
- **FeatureDeduplicator**: Prevents duplicate features
- **IdempotencyChecker**: SHA256 hash of file+description
- **ImprovementMemory**: SQLite database of all improvement attempts

### Integration Layer
- **CodeIntegrator**: Body-only AST replacement
- **StalenessGuard**: SHA256 file snapshots
- **ImportResolver**: Auto-detect missing imports
- **NoOpDetector**: AST comparison
- **TestValidator**: Automated pytest and syntax validation

### Logging
- **LLMLogger**: Consolidated session logs (10MB rotation, 7-day cleanup)
- **System logs**: Per-component JSON logs
- **Error logs**: Analyzed by ErrorPrioritizer for improvement targeting

---

## Policy Enforcement

### Controller Enforces (NOT LLM):
- File selection (autonomous mode)
- Category constraints
- Size limits (80 lines, single method)
- Cooldown periods
- Protected interfaces
- Method existence
- Abstract method safety
- Constructor restrictions

### LLM Handles:
- Semantic mapping (intent-driven mode)
- Feature selection (within allowed categories)
- Code implementation (within constraints)

---

## Risk Scoring

**Formula**: `risk_weight * 0.4 + (blast_radius/10) * 0.3 + (is_core ? 0.3 : 0)`

**Factors**:
- Failure history (temporal decay: 10% per 30 days, capped at 0.8)
- Blast radius (direct + transitive dependents)
- Core module flag
- Multiplicative escalation (core + high blast = 1.5x)

**Early rejection**: Skip if early_risk > 0.7 (before LLM call)

---

## Constraints for Qwen 14B

### Small Block Strategy:
- Max 80 lines per modification
- Single method only
- Body-only replacement (preserves structure)

### Deterministic Selection:
- Autonomous mode uses scoring, not LLM
- LLM only for semantic tasks

### Strict Validation:
- 12+ validation gates before acceptance
- Hard fails on: empty methods, placeholders, async, caching, vague features

### Failure Learning:
- Classifies failures (5 types)
- Baseline failure = immediate stop
- No blind retries

---

## Protected Files
- `core/immutable_brain_stem.py`
- `tools/tool_interface.py`
- `tools/tool_result.py`
- `core/config_manager.py`
- All files in `updater/` (high blast radius)

---

## Maturity Levels
- **Immature** (<3 features): Priority score +50
- **Growing** (3-5 features): Priority score +20
- **Mature** (6-8 features): Priority score +0
- **Complete** (9+ features): Cooldown 5 iterations

---

## Test Strategy
- 95 passing tests (10 broken tests skipped)
- Baseline gate before loop start
- Coverage delta check (rejects if drops >2%)
- Sandbox isolation (temp directory)
- Timeout: 120s

---

## Limitations
- **Cannot create new tools** (only modify existing)
- **Cannot modify multiple methods** (single method only)
- **Cannot do large refactors** (max 80 lines)
- **Cannot break interfaces** (abstract methods protected)
- **14B model constraints** (small context, formatting fragile)

---

## Success Metrics
- Baseline healthy: ✅
- Deterministic selection: ✅
- Category enforcement: ✅
- No TTL caching spam: ✅
- No async for subprocess: ✅
- Failure classification: ✅
- Protected interfaces: ✅

---

## Architecture Strengths
1. **Hybrid improvement engine** (80% success rate vs 50%)
2. **Error-driven targeting** (prioritizes files with most errors)
3. **Memory system** (prevents repeating failed changes)
4. **Token optimization** (70% reduction via context optimizer)
5. **Automated validation** (syntax + test checks before applying)
6. **Stable feedback signal** (baseline gate)
7. **Deterministic evaluation** (policy in controller)
8. **Small model optimized** (small blocks, body-only)
9. **Failure learning** (temporal decay, classification)
10. **Multi-layer validation** (12+ gates)
11. **Safe rollback** (git + manual backups)
12. **Modern UI** (glassmorphism, real-time updates, voice input)
13. **Lazy initialization** (avoids circular dependencies)

## Architecture Weaknesses
1. **AST strips formatting** (should use CST/libcst)
2. **No test generation** (relies on existing tests)
3. **Cannot create new files** (modification only)
4. **Formatting fragile** (zero-indent prompts)
5. **14B model limits** (context, reasoning depth)
6. **Hybrid engine dependencies** (requires pytest, log files)

---

## Data Flow

### User Interaction Flow
```
User (React UI) → WebSocket/REST API → FastAPI Server → Agent Core
                                                        ↓
                                    Tool Registry → Specific Tool → Execution
                                                        ↓
                                    Safety Validation (BrainStem)
                                                        ↓
                                    Result → API → UI (Toast/Chat)
```

### Hybrid Improvement Flow (Primary - 80% Success)
```
Trigger → HybridImprovementEngine
              ↓
          ErrorPrioritizer → Analyze logs → Priority files (by error count)
              ↓
          ContextOptimizer → Extract relevant code → 70% token reduction
              ↓
          ImprovementMemory → Check past attempts → Avoid repeating failures
              ↓
          LLMClient → Generate improvement proposal
              ↓
          TestValidator → Syntax check + pytest
              ↓
      [Pass] → AtomicApplier → Apply changes → ImprovementMemory.record()
      [Fail] → Iterate with error feedback (max 3x) → ImprovementMemory.record()
```

### Evolution Controller Flow (Autonomous)
```
Trigger → EvolutionController.run_evolution_cycle()
              ↓
          BaselineHealthChecker → Syntax + imports + tests
              ↓
          SelfReflector.analyze_system()
              ↓
              ├─→ Detect long methods (>80 lines)
              ├─→ Find code duplication
              ├─→ Identify capability gaps
              └─→ Detect missing abstractions
              ↓
          InsightEnricher → Convert metrics to concrete facts
              ↓
              ├─→ Extract duplicate blocks
              ├─→ Identify pattern types (header, payload, error, etc.)
              └─→ List all methods in file
              ↓
          LLMClient._generate_proposal() → Propose evolution
              ↓
              ├─→ Types: micro_patch, structural_upgrade, tool_extension, new_tool
              ├─→ Constraints: Single file, max 3 methods, no interface changes
              └─→ Validation: AST checks, structural constraints, risk scoring
              ↓
          ASTValidator → Validate against actual code structure
              ↓
          _execute_proposal() → Route by type
              ↓
              ├─→ _execute_refactoring()
              ├─→ _execute_extension()
              ├─→ _execute_patch()
              └─→ _execute_new_tool()
              ↓
          _extract_method_code() → Read actual method content (prevents hallucination)
              ↓
          ProposalGenerator → Generate code with real context
              ↓
          AtomicApplier → Apply changes
              ↓
          GrowthBudget.increment_cycle()
```

### Code Generation Pipeline (Detailed)
```
Task → ProposalGenerator.generate_proposal()
          ↓
      StepPlanner → Break into 1-3 steps
          ↓
      [1 step] → Single-shot generation
      [2+ steps] → Incremental generation
          ↓
      OrchestratedCodeGenerator.generate_code()
          ↓
          ├─→ Extract method name from request
          │   ├─→ Regex patterns: "the X method", "named `X`", "called X"
          │   ├─→ Blacklist: common words (method, function, helper, etc.)
          │   └─→ Explicit failure if extraction fails (no silent fallback)
          │
          ├─→ Check if method exists
          │   ├─→ [Exists] → Rewrite strategy
          │   └─→ [New] → Insert strategy
          │
          ├─→ LLMClient._call_llm()
          │   ├─→ Refactoring: max_tokens=4096 (both methods)
          │   ├─→ Other: max_tokens=3072
          │   └─→ Temperature=0.2 (deterministic)
          │
          ├─→ Parse LLM response
          │   ├─→ Extract code blocks
          │   ├─→ Handle multiple methods (refactoring)
          │   └─→ Validate structure
          │
          └─→ OutputValidator.validate_method_code()
              ├─→ AST parse
              ├─→ ast.walk() to find functions (including nested)
              ├─→ Validate signatures, return types
              └─→ Check for placeholders/TODOs
          ↓
      [Valid] → Return complete file content
      [Invalid] → Return None (explicit failure)
          ↓
      PatchGenerator.generate_patch()
          ↓
          ├─→ Compare old vs new file
          ├─→ Create FILE_REPLACE patch
          └─→ Include full file content
          ↓
      AtomicApplier.apply_update()
          ↓
          ├─→ Backup original file
          ├─→ Write new content
          ├─→ Validate syntax
          └─→ [Fail] → Rollback from backup
```

### Standard Loop Flow (Fallback - 50% Success)
```
Baseline Check → File Selection → Feature Suggestion → Code Generation
                                                              ↓
                                        Validation Gates (12+)
                                                              ↓
                                        Sandbox Testing
                                                              ↓
                                [Pass] → Apply → Track
                                [Fail] → Classify → Retry/Skip
```

### Error-Driven Improvement Flow
```
System Logs → ErrorPrioritizer.analyze_logs()
                  ↓
              Parse log files → Extract errors by file
                  ↓
              Count errors per file → Rank by frequency
                  ↓
              Extract error patterns → Common exceptions
                  ↓
              Return priority list → Files with most errors
                  ↓
              HybridImprovementEngine → Target high-error files first
```

---

## File Structure
```
cua/
├── core/                              # Core system components
│   ├── immutable_brain_stem.py      # Safety validation (read-only)
│   ├── improvement_loop.py           # Main loop + hybrid trigger
│   ├── loop_controller.py            # Loop orchestration
│   │
│   ├── hybrid_improvement_engine.py  # Hybrid orchestrator (80% success)
│   ├── improvement_memory.py         # SQLite improvement tracking
│   ├── error_prioritizer.py          # Log analysis for targeting
│   ├── test_validator.py             # Automated validation
│   ├── context_optimizer.py          # Token optimization (70% reduction)
│   │
│   ├── evolution_controller.py       # Autonomous capability engine
│   ├── self_reflector.py             # Strategic system analysis
│   ├── insight_enricher.py           # Metrics to structural facts
│   ├── capability_graph.py           # Tool capability tracking
│   ├── growth_budget.py              # Evolution rate control
│   ├── ast_validator.py              # Proposal validation
│   │
│   ├── task_analyzer.py              # File/feature selection
│   ├── proposal_generator.py         # Code generation orchestrator
│   ├── orchestrated_code_generator.py # Main code generator
│   ├── step_planner.py               # Task decomposition
│   ├── incremental_code_builder.py   # Step-by-step code building
│   ├── output_validator.py           # Generated code validation
│   ├── patch_generator.py            # FILE_REPLACE patch creation
│   │
│   ├── sandbox_runner.py             # Isolated testing
│   ├── system_analyzer.py            # System analysis utilities
│   ├── feature_tracker.py            # Maturity tracking
│   ├── plan_history.py               # Historical tracking
│   ├── improvement_analytics.py      # Analytics and metrics
│   ├── llm_logger.py                 # LLM session logging
│   │
│   ├── baseline_health_checker.py    # Pre-loop health gate
│   ├── failure_classifier.py         # Failure type detection
│   ├── interface_protector.py        # Abstract class protection
│   ├── staleness_guard.py            # File change detection
│   └── idempotency_checker.py        # Duplicate change prevention
│
├── tools/                             # Tool system
│   ├── tool_interface.py             # Base tool class (protected)
│   ├── tool_result.py                # Result standardization (protected)
│   ├── tool_registry.py              # Dynamic tool discovery
│   ├── tool_capability.py            # Capability definitions
│   │
│   ├── file_tool.py                  # File operations
│   ├── shell_tool.py                 # Command execution
│   ├── search_tool.py                # Web search
│   ├── web_content_extractor.py      # HTML parsing (test tool)
│   └── test_web_content_extractor.py # Tool tests
│
├── planner/                           # LLM integration
│   ├── llm_client.py                 # Qwen 14B integration
│   ├── prompt_templates.py           # Optimized prompts
│   └── model_config.py               # Model configuration
│
├── updater/                           # Update system
│   ├── orchestrator.py               # Update orchestration
│   ├── atomic_applier.py             # Safe file modifications
│   ├── code_integrator.py            # AST-based code merging
│   └── rollback_manager.py           # Git/manual rollback
│
├── api/                               # FastAPI backend
│   ├── server.py                     # Main API server
│   ├── hybrid_api.py                 # Hybrid engine endpoints
│   ├── websocket.py                  # Real-time updates
│   └── routes/                       # API route modules
│
├── ui/                                # React frontend
│   ├── src/
│   │   ├── App.js                    # Main React app
│   │   ├── App.css                   # Glassmorphism styles
│   │   │
│   │   ├── components/
│   │   │   ├── ChatPanel.js          # Chat interface
│   │   │   ├── ChatPanel.css
│   │   │   ├── AgentControlPanel.js  # Agent controls
│   │   │   ├── AgentControlPanel.css
│   │   │   ├── CombinedToolsPanel.js # Tools/libs/registry
│   │   │   ├── CombinedToolsPanel.css
│   │   │   ├── Header.js             # App header
│   │   │   ├── Header.css
│   │   │   ├── Toast.js              # Notifications
│   │   │   ├── Toast.css
│   │   │   ├── CollapsibleSection.js # Collapsible UI
│   │   │   └── CollapsibleSection.css
│   │   │
│   │   └── styles/
│   │       └── variables.css         # Glassmorphism theme
│   │
│   └── package.json                  # React dependencies
│
├── docs/                              # Documentation
│   ├── ARCHITECTURE.md               # This file
│   └── CAPABILITY_GAP_TEST_PROMPTS.md # Test prompts
│
├── logs/                              # System logs
│   ├── llm_sessions/                 # LLM interaction logs
│   ├── system.log                    # Main system log
│   └── error.log                     # Error log
│
├── data/                              # Data storage
│   └── improvement_memory.db         # SQLite database
│
├── requirements.txt                   # Python dependencies
├── start.py                           # System startup
└── README.md                          # Project overview
```

---

## API Endpoints

### Main API
- `POST /agent/start` - Start agent
- `POST /agent/stop` - Stop agent
- `GET /agent/status` - Get status
- `POST /chat` - Send chat message
- `GET /tools` - List available tools
- `GET /history` - Get execution history
- `WS /ws` - WebSocket for real-time updates

### Hybrid API
- `GET /hybrid/stats` - Get improvement statistics
- `GET /hybrid/priority-files` - Get error-prioritized files
- `GET /hybrid/memory` - Get improvement memory
- `POST /hybrid/analyze` - Trigger error analysis
- `GET /hybrid/errors/{file_path}` - Get errors for specific file

---

## Technology Stack

### Backend
- **Python 3.10+**
- **FastAPI** - Web framework
- **Uvicorn** - ASGI server
- **SQLite** - Improvement memory storage
- **Qwen 14B** - LLM for code generation
- **pytest** - Test validation
- **AST** - Code parsing and manipulation

### Frontend
- **React 18** - UI framework
- **Lucide React** - Icon library
- **CSS3** - Glassmorphism styling
- **WebSocket** - Real-time communication
- **Web Speech API** - Voice input

### DevOps
- **Git** - Version control and rollback
- **Virtual Environment** - Dependency isolation
- **Log Rotation** - 10MB limit, 7-day cleanup

---

## Configuration

### Environment Variables
- `LLM_MODEL` - Model name (default: Qwen/Qwen2.5-Coder-14B-Instruct)
- `API_PORT` - Backend port (default: 8000)
- `UI_PORT` - Frontend port (default: 3000)
- `LOG_LEVEL` - Logging verbosity
- `MAX_ITERATIONS` - Improvement loop limit

### Safety Limits
- Max 80 lines per modification
- Single method only
- 3-iteration cooldown per file
- 120s test timeout
- Max 3 validation attempts
- Protected files list

---

## Deployment

### Development
```bash
pip install -r requirements.txt
python start.py
cd ui && npm install && npm start
```

### Production Considerations
- Use production ASGI server (gunicorn + uvicorn workers)
- Enable HTTPS for API
- Configure CORS properly
- Set up log aggregation
- Monitor memory usage (SQLite growth)
- Regular backup of improvement memory DB
- Rate limiting on API endpoints
