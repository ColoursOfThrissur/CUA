# CUA Architecture Refactor Plan

## Purpose

This document defines the full-picture refactor plan for CUA before major implementation begins.

The goal is to evolve CUA from a mostly tool-centric autonomous agent into a layered system with:

- a stronger central agent
- a first-class skill layer
- tools and connectors as execution primitives
- richer gap analysis and growth logic
- output-aware UI surfaces

This is a migration plan, not a rewrite plan.

## Why This Direction

The current codebase already has meaningful foundations:

- central agent and planning paths
- tool orchestration
- tool creation and evolution
- gap tracking
- approval and validation flows
- observability
- a multi-surface UI

The main weakness is that domain behavior, routing, execution, and growth logic are still mixed together too often.

The refactor should improve:

- request understanding
- planning quality
- tool and connector routing
- missing-capability diagnosis
- creation/evolution targeting
- UI clarity for outputs and domains

The refactor should preserve:

- the current execution layer
- approval gates
- sandbox validation
- observability
- existing tool creation and evolution mechanics where still useful

## Architectural Position

The best-fit architecture for CUA is not:

- tools only
- agent only
- skills only

The target architecture is:

**Agent Core + Skills + Tools/Connectors + Growth Engine + Output UI**

This matches the current direction of modern agent systems more closely than a pure tool registry model.

## Core Design Principles

1. The main CUA agent remains the central orchestrator.
2. Skills become the primary domain abstraction.
3. Tools remain the main execution primitive for local and generated capabilities.
4. Connectors become the standard bridge to MCP servers and external applications.
5. Gap analysis must distinguish missing skill, missing tool, missing connector, weak planning, and weak execution.
6. UI should render task outputs by result type, not just as generic chat text.
7. Migration must be incremental and reversible.

## Target Architecture

## 1. Agent Core

The Agent Core owns:

- request understanding
- clarification decisions
- task decomposition
- skill selection
- execution supervision
- verification and stopping criteria
- fallback and recovery behavior

It does not directly encode domain workflows. That responsibility moves to skills.

### Responsibilities

- classify ask type
- decide whether the ask is clear enough to act
- select one or more skills
- decide execution depth
- supervise plan execution
- interpret failures
- hand failure context to the Growth Engine

## 2. Skill Layer

Skills become first-class runtime objects.

A skill is not a tool. A skill is a reusable capability package that defines:

- when it should be used
- how tasks in its domain should be broken down
- which tools or connectors it prefers
- what outputs it should produce
- how success should be verified
- how failures should be interpreted

### Examples

- web_research
- web_automation
- computer_automation
- repo_debugging
- code_editing
- document_extraction
- blender_automation

### Skill Structure

Each skill should have:

- human-readable instructions
- structured metadata
- optional prompt templates
- optional verification and renderer hints

Proposed layout:

```text
skills/
  web_research/
    SKILL.md
    skill.json
    templates/
  computer_automation/
    SKILL.md
    skill.json
```

### Proposed Metadata Fields

- `name`
- `category`
- `description`
- `trigger_examples`
- `required_tools`
- `preferred_tools`
- `required_connectors`
- `input_types`
- `output_types`
- `verification_mode`
- `risk_level`
- `ui_renderer`
- `fallback_strategy`

## 3. Execution Layer

The Execution Layer provides runtime actions to the agent and skills.

It includes:

- current tools
- generated tools
- MCP connectors
- application adapters

### Tools

Tools remain the primary execution unit for local capabilities.

They should continue to support:

- capability metadata
- orchestration
- validation
- sandbox testing
- quality analysis

### Connectors

Connectors are not tools in the same sense.

They represent external capability surfaces, including:

- MCP servers
- external application integrations
- remote service bridges

### Adapters

Adapters are specialized connectors for software systems like:

- Blender
- browser automation systems
- local applications exposing APIs or sockets

### Execution Contract

Skills should not invoke tools directly by hardcoded assumptions.

Instead:

- skills declare preferred capabilities
- routing resolves to tools or connectors
- execution is logged and verified through one orchestration path

## 4. Growth Engine

The Growth Engine replaces the current narrow tool-gap model with a richer capability model.

It should answer:

- was the failure due to missing skill?
- missing tool?
- weak tool?
- missing connector?
- weak planning?
- unclear user request?
- permissions or policy?

