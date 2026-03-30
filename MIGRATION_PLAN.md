# Core/ Migration Plan - Phase 6

## Overview
Migrating 137 files from `core/` to appropriate layers in Clean Architecture.

## Migration Categories

### 1. Domain Services (Pure Business Logic)
**Target:** `domain/services/`

- [ ] `capability_resolver.py` → `domain/services/capability_resolution_service.py` (already exists, merge)
- [ ] `gap_detector.py` → `domain/services/gap_analysis_service.py` (already exists, merge)
- [ ] `gap_tracker.py` → `domain/services/gap_tracking_service.py`
- [ ] `decision_engine.py` → `domain/services/decision_service.py`
- [ ] `feature_gap_analyzer.py` → `domain/services/feature_gap_service.py`
- [ ] `tool_quality_analyzer.py` → `domain/services/tool_quality_service.py`

### 2. Infrastructure Services
**Target:** `infrastructure/persistence/`, `infrastructure/external/`, `infrastructure/validation/`

#### Persistence
- [ ] `credential_store.py` → `infrastructure/persistence/credential_store.py`
- [ ] `storage_broker.py` → `infrastructure/persistence/storage_broker.py`
- [ ] `strategic_memory.py` → `infrastructure/persistence/file_storage/strategic_memory.py`
- [ ] `unified_memory.py` → `infrastructure/persistence/file_storage/unified_memory.py`
- [ ] `conversation_memory.py` → `infrastructure/persistence/file_storage/conversation_memory.py`
- [ ] `memory_system.py` → `infrastructure/persistence/file_storage/memory_system.py`
- [ ] `improvement_memory.py` → `infrastructure/persistence/file_storage/improvement_memory.py`
- [ ] `evolution_constraint_memory.py` → `infrastructure/persistence/file_storage/evolution_constraint_memory.py`
- [ ] `database_schema_registry.py` → `infrastructure/persistence/sqlite/schema_registry.py`
- [ ] `sqlite_utils.py` → `infrastructure/persistence/sqlite/utils.py`
- [ ] `sqlite_logging.py` → `infrastructure/persistence/sqlite/logging.py`

#### Validation (already partially done)
- [ ] `tool_creation/validator.py` → merge with `infrastructure/validation/ast/ast_validator.py`
- [ ] `tool_evolution/validator.py` → merge with `infrastructure/validation/ast/ast_validator.py`
- [ ] `validation_pipeline.py` → `infrastructure/validation/validation_pipeline.py`
- [ ] `validation_service.py` → `infrastructure/validation/validation_service.py`
- [ ] `test_validator.py` → `infrastructure/validation/test_validator.py`
- [ ] `output_validator.py` → `infrastructure/validation/output_validator.py`
- [ ] `input_validation.py` → `infrastructure/validation/input_validator.py`
- [ ] `verification_engine.py` → `infrastructure/validation/verification_engine.py`

#### Sandbox
- [ ] `tool_creation/sandbox_runner.py` → merge with `infrastructure/sandbox/unified_sandbox_runner.py`
- [ ] `tool_evolution/sandbox_runner.py` → merge with `infrastructure/sandbox/unified_sandbox_runner.py`
- [ ] `sandbox_tester.py` → `infrastructure/sandbox/sandbox_tester.py`
- [ ] `secure_executor.py` → `infrastructure/sandbox/secure_executor.py`

#### External Services
- [ ] `service_registry.py` → `infrastructure/external/service_registry.py`
- [ ] `service_generator.py` → `infrastructure/external/service_generator.py`
- [ ] `service_injector.py` → `infrastructure/external/service_injector.py`
- [ ] `service_validation.py` → `infrastructure/external/service_validation.py`
- [ ] `service_generation_integration.py` → `infrastructure/external/service_generation_integration.py`

#### Logging
- [ ] `llm_logger.py` → `infrastructure/llm/llm_logger.py`
- [ ] `llm_test_logger.py` → `infrastructure/llm/llm_test_logger.py`
- [ ] `logging_system.py` → `infrastructure/logging/logging_system.py`
- [ ] `tool_creation_logger.py` → `infrastructure/logging/tool_creation_logger.py`
- [ ] `tool_evolution_logger.py` → `infrastructure/logging/tool_evolution_logger.py`
- [ ] `tool_execution_logger.py` → `infrastructure/logging/tool_execution_logger.py`
- [ ] `chat_history_logger.py` → `infrastructure/logging/chat_history_logger.py`

