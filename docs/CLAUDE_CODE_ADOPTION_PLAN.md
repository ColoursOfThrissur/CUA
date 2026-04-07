# Claude Code Adoption Plan
**Created**: April 4, 2026  
**Status**: Phase 1, Phase 2, Phase 3, Phase 4, Phase 5, Phase 6, Phase 7, Phase 8, and Phase 9 completed  
**Purpose**: Track which ideas from `777genius/claude-code-source-code-full` are worth adopting into Forge, how we should implement them, and in what order.

---

## Scope

This document is a clean-room adoption plan based on public documentation and repository structure from:

- `777genius/claude-code-source-code-full`
- Repo README and docs for commands, tools, and subsystem layout

We should treat that repository as an ideas/reference source, not as code to copy.

This file should be the working reference for future follow-up work in this thread and in the repo.

---

## Delivery Status

### Phase 1 complete

Implemented in Forge:

- command registry skeleton under `application/commands/`
- `/status` slash command
- `/doctor` slash command
- `GlobTool`
- `GrepTool`
- command and search-tool unit coverage

### How Phase 1 helps

- gives Forge a stable slash-command entry seam for system-level workflows
- makes health and diagnostics faster to run and easier to trust
- reduces shell dependence for repo inspection by giving the planner dedicated search tools
- prepares the architecture for later `/review`, `/session`, `/memory`, and permission work

### Phase 2 complete

Implemented in Forge:

- persistent task artifact model and service
- task artifact persistence in `cua.db`
- execution-engine integration for tracked workflow state
- `/session`, `/summary`, `/export`, and `/resume` slash commands
- session workflow service for summary/export/resume behavior
- session router endpoints for summary, export, and resume
- unit coverage for task artifact persistence and session workflow commands

### How Phase 2 helps

- gives long-running work a durable workflow object instead of relying on transient in-memory state
- makes approval flows resumable by restoring pending plans from persisted task artifacts
- makes session inspection/export much more useful because messages and tracked tasks now travel together
- provides the architecture base for future review queues, permissions, and richer session UX

### Phase 3 complete

Implemented in Forge:

- command-level permission policy in the session permission gate
- dispatch-time permission checks and command execution logging
- `/review` workspace diff review command
- `/security-review` security-focused diff review command
- `/mcp` runtime MCP adapter summary command
- `/skills` runtime skill registry summary command
- unit coverage for review, MCP, skills, and permission-denial command flows

### How Phase 3 helps

- makes slash commands safer by giving them an explicit policy layer instead of implicit trust
- packages review behavior into dedicated commands so operator workflows are faster and more repeatable
- exposes live MCP and skill state directly in chat, which makes runtime inspection simpler during debugging
- creates the right control surface for later permission UX and richer command governance

### Phase 4 complete

Implemented in Forge:

- read-only Forge MCP server mode in `mcp_server/forge_mcp_server.py`
- inspection tools for health, sessions, task artifacts, skills, recent executions, observability summary, and configured MCP servers
- stdio JSON-RPC request handling for MCP-compatible clients
- unit coverage for MCP tool listing, data inspection, and JSON-RPC request handling

### How Phase 4 helps

- lets other MCP-capable agents inspect Forge through a stable read-only surface instead of scraping internal files or APIs directly
- exposes high-value runtime state like sessions, tasks, skills, and observability counts in a composable agent-to-agent format
- creates a safer extension seam because the first MCP surface is inspect-only, not mutation-heavy
- gives us an integration layer that can grow before we commit to a broader plugin marketplace design

### Phase 5 complete

Implemented in Forge:

- explicit user- and project-scoped memory notes in `cua.db`
- `/memory` command surface for overview, list, search, and save flows
- deterministic session compaction via `/compact`
- session compaction persistence through `SessionWorkflowService`
- normalized diff payload generation for review and future approval UX reuse
- session compact endpoint in the session router
- unit coverage for scoped memory, compaction, and diff payload formatting

### How Phase 5 helps

- turns memory into an explicit product surface instead of a mostly internal implementation detail
- gives long sessions a safe way to shrink context while preserving the important recent turns and a durable summary
- feeds better reusable memory back into planning through the unified memory layer
- creates a backend diff contract that future review, approval, and staging UI can all share instead of reparsing patches in multiple places

### Phase 6 complete

Implemented in Forge:

- shared diff viewer component for chat outputs, approval flows, history details, code preview, and staging preview
- frontend/client diff payload normalization to match the backend diff contract
- `/worktree` command for read-only git worktree readiness checks
- worktree readiness service for future isolated agent execution
- normalized diff payload returned from plan-history detail lookups
- unit coverage for worktree readiness command and service behavior

### How Phase 6 helps

- makes diff rendering a reusable UI primitive instead of a collection of one-off patch views
- keeps review, approval, and history workflows visually aligned around the same payload shape
- creates a safer path toward isolated git work because Forge can now report whether the repository state is suitable before taking action
- reduces architecture risk by shipping inspection and readiness first, then isolated execution later

### Phase 7 complete

Implemented in Forge:

- `/plan` and `/ultraplan` approval-gated deep planning command flow
- deeper planning prompt guidance and larger past-plan retrieval for explicit deep-planning mode
- explicit memory maintenance service plus `/memory maintain`
- background memory maintenance loop wired into runtime startup and shutdown
- readiness-gated `/worktree create <label>` command backed by actual git worktree provisioning service
- unit coverage for deep planning prompt guidance, worktree creation service, and new command flows

### How Phase 7 helps

- gives operators a plan-first workflow that asks for a stronger decomposition before any execution starts
- keeps explicit memory stores from drifting upward in duplicate low-value notes over time
- upgrades worktree isolation from a readiness report to a real bounded provisioning path
- preserves safety by refusing worktree creation when the repository state is not clean enough for isolation

### Phase 8 complete

Implemented in Forge:

