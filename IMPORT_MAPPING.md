# Import Mapping - Old Paths → New Paths

## Core → Shared

| Old Import | New Import |
|------------|------------|
| `from core.config_manager import` | `from shared.config.config_manager import` |
| `from core.model_manager import` | `from shared.config.model_manager import` |
| `from core.correlation_context import` | `from shared.utils.correlation_context import` |
| `from core.import_resolver import` | `from shared.utils.import_resolver import` |
| `from core.idempotency_checker import` | `from shared.utils.idempotency_checker import` |
| `from core.staleness_guard import` | `from shared.utils.staleness_guard import` |
| `from core.feature_deduplicator import` | `from shared.utils.feature_deduplicator import` |
| `from core.feature_tracker import` | `from shared.utils.feature_tracker import` |

## Core → Domain

| Old Import | New Import |
|------------|------------|
| `from core.artifact_policy import` | `from domain.policies.artifact_policy import` |
| `from core.refactoring_permissions import` | `from domain.policies.refactoring_permissions import` |
| `from core.session_permissions import` | `from domain.policies.session_permissions import` |
| `from core.immutable_brain_stem import` | `from domain.policies.immutable_brain_stem import` |
| `from core.interface_protector import` | `from domain.policies.interface_protector import` |
| `from core.growth_budget import` | `from domain.policies.growth_budget import` |
| `from core.gap_detector import` | `from domain.services.gap_detector import` |
| `from core.gap_tracker import` | `from domain.services.gap_tracker import` |
| `from core.capability_resolver import` | `from domain.services.capability_resolver import` |
| `from core.decision_engine import` | `from domain.services.decision_engine import` |
| `from core.feature_gap_analyzer import` | `from domain.services.feature_gap_analyzer import` |
| `from core.tool_quality_analyzer import` | `from domain.services.tool_quality_analyzer import` |
| `from core.capability_graph import` | `from domain.services.capability_graph import` |
| `from core.risk_weighted_decision import` | `from domain.services.risk_weighted_decision import` |
| `from core.skills.execution_context import` | `from domain.value_objects.execution_context import` |
| `from core.skills.context import` | `from domain.value_objects.skill_context import` |
| `from core.skills.models import` | `from domain.entities.skill_models import` |
| `from core.proposal_types import` | `from domain.value_objects.proposal_types import` |
| `from core.tool_generation_context import` | `from domain.value_objects.tool_generation_context import` |
| `from core.state_machine import` | `from domain.value_objects.state_machine import` |

## Core → Infrastructure

