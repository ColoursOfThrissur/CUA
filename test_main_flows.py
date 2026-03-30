"""Current-architecture smoke test for the main platform flows."""
import os
import sys
import traceback
from pathlib import Path

from shared.config.branding import get_platform_name


if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))


def test_imports():
    """Verify the live module paths import successfully."""
    print("\n=== Testing Critical Imports ===")
    try:
        from api.bootstrap import build_runtime, include_router_bundle, load_router_bundle
        from application.services.skill_context_hydrator import SkillContextHydrator
        from application.services.skill_registry import SkillRegistry
        from application.services.skill_selector import SkillSelector
        from application.use_cases.autonomy.autonomous_agent import AutonomousAgent
        from application.use_cases.execution.execution_engine import ExecutionEngine
        from application.use_cases.planning.task_planner import TaskPlanner
        from application.use_cases.tool_lifecycle.tool_creation_flow import ToolCreationOrchestrator
        from application.use_cases.tool_lifecycle.tool_evolution_flow import ToolEvolutionOrchestrator
        from application.use_cases.tool_lifecycle.tool_orchestrator import ToolOrchestrator
        from infrastructure.persistence.sqlite.cua_database import get_conn
        from planner.llm_client import LLMClient
        from tools.capability_registry import CapabilityRegistry

        imported = [
            build_runtime,
            include_router_bundle,
            load_router_bundle,
            SkillContextHydrator,
            SkillRegistry,
            SkillSelector,
            AutonomousAgent,
            ExecutionEngine,
            TaskPlanner,
            ToolCreationOrchestrator,
            ToolEvolutionOrchestrator,
            ToolOrchestrator,
            get_conn,
            LLMClient,
            CapabilityRegistry,
        ]
        print(f"[OK] Imported {len(imported)} live architecture symbols")
        return True
    except Exception as e:
        print(f"[FAIL] Import failed: {e}")
        traceback.print_exc()
        return False


def test_database():
    """Verify the consolidated SQLite database is reachable."""
    print("\n=== Testing Database ===")
    try:
        from infrastructure.persistence.sqlite.cua_database import get_conn

        with get_conn() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        table_names = [row[0] for row in tables]
        required = {"conversations", "evolution_runs", "executions", "tool_creations"}
        missing = sorted(required - set(table_names))
        if missing:
            raise AssertionError(f"Missing expected tables: {missing}")
        print(f"[OK] Database ready with {len(table_names)} tables")
        return True
    except Exception as e:
        print(f"[FAIL] Database test failed: {e}")
        traceback.print_exc()
        return False


def test_skill_system():
    """Verify registry, selector, and context hydrator agree on live skill definitions."""
    print("\n=== Testing Skill System ===")
    try:
        from application.services.skill_context_hydrator import SkillContextHydrator
        from application.services.skill_registry import SkillRegistry
        from application.services.skill_selector import SkillSelector

        registry = SkillRegistry()
        registry.load_all()
        selector = SkillSelector()

        selection = selector.select_skill(
            "search the web for Python tutorials",
            registry,
            llm_client=None,
        )
        if not selection.matched:
            raise AssertionError("Skill selector failed to match a basic web request")

        skill = registry.get(selection.skill_name)
        if not skill:
            raise AssertionError(f"Selected skill '{selection.skill_name}' missing from registry")

        context = SkillContextHydrator.build_context(selection, skill, "search the web for Python tutorials")
        print(
            f"[OK] Selected '{selection.skill_name}' with {len(context.preferred_tools)} preferred tool(s)"
        )
        return True
    except Exception as e:
        print(f"[FAIL] Skill system test failed: {e}")
        traceback.print_exc()
        return False


def test_tool_registry():
    """Verify core tools can register and expose capabilities."""
    print("\n=== Testing Tool Registry ===")
    try:
        from tools.capability_registry import CapabilityRegistry
        from tools.enhanced_filesystem_tool import FilesystemTool
        from tools.http_tool import HTTPTool
        from tools.json_tool import JSONTool
        from tools.shell_tool import ShellTool

        registry = CapabilityRegistry()
        for tool in (FilesystemTool(), HTTPTool(), JSONTool(), ShellTool()):
            registry.register_tool(tool)

        capabilities = registry.get_all_capabilities()
        if not capabilities:
            raise AssertionError("No tool capabilities were registered")
        print(f"[OK] Registered {len(registry.tools)} tool(s) with {len(capabilities)} capability entries")
        return True
    except Exception as e:
        print(f"[FAIL] Tool registry test failed: {e}")
        traceback.print_exc()
        return False