- worktree lifecycle management with list and remove support in `WorktreeTaskService`
- `/worktree list` and `/worktree remove <label>` command flows
- worktree lifecycle API endpoints in `api/rest/system/worktree_router.py`
- `/plan isolated <goal>` flow that prepares and persists a managed worktree execution profile
- workflow-metadata preservation across task artifacts and approval responses
- session overlay controls for summary, resume, compact, export, memory maintenance, doctor, and worktree operations
- chat welcome shortcuts for `/doctor`, `/memory maintain`, `/worktree`, and deep-planning drafts
- unit coverage for isolated planning and worktree lifecycle behavior

### How Phase 8 helps

- moves worktree isolation from one-shot provisioning into a manageable lifecycle with inspection and cleanup
- attaches isolated workspace preparation to approval-gated planning so the workflow object knows which repo copy it was prepared for
- exposes planning and maintenance controls directly in the UI, which reduces dependence on memorized slash commands
- keeps the isolation story safer by separating lifecycle governance from any future automated multi-agent execution

### Phase 9 complete

Implemented in Forge:

- worktree-aware execution routing for bounded repo tools in `WorktreeExecutionService`
- execution-engine integration that re-roots isolated-plan file, search, and shell working paths into the prepared worktree
- workflow-metadata persistence tests for task artifacts and restored plans
- active task UI visibility for isolated execution mode and target worktree path
- approval-card visibility for isolated plan targets before execution begins
- unit coverage for worktree execution routing and workflow-metadata round trips

### How Phase 9 helps

- turns isolated planning into an actual execution contract for repo-facing tools instead of leaving it as metadata only
- keeps file reads, writes, search, and shell-based repo commands bounded to the prepared worktree for isolated plans
- makes active execution safer to reason about because operators can see which isolated workspace a task is using
- preserves isolated execution context across approval and restore flows so resumability stays intact

### Phase 10 complete

Implemented in Forge:

- persisted managed-worktree metadata for creation time, last activity, and routed execution activity
- cleanup recommendation analysis on worktree list responses with idle-age based governance signals
- worktree policy guidance service for when isolation is optional, suggested, or required
- `/plan` isolation guidance for non-isolated deep plans plus a policy endpoint in `api/rest/system/worktree_router.py`
- richer session worktree UI for age, idle time, and cleanup recommendations
- expanded task UI with recent task history plus isolated execution policy/worktree context beyond the active task card
- unit coverage for worktree lifecycle metadata, cleanup recommendations, routed activity tracking, and isolation policy guidance

### How Phase 10 helps

- turns managed worktrees into governed assets instead of anonymous directories
- gives operators clear cleanup signals before any cleanup automation is introduced
- makes isolation policy visible during planning, not only after execution starts
- broadens isolated-execution visibility into recent task history so teams can understand past execution context more easily

### Phase 11 complete

Implemented in Forge:

- reviewed cleanup helpers for stale managed worktrees through preview/apply cleanup flows
- stronger deep-planning guidance that recommends `/plan isolated <goal>` when isolation policy is `required` and readiness is green
- durable `worktree_events` observability stream for create/remove/cleanup/activity/preparation lifecycle events
- session export support for related worktree lifecycle history
- observability and MCP summary visibility for worktree event counts and inspection
- bounded worktree handoff prototype with explicit owner, purpose, lease timing, and cleanup expectation
- worktree handoff API and slash-command flows for assign, release, and list
- session worktree UI visibility for active handoffs and release actions

### How Phase 11 helps

- closes the loop from isolated plan preparation to cleanup and explicit ownership
- makes future parallel or delegated work safer because a worktree can now be handed off with clear responsibility
- improves auditability by keeping lifecycle and handoff history in the same observability/export surfaces

### Adoption status

The planned Claude Code-inspired adoption roadmap is now complete for Forge.

Deferred by choice:

- plugin-style extension surfaces remain intentionally deferred
- full autonomous multi-agent execution is still beyond this adoption plan and should be treated as a separate roadmap

Suggested release tag after this adoption pass:

- `v1.1.0`

Plugin-style extension surfaces should stay deferred until the command, permission, and MCP integration layers mature further.

---

## What Stands Out In That Repo

The strongest ideas visible from the repository and its docs are:

- A first-class command system with typed commands
- A very broad slash-command UX surface
- Explicit tool permission scoping per command
- Strong session/context controls like compact, resume, export, summary
- A structured task/todo artifact
- Dedicated search/file tools like glob and grep
- Diagnostics commands like `/doctor` and `/status`
- MCP as both a consumer layer and an explorer/integration surface
- A plugin/skills management layer presented as product features

Useful source references:

- Repo README: <https://github.com/777genius/claude-code-source-code-full>
- Commands doc: <https://github.com/777genius/claude-code-source-code-full/blob/main/docs/commands.md>
- Tools doc: <https://github.com/777genius/claude-code-source-code-full/blob/main/docs/tools.md>
- Collection repo: <https://github.com/chauncygu/collection-claude-code-source-code>
- Yasas mirror repo: <https://github.com/yasasbanukaofficial/claude-code>

---

## Additional Review: `collection-claude-code-source-code`

This repository is more useful than a plain mirror because it bundles multiple lines of follow-on work:

- a collected source snapshot
- an annotated/decompiled tree
- `claw-code`, a Python clean-room rewrite workspace
- `nano-claude-code`, a minimal Python reimplementation that has already packaged several useful product ideas

### What is materially useful from this repo

The strongest incremental ideas come from `nano-claude-code`, not from the raw leaked-source mirrors:

- dual-scope persistent memory with user scope and project scope
- explicit memory tools with save, delete, search, and list
- skill execution with argument substitution
- fork vs inline skill execution modes
- typed sub-agents with dedicated roles
- git worktree isolation for sub-agents
- automatic context compression with both cheap truncation and model-generated compact summaries
- built-in diff rendering for write/edit operations
- plugin-style tool registration through a central registry
- session persistence and slash-command ergonomics

Useful public references:

- collection repo overview: <https://github.com/chauncygu/collection-claude-code-source-code>
- `nano-claude-code` features and architecture: <https://github.com/chauncygu/collection-claude-code-source-code/tree/main/nano-claude-code>
- `claw-code` clean-room rewrite framing: <https://github.com/chauncygu/collection-claude-code-source-code/tree/main/claw-code>

### What it changes in our plan

