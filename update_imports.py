#!/usr/bin/env python3
"""
Import Update Script - Phase 8
Automatically updates all imports from old core/ paths to new architecture paths
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

# Import mapping: old_pattern -> new_import
IMPORT_MAPPINGS = {
    # Shared
    r'from core\.config_manager import': 'from shared.config.config_manager import',
    r'from core\.model_manager import': 'from shared.config.model_manager import',
    r'from core\.correlation_context import': 'from shared.utils.correlation_context import',
    r'from core\.import_resolver import': 'from shared.utils.import_resolver import',
    r'from core\.idempotency_checker import': 'from shared.utils.idempotency_checker import',
    r'from core\.staleness_guard import': 'from shared.utils.staleness_guard import',
    r'from core\.feature_deduplicator import': 'from shared.utils.feature_deduplicator import',
    r'from core\.feature_tracker import': 'from shared.utils.feature_tracker import',
    
    # Domain Policies
    r'from core\.artifact_policy import': 'from domain.policies.artifact_policy import',
    r'from core\.refactoring_permissions import': 'from domain.policies.refactoring_permissions import',
    r'from core\.session_permissions import': 'from domain.policies.session_permissions import',
    r'from core\.immutable_brain_stem import': 'from domain.policies.immutable_brain_stem import',
    r'from core\.interface_protector import': 'from domain.policies.interface_protector import',
    r'from core\.growth_budget import': 'from domain.policies.growth_budget import',
    
    # Domain Services
    r'from core\.gap_detector import': 'from domain.services.gap_detector import',
    r'from core\.gap_tracker import': 'from domain.services.gap_tracker import',
    r'from core\.capability_resolver import': 'from domain.services.capability_resolver import',
    r'from core\.decision_engine import': 'from domain.services.decision_engine import',
    r'from core\.feature_gap_analyzer import': 'from domain.services.feature_gap_analyzer import',
    r'from core\.tool_quality_analyzer import': 'from domain.services.tool_quality_analyzer import',
    r'from core\.capability_graph import': 'from domain.services.capability_graph import',
    r'from core\.risk_weighted_decision import': 'from domain.services.risk_weighted_decision import',
    
    # Domain Value Objects & Entities
    r'from core\.skills\.execution_context import': 'from domain.value_objects.execution_context import',
    r'from core\.skills\.context import': 'from domain.value_objects.skill_context import',
    r'from core\.skills\.models import': 'from domain.entities.skill_models import',
    r'from core\.proposal_types import': 'from domain.value_objects.proposal_types import',
    r'from core\.tool_generation_context import': 'from domain.value_objects.tool_generation_context import',
    r'from core\.state_machine import': 'from domain.value_objects.state_machine import',
    
    # Infrastructure Services
    r'from core\.services\.credential_service import': 'from infrastructure.services.credential_service import',
    r'from core\.services\.filesystem_service import': 'from infrastructure.services.filesystem_service import',
    r'from core\.services\.json_service import': 'from infrastructure.services.json_service import',
    r'from core\.services\.llm_service import': 'from infrastructure.services.llm_service import',
    r'from core\.tool_services import': 'from infrastructure.services.tool_services import',
    
    # Infrastructure Persistence
    r'from core\.credential_store import': 'from infrastructure.persistence.credential_store import',
    r'from core\.storage_broker import': 'from infrastructure.persistence.storage_broker import',
    r'from core\.database_schema_registry import': 'from infrastructure.persistence.sqlite.schema_registry import',
    r'from core\.sqlite_utils import': 'from infrastructure.persistence.sqlite.utils import',
    r'from core\.sqlite_logging import': 'from infrastructure.persistence.sqlite.logging import',
    r'from core\.strategic_memory import': 'from infrastructure.persistence.file_storage.strategic_memory import',
    r'from core\.unified_memory import': 'from infrastructure.persistence.file_storage.unified_memory import',
    r'from core\.conversation_memory import': 'from infrastructure.persistence.file_storage.conversation_memory import',
    r'from core\.memory_system import': 'from infrastructure.persistence.file_storage.memory_system import',
    r'from core\.improvement_memory import': 'from infrastructure.persistence.file_storage.improvement_memory import',
    r'from core\.evolution_constraint_memory import': 'from infrastructure.persistence.file_storage.evolution_constraint_memory import',
    
    # Infrastructure Logging
    r'from core\.logging_system import': 'from infrastructure.logging.logging_system import',
    r'from core\.tool_creation_logger import': 'from infrastructure.logging.tool_creation_logger import',
    r'from core\.tool_evolution_logger import': 'from infrastructure.logging.tool_evolution_logger import',
    r'from core\.tool_execution_logger import': 'from infrastructure.logging.tool_execution_logger import',
    r'from core\.chat_history_logger import': 'from infrastructure.logging.chat_history_logger import',
    r'from core\.llm_logger import': 'from infrastructure.llm.llm_logger import',
    r'from core\.llm_test_logger import': 'from infrastructure.llm.llm_test_logger import',
    
    # Infrastructure Metrics
    r'from core\.metrics_aggregator import': 'from infrastructure.metrics.aggregator import',
    r'from core\.metrics_scheduler import': 'from infrastructure.metrics.scheduler import',
    
    # Infrastructure Analysis
    r'from core\.dependency_analyzer import': 'from infrastructure.analysis.dependency_analyzer import',
    r'from core\.dependency_checker import': 'from infrastructure.analysis.dependency_checker import',
    r'from core\.dependency_resolver import': 'from infrastructure.analysis.dependency_resolver import',
    r'from core\.cua_code_analyzer import': 'from infrastructure.analysis.cua_code_analyzer import',
    r'from core\.system_analyzer import': 'from infrastructure.analysis.system_analyzer import',
    r'from core\.task_analyzer import': 'from infrastructure.analysis.task_analyzer import',
    r'from core\.output_analyzer import': 'from infrastructure.analysis.output_analyzer import',
    r'from core\.llm_tool_health_analyzer import': 'from infrastructure.analysis.llm_tool_health_analyzer import',
    r'from core\.abstract_method_checker import': 'from infrastructure.analysis.abstract_method_checker import',
    r'from core\.noop_detector import': 'from infrastructure.analysis.noop_detector import',
    
    # Infrastructure Failure Handling
    r'from core\.failure_classifier import': 'from infrastructure.failure_handling.failure_classifier import',
    r'from core\.failure_learner import': 'from infrastructure.failure_handling.failure_learner import',
    r'from core\.error_recovery import': 'from infrastructure.failure_handling.error_recovery import',
    r'from core\.error_prioritizer import': 'from infrastructure.failure_handling.error_prioritizer import',
    r'from core\.circuit_breaker import': 'from infrastructure.failure_handling.circuit_breaker import',
    r'from core\.retry_coordinator import': 'from infrastructure.failure_handling.retry_coordinator import',
    r'from core\.tool_creation\.failure_classifier import': 'from infrastructure.failure_handling.creation_failure_classifier import',
    r'from core\.tool_evolution\.failure_classifier import': 'from infrastructure.failure_handling.evolution_failure_classifier import',
    
    # Infrastructure Validation
    r'from core\.validation_pipeline import': 'from infrastructure.validation.validation_pipeline import',
    r'from core\.validation_service import': 'from infrastructure.validation.validation_service import',
    r'from core\.test_validator import': 'from infrastructure.validation.test_validator import',
    r'from core\.output_validator import': 'from infrastructure.validation.output_validator import',
    r'from core\.input_validation import': 'from infrastructure.validation.input_validator import',
    r'from core\.verification_engine import': 'from infrastructure.validation.verification_engine import',
    r'from core\.plan_validator import': 'from infrastructure.validation.plan_validator_core import',
    r'from core\.tool_creation\.validator import': 'from infrastructure.validation.ast.tool_creation_validator import',
    r'from core\.tool_evolution\.validator import': 'from infrastructure.validation.ast.tool_evolution_validator import',
    
    # Infrastructure Sandbox
    r'from core\.sandbox_tester import': 'from infrastructure.sandbox.sandbox_tester import',
    r'from core\.secure_executor import': 'from infrastructure.sandbox.secure_executor import',
    r'from core\.tool_creation\.sandbox_runner import': 'from infrastructure.sandbox.creation_sandbox_runner import',
    r'from core\.tool_evolution\.sandbox_runner import': 'from infrastructure.sandbox.evolution_sandbox_runner import',
    
    # Infrastructure Code Generation
    r'from core\.block_code_generator import': 'from infrastructure.code_generation.block_generator import',
    r'from core\.incremental_code_builder import': 'from infrastructure.code_generation.incremental_builder import',
    r'from core\.orchestrated_code_generator import': 'from infrastructure.code_generation.orchestrated_generator import',
    r'from core\.patch_generator import': 'from infrastructure.code_generation.patch_generator import',
    r'from core\.code_integrator import': 'from infrastructure.code_generation.code_integrator import',
    r'from core\.code_critic import': 'from infrastructure.code_generation.code_critic import',
    r'from core\.method_extractor import': 'from infrastructure.code_generation.method_extractor import',
    r'from core\.schema_generator import': 'from infrastructure.code_generation.schema_generator import',
    r'from core\.tool_creation\.spec_generator import': 'from infrastructure.code_generation.spec_generator import',
    r'from core\.tool_evolution\.code_generator import': 'from infrastructure.code_generation.tool_evolution_generator import',
    r'from core\.tool_creation\.code_generator': 'from infrastructure.code_generation.tool_creation',
    
    # Infrastructure External
    r'from core\.service_registry import': 'from infrastructure.external.service_registry import',
    r'from core\.service_generator import': 'from infrastructure.external.service_generator import',
    r'from core\.service_injector import': 'from infrastructure.external.service_injector import',
    r'from core\.service_validation import': 'from infrastructure.external.service_validation import',
    r'from core\.service_generation_integration import': 'from infrastructure.external.service_generation_integration import',
    
    # Infrastructure Testing
    r'from core\.llm_test_orchestrator import': 'from infrastructure.testing.llm_test_orchestrator import',
    
    # Application Managers
    r'from core\.pending_tools_manager import': 'from application.managers.pending_tools_manager import',
    r'from core\.pending_evolutions_manager import': 'from application.managers.pending_evolutions_manager import',
    r'from core\.pending_skills_manager import': 'from application.managers.pending_skills_manager import',
    r'from core\.pending_services_manager import': 'from application.managers.pending_services_manager import',
    r'from core\.pending_libraries_manager import': 'from application.managers.pending_libraries_manager import',
    
    # Application Services
    r'from core\.skills\.selector import': 'from application.services.skill_selector import',
    r'from core\.skills\.tool_selector import': 'from application.services.tool_selector import',
    r'from core\.skills\.context_hydrator import': 'from application.services.skill_context_hydrator import',
    r'from core\.skills\.loader import': 'from application.services.skill_loader import',
    r'from core\.skills\.registry import': 'from application.services.skill_registry import',
    r'from core\.skills\.updater import': 'from application.services.skill_updater import',
    r'from core\.auto_skill_detection import': 'from application.services.auto_skill_detection import',
    r'from core\.semantic_router import': 'from application.services.semantic_router import',
    r'from core\.context_optimizer import': 'from application.services.context_optimizer import',
    r'from core\.parameter_resolution import': 'from application.services.parameter_resolution import',
    r'from core\.capability_mapper import': 'from application.services.capability_mapper import',
    r'from core\.vision_manager import': 'from application.services.vision_manager import',
    r'from core\.expansion_mode import': 'from application.services.expansion_mode import',
    r'from core\.loop_controller import': 'from application.services.loop_controller import',
    r'from core\.insight_enricher import': 'from application.services.insight_enricher import',
    r'from core\.integration_knowledge import': 'from application.services.integration_knowledge import',
    r'from core\.skill_gap_reporter import': 'from application.services.skill_gap_reporter import',
    
    # Application Use Cases
    r'from core\.execution_engine import': 'from application.use_cases.execution.execution_engine import',
    r'from core\.execution_supervisor import': 'from application.use_cases.autonomy.execution_supervisor import',
    r'from core\.tool_orchestrator import': 'from application.use_cases.tool_lifecycle.tool_orchestrator import',
    r'from core\.tool_registrar import': 'from application.use_cases.tool_lifecycle.tool_registrar import',
    r'from core\.tool_registry_manager import': 'from application.use_cases.tool_lifecycle.tool_registry_manager import',
    r'from core\.tool_generation_orchestrator import': 'from application.use_cases.tool_lifecycle.tool_generation_orchestrator import',
    r'from core\.tool_creation\.flow import': 'from application.use_cases.tool_lifecycle.tool_creation_flow import',
    r'from core\.tool_evolution\.flow import': 'from application.use_cases.tool_lifecycle.tool_evolution_flow import',
    r'from core\.skill_aware_creation import': 'from application.use_cases.tool_lifecycle.skill_aware_creation import',
    r'from core\.tool_creation\.skill_aware_creation import': 'from application.use_cases.tool_lifecycle.tool_creation_skill_aware import',
    r'from core\.autonomous_agent import': 'from application.use_cases.autonomy.autonomous_agent import',
    r'from core\.coordinated_autonomy_engine import': 'from application.use_cases.autonomy.coordinated_autonomy_engine import',
    r'from core\.auto_evolution_orchestrator import': 'from application.use_cases.autonomy.auto_evolution_orchestrator import',
    r'from core\.auto_evolution_orchestrator_adapter import': 'from application.use_cases.autonomy.auto_evolution_adapter import',
    r'from core\.auto_evolution_trigger import': 'from application.use_cases.autonomy.auto_evolution_trigger import',
    r'from core\.baseline_health_checker import': 'from application.use_cases.autonomy.baseline_health_checker import',
    r'from core\.tool_evolution\.analyzer import': 'from application.use_cases.evolution.tool_analyzer import',
    r'from core\.tool_evolution\.proposal_generator import': 'from application.use_cases.evolution.tool_proposal_generator import',
    r'from core\.evolution_controller import': 'from application.use_cases.evolution.evolution_controller import',
    r'from core\.evolution_bridge import': 'from application.use_cases.evolution.evolution_bridge import',
    r'from core\.evolution_queue import': 'from application.use_cases.evolution.evolution_queue import',
    r'from core\.agentic_evolution_chat import': 'from application.use_cases.evolution.agentic_evolution_chat import',
    r'from core\.task_planner import': 'from application.use_cases.planning.task_planner import',
    r'from core\.task_planner_clean import': 'from application.use_cases.planning.task_planner_clean import',
    r'from core\.step_planner import': 'from application.use_cases.planning.step_planner import',
    r'from core\.plan_history import': 'from application.use_cases.planning.plan_history import',
    r'from core\.web_research_agent import': 'from application.use_cases.chat.web_research_agent import',
    r'from core\.improvement_loop import': 'from application.use_cases.improvement.improvement_loop import',
    r'from core\.improvement_scheduler import': 'from application.use_cases.improvement.improvement_scheduler import',
    r'from core\.improvement_analytics import': 'from application.use_cases.improvement.improvement_analytics import',
    r'from core\.hybrid_improvement_engine import': 'from application.use_cases.improvement.hybrid_improvement_engine import',
    r'from core\.self_evolution import': 'from application.use_cases.improvement.self_evolution import',
    r'from core\.self_reflector import': 'from application.use_cases.improvement.self_reflector import',
    
    # Application DTOs
    r'from core\.plan_schema import': 'from application.dto.plan_schema import',
    r'from core\.proposal_generator import': 'from application.dto.proposal_generator import',
}


def find_python_files(root_dir: str, exclude_dirs: List[str] = None) -> List[Path]:
    """Find all Python files in the project, excluding specified directories."""
    if exclude_dirs is None:
        exclude_dirs = ['__pycache__', '.pytest_cache', 'venv', 'env', '.git', 'node_modules', 'ui']
    
    python_files = []
    root_path = Path(root_dir)
    
    for py_file in root_path.rglob('*.py'):
        # Check if file is in excluded directory
        if any(excluded in py_file.parts for excluded in exclude_dirs):
            continue
        python_files.append(py_file)
    
    return python_files


def update_imports_in_file(file_path: Path, mappings: Dict[str, str]) -> Tuple[int, List[str]]:
    """Update imports in a single file. Returns (num_changes, list_of_changes)."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return 0, []
    
    original_content = content
    changes = []
    
    # Apply each mapping
    for old_pattern, new_import in mappings.items():
        matches = re.findall(old_pattern, content)
        if matches:
            content = re.sub(old_pattern, new_import, content)
            changes.append(f"{old_pattern} -> {new_import}")
    
    # Only write if changes were made
    if content != original_content:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return len(changes), changes
        except Exception as e:
            print(f"Error writing {file_path}: {e}")
            return 0, []
    
    return 0, []