| Old Import | New Import |
|------------|------------|
| `from core.services.credential_service import` | `from infrastructure.services.credential_service import` |
| `from core.services.filesystem_service import` | `from infrastructure.services.filesystem_service import` |
| `from core.services.json_service import` | `from infrastructure.services.json_service import` |
| `from core.services.llm_service import` | `from infrastructure.services.llm_service import` |
| `from core.tool_services import` | `from infrastructure.services.tool_services import` |
| `from core.credential_store import` | `from infrastructure.persistence.credential_store import` |
| `from core.storage_broker import` | `from infrastructure.persistence.storage_broker import` |
| `from core.database_schema_registry import` | `from infrastructure.persistence.sqlite.schema_registry import` |
| `from core.sqlite_utils import` | `from infrastructure.persistence.sqlite.utils import` |
| `from core.sqlite_logging import` | `from infrastructure.persistence.sqlite.logging import` |
| `from core.strategic_memory import` | `from infrastructure.persistence.file_storage.strategic_memory import` |
| `from core.unified_memory import` | `from infrastructure.persistence.file_storage.unified_memory import` |
| `from core.conversation_memory import` | `from infrastructure.persistence.file_storage.conversation_memory import` |
| `from core.memory_system import` | `from infrastructure.persistence.file_storage.memory_system import` |
| `from core.improvement_memory import` | `from infrastructure.persistence.file_storage.improvement_memory import` |
| `from core.evolution_constraint_memory import` | `from infrastructure.persistence.file_storage.evolution_constraint_memory import` |
| `from core.logging_system import` | `from infrastructure.logging.logging_system import` |
| `from core.tool_creation_logger import` | `from infrastructure.logging.tool_creation_logger import` |
| `from core.tool_evolution_logger import` | `from infrastructure.logging.tool_evolution_logger import` |
| `from core.tool_execution_logger import` | `from infrastructure.logging.tool_execution_logger import` |
| `from core.chat_history_logger import` | `from infrastructure.logging.chat_history_logger import` |
| `from core.llm_logger import` | `from infrastructure.llm.llm_logger import` |
| `from core.llm_test_logger import` | `from infrastructure.llm.llm_test_logger import` |
| `from core.metrics_aggregator import` | `from infrastructure.metrics.aggregator import` |
| `from core.metrics_scheduler import` | `from infrastructure.metrics.scheduler import` |
| `from core.dependency_analyzer import` | `from infrastructure.analysis.dependency_analyzer import` |
| `from core.dependency_checker import` | `from infrastructure.analysis.dependency_checker import` |
| `from core.dependency_resolver import` | `from infrastructure.analysis.dependency_resolver import` |
| `from core.cua_code_analyzer import` | `from infrastructure.analysis.cua_code_analyzer import` |
| `from core.system_analyzer import` | `from infrastructure.analysis.system_analyzer import` |
| `from core.task_analyzer import` | `from infrastructure.analysis.task_analyzer import` |
| `from core.output_analyzer import` | `from infrastructure.analysis.output_analyzer import` |
| `from core.llm_tool_health_analyzer import` | `from infrastructure.analysis.llm_tool_health_analyzer import` |
| `from core.abstract_method_checker import` | `from infrastructure.analysis.abstract_method_checker import` |
| `from core.noop_detector import` | `from infrastructure.analysis.noop_detector import` |
| `from core.failure_classifier import` | `from infrastructure.failure_handling.failure_classifier import` |
| `from core.failure_learner import` | `from infrastructure.failure_handling.failure_learner import` |
| `from core.error_recovery import` | `from infrastructure.failure_handling.error_recovery import` |
| `from core.error_prioritizer import` | `from infrastructure.failure_handling.error_prioritizer import` |
| `from core.circuit_breaker import` | `from infrastructure.failure_handling.circuit_breaker import` |
| `from core.retry_coordinator import` | `from infrastructure.failure_handling.retry_coordinator import` |
| `from core.tool_creation.failure_classifier import` | `from infrastructure.failure_handling.creation_failure_classifier import` |
| `from core.tool_evolution.failure_classifier import` | `from infrastructure.failure_handling.evolution_failure_classifier import` |
| `from core.validation_pipeline import` | `from infrastructure.validation.validation_pipeline import` |
| `from core.validation_service import` | `from infrastructure.validation.validation_service import` |
| `from core.test_validator import` | `from infrastructure.validation.test_validator import` |
| `from core.output_validator import` | `from infrastructure.validation.output_validator import` |
| `from core.input_validation import` | `from infrastructure.validation.input_validator import` |
| `from core.verification_engine import` | `from infrastructure.validation.verification_engine import` |
| `from core.plan_validator import` | `from infrastructure.validation.plan_validator_core import` |
| `from core.tool_creation.validator import` | `from infrastructure.validation.ast.tool_creation_validator import` |
| `from core.tool_evolution.validator import` | `from infrastructure.validation.ast.tool_evolution_validator import` |
| `from core.sandbox_tester import` | `from infrastructure.sandbox.sandbox_tester import` |
| `from core.secure_executor import` | `from infrastructure.sandbox.secure_executor import` |
| `from core.tool_creation.sandbox_runner import` | `from infrastructure.sandbox.creation_sandbox_runner import` |
| `from core.tool_evolution.sandbox_runner import` | `from infrastructure.sandbox.evolution_sandbox_runner import` |
| `from core.block_code_generator import` | `from infrastructure.code_generation.block_generator import` |
| `from core.incremental_code_builder import` | `from infrastructure.code_generation.incremental_builder import` |
| `from core.orchestrated_code_generator import` | `from infrastructure.code_generation.orchestrated_generator import` |
| `from core.patch_generator import` | `from infrastructure.code_generation.patch_generator import` |
| `from core.code_integrator import` | `from infrastructure.code_generation.code_integrator import` |
| `from core.code_critic import` | `from infrastructure.code_generation.code_critic import` |
| `from core.method_extractor import` | `from infrastructure.code_generation.method_extractor import` |
| `from core.schema_generator import` | `from infrastructure.code_generation.schema_generator import` |
| `from core.tool_creation.spec_generator import` | `from infrastructure.code_generation.spec_generator import` |
| `from core.tool_evolution.code_generator import` | `from infrastructure.code_generation.tool_evolution_generator import` |
| `from core.tool_creation.code_generator import` | `from infrastructure.code_generation.tool_creation import` |
| `from core.service_registry import` | `from infrastructure.external.service_registry import` |
| `from core.service_generator import` | `from infrastructure.external.service_generator import` |
| `from core.service_injector import` | `from infrastructure.external.service_injector import` |
| `from core.service_validation import` | `from infrastructure.external.service_validation import` |
| `from core.service_generation_integration import` | `from infrastructure.external.service_generation_integration import` |
| `from core.llm_test_orchestrator import` | `from infrastructure.testing.llm_test_orchestrator import` |

## Core → Application

