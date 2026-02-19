# CUA Architecture Reliability Plan (2026-02-19)

## Current Runtime Architecture
```text
UI (React)
  |-- REST --> FastAPI Routers
  |             |-- /improvement/*  (loop control, create tool)
  |             |-- /pending-tools/* (approve/reject queue)
  |             |-- /api/tools/*     (registry + capability sync)
  |
  |-- WS -----> /ws initial_state + event stream
                 |
                 v
         SelfImprovementLoop
           |-- LoopController (deterministic/evolution flow)
           |-- HybridImprovementEngine (analysis + proposal)
           |-- PendingToolsManager (disk-backed queue)
           |-- EventBus (UI updates)
                 |
                 v
          ProposalGenerator -> SandboxTester -> AtomicApplier
                                            \-> rollback/backups
```

## Completed In This Fix Pass
- `api/server.py`
  - CORS is now environment-configurable via `CORS_ALLOW_ORIGINS`.
  - `allow_credentials` is now derived safely (`false` when wildcard origin is used).
  - WebSocket `initial_state` now includes real `pending_tools` from `PendingToolsManager`.
- `core/improvement_loop.py`
  - Hybrid engine execution moved to `asyncio.to_thread(...)` to prevent blocking the async loop.
- `api/improvement_api.py`
  - `/improvement/tools/create` now accepts JSON body payload in addition to query params:
    - Body: `{ "description": "...", "tool_name": "..." }`
  - Backward compatibility for existing query-style callers is preserved.
- `core/pending_tools_manager.py`
  - Replaced silent exception swallowing with warning logs for read/write/delete failures.
- `updater/atomic_applier.py`
  - Added rollback safety gate: skip `git reset --hard` when working tree is dirty.

## Priority Backlog

## P0 (Stability/Safety)
1. Single-process state authority for managers currently held via module globals.
2. Add startup health endpoint asserting manager wiring (`loop_instance`, pending manager, registry manager).
3. Add integration test for create -> pending -> approve -> registry -> sync pipeline.

## P1 (Correctness)
1. Normalize all create/sync API contracts to typed request/response models.
2. Add explicit "tool already exists" detection to prevent repeated edits on already-fixed files.
3. Persist loop mode transitions (`deterministic/evolution`) with audit tags in logs.

## P2 (Scale/Observability)
1. Add correlation IDs through loop iteration, proposal, sandbox, apply.
2. Add structured metrics dashboard for failure classes and rollback causes.
3. Add periodic reconciliation task: disk `pending_tools.json` vs in-memory queue state.

## Operational Guidance
- Default run mode should remain one iteration per start (`max_iterations=1`) unless explicitly overridden.
- For Qwen 2.5 14B, keep multi-step generation enabled; avoid single-shot for refactors.
- Treat experimental tools as untrusted until:
  - syntax parse passes,
  - capability extraction passes,
  - pending approval is completed.