def main():
    """Main function to update all imports."""
    print("=" * 80)
    print("PHASE 8: Import Update Script")
    print("=" * 80)
    print()
    
    # Get project root (assuming script is in project root)
    project_root = Path(__file__).parent
    
    print(f"Project root: {project_root}")
    print(f"Finding Python files...")
    
    # Find all Python files
    python_files = find_python_files(str(project_root))
    print(f"Found {len(python_files)} Python files to process")
    print()
    
    # Update imports in each file
    total_changes = 0
    files_modified = 0
    
    for file_path in python_files:
        num_changes, changes = update_imports_in_file(file_path, IMPORT_MAPPINGS)
        
        if num_changes > 0:
            files_modified += 1
            total_changes += num_changes
            print(f"[OK] {file_path.relative_to(project_root)}: {num_changes} imports updated")
            for change in changes:
                print(f"  - {change}")
            print()
    
    print("=" * 80)
    print(f"SUMMARY:")
    print(f"  Files processed: {len(python_files)}")
    print(f"  Files modified: {files_modified}")
    print(f"  Total imports updated: {total_changes}")
    print("=" * 80)
    print()
    print("[SUCCESS] Import update complete!")
    print()
    print("Next steps:")
    print("1. Run tests: pytest -q")
    print("2. Check for any remaining 'from core.' imports")
    print("3. Fix any import errors manually")


if __name__ == "__main__":
    main()