This repo reinforces and sharpens several items already in scope:

1. Dual-scope memory should move higher in priority
   Forge already has memory systems, but `nano-claude-code` makes the product contract clearer:
   - user-level memory
   - project-level memory
   - explicit memory listing/search/update UX
   - compact memory index injected into planning context

2. Context compression should become a first-class feature
   Their "snip + auto-compact" split is good product design:
   - cheap deterministic truncation for stale heavy outputs
   - model-generated summary only when needed

3. Worktree-isolated agents are worth planning explicitly
   This is one of the strongest clean-room ideas in the collection repo and is especially relevant for Forge because it already has multi-step execution and code-generation flows.

4. Skills should support argument substitution and execution mode
   Forge already has strong skills, but this suggests a useful upgrade:
   - inline skill execution in current context
   - forked skill execution in isolated context
   - richer skill metadata

5. Diff view deserves to be productized
   Forge already has some preview surfaces, but a unified git-style diff view for edits and generated changes would improve operator confidence.

### New adoption items from this repo

#### 9. Dual-Scope Memory Contract

### Why

Forge has memory internals already, but this repo demonstrates a very legible product model: user memory vs project memory, both inspectable and searchable.

### What to add

- explicit memory scopes
- explicit memory commands and UI
- memory index artifact for prompt injection
- staleness markers and freshness review UX

### Proposed implementation

- extend the existing memory layer to expose `user` and `project` scope directly
- add `/memory`, `/memory search`, `/memory list`, `/memory save` commands
- build a compact memory index artifact for planning prompt injection

### Candidate files

- `infrastructure/persistence/file_storage/unified_memory.py`
- `infrastructure/persistence/file_storage/strategic_memory.py`
- `application/services/skill_context_hydrator.py`
- future command registry files

#### 10. Context Compression

### Why

This is one of the clearest practical gaps between Forge's backend strength and operator ergonomics.

### What to add

- deterministic truncation of stale bulky tool outputs
- automatic compact summary generation when context pressure crosses a threshold
- visible compaction markers in session UI

### Proposed implementation

- add a compaction service that runs before planner/LLM calls
- separate "truncate old output" from "summarize old conversation"
- expose a manual `/compact` command and an automatic threshold-based compactor

### Candidate files

- `api/chat_helpers.py`
- `application/services/context_optimizer.py`
- `infrastructure/persistence/file_storage/conversation_memory.py`
- `ui/src/components/SessionManagement.js`

#### 11. Worktree-Isolated Sub-Agents

### Why

This is a high-value implementation idea for safe parallel coding work.

### What to add

- optional `worktree` isolation mode for sub-agents
- auto-cleanup for no-op worktrees
- branch/report metadata returned to the UI

### Proposed implementation

- extend Forge's agent/task model to allow isolated git worktree execution
- use it first for code-generation, review, and test-focused worker tasks
- keep it opt-in behind explicit policy and local-git checks

### Candidate files

- future multi-agent or task-execution command layer
- `application/use_cases/autonomy/autonomous_agent.py`
- `application/use_cases/tool_lifecycle/tool_creation_flow.py`
- `application/use_cases/tool_lifecycle/tool_evolution_flow.py`

### Caution

This should only be implemented after command permissions and task orchestration are more explicit.

#### 12. Diff View As A Core UX Primitive

### Why

This repo's minimal implementation makes a strong case for treating diff rendering as a first-class workflow primitive.

### What to add

- unified diff rendering for edits, generated code, and approval flows
- reusable backend diff format
- consistent UI for patch preview across tool creation/evolution/manual edits

### Candidate files

- `ui/src/components/CodePreviewModal.js`
- `ui/src/components/StagingPreviewModal.js`
- `ui/src/components/TaskManagerPanel.js`

### Conclusion on this repo

The collection repo is worth using as a reference source mainly because `nano-claude-code` and `claw-code` convert the leak discussion into actionable clean-room product ideas. For Forge, the most adoptable deltas are:

- dual-scope memory
- context compression
- worktree-isolated agents
- richer skills
- diff-first UX

---

## Additional Review: `yasasbanukaofficial/claude-code`

This repo appears to be primarily a documented mirror/back-up of the leaked TypeScript skeleton rather than a clean-room reimplementation or opinionated product evolution.

### What is useful from this repo

Its README is still useful because it highlights several distinctive concepts in the leaked Claude Code internals:

- the `buddy` companion subsystem
- "undercover mode" for preventing identity/internal-info leakage
- the "dream" system for memory consolidation
- KAIROS as an always-on proactive assistant
- ULTRAPLAN as a deep planning mode offload

Useful public reference:

- repo README: <https://github.com/yasasbanukaofficial/claude-code>

### What is actually relevant to Forge

Most of these are not immediate adoption targets, but a few ideas are strategically interesting:

#### Worth considering later

- background memory consolidation
  This maps loosely to the "dream" idea and could become an offline maintenance task for Forge memory quality.

- deeper planning mode
  Forge already has planning and autonomy. A named "ultraplan" style mode could simply be a more explicit high-effort planning profile rather than a different architecture.

- stronger identity/privacy guardrails
  The "undercover mode" concept reinforces the value of prompt-layer and output-layer rules that prevent accidental disclosure of internal codenames, hidden instructions, or system metadata.

#### Not worth prioritizing

- buddy / Tamagotchi companion system
- brand-specific lore or internal codename handling
- features that depend on Anthropic product internals

### New adoption items inspired by this repo

#### 13. Background Memory Consolidation

### Why

The repo's description of a background "dream" style memory maintenance service reinforces an idea that already fits Forge well: maintenance work should improve memory quality without blocking interactive use.

### What to add

- periodic memory cleanup/consolidation
- stale memory pruning
- merge duplicate notes or repeated observations
- generate compact durable summaries for long-running projects

### Proposed implementation

- run as a scheduled maintenance use case, not as an always-on autonomous actor
- keep all writes observable and reviewable
- store before/after summaries in observability logs

### Candidate files

- `application/use_cases/improvement/improvement_scheduler.py`
- `infrastructure/persistence/file_storage/unified_memory.py`
- `infrastructure/persistence/file_storage/strategic_memory.py`