#### Metrics
- [ ] `metrics_aggregator.py` → `infrastructure/metrics/aggregator.py`
- [ ] `metrics_scheduler.py` → `infrastructure/metrics/scheduler.py`

### 3. Application Use Cases (Orchestration)
**Target:** `application/use_cases/`

#### Tool Lifecycle (merge with existing)
- [ ] `tool_creation/flow.py` → merge with `application/use_cases/tool_lifecycle/create_tool.py`
- [ ] `tool_evolution/flow.py` → merge with `application/use_cases/tool_lifecycle/evolve_tool.py`
- [ ] `tool_generation_orchestrator.py` → merge with `application/use_cases/tool_lifecycle/create_tool.py`
- [ ] `tool_orchestrator.py` → `application/use_cases/tool_lifecycle/tool_orchestrator.py`
- [ ] `tool_registrar.py` → `application/use_cases/tool_lifecycle/tool_registrar.py`
- [ ] `tool_registry_manager.py` → `application/use_cases/tool_lifecycle/tool_registry_manager.py`

#### Autonomy (merge with existing)
- [ ] `autonomous_agent.py` → merge with `application/use_cases/autonomy/run_autonomy_cycle.py`
- [ ] `coordinated_autonomy_engine.py` → merge with `application/use_cases/autonomy/run_autonomy_cycle.py`
- [ ] `auto_evolution_orchestrator.py` → `application/use_cases/autonomy/auto_evolution_orchestrator.py`
- [ ] `auto_evolution_orchestrator_adapter.py` → `application/use_cases/autonomy/auto_evolution_adapter.py`
- [ ] `auto_evolution_trigger.py` → `application/use_cases/autonomy/auto_evolution_trigger.py`
- [ ] `baseline_health_checker.py` → merge with `application/use_cases/autonomy/check_system_health.py`
- [ ] `execution_supervisor.py` → `application/use_cases/autonomy/execution_supervisor.py`

#### Evolution (merge with existing)
- [ ] `tool_evolution/analyzer.py` → merge with `application/use_cases/evolution/analyze_gaps.py`
- [ ] `tool_evolution/proposal_generator.py` → merge with `application/use_cases/evolution/propose_evolution.py`
- [ ] `evolution_controller.py` → `application/use_cases/evolution/evolution_controller.py`
- [ ] `evolution_bridge.py` → `application/use_cases/evolution/evolution_bridge.py`
- [ ] `evolution_queue.py` → `application/use_cases/evolution/evolution_queue.py`
- [ ] `agentic_evolution_chat.py` → `application/use_cases/evolution/agentic_evolution_chat.py`

#### Planning (merge with existing)
- [ ] `task_planner.py` → merge with `application/use_cases/planning/create_plan.py`
- [ ] `task_planner_clean.py` → merge with `application/use_cases/planning/create_plan.py`
- [ ] `step_planner.py` → `application/use_cases/planning/step_planner.py`
- [ ] `plan_history.py` → `application/use_cases/planning/plan_history.py`
- [ ] `plan_schema.py` → `application/dto/plan_dto.py`

#### Execution
- [ ] `execution_engine.py` → `application/use_cases/execution/execution_engine.py`

#### Chat (merge with existing)
- [ ] `web_research_agent.py` → `application/use_cases/chat/web_research_agent.py`

#### Improvement
- [ ] `improvement_loop.py` → `application/use_cases/improvement/improvement_loop.py`
- [ ] `improvement_scheduler.py` → `application/use_cases/improvement/improvement_scheduler.py`
- [ ] `improvement_analytics.py` → `application/use_cases/improvement/improvement_analytics.py`
- [ ] `hybrid_improvement_engine.py` → `application/use_cases/improvement/hybrid_improvement_engine.py`
- [ ] `self_evolution.py` → `application/use_cases/improvement/self_evolution.py`
- [ ] `self_reflector.py` → `application/use_cases/improvement/self_reflector.py`

### 4. Application Services (Helpers/Utilities for Use Cases)
**Target:** `application/services/`