| Old Import | New Import |
|------------|------------|
| `from core.pending_tools_manager import` | `from application.managers.pending_tools_manager import` |
| `from core.pending_evolutions_manager import` | `from application.managers.pending_evolutions_manager import` |
| `from core.pending_skills_manager import` | `from application.managers.pending_skills_manager import` |
| `from core.pending_services_manager import` | `from application.managers.pending_services_manager import` |
| `from core.pending_libraries_manager import` | `from application.managers.pending_libraries_manager import` |
| `from core.skills.selector import` | `from application.services.skill_selector import` |
| `from core.skills.tool_selector import` | `from application.services.tool_selector import` |
| `from core.skills.context_hydrator import` | `from application.services.skill_context_hydrator import` |
| `from core.skills.loader import` | `from application.services.skill_loader import` |
| `from core.skills.registry import` | `from application.services.skill_registry import` |
| `from core.skills.updater import` | `from application.services.skill_updater import` |
| `from core.auto_skill_detection import` | `from application.services.auto_skill_detection import` |
| `from core.semantic_router import` | `from application.services.semantic_router import` |
| `from core.context_optimizer import` | `from application.services.context_optimizer import` |
| `from core.parameter_resolution import` | `from application.services.parameter_resolution import` |
| `from core.capability_mapper import` | `from application.services.capability_mapper import` |
| `from core.vision_manager import` | `from application.services.vision_manager import` |
| `from core.expansion_mode import` | `from application.services.expansion_mode import` |
| `from core.loop_controller import` | `from application.services.loop_controller import` |
| `from core.insight_enricher import` | `from application.services.insight_enricher import` |
| `from core.integration_knowledge import` | `from application.services.integration_knowledge import` |
| `from core.skill_gap_reporter import` | `from application.services.skill_gap_reporter import` |
| `from core.execution_engine import` | `from application.use_cases.execution.execution_engine import` |
| `from core.execution_supervisor import` | `from application.use_cases.autonomy.execution_supervisor import` |
| `from core.tool_orchestrator import` | `from application.use_cases.tool_lifecycle.tool_orchestrator import` |
| `from core.tool_registrar import` | `from application.use_cases.tool_lifecycle.tool_registrar import` |
| `from core.tool_registry_manager import` | `from application.use_cases.tool_lifecycle.tool_registry_manager import` |
| `from core.tool_generation_orchestrator import` | `from application.use_cases.tool_lifecycle.tool_generation_orchestrator import` |
| `from core.tool_creation.flow import` | `from application.use_cases.tool_lifecycle.tool_creation_flow import` |
| `from core.tool_evolution.flow import` | `from application.use_cases.tool_lifecycle.tool_evolution_flow import` |
| `from core.skill_aware_creation import` | `from application.use_cases.tool_lifecycle.skill_aware_creation import` |
| `from core.tool_creation.skill_aware_creation import` | `from application.use_cases.tool_lifecycle.tool_creation_skill_aware import` |
| `from core.autonomous_agent import` | `from application.use_cases.autonomy.autonomous_agent import` |
| `from core.coordinated_autonomy_engine import` | `from application.use_cases.autonomy.coordinated_autonomy_engine import` |
| `from core.auto_evolution_orchestrator import` | `from application.use_cases.autonomy.auto_evolution_orchestrator import` |
| `from core.auto_evolution_orchestrator_adapter import` | `from application.use_cases.autonomy.auto_evolution_adapter import` |
| `from core.auto_evolution_trigger import` | `from application.use_cases.autonomy.auto_evolution_trigger import` |
| `from core.baseline_health_checker import` | `from application.use_cases.autonomy.baseline_health_checker import` |
| `from core.tool_evolution.analyzer import` | `from application.use_cases.evolution.tool_analyzer import` |
| `from core.tool_evolution.proposal_generator import` | `from application.use_cases.evolution.tool_proposal_generator import` |
| `from core.evolution_controller import` | `from application.use_cases.evolution.evolution_controller import` |
| `from core.evolution_bridge import` | `from application.use_cases.evolution.evolution_bridge import` |
| `from core.evolution_queue import` | `from application.use_cases.evolution.evolution_queue import` |
| `from core.agentic_evolution_chat import` | `from application.use_cases.evolution.agentic_evolution_chat import` |
| `from core.task_planner import` | `from application.use_cases.planning.task_planner import` |
| `from core.task_planner_clean import` | `from application.use_cases.planning.task_planner_clean import` |
| `from core.step_planner import` | `from application.use_cases.planning.step_planner import` |
| `from core.plan_history import` | `from application.use_cases.planning.plan_history import` |
| `from core.web_research_agent import` | `from application.use_cases.chat.web_research_agent import` |
| `from core.improvement_loop import` | `from application.use_cases.improvement.improvement_loop import` |
| `from core.improvement_scheduler import` | `from application.use_cases.improvement.improvement_scheduler import` |
| `from core.improvement_analytics import` | `from application.use_cases.improvement.improvement_analytics import` |
| `from core.hybrid_improvement_engine import` | `from application.use_cases.improvement.hybrid_improvement_engine import` |
| `from core.self_evolution import` | `from application.use_cases.improvement.self_evolution import` |
| `from core.self_reflector import` | `from application.use_cases.improvement.self_reflector import` |
| `from core.plan_schema import` | `from application.dto.plan_schema import` |
| `from core.proposal_generator import` | `from application.dto.proposal_generator import` |

## Special Cases

| Old Import | New Import | Notes |
|------------|------------|-------|
| `from core.cua_db import` | `from infrastructure.persistence.sqlite.cua_database import` | Already moved by Gemini |
| `from core.ast_validator import` | `from infrastructure.validation.ast.ast_validator import` | Already moved by Gemini |