#### 14. Explicit High-Effort Planning Mode

### Why

The repo's "ULTRAPLAN" framing is useful as a product concept even if we do not mirror the implementation.

### What to add

- a named high-effort planning mode
- deeper decomposition
- stronger verification and assumptions surfacing
- optional human approval before execution

### Proposed implementation

- expose as `/plan` or `/ultraplan`
- map it to stronger planning hints and larger context allowance
- reuse existing planner and approval pathways

### Candidate files

- `application/use_cases/planning/task_planner_clean.py`
- `application/planning/create_plan.py`
- future command registry files

### Conclusion on this repo

This repo has much less direct implementation value than the collection repo. It is mostly useful as a lens on a few interesting concepts:

- background memory maintenance
- explicit deep-planning UX
- stronger privacy/identity guardrails

It should not materially change Forge's roadmap by itself.

---

## Adoption Principles

We should only adopt ideas that fit Forge's current architecture:

- Reuse Forge's existing planner, execution engine, tool orchestrator, skill system, MCP integration, session state, and UI overlays
- Prefer additive features over architecture rewrites
- Keep the current FastAPI + React + Python runtime as the system of record
- Build clean-room equivalents with our own naming, contracts, and tests
- Prioritize features that improve reliability, operator control, and user workflow

We should avoid:

- Rebuilding the entire product as a terminal-first CLI clone
- Copying Anthropic-specific workflows or proprietary assumptions
- Pulling in bridge/mobile/teleport features too early
- Replacing strong existing core components just to mirror another product's layout

---

## Recommended Priorities

### Tier 1: Build Soon

1. Command registry and slash-command layer
2. `/doctor` diagnostics workflow
3. Structured todo/task artifact
4. Session compaction, summary, export, and resume
5. Dedicated `GlobTool` and `GrepTool`
6. Explicit permission rules at the command layer

### Tier 2: Good Follow-Up

1. `/review` and `/security-review`
2. `/mcp`, `/skills`, `/permissions`, `/session` management UX
3. MCP server mode for Forge itself
4. Richer status/cost/usage reporting

### Tier 3: Defer

1. IDE bridge system
2. Device handoff like desktop/mobile/teleport
3. Deep terminal theming and keybinding work
4. Notebook editing support
5. Full plugin marketplace before command infrastructure is stable

---

## Current Forge Strengths To Build On

Forge already has strong foundations that make adoption easier:

- Skill routing and execution context hydration
- A planner and execution engine with retries, replanning, and verification
- Tool orchestration with validation, normalization, and circuit breaking
- Session memory and persistent conversation state
- MCP configuration and runtime loading
- Session/status UI, observability, and task panels

Key local entry points:

- `api/server.py`
- `api/chat_helpers.py`
- `application/use_cases/tool_lifecycle/tool_orchestrator.py`
- `application/use_cases/execution/execution_engine.py`
- `application/state/state_registry.py`
- `application/services/skill_registry.py`
- `domain/policies/session_permissions.py`
- `ui/src/components/SessionManagement.js`
- `ui/src/components/TaskManagerPanel.js`
- `ui/src/components/MCPPanel.js`

---

## Forge Integration Architecture

This section maps each planned adoption to the actual Forge architecture so implementation work lands in the right layer.

### Existing seams we should reuse

#### Chat and request entry

Primary request entry already lives in:

- `api/server.py`
- `api/chat_helpers.py`
- `api/chat/*`

This is the correct place to intercept:

- slash commands
- session-scoped UI actions
- compact/resume/export command routing
- command-specific permission checks before normal skill routing

#### Planning and execution

The execution backbone already exists in:

- `application/planning/create_plan.py`
- `application/use_cases/planning/task_planner_clean.py`
- `application/use_cases/execution/execution_engine.py`
- `application/state/state_registry.py`
- `application/use_cases/tool_lifecycle/tool_orchestrator.py`

This is where we should integrate:

- task artifacts
- context compaction inputs
- planner-visible memory indexes
- command-triggered execution plans
- richer review and doctor workflows

#### Memory

Memory is already split across multiple stores:

- `infrastructure/persistence/file_storage/conversation_memory.py`
- `infrastructure/persistence/file_storage/memory_system.py`
- `infrastructure/persistence/file_storage/strategic_memory.py`
- `infrastructure/persistence/file_storage/unified_memory.py`

This is the right place to add:

- dual-scope memory
- memory search/list/save commands
- background memory consolidation
- compact memory indexes for prompt injection

#### Permissions and policy

Current policy entry exists in:

- `domain/policies/session_permissions.py`
- `domain/policies/immutable_brain_stem.py`
- `domain/policies/refactoring_permissions.py`

This is where command-level permissions should live.

#### Session and task product surfaces

The UI/API surfaces already exist but are incomplete:

- `api/rest/config/session_router.py`
- `api/rest/system/task_manager_router.py`
- `application/managers/task_manager_stub.py`
- `ui/src/components/SessionManagement.js`
- `ui/src/components/TaskManagerPanel.js`

This is the correct seam for:

- session resume/export/summary/compact
- task artifacts and task board state
- pending plan/task visualization
- diff and staging previews

#### Tools and runtime registration

Tool addition points already exist in:

- `tools/`
- `tools/capability_registry.py`
- `api/bootstrap.py`

This is where `GlobTool`, `GrepTool`, `TodoTool`, and future memory tools should be added.

---

## How Each Adoption Fits Into Forge

## 1. Command Registry

### Where it belongs

Add a new application layer for commands:

- `application/commands/command_models.py`
- `application/commands/command_registry.py`
- `application/commands/dispatch_command.py`
- `application/commands/builtin/`

### How it integrates

Flow:

1. `api/chat_helpers.py` checks whether a message starts with `/`
2. if yes, it routes to `dispatch_command.py`
3. command handlers either:
   - return local data directly
   - invoke existing use cases
   - return UI/navigation metadata
4. if no command matches, Forge continues with current skill routing

### Why this fits cleanly

It adds a new entry layer without rewriting the planner, skill system, or tool orchestrator.