- [ ] `skills/selector.py` → `application/services/skill_selector.py`
- [ ] `skills/tool_selector.py` → `application/services/tool_selector.py`
- [ ] `skills/context_hydrator.py` → `application/services/skill_context_hydrator.py`
- [ ] `skills/loader.py` → `application/services/skill_loader.py`
- [ ] `skills/registry.py` → `application/services/skill_registry.py`
- [ ] `skills/updater.py` → `application/services/skill_updater.py`
- [ ] `auto_skill_detection.py` → `application/services/auto_skill_detection.py`
- [ ] `semantic_router.py` → `application/services/semantic_router.py`
- [ ] `context_optimizer.py` → `application/services/context_optimizer.py`
- [ ] `parameter_resolution.py` → `application/services/parameter_resolution.py`

### 5. Code Generation (Infrastructure)
**Target:** `infrastructure/code_generation/`

- [ ] `tool_creation/code_generator/` → `infrastructure/code_generation/tool_creation/`
- [ ] `tool_evolution/code_generator.py` → `infrastructure/code_generation/tool_evolution/`
- [ ] `tool_creation/spec_generator.py` → `infrastructure/code_generation/spec_generator.py`
- [ ] `block_code_generator.py` → `infrastructure/code_generation/block_generator.py`
- [ ] `incremental_code_builder.py` → `infrastructure/code_generation/incremental_builder.py`
- [ ] `orchestrated_code_generator.py` → `infrastructure/code_generation/orchestrated_generator.py`
- [ ] `patch_generator.py` → `infrastructure/code_generation/patch_generator.py`
- [ ] `code_integrator.py` → `infrastructure/code_generation/code_integrator.py`
- [ ] `code_critic.py` → `infrastructure/code_generation/code_critic.py`
- [ ] `method_extractor.py` → `infrastructure/code_generation/method_extractor.py`
- [ ] `schema_generator.py` → `infrastructure/code_generation/schema_generator.py`

### 6. Analysis & Detection (Infrastructure)
**Target:** `infrastructure/analysis/`

- [ ] `dependency_analyzer.py` → `infrastructure/analysis/dependency_analyzer.py`
- [ ] `dependency_checker.py` → `infrastructure/analysis/dependency_checker.py`
- [ ] `dependency_resolver.py` → `infrastructure/analysis/dependency_resolver.py`
- [ ] `cua_code_analyzer.py` → `infrastructure/analysis/cua_code_analyzer.py`
- [ ] `system_analyzer.py` → `infrastructure/analysis/system_analyzer.py`
- [ ] `task_analyzer.py` → `infrastructure/analysis/task_analyzer.py`
- [ ] `output_analyzer.py` → `infrastructure/analysis/output_analyzer.py`
- [ ] `llm_tool_health_analyzer.py` → `infrastructure/analysis/llm_tool_health_analyzer.py`
- [ ] `abstract_method_checker.py` → `infrastructure/analysis/abstract_method_checker.py`
- [ ] `noop_detector.py` → `infrastructure/analysis/noop_detector.py`

### 7. Failure Handling (Infrastructure)
**Target:** `infrastructure/failure_handling/`

- [ ] `tool_creation/failure_classifier.py` → `infrastructure/failure_handling/creation_failure_classifier.py`
- [ ] `tool_evolution/failure_classifier.py` → `infrastructure/failure_handling/evolution_failure_classifier.py`
- [ ] `failure_classifier.py` → `infrastructure/failure_handling/failure_classifier.py`
- [ ] `failure_learner.py` → `infrastructure/failure_handling/failure_learner.py`
- [ ] `error_recovery.py` → `infrastructure/failure_handling/error_recovery.py`
- [ ] `error_prioritizer.py` → `infrastructure/failure_handling/error_prioritizer.py`
- [ ] `circuit_breaker.py` → `infrastructure/failure_handling/circuit_breaker.py`
- [ ] `retry_coordinator.py` → `infrastructure/failure_handling/retry_coordinator.py`

### 8. Shared Utilities
**Target:** `shared/utils/`

- [ ] `config_manager.py` → `shared/config/config_manager.py`
- [ ] `model_manager.py` → `shared/config/model_manager.py`
- [ ] `correlation_context.py` → `shared/utils/correlation_context.py`
- [ ] `import_resolver.py` → `shared/utils/import_resolver.py`
- [ ] `idempotency_checker.py` → `shared/utils/idempotency_checker.py`
- [ ] `staleness_guard.py` → `shared/utils/staleness_guard.py`
- [ ] `feature_deduplicator.py` → `shared/utils/feature_deduplicator.py`
- [ ] `feature_tracker.py` → `shared/utils/feature_tracker.py`