def test_core_runtime_objects():
    """Verify planner, orchestrator, execution engine, and autonomous agent instantiate together."""
    print("\n=== Testing Core Runtime Objects ===")
    try:
        from application.services.skill_registry import SkillRegistry
        from application.services.skill_selector import SkillSelector
        from application.use_cases.autonomy.autonomous_agent import AutonomousAgent
        from application.use_cases.execution.execution_engine import ExecutionEngine
        from application.use_cases.planning.task_planner import TaskPlanner
        from application.use_cases.tool_lifecycle.tool_orchestrator import ToolOrchestrator
        from infrastructure.persistence.file_storage.memory_system import MemorySystem
        from planner.llm_client import LLMClient
        from tools.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        skill_registry = SkillRegistry()
        skill_registry.load_all()
        llm = LLMClient(registry=registry)
        planner = TaskPlanner(llm, registry, skill_registry=skill_registry)
        orchestrator = ToolOrchestrator(registry=registry, skill_registry=skill_registry)
        engine = ExecutionEngine(registry, tool_orchestrator=orchestrator, task_planner=planner)
        agent = AutonomousAgent(
            task_planner=planner,
            execution_engine=engine,
            memory_system=MemorySystem(),
            llm_client=llm,
            skill_registry=skill_registry,
            skill_selector=SkillSelector(),
        )
        print(
            f"[OK] Built planner={type(planner).__name__}, engine={type(engine).__name__}, "
            f"agent={type(agent).__name__}"
        )
        return True
    except Exception as e:
        print(f"[FAIL] Core runtime test failed: {e}")
        traceback.print_exc()
        return False


def test_tool_lifecycle_objects():
    """Verify current creation and evolution orchestrators instantiate with live dependencies."""
    print("\n=== Testing Tool Lifecycle Objects ===")
    try:
        from application.services.expansion_mode import ExpansionMode
        from application.services.skill_registry import SkillRegistry
        from application.use_cases.tool_lifecycle.tool_creation_flow import ToolCreationOrchestrator
        from application.use_cases.tool_lifecycle.tool_evolution_flow import ToolEvolutionOrchestrator
        from domain.services.capability_graph import CapabilityGraph
        from domain.services.tool_quality_analyzer import ToolQualityAnalyzer
        from infrastructure.logging.tool_execution_logger import get_execution_logger
        from planner.llm_client import LLMClient

        skill_registry = SkillRegistry()
        skill_registry.load_all()
        llm = LLMClient()
        creation = ToolCreationOrchestrator(
            capability_graph=CapabilityGraph(),
            expansion_mode=ExpansionMode(enabled=True),
            skill_registry=skill_registry,
            llm_client=llm,
        )
        evolution = ToolEvolutionOrchestrator(
            quality_analyzer=ToolQualityAnalyzer(get_execution_logger()),
            expansion_mode=ExpansionMode(enabled=True),
            llm_client=llm,
        )
        print(
            f"[OK] Built creation={type(creation).__name__}, evolution={type(evolution).__name__}"
        )
        return True
    except Exception as e:
        print(f"[FAIL] Tool lifecycle test failed: {e}")
        traceback.print_exc()
        return False


def test_router_bundle():
    """Verify the current router bundle loader exposes the active API surface."""
    print("\n=== Testing Router Bundle ===")
    try:
        from api.bootstrap import load_router_bundle

        bundle = load_router_bundle()
        if not bundle.routers_available:
            raise AssertionError(f"Routers unavailable: {bundle.import_error}")

        if not bundle.routers:
            raise AssertionError("Router bundle loaded with zero routers")

        print(f"[OK] Loaded {len(bundle.routers)} router(s)")
        return True
    except Exception as e:
        print(f"[FAIL] Router bundle test failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run the smoke suite."""
    print("=" * 60)
    print(f"{get_platform_name().upper()} MAIN FLOWS SMOKE TEST")
    print("=" * 60)

    tests = [
        ("Imports", test_imports),
        ("Database", test_database),
        ("Skill System", test_skill_system),
        ("Tool Registry", test_tool_registry),
        ("Core Runtime", test_core_runtime_objects),
        ("Tool Lifecycle", test_tool_lifecycle_objects),
        ("Router Bundle", test_router_bundle),
    ]

    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"\n[FAIL] {name} test crashed: {e}")
            traceback.print_exc()
            results[name] = False

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for value in results.values() if value)
    total = len(results)

    for name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status:8} {name}")

    print(f"\nTotal: {passed}/{total} tests passed")
    if passed == total:
        print("\n[SUCCESS] Smoke suite passed")
        return 0

    print(f"\n[WARNING] {total - passed} smoke test(s) failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