---

## 2. `/doctor` and system diagnostics

### Where it belongs

Backend:

- `application/use_cases/system/run_doctor.py`
- optionally `application/dto/doctor_dto.py`

API/UI:

- route through the command registry
- expose result cards in `ui/src/components/ChatPanel.js`
- optionally add a detail panel near `ui/src/components/MCPPanel.js`

### How it integrates

`run_doctor.py` should gather health from:

- runtime state in `api/server.py`
- MCP state from `api/rest/config/mcp_router.py`
- memory/session state from `api/rest/config/session_router.py`
- credential store from `infrastructure/persistence/credential_store.py`
- scheduler state from `application/use_cases/improvement/improvement_scheduler.py`
- metrics scheduler from `infrastructure/metrics/scheduler.py`

### Architecture note

This should be a read-only orchestration use case, not a tool.

---

## 3. Structured task artifact

### Where it belongs

Domain and application:

- `domain/entities/task_artifact.py`
- `application/services/task_artifact_service.py`

Execution integration:

- `application/use_cases/execution/execution_engine.py`
- `application/state/state_registry.py`

API/UI:

- `api/rest/system/task_manager_router.py`
- `application/managers/task_manager_stub.py` should be replaced with a real task manager
- `ui/src/components/TaskManagerPanel.js`

### How it integrates

The current `TaskManagerPanel` is wired to a task-manager contract, but the runtime only provides `TaskManagerStub`.

That means the clean path is:

1. define a real task artifact model
2. implement a real manager behind the existing router contract
3. feed plan creation and execution updates into it
4. keep `StateRegistry` as the execution-trace source of truth
5. derive UI task state from the task artifact service

### Architecture note

Do not overload `ExecutionPlan` itself with persistent task-board concerns. Keep:

- `ExecutionPlan` as runtime plan
- `TaskArtifact` as persistent product/workflow object

---

## 4. Session compaction, summary, export, resume

### Where it belongs

Memory/session services:

- `infrastructure/persistence/file_storage/conversation_memory.py`
- `infrastructure/persistence/file_storage/memory_system.py`
- `infrastructure/persistence/file_storage/unified_memory.py`

Command/API/UI:

- command layer for `/compact`, `/summary`, `/export`, `/resume`
- `api/rest/config/session_router.py`
- `ui/src/components/SessionManagement.js`

### How it integrates

- `compact` should summarize and prune chat-heavy session context
- `summary` should produce a durable session summary artifact
- `export` should serialize messages, plans, tool history, and results
- `resume` should restore pending plans, active goals, and memory context

### Architecture note

Do not make `ConversationMemory` responsible for all resume logic. It should stay as storage. Resume orchestration should live in a dedicated use case, for example:

- `application/use_cases/session/resume_session.py`

---

## 5. Dual-scope memory

### Where it belongs

Memory layer:

- extend `infrastructure/persistence/file_storage/unified_memory.py`
- extend `infrastructure/persistence/file_storage/memory_system.py`
- optionally add `infrastructure/persistence/file_storage/user_memory.py`
- optionally add `infrastructure/persistence/file_storage/project_memory.py`

Command layer:

- `/memory`
- `/memory list`
- `/memory search`
- `/memory save`

Planner integration:

- `application/planning/create_plan.py`
- `application/services/skill_context_hydrator.py`

### How it integrates

Forge already has memory internals, so this should be a surfacing and indexing improvement:

- keep existing stores
- add explicit scope metadata
- expose user/project scoped search
- inject a compact memory index into planning prompts

### Architecture note

This should evolve existing memory, not replace it.

---

## 6. Context compression

### Where it belongs

Application layer:

- `application/services/context_compactor.py`

Integration points:

- `api/chat_helpers.py`
- `application/planning/create_plan.py`
- `application/use_cases/autonomy/autonomous_agent.py`
- `infrastructure/persistence/file_storage/conversation_memory.py`

UI:

- `ui/src/components/SessionManagement.js`
- optional markers in `ui/src/components/ChatPanel.js`

### How it integrates

Two-stage design:

1. deterministic compaction
   - trim stale tool outputs
   - shrink repeated messages
   - preserve recent + important artifacts

2. semantic compaction
   - generate a durable compact summary only when thresholds are exceeded

### Architecture note

This should happen before prompt building, not inside the LLM gateway itself.

---

## 7. `GlobTool` and `GrepTool`

### Where they belong

New tools:

- `tools/glob_tool.py`
- `tools/grep_tool.py`

Registration:

- `api/bootstrap.py`
- `tools/capability_registry.py`

Planner preference:

- `application/services/skill_selector.py`
- `application/use_cases/planning/task_planner_clean.py`

### How they integrate

These tools should become the planner’s preferred path for:

- file discovery
- repo search
- content search
- codebase inspection

This reduces shell dependence and makes results easier to validate and summarize.

---

## 8. Command-level permissions

### Where it belongs

Policy:

- extend `domain/policies/session_permissions.py`

Command layer:

- each command definition gets `allowed_tools`, `risk_level`, and optional `requires_confirmation`

Chat dispatch:

- `api/chat_helpers.py`

### How it integrates

Permission evaluation order should be:

1. command-level policy
2. tool-level/session-level policy
3. existing immutable brain-stem validation

### Architecture note

Current `PermissionGate` is tool-operation-centric. We should extend it, not fork it:

- add command policies
- keep tool-operation validation as the lower-level enforcement

---

## 9. `/review` and `/security-review`

### Where they belong

New use cases:

- `application/use_cases/review/review_workspace.py`
- `application/use_cases/review/security_review.py`

Command dispatch:

- builtin command handlers

UI:

- reuse `ui/src/components/CodePreviewModal.js`
- reuse `ui/src/components/StagingPreviewModal.js`

### How they integrate

Use git diff or workspace diff as input, then format findings using the same review-first style we already expect from the assistant.

### Architecture note

This should be a command/use-case feature, not a generic tool.

---

## 10. Worktree-isolated sub-agents

### Where it belongs

Agent orchestration:

- future `application/use_cases/agents/`
- extend `application/use_cases/autonomy/autonomous_agent.py`