### 9. Domain Models (Move to domain/entities or value_objects)
- [ ] `skills/models.py` → merge with `domain/entities/skill.py`
- [ ] `skills/execution_context.py` → `domain/value_objects/execution_context.py`
- [ ] `skills/context.py` → `domain/value_objects/skill_context.py`
- [ ] `proposal_types.py` → merge with `domain/value_objects/evolution_proposal.py`
- [ ] `tool_generation_context.py` → `domain/value_objects/tool_generation_context.py`
- [ ] `state_machine.py` → `domain/value_objects/state_machine.py`

### 10. Managers (Application Layer)
**Target:** `application/managers/`

- [ ] `pending_tools_manager.py` → `application/managers/pending_tools_manager.py`
- [ ] `pending_evolutions_manager.py` → `application/managers/pending_evolutions_manager.py`
- [ ] `pending_skills_manager.py` → `application/managers/pending_skills_manager.py`
- [ ] `pending_services_manager.py` → `application/managers/pending_services_manager.py`
- [ ] `pending_libraries_manager.py` → `application/managers/pending_libraries_manager.py`

### 11. Policies & Permissions (Domain or Shared)
**Target:** `domain/policies/` or `shared/policies/`

- [ ] `artifact_policy.py` → `domain/policies/artifact_policy.py`
- [ ] `refactoring_permissions.py` → `domain/policies/refactoring_permissions.py`
- [ ] `session_permissions.py` → `domain/policies/session_permissions.py`
- [ ] `immutable_brain_stem.py` → `domain/policies/immutable_brain_stem.py`
- [ ] `interface_protector.py` → `domain/policies/interface_protector.py`

### 12. Specialized Features
**Target:** Various locations

- [ ] `capability_graph.py` → `domain/services/capability_graph_service.py`
- [ ] `capability_mapper.py` → `application/services/capability_mapper.py`
- [ ] `vision_manager.py` → `application/services/vision_manager.py`
- [ ] `llm_test_orchestrator.py` → `infrastructure/testing/llm_test_orchestrator.py`
- [ ] `expansion_mode.py` → `application/services/expansion_mode.py`
- [ ] `growth_budget.py` → `domain/policies/growth_budget.py`
- [ ] `loop_controller.py` → `application/services/loop_controller.py`
- [ ] `risk_weighted_decision.py` → `domain/services/risk_weighted_decision.py`
- [ ] `insight_enricher.py` → `application/services/insight_enricher.py`
- [ ] `integration_knowledge.py` → `application/services/integration_knowledge.py`
- [ ] `skill_gap_reporter.py` → `application/services/skill_gap_reporter.py`
- [ ] `skill_aware_creation.py` → merge with `application/use_cases/tool_lifecycle/create_tool.py`
- [ ] `tool_creation/skill_aware_creation.py` → merge with above

### 13. Core Services (Infrastructure)
**Target:** `infrastructure/services/`

- [ ] `services/credential_service.py` → `infrastructure/services/credential_service.py`
- [ ] `services/filesystem_service.py` → `infrastructure/services/filesystem_service.py`
- [ ] `services/json_service.py` → `infrastructure/services/json_service.py`
- [ ] `services/llm_service.py` → `infrastructure/services/llm_service.py`
- [ ] `tool_services.py` → `infrastructure/services/tool_services.py`

## Migration Strategy

### Step 1: Create Missing Directories
- `shared/utils/`
- `shared/config/`
- `shared/policies/`
- `application/services/`
- `application/managers/`
- `application/use_cases/execution/`
- `application/use_cases/improvement/`
- `infrastructure/code_generation/`
- `infrastructure/analysis/`
- `infrastructure/failure_handling/`
- `infrastructure/logging/`
- `infrastructure/metrics/`
- `infrastructure/testing/`
- `infrastructure/services/`
- `domain/policies/`

### Step 2: Move Files in Order
1. Shared utilities first (no dependencies)
2. Domain models and policies
3. Infrastructure services
4. Application services
5. Application use cases
6. Update imports

### Step 3: Test After Each Major Category
- Run tests after moving each category
- Fix import errors incrementally

### Step 4: Remove Empty core/ Directory
- Once all files moved, delete core/

## Progress Tracking
- Total files to migrate: ~137
- Completed: 0
- In Progress: 0
- Remaining: 137