### Growth Engine Components

- gap classifier
- gap tracker
- creation prioritizer
- evolution prioritizer
- connector suggestion path
- approval-aware proposal system

### Target Gap Types

- `missing_skill`
- `missing_tool`
- `weak_tool`
- `missing_connector`
- `weak_skill_workflow`
- `weak_planning`
- `unclear_request`
- `blocked_by_policy`

### Gap Record Fields

- original request
- chosen skill
- plan summary
- execution trace summary
- failure point
- failure category
- suggested remedy
- confidence
- repetition count
- domain/category

## 5. Output UI Layer

The UI should not be centered only on modes. It should also become output-aware.

### Output-aware rendering

Result renderers should support:

- research summary
- extracted structured data
- file diffs
- execution traces
- task plans
- approval cards
- capability gap reports
- connector status
- media or application artifacts

### Domain-aware navigation

The UI should eventually support skill/category views such as:

- Web
- Computer Automation
- Code
- Research
- Integrations

This should be layered on top of output-aware rendering, not instead of it.

## Runtime Flow

The target runtime flow is:

1. User submits request
2. Agent Core interprets request
3. Agent decides:
   - clarify
   - route to one skill
   - route to multiple skills
   - reject due to policy
4. Skill provides workflow guidance
5. Planner generates constrained execution plan
6. Execution Layer runs tools/connectors through shared orchestration
7. Verifier checks outcome
8. If failed or partial, Growth Engine classifies the gap
9. Gap is recorded and prioritized
10. UI renders the result, trace, approvals, and any detected growth opportunities

## Current-to-Target Module Map

## Current modules that can be preserved

- [core/autonomous_agent.py](/c:/Users/derik/Desktop/Derik/Projects/CUA/core/autonomous_agent.py)
- [core/task_planner.py](/c:/Users/derik/Desktop/Derik/Projects/CUA/core/task_planner.py)
- [core/execution_engine.py](/c:/Users/derik/Desktop/Derik/Projects/CUA/core/execution_engine.py)
- [core/tool_orchestrator.py](/c:/Users/derik/Desktop/Derik/Projects/CUA/core/tool_orchestrator.py)
- [tools/capability_registry.py](/c:/Users/derik/Desktop/Derik/Projects/CUA/tools/capability_registry.py)
- [core/tool_creation/](/c:/Users/derik/Desktop/Derik/Projects/CUA/core/tool_creation)
- [core/tool_evolution/](/c:/Users/derik/Desktop/Derik/Projects/CUA/core/tool_evolution)
- approval and sandbox systems
- observability systems

## Current modules that need to evolve

- [core/gap_detector.py](/c:/Users/derik/Desktop/Derik/Projects/CUA/core/gap_detector.py)
- [core/gap_tracker.py](/c:/Users/derik/Desktop/Derik/Projects/CUA/core/gap_tracker.py)
- [core/tool_registry_manager.py](/c:/Users/derik/Desktop/Derik/Projects/CUA/core/tool_registry_manager.py)
- [api/server.py](/c:/Users/derik/Desktop/Derik/Projects/CUA/api/server.py)
- planning and routing logic in chat path
- tools-management and observability UI organization

## New modules likely required

- `core/skills/models.py`
- `core/skills/loader.py`
- `core/skills/registry.py`
- `core/skills/router.py`
- `core/connectors/models.py`
- `core/connectors/registry.py`
- `core/connectors/mcp_adapter.py`
- `core/growth/gap_classifier.py`
- `core/growth/models.py`
- `core/output/render_types.py`
- `core/output/result_router.py`

## Refactor Strategy

This must be an incremental migration.

Do not replace the current tool runtime first.

### Phase 0: Architecture Spec and Safety Setup

Deliverables:

- this plan
- terminology alignment
- migration plan
- feature flags for skills and connectors where needed

Exit criteria:

- target abstractions are agreed
- migration order is fixed

### Phase 1: Introduce Skill Foundation

Deliverables:

- skill model
- skill loader and registry
- initial skill folders
- skill selection path in agent routing

Implementation rule:

- skills route to existing tools underneath
- no large tool-runtime rewrite yet

Exit criteria:

- at least 3 skills operational through current execution layer
- requests can be routed by skill before capability selection

### Phase 2: Upgrade Gap Analysis

Deliverables:

- richer gap model
- new classifier
- migration for stored gap records
- priority scoring for skill/tool/connector needs

Exit criteria:

- failures are classified beyond just missing capability
- repeated missing-skill and missing-connector cases are visible

### Phase 3: Make Creation and Evolution Skill-aware

Deliverables:

- creation engine accepts skill/domain context
- evolution engine records skill-context failures
- proposals include target skill and verification hints
- registry stores domain/category/skill metadata

Exit criteria:

- generated tools are attached to a skill/domain
- evolution recommendations distinguish tool weakness from workflow weakness

### Phase 4: Introduce Connector Layer

Deliverables:

- connector model
- connector registry
- MCP adapter path
- application adapter contract

Exit criteria:

- connectors are routable beside tools
- at least one MCP path and one app-adapter path are supported

### Phase 5: UI Refactor for Domains and Outputs

Deliverables:

- output-type renderers
- domain navigation
- connector visibility
- skill-aware traces and approval surfaces

Exit criteria:

- outputs are not only shown as chat text
- users can understand what domain handled a task and why

## Data Model Direction

The refactor should standardize around these models:

### SkillDefinition

- identity
- category
- trigger rules
- execution preferences
- verification rules
- renderer hints

### ToolDefinition

- current capability metadata
- owning skill/domain
- safety level
- quality metrics
- standalone connector requirements if any

### ConnectorDefinition

- connector type
- remote/local target
- auth/config requirements
- exposed capabilities
- trust/risk level

### CapabilityGapRecord

- request
- selected skill
- failure classification
- suggested remedy
- confidence
- repetition history

### OutputArtifact

- type
- renderer
- source execution
- associated skill
- associated approval or trace link

## Registry Direction

The current registry should evolve from tool-only to capability-surface-aware.

Target registry should understand:

- skills
- tools
- connectors
- adapters
- renderers

This does not require replacing the current tool registry immediately. It means introducing a broader registry model above it.

## Risks

### 1. Over-refactor risk

If skills, connectors, UI, and growth logic are all changed at once, the system will destabilize.

Mitigation:

- phase-based migration
- feature flags
- keep existing tool path alive until skills route cleanly

### 2. Duplicate abstractions

Bad outcome:

- tools, skills, and connectors all start doing overlapping work

Mitigation:

- strict responsibility boundaries

### 3. Regressions in chat path

The current chat path already works. Routing changes can break it.

Mitigation:

- preserve existing fallback path while introducing skill routing
- add regression tests around representative asks

### 4. Creation/evolution drift

If the creation engine is updated before gap classification improves, it may still generate the wrong artifacts.

Mitigation:

- refactor gap classification before major creation/evolution logic changes

## Rollback Strategy

Because git fallback exists, the refactor can be staged safely, but rollback should still be designed.

### Rollback rules

- each phase should land in isolated commits
- feature flags should allow disabling skill routing
- connector integration should be opt-in initially
- current tool path should remain usable until the new path is proven

## Recommended First Implementation Slice

The first implementation slice after this planning phase should be:

1. add skill models and registry
2. create 3 initial skills
3. route asks through skill selection before direct tool routing
4. keep existing tools and orchestrator unchanged underneath

This gives the architecture a visible backbone without breaking the current runtime.

## Open Decisions Before Implementation

These should be finalized before Phase 1 coding begins:

1. Should skills support multiple execution backends from day one, or only tools first?
2. Should MCP be introduced in Phase 4 only, or should connector abstractions exist earlier as empty shells?
3. Should the UI first expose domains or output renderers?
4. Should category and skill be separate fields, or should category just be a higher-level grouping over skills?
5. Should tool creation be allowed to create new skills, or only create tools inside existing skills at first?

## Recommended Answers

1. Tools first; connectors later.
2. Define connector models early, but integrate runtime use in Phase 4.
3. Output renderers first, domains second.
4. Keep category and skill separate.
5. At first, create tools inside existing skills only; add skill creation later.

## Phase 1 Locked Decisions

The following decisions are now locked for the first implementation slice.

### 1. Skill Model

Skills will be first-class runtime objects backed by both:

- `SKILL.md` for human-readable domain behavior
- `skill.json` for structured routing and UI metadata

Skills are not prompt fragments and not direct execution units.

They are orchestration objects that provide:

- trigger guidance
- domain workflow guidance
- preferred execution surfaces
- verification guidance
- output renderer hints

### Phase 1 Skill Contract

Each skill must define:

- `name`
- `category`
- `description`
- `trigger_examples`
- `preferred_tools`
- `required_tools`
- `preferred_connectors`
- `input_types`
- `output_types`
- `verification_mode`
- `risk_level`
- `ui_renderer`
- `fallback_strategy`

Each skill may optionally define:

- prompt templates
- planning constraints
- capability gap heuristics
- domain-specific clarification rules

### 2. Category vs Skill

Category and skill will remain separate.

Reason:

- category is for grouping and UI organization
- skill is the executable domain workflow abstraction

Example:

- category: `web`
- skills:
  - `web_research`
  - `web_automation`
  - `web_extraction`

This is cleaner than making categories executable, and more flexible than flattening everything into skills only.

### 3. Connector Timing

Connector models will be introduced early as stable abstractions, but runtime connector usage will not be part of Phase 1.

Phase 1 execution continues to route into current tools.

Reason:

- current system is already tool-centric and working
- introducing live MCP/runtime connectors too early adds risk
- skill routing can deliver value immediately even if connectors are still placeholders

### Phase 1 connector rule

- define connector model and registry interfaces only if needed by shared schemas
- do not integrate MCP execution into the main runtime path yet
- do not block skill routing on connector implementation

### 4. First Skills To Introduce

The first three skills should align with the current repo’s strongest usable surfaces.

#### Skill 1: `web_research`

Category: `web`

Purpose:

- browse
- fetch web content
- summarize findings
- compare sources
- produce structured research output

Why first:

- directly matches the user-facing direction
- can use current browser/http/summarization surfaces
- gives immediate value to routing, output rendering, and gap analysis

Primary execution surfaces:

- `BrowserAutomationTool`
- `HTTPTool`
- `ContextSummarizerTool`

#### Skill 2: `computer_automation`

Category: `computer`

Purpose:

- file operations
- local command execution
- local workflow automation
- controlled desktop-style task execution through existing local tools

Why second:

- matches the current execution and filesystem strengths
- maps well to approvals and safety policy
- provides a clear non-web domain for the new architecture

Primary execution surfaces:

- `FilesystemTool`
- `ShellTool`
- future local app adapters

#### Skill 3: `code_workspace`

Category: `development`

Purpose:

- inspect code
- modify code
- run validations
- summarize diffs and execution outcomes

Why third:

- current repo already contains strong code-generation/evolution workflows
- this skill will eventually unify code editing, testing, tool creation, and evolution under one domain
- it is a natural bridge between the main agent and the growth system

Primary execution surfaces:

- `FilesystemTool`
- `ShellTool`
- existing tool creation/evolution subsystems

### Deferred Skills

The following should wait until the first three are stable:

- `web_automation` as a separate skill
- `document_extraction`
- `blender_automation`
- MCP-specific integration skills
- skill-creation by the system itself

## Phase 1 Runtime Rules

To reduce migration risk, Phase 1 must obey these rules:

1. Skill routing happens before direct tool routing.
2. Skills produce guidance, not raw tool execution by themselves.
3. Existing tool orchestration remains the execution backend.
4. Existing chat and goal APIs continue to work.
5. If no skill matches confidently, the system falls back to current direct tool/capability behavior.

## Phase 1 Success Criteria

Phase 1 is complete when:

- three skills are loadable from disk
- the agent can route representative asks into those skills
- planning incorporates skill context
- execution still uses the current tool orchestration path
- failures can at least distinguish:
  - no matching skill
  - matched skill but missing tool capability
  - matched skill but weak execution

## Notes On Suitability

This architecture is suitable for current technology because:

- current agent systems work best when orchestration is explicit
- skills provide reusable domain behavior without collapsing everything into one prompt
- tools remain the right execution primitive for local runtime safety and observability
- MCP and external application integrations fit naturally as connectors once the skill layer exists

For CUA specifically, this is a better fit than:

- staying purely tool-centric, which keeps gap diagnosis too shallow
- going full skill-only, which would weaken execution structure and validation boundaries
- jumping to connectors first, which would increase runtime complexity before routing is mature

## Phase 1 Technical Design

This section defines the concrete implementation shape for the first migration slice.

Phase 1 must introduce skills with minimal disruption to:

- current chat flow
- current autonomous goal flow
- current tool execution path
- current approval and observability behavior

## 1. File and Folder Layout

### New backend modules

```text
core/
  skills/
    __init__.py
    models.py
    loader.py
    registry.py
    selector.py
    context.py
```

### New skill assets

```text
skills/
  web_research/
    SKILL.md
    skill.json
  computer_automation/
    SKILL.md
    skill.json
  code_workspace/
    SKILL.md
    skill.json
```

### UI impact in Phase 1

No new top-level UI page is required in Phase 1.

Phase 1 should only add:

- skill metadata in task responses
- skill badges or labels in existing chat/task surfaces
- optional filtering hooks for later domain views

## 2. Core Models

### `SkillDefinition`

`core/skills/models.py`

Responsibilities:

- represent the static skill contract loaded from disk
- expose normalized trigger and renderer metadata

Suggested fields:

- `name: str`
- `category: str`
- `description: str`
- `trigger_examples: list[str]`
- `preferred_tools: list[str]`
- `required_tools: list[str]`
- `preferred_connectors: list[str]`
- `input_types: list[str]`
- `output_types: list[str]`
- `verification_mode: str`
- `risk_level: str`
- `ui_renderer: str`
- `fallback_strategy: str`
- `skill_dir: str`
- `instructions_path: str`

### `SkillSelection`

`core/skills/models.py`

Responsibilities:

- represent the result of skill selection before planning

Suggested fields:

- `matched: bool`
- `skill_name: str | None`
- `category: str | None`
- `confidence: float`
- `reason: str`
- `fallback_mode: str`
- `candidate_skills: list[str]`

### `SkillPlanningContext`

`core/skills/context.py`

Responsibilities:

- adapt a selected skill into structured planner context

Suggested fields:

- `skill_name`
- `category`
- `instructions_summary`
- `preferred_tools`
- `required_tools`
- `verification_mode`
- `output_types`
- `ui_renderer`
- `skill_constraints`

## 3. Skill Loader

### `SkillLoader`

`core/skills/loader.py`

Responsibilities:

- load skills from `skills/`
- validate `skill.json`
- ensure `SKILL.md` exists
- return normalized `SkillDefinition` objects

### Loader rules

1. `skill.json` is required.
2. `SKILL.md` is required.
3. Invalid skills are skipped and logged, not fatal to startup.
4. Skills are loaded at startup and can be refreshed later.

## 4. Skill Registry

### `SkillRegistry`

`core/skills/registry.py`

Responsibilities:

- hold loaded skills in memory
- resolve skill by name
- list skills by category
- provide lightweight selection context for the agent

### Minimum API

- `load_all() -> dict[str, SkillDefinition]`
- `get(name: str) -> SkillDefinition | None`
- `list_all() -> list[SkillDefinition]`
- `list_by_category(category: str) -> list[SkillDefinition]`
- `to_routing_context() -> list[dict]`

### Design rule

The skill registry does not execute anything.

It is read-only runtime metadata for routing and planning.

## 5. Skill Selection Flow

### `SkillSelector`

`core/skills/selector.py`

Responsibilities:

- inspect a user request
- select the best matching skill or return no-skill match
- provide a confidence score and fallback reason

### Selection strategy in Phase 1

Use a hybrid approach:

1. heuristic fast-pass
2. LLM disambiguation when needed

#### Heuristic fast-pass

Use:

- trigger examples
- category keywords
- required/preferred tool presence
- current ask patterns already visible in the chat path

#### LLM disambiguation

Use only when:

- multiple skills match similarly
- user ask is broad or ambiguous
- no skill is matched by heuristics but the ask is clearly actionable

### Minimum API

- `select_skill(user_message: str, registry, llm_client, runtime_context=None) -> SkillSelection`

### Phase 1 fallback behavior

If no skill matches confidently:

- return `matched = False`
- preserve current capability/tool path
- annotate the result for future gap analysis

## 6. Chat Path Integration

### Current insertion point