If implemented for coding flows:

- `application/use_cases/tool_lifecycle/tool_creation_flow.py`
- `application/use_cases/tool_lifecycle/tool_evolution_flow.py`

### How it integrates

This should be introduced as an execution mode, not as the default:

- inline mode for normal flows
- isolated worktree mode for risky or parallel coding tasks

### Architecture note

This should come only after the command/task architecture is stable.

---

## 11. MCP server mode for Forge

### Where it belongs

New package/module:

- `mcp-server/forge_mcp_server/` or equivalent

Reuse backend services from:

- `api/rest/*`
- `tools/capability_registry.py`
- observability and session services

### How it integrates

Expose Forge state through a read-only MCP surface first:

- tools
- skills
- runtime health
- session summaries
- recent executions
- observability snapshots

### Architecture note

Do not bind the MCP server directly to UI components. It should sit on top of application services.

---

## 12. Diff-first UX

### Where it belongs

Backend:

- add a normalized diff payload format

UI:

- `ui/src/components/CodePreviewModal.js`
- `ui/src/components/StagingPreviewModal.js`
- `ui/src/components/TaskManagerPanel.js`

### How it integrates

Any operation that edits code or stages generated output should emit:

- artifact metadata
- raw or structured diff
- status and approval hints

This can then be rendered consistently across tool creation, evolution, review, and manual task workflows.

---

## Concrete Architecture Additions

These are the new architecture pieces I would actually add to Forge.

### New application modules

- `application/commands/`
- `application/use_cases/system/`
- `application/use_cases/session/`
- `application/use_cases/review/`
- `application/services/context_compactor.py`
- `application/services/task_artifact_service.py`

### New domain modules

- `domain/entities/task_artifact.py`
- `domain/entities/command_definition.py`

### New tools

- `tools/glob_tool.py`
- `tools/grep_tool.py`
- `tools/todo_tool.py` or task artifact writer if tool exposure is needed

### Existing modules to extend, not replace

- `api/chat_helpers.py`
- `domain/policies/session_permissions.py`
- `application/state/state_registry.py`
- `application/planning/create_plan.py`
- `infrastructure/persistence/file_storage/unified_memory.py`
- `ui/src/components/SessionManagement.js`
- `ui/src/components/TaskManagerPanel.js`

---

## Recommended build order from an architecture perspective

1. Add command registry architecture
2. Add `/doctor` and `/status`
3. Add `GlobTool` and `GrepTool`
4. Replace task manager stub with real task artifact service
5. Add session compaction/export/resume
6. Add dual-scope memory and memory commands
7. Add command-level permissions
8. Add review commands
9. Add diff-first UX normalization
10. Add MCP server mode
11. Consider worktree-isolated sub-agents later

---

## Implementation Plan

## 1. Command Registry and Slash Commands

### Why

Forge currently has strong backend capability but lacks a unified user-facing action model. A command registry would make the product easier to operate and easier to extend.

### What to add

- A command definition model
- Command categories
- Command dispatch before general chat routing
- Command-specific permissions
- UI help and discoverability

### Suggested command types

- `PromptCommand`
  Used when the command should invoke the planner/LLM/tool chain
  Examples: `/review`, `/security-review`, `/advisor`, `/plan`

- `LocalCommand`
  Used when the command is simple and deterministic
  Examples: `/status`, `/doctor`, `/cost`, `/version`

- `UICommand`
  Used when the command mainly opens or configures UI state
  Examples: `/mcp`, `/skills`, `/session`, `/permissions`

### Proposed implementation

Backend:

- Add `application/commands/command_registry.py`
- Add `application/commands/command_models.py`
- Add `application/commands/dispatch_command.py`
- Intercept messages beginning with `/` in `api/chat_helpers.py`
- Route command execution before normal skill selection

Frontend:

- Add a slash-command help surface in chat UI
- Add command autocomplete to `ui/src/components/ChatPanel.js`

### Commands to implement first

- `/doctor`
- `/status`
- `/review`
- `/session`
- `/mcp`
- `/skills`
- `/permissions`
- `/plan`

### Tests

- command parsing tests
- permission enforcement tests
- chat dispatch tests for command vs normal message

---

## 2. `/doctor` Diagnostics

### Why

This is one of the highest-value adoptions. Forge already has enough moving pieces that a unified diagnostic report will save real debugging time.

### What `/doctor` should check

- runtime initialized
- current model configured and reachable
- tool registry load count
- skill registry load count
- MCP server states
- credential store readability
- database availability
- scheduler status
- health of critical services

### Proposed implementation

Backend:

- Add `application/use_cases/system/run_doctor.py`
- Expose a normalized doctor report via API
- Wire `/doctor` through the command registry

Frontend:

- Reuse or extend `ui/src/components/MCPPanel.js`
- Add a diagnostic card or modal

### Candidate files

- `api/server.py`
- `api/rest/system/services_router.py`
- `api/rest/config/mcp_router.py`
- `infrastructure/persistence/credential_store.py`
- `application/use_cases/improvement/improvement_scheduler.py`
- `infrastructure/metrics/scheduler.py`

### Tests

- doctor report with healthy runtime
- doctor report with degraded runtime
- command integration test

---

## 3. Structured Todo and Task Artifact

### Why

Claude Code's todo-oriented flow maps well to Forge's planner and task UI. We already have plans and step state, but not a single structured task artifact that survives across planning, execution, resume, and approval flows.

### What to add

- A canonical task artifact schema
- Planner output that can optionally emit/update task artifacts
- A `TodoTool` or task-writer service
- UI support for active task list and completion state

### Proposed task schema

- task id
- title
- source request
- status
- priority
- steps
- current step
- owner
- timestamps
- links to execution ids and artifacts

### Proposed implementation

Backend:

- Add `domain/entities/todo.py` or `domain/entities/task_board.py`
- Add `application/services/todo_service.py`
- Add `tools/todo_tool.py` if tool exposure is useful
- Persist task artifacts in file storage or SQLite

Frontend:

- Extend `ui/src/components/TaskManagerPanel.js`
- Show pending, in-progress, blocked, completed

### Candidate files

- `application/use_cases/execution/execution_engine.py`
- `application/state/state_registry.py`
- `domain/entities/task.py`
- `ui/src/components/TaskManagerPanel.js`

### Tests

- task artifact creation from plan
- status transitions from execution results
- resume from partial state

---

## 4. Session Compaction, Summary, Export, Resume

### Why

Forge already has session state and memory, but explicit controls are thin. This is a strong product improvement with relatively low architectural risk.

### Features to add

- `/compact`
- `/summary`
- `/export`
- `/resume`
- session metadata view

### Proposed implementation

- `compact`: summarize current session and trim non-critical history
- `summary`: generate a reusable summary artifact
- `export`: dump messages, plan history, tool history, and results
- `resume`: restore working state for a prior session

### Candidate files

- `infrastructure/persistence/file_storage/conversation_memory.py`
- `infrastructure/persistence/file_storage/unified_memory.py`
- `ui/src/components/SessionManagement.js`
- `api/chat_helpers.py`

### Tests

- compact preserves critical context
- export format contains expected sections
- resume restores pending or active work correctly

---

## 5. Dedicated `GlobTool` and `GrepTool`

### Why

Forge currently leans on shell and filesystem operations. Dedicated search tools would be more planner-friendly, easier to validate, and safer than shell-heavy fallback behavior.

### What to add

- `GlobTool` for file pattern search
- `GrepTool` for content search using ripgrep where available

### Proposed implementation

- Add `tools/glob_tool.py`
- Add `tools/grep_tool.py`
- Register them in bootstrap
- Add capability metadata with safe parameter schemas
- Bias the planner toward them for search tasks

### Candidate files

- `api/bootstrap.py`
- `tools/`
- `application/services/skill_selector.py`
- `application/use_cases/planning/task_planner_clean.py`

### Tests

- file matching behavior
- content search behavior
- planner preference tests where applicable

---

## 6. Command-Level Permission Rules

### Why

Forge already has policy components, but permissions are not yet surfaced as a first-class user-facing contract. Adopting that pattern would reduce ambiguity and increase safety.

### What to add

- command -> allowed tool mapping
- command -> escalation rules
- session-scoped overrides
- UI visibility based on permission state

### Proposed implementation

- Extend `domain/policies/session_permissions.py`
- Add command metadata field `allowed_tools`
- Validate at command dispatch time before tool execution
- Show permission denials in structured form

### Candidate files

- `domain/policies/session_permissions.py`
- `api/chat_helpers.py`
- future command registry files

### Tests

- command denied when disallowed tool is requested
- command allowed when session policy permits

---

## 7. `/review` and `/security-review`

### Why

This is a strong user-facing feature and matches how people already use coding agents. Forge already has the review mindset in the assistant behavior, so this is more packaging than invention.

### What to add

- `/review` for staged or workspace diff review
- `/security-review` for risk-focused review

### Proposed implementation

- Use git diff or worktree diff as input
- Route to a specialized prompt/use case
- Return structured findings first

### Candidate files

- `application/use_cases/code_review/`
- `api/chat_helpers.py`
- `ui/src/components/CodePreviewModal.js`

### Tests

- review output format
- no-findings path
- security review severity ordering

---

## 8. MCP Server Mode for Forge

### Why

Forge already consumes MCP. Exposing Forge as an MCP server would let other agents inspect or orchestrate it.

### What to expose

- list tools
- list skills
- query health
- query recent executions
- inspect plans
- inspect observability summaries

### Proposed implementation

- Add a dedicated `forge-mcp-server`
- Reuse existing API services as the backing implementation
- Keep the surface read-only first

### Candidate files

- `mcp-server/` or `tools/mcp_server/`
- `api/rest/*`
- `infrastructure/messaging/*`

### Tests

- MCP tool registration
- basic health and listing calls

---

## Proposed Delivery Order

### Phase 1

- command registry skeleton
- `/doctor`
- `/status`
- `GlobTool`
- `GrepTool`

Status: completed

Delivered in:

- `application/commands/`
- `api/chat_helpers.py`
- `tools/glob_tool.py`
- `tools/grep_tool.py`
- `api/bootstrap.py`
- `application/use_cases/planning/task_planner_clean.py`
- `tests/unit/test_command_dispatch.py`
- `tests/unit/test_search_tools.py`

### Phase 2

- structured todo/task artifact
- `/session`
- `/summary`
- `/export`
- `/resume`

Status: completed

Delivered in:

- `domain/entities/task_artifact.py`
- `application/services/task_artifact_service.py`
- `application/services/session_workflow_service.py`
- `api/chat_helpers.py`
- `application/use_cases/execution/execution_engine.py`
- `application/use_cases/autonomy/autonomous_agent.py`
- `api/rest/config/session_router.py`
- `infrastructure/persistence/sqlite/cua_database.py`
- `tests/unit/test_task_artifact_service.py`
- `tests/unit/test_command_dispatch.py`

### Phase 3

- command permissions
- `/review`
- `/security-review`
- `/mcp`
- `/skills`

Status: completed

Delivered in:

- `domain/policies/session_permissions.py`
- `application/commands/command_models.py`
- `application/commands/dispatch_command.py`
- `application/commands/builtin/system_commands.py`
- `application/use_cases/review/workspace_review.py`
- `tests/unit/test_command_dispatch.py`

### Phase 4

Status: completed

Delivered in:

- `mcp_server/forge_mcp_server.py`
- `tests/unit/test_forge_mcp_server.py`

Notes:

- Forge now exposes a read-only MCP server mode for external inspection and orchestration use cases
- plugin-style extension surface remains intentionally deferred until the policy and integration seams are stronger

### Phase 5

Status: completed

Delivered in:

- `application/services/context_compactor.py`
- `application/services/diff_payload.py`
- `infrastructure/persistence/file_storage/memory_system.py`
- `infrastructure/persistence/file_storage/conversation_memory.py`
- `infrastructure/persistence/file_storage/unified_memory.py`
- `application/services/session_workflow_service.py`
- `application/commands/builtin/system_commands.py`
- `application/use_cases/review/workspace_review.py`
- `api/rest/config/session_router.py`
- `tests/unit/test_phase5_memory_and_diff.py`
- `tests/unit/test_task_artifact_service.py`
- `tests/unit/test_command_dispatch.py`