The Phase 1 skill hook should be inserted into the current `/chat` flow before:

- intent branching into direct tool behavior
- native tool-calling fallback
- regex/direct capability routing

### New order in `/chat`

1. validate input
2. refresh runtime if needed
3. select skill
4. if skill matched:
   - add skill context
   - route into planning or tool calling using skill-aware prompts
5. if no skill matched:
   - use current fallback path

### Response metadata to add

Assistant responses should start carrying:

- `selected_skill`
- `selected_category`
- `skill_confidence`
- `fallback_used`

This lets the UI expose skills without requiring a full redesign yet.

## 7. Autonomous Goal Flow Integration

### Current insertion point

`AutonomousAgent._plan_iteration()` should enrich planner context with selected skill information.

### New behavior

Before calling `TaskPlanner.plan_task(...)`:

- select skill from `goal.goal_text`
- if matched, attach `SkillPlanningContext`
- include skill constraints and preferred tools in planner context

### Design rule

The autonomous agent does not need a separate planning system in Phase 1.

It should continue using `TaskPlanner`, but with better context.

## 8. Planner Integration

### `TaskPlanner` changes

Phase 1 should not replace the planner. It should make it skill-aware.

The planner prompt should receive:

- selected skill name
- selected category
- preferred tools
- required tools
- output type expectations
- verification mode
- skill instructions summary

### Planner rule

Skill context constrains planning; it does not generate the plan by itself.

That keeps the planner as the execution-plan producer while skills supply domain guidance.

## 9. Fallback Rules

Fallback must be explicit and deterministic.

### Fallback cases

#### Case 1: no skill match

Behavior:

- use existing direct tool/capability path
- record `no_matching_skill`

#### Case 2: skill matched, required tools unavailable

Behavior:

- do not silently degrade into unrelated tools
- record `matched_skill_missing_tool`
- optionally provide a partial explanation to the user

#### Case 3: skill matched, execution fails

Behavior:

- keep current execution failure path
- enrich gap analysis with selected skill context

#### Case 4: ambiguous ask

Behavior:

- ask clarifying question if confidence is too low
- otherwise use best skill with low-confidence marker

## 10. Phase 1 Gap Analysis Upgrade

Phase 1 does not need the full Growth Engine rewrite, but it must add skill-aware signals.

### Minimum new fields for gap recording

- selected skill
- selected category
- skill match confidence
- fallback path taken
- missing required tool if known

### Minimum new classifications

- `no_matching_skill`
- `matched_skill_missing_tool`
- `matched_skill_execution_failed`

These can initially coexist with the existing gap model.

## 11. UI Contract for Phase 1

The existing UI should remain mostly intact.

### Required additions

- show selected skill in chat/task execution responses
- preserve current `OutputRenderer` behavior
- allow output components to include `skill` and `category` metadata

### Not required in Phase 1

- separate skill tabs
- separate domain workspaces
- connector configuration UI

## 12. Phase 1 API Contract

Phase 1 should avoid introducing many new endpoints.

### Preferred approach

Reuse current endpoints and enrich payloads.

Possible additions later:

- `GET /skills/list`
- `GET /skills/{skill_name}`

These are useful but not required to complete Phase 1.

## 13. Observability Requirements

Phase 1 logs and traces should include:

- selected skill
- skill selection confidence
- fallback reason
- selected category

This is critical because skill routing quality will need early measurement.

## 14. Implementation Order Within Phase 1

1. create skill model and loader
2. create skill registry
3. add three initial skills on disk
4. add skill selector
5. integrate selector into `/chat`
6. integrate skill context into `AutonomousAgent` and `TaskPlanner`
7. enrich gap recording and response metadata
8. add tests

## 15. Phase 1 Tests

Minimum tests to add:

- skill loader loads valid skills
- invalid skill definitions are skipped safely
- selector chooses `web_research` for web research asks
- selector chooses `computer_automation` for file/local asks
- selector chooses `code_workspace` for repo/code asks
- planner receives skill context
- `/chat` falls back safely when no skill matches
- gap recording stores skill metadata when available

## 16. Explicit Non-Goals

Phase 1 should not:

- introduce live MCP execution
- replace tool orchestration
- create new skills automatically
- build a new top-level UI mode
- replace the existing agent or planner