Notes:

- Forge now has explicit dual-scope memory notes for user and project context
- session compaction is available both through slash commands and the session API
- review/security-review can now emit a normalized diff payload for future shared UI rendering

### Phase 6

Status: completed

Delivered in:

- `application/services/worktree_isolation_service.py`
- `application/use_cases/planning/plan_history.py`
- `application/commands/builtin/system_commands.py`
- `ui/src/utils/diffPayload.js`
- `ui/src/components/output/DiffViewer.js`
- `ui/src/components/output/DiffViewer.css`
- `ui/src/components/output/rendererRegistry.js`
- `ui/src/components/DiffModal.js`
- `ui/src/components/CodePreviewModal.js`
- `ui/src/components/StagingPreviewModal.js`
- `ui/src/components/HistoryViewer.js`
- `tests/unit/test_worktree_isolation_service.py`
- `tests/unit/test_command_dispatch.py`

Notes:

- Forge now uses one shared diff viewer across the main diff-oriented UI surfaces
- worktree isolation is now an explicit readiness-checked capability, but actual isolated execution is intentionally deferred to the next phase
- plan-history detail payloads can now provide normalized diff data directly to the UI

### Phase 7

Status: completed

Delivered in:

- `application/services/memory_maintenance_service.py`
- `application/services/worktree_task_service.py`
- `application/planning/create_plan.py`
- `infrastructure/llm/prompt_builder.py`
- `infrastructure/persistence/file_storage/memory_system.py`
- `infrastructure/persistence/file_storage/strategic_memory.py`
- `application/commands/builtin/system_commands.py`
- `api/bootstrap.py`
- `tests/unit/test_phase7_services.py`
- `tests/unit/test_planning_profile_context.py`
- `tests/unit/test_command_dispatch.py`

Notes:

- Forge now has an explicit deep-planning command path that stages plans for approval instead of execution
- memory maintenance is both command-invocable and background-capable through a lightweight runtime loop
- worktree creation is now real and bounded, but it is still kept behind readiness checks and not yet attached to automated sub-agent execution

### Phase 8

Status: completed

Delivered in:

- `application/services/worktree_task_service.py`
- `application/services/task_artifact_service.py`
- `application/commands/builtin/system_commands.py`
- `api/chat_helpers.py`
- `api/rest/system/worktree_router.py`
- `api/bootstrap.py`
- `ui/src/components/SessionManagement.js`
- `ui/src/components/SessionManagement.css`
- `ui/src/components/ChatPanel.js`
- `ui/src/components/ChatPanel.css`
- `ui/src/App.js`
- `tests/unit/test_command_dispatch.py`
- `tests/unit/test_phase7_services.py`

Notes:

- Forge now has list/create/remove lifecycle support for managed git worktrees instead of only readiness plus create
- isolated deep plans can prepare and persist a worktree-backed execution profile for approval-gated follow-up
- task artifacts and approval responses preserve workflow metadata so isolated-plan context survives export and resume flows
- the session overlay now exposes runtime operations and worktree controls directly, while chat welcome shortcuts surface the highest-value planning and maintenance commands

### Phase 9

Status: completed

Delivered in:

- `application/services/worktree_execution_service.py`
- `application/use_cases/execution/execution_engine.py`
- `application/services/worktree_task_service.py`
- `application/services/task_artifact_service.py`
- `ui/src/components/TaskManagerPanel.js`
- `ui/src/components/TaskManagerPanel.css`
- `ui/src/components/ChatPanel.js`
- `tests/unit/test_phase9_worktree_execution.py`
- `tests/unit/test_task_artifact_service.py`

Notes:

- isolated plans now route bounded repo-facing tool parameters into their prepared worktree instead of only carrying worktree metadata
- relative and repo-root absolute paths are re-based for `FilesystemTool`, `GlobTool`, `GrepTool`, and `ShellTool` working directories
- workflow metadata remains durable across task artifact persistence and restore flows
- operators can now see active isolated execution mode and worktree target directly in the task UI and approval card

---

## Suggested File Additions

If we execute this plan, likely new files will include:

- `application/commands/command_models.py`
- `application/commands/command_registry.py`
- `application/commands/dispatch_command.py`
- `application/use_cases/system/run_doctor.py`
- `application/services/todo_service.py`
- `tools/glob_tool.py`
- `tools/grep_tool.py`
- `tools/todo_tool.py`
- `mcp_server/forge_mcp_server.py`
- `tests/unit/test_command_registry.py`
- `tests/unit/test_doctor_command.py`
- `tests/unit/test_glob_tool.py`
- `tests/unit/test_grep_tool.py`
- `tests/unit/test_forge_mcp_server.py`

---

## Suggested Success Metrics

- users can discover and use commands without memorizing internals
- common diagnostics become one-step instead of multi-step
- planner uses search tools instead of shelling out for everything
- sessions can be compacted and resumed predictably
- tasks remain inspectable across long-running workflows
- permission denials are explicit and explainable

---

## Risks and Guardrails

### Risks

- building too much CLI-style surface too quickly
- duplicating existing skill functionality with commands
- adding UX complexity before the command model is stable
- letting plugin ideas outrun security policy

### Guardrails

- start with read-only and diagnostic commands
- keep command dispatch thin and reuse existing use cases
- define permissions before exposing destructive commands
- add tests for every new command category

---

## What Not To Do Yet

- do not rebuild Forge around a terminal UI architecture
- do not prioritize bridge/mobile/teleport features
- do not build a public plugin marketplace before permission controls are mature
- do not replace existing planning/execution primitives that already work well

---

## Next Action I Recommend

Start with a narrow implementation batch:

1. add command registry skeleton
2. implement `/doctor`
3. implement `/status` through the same command path
4. add `GlobTool`
5. add `GrepTool`
6. add tests and small chat UI affordance for slash commands

That gives Forge an immediate product upgrade without destabilizing the core runtime.
