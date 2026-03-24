"""Application bootstrap helpers for router loading and runtime initialization."""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

CURATED_EXPERIMENTAL_RUNTIME_TOOLS = (
    "ContextSummarizerTool",
    "DatabaseQueryTool",
    "BrowserAutomationTool",
    "LocalCodeSnippetLibraryTool",
    "LocalRunNoteTool",
    "BenchmarkRunnerTool",
)

_EXPERIMENTAL_LOAD_TIMEOUT = 5  # seconds per tool


@dataclass
class RouterBundle:
    routers_available: bool
    routers: List[Any] = field(default_factory=list)
    refresh_runtime_registry_from_files: Optional[Callable[..., Any]] = None
    setters: Dict[str, Callable[..., Any]] = field(default_factory=dict)
    import_error: Optional[str] = None


@dataclass
class RuntimeState:
    system_available: bool
    registry: Any = None
    executor: Any = None
    parser: Any = None
    permission_gate: Any = None
    llm_client: Any = None
    state_manager: Any = None
    plan_validator: Any = None
    logger: Any = None
    error_recovery: Any = None
    improvement_loop: Any = None
    conversation_memory: Any = None
    scheduler: Any = None
    registry_manager: Any = None
    libraries_manager: Any = None
    task_planner: Any = None
    execution_engine: Any = None
    memory_system: Any = None
    autonomous_agent: Any = None
    tool_orchestrator: Any = None
    tool_registrar: Any = None
    skill_registry: Any = None
    skill_selector: Any = None
    coordinated_autonomy_engine: Any = None
    circuit_breaker: Any = None
    # Singleton managers (created once here, reused by routers)
    quality_analyzer: Any = None
    evolution_orchestrator: Any = None
    pending_evolutions_manager: Any = None
    pending_services_manager: Any = None
    pending_skills_manager: Any = None
    service_injector: Any = None
    init_error: Optional[str] = None
    # Scheduler stop event for clean shutdown
    _scheduler_stop: Any = field(default=None, repr=False)


def _load_tool_with_timeout(tool_module_name: str, orchestrator, timeout: float) -> Any:
    """Load an experimental tool in a thread with a timeout. Returns tool instance or None."""
    result = [None]
    exc = [None]

    def _load():
        try:
            module = __import__(f"tools.experimental.{tool_module_name}", fromlist=[tool_module_name])
            tool_cls = getattr(module, tool_module_name)
            result[0] = tool_cls(orchestrator=orchestrator)
        except Exception as e:
            exc[0] = e

    t = threading.Thread(target=_load, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        print(f"Warning: {tool_module_name} load timed out after {timeout}s — skipped")
        return None
    if exc[0]:
        print(f"Warning: Could not load {tool_module_name}: {exc[0]}")
        return None
    return result[0]


def load_router_bundle() -> RouterBundle:
    try:
        from updater.api import router as update_router
        from api.improvement_api import router as improvement_router, set_loop_instance
        from api.settings_api import router as settings_router, set_llm_client
        from api.scheduler_api import router as scheduler_router, set_scheduler
        from api.task_manager_api import router as task_manager_router, set_task_manager
        from api.pending_tools_api import (
            router as pending_tools_router,
            set_pending_tools_manager,
            set_tool_registrar,
            set_registry_manager_for_pending,
        )
        from api.llm_logs_api import router as llm_logs_router
        from api.tools_api import (
            router as tools_router,
            set_registry_manager,
            set_llm_client_for_sync,
            set_runtime_registry,
            set_tool_registrar_for_sync,
            set_tool_orchestrator_for_sync,
            refresh_runtime_registry_from_files,
        )
        from api.libraries_api import router as libraries_router, set_libraries_manager
        from api.hybrid_api import router as hybrid_router
        from api.quality_api import router as quality_router
        from api.tool_evolution_api import router as evolution_router, set_evolution_dependencies
        from api.observability_api import router as observability_router
        from api.observability_data_api import router as observability_data_router
        from api.cleanup_api import router as cleanup_router
        from api.tool_info_api import router as tool_info_router
        from api.tool_list_api import router as tool_list_router
        from api.tools_management_api import router as tools_management_router
        from api.metrics_api import router as metrics_router
        from api.auto_evolution_api import router as auto_evolution_router, set_coordinated_engine
        from api.agent_api import router as agent_router, set_agent_dependencies
        from api.skills_api import router as skills_router, set_skill_registry
        from api.trace_ws import router as trace_router
        from api.circuit_breaker_api import router as circuit_breaker_router, set_skill_registry_for_cb
        from api.session_api import router as session_router
        from api.services_api import router as services_router, set_services_dependencies
        from api.pending_skills_api import router as pending_skills_router, set_skills_dependencies
        from api.mcp_api import router as mcp_router, set_registry as set_mcp_registry
        from api.credentials_api import router as credentials_router

        return RouterBundle(
            routers_available=True,
            routers=[
                update_router, improvement_router, settings_router, scheduler_router,
                task_manager_router, pending_tools_router, llm_logs_router, tools_router,
                libraries_router, hybrid_router, quality_router, evolution_router,
                observability_router, observability_data_router, cleanup_router,
                tool_info_router, tool_list_router, tools_management_router, metrics_router,
                auto_evolution_router, agent_router, skills_router, trace_router,
                circuit_breaker_router, session_router, services_router,
                pending_skills_router, mcp_router, credentials_router,
            ],
            refresh_runtime_registry_from_files=refresh_runtime_registry_from_files,
            setters={
                "set_loop_instance": set_loop_instance,
                "set_llm_client": set_llm_client,
                "set_scheduler": set_scheduler,
                "set_task_manager": set_task_manager,
                "set_pending_tools_manager": set_pending_tools_manager,
                "set_tool_registrar": set_tool_registrar,
                "set_registry_manager_for_pending": set_registry_manager_for_pending,
                "set_registry_manager": set_registry_manager,
                "set_llm_client_for_sync": set_llm_client_for_sync,
                "set_runtime_registry": set_runtime_registry,
                "set_tool_registrar_for_sync": set_tool_registrar_for_sync,
                "set_tool_orchestrator_for_sync": set_tool_orchestrator_for_sync,
                "set_libraries_manager": set_libraries_manager,
                "set_evolution_dependencies": set_evolution_dependencies,
                "set_agent_dependencies": set_agent_dependencies,
                "set_skill_registry": set_skill_registry,
                "set_services_dependencies": set_services_dependencies,
                "set_skills_dependencies": set_skills_dependencies,
                "set_coordinated_engine": set_coordinated_engine,
                "set_mcp_registry": set_mcp_registry,
                "set_skill_registry_for_cb": set_skill_registry_for_cb,
            },
        )
    except ImportError as e:
        print(f"Routers not available: {e}")
        return RouterBundle(routers_available=False, import_error=str(e))


def include_router_bundle(app, bundle: RouterBundle) -> None:
    if not bundle.routers_available:
        return
    for router in bundle.routers:
        app.include_router(router)


def build_runtime(bundle: Optional[RouterBundle] = None) -> RuntimeState:
    try:
        from tools.capability_registry import CapabilityRegistry
        from tools.enhanced_filesystem_tool import FilesystemTool
        from tools.http_tool import HTTPTool
        from tools.json_tool import JSONTool
        from tools.shell_tool import ShellTool
        from tools.web_access_tool import WebAccessTool
        from core.secure_executor import SecureExecutor
        from planner.plan_parser import PlanParser
        from core.session_permissions import PermissionGate
        from planner.llm_client import LLMClient
        from core.state_machine import StateManager
        from core.plan_validator import PlanValidator
        from core.sqlite_logging import get_logger
        from core.error_recovery import ErrorRecovery
        from updater.orchestrator import UpdateOrchestrator
        from core.improvement_loop import SelfImprovementLoop
        from core.conversation_memory import ConversationMemory
        from core.improvement_scheduler import ImprovementScheduler
        from core.config_manager import get_config
        from core.tool_registrar import ToolRegistrar
        from core.tool_registry_manager import ToolRegistryManager
        from core.pending_libraries_manager import PendingLibrariesManager
        from core.tool_orchestrator import ToolOrchestrator
        from core.task_planner import TaskPlanner
        from core.execution_engine import ExecutionEngine
        from core.memory_system import MemorySystem
        from core.autonomous_agent import AutonomousAgent
        from core.metrics_scheduler import get_metrics_scheduler
        from core.skills import SkillRegistry, SkillSelector
        from core.coordinated_autonomy_engine import CoordinatedAutonomyEngine
        from core.circuit_breaker import get_circuit_breaker
        from core.decision_engine import get_decision_engine
        from core.tool_evolution.flow import ToolEvolutionOrchestrator
        from core.pending_evolutions_manager import PendingEvolutionsManager
        from core.tool_quality_analyzer import ToolQualityAnalyzer
        from core.expansion_mode import ExpansionMode
        from core.pending_services_manager import PendingServicesManager
        from core.pending_skills_manager import PendingSkillsManager

        config = get_config()
        circuit_breaker = get_circuit_breaker()

        registry = CapabilityRegistry()
        tool_orchestrator = ToolOrchestrator(registry=registry)

        for tool in (FilesystemTool(), HTTPTool(), JSONTool(), ShellTool(), WebAccessTool(orchestrator=tool_orchestrator)):
            registry.register_tool(tool)

        # Load experimental tools with per-tool timeout
        for tool_module_name in CURATED_EXPERIMENTAL_RUNTIME_TOOLS:
            tool = _load_tool_with_timeout(tool_module_name, tool_orchestrator, _EXPERIMENTAL_LOAD_TIMEOUT)
            if tool:
                registry.register_tool(tool)

        # Load MCP adapters (non-blocking: skip if unreachable)
        for mcp_server in (config.mcp_servers or []):
            if not mcp_server.enabled:
                continue
            try:
                from tools.experimental.MCPAdapterTool import MCPAdapterTool
                adapter = MCPAdapterTool(server_name=mcp_server.name, server_url=mcp_server.url)
                if adapter.is_connected():
                    registry.register_tool(adapter)
                    print(f"MCP adapter loaded: {mcp_server.name} ({len(adapter._mcp_tools)} tools)")
                else:
                    print(f"Warning: MCP server '{mcp_server.name}' at {mcp_server.url} not reachable — skipped")
            except Exception as e:
                print(f"Warning: Could not load MCP adapter for '{mcp_server.name}': {e}")

        executor = SecureExecutor(registry)
        parser = PlanParser()
        permission_gate = PermissionGate()
        llm_client = LLMClient(registry=registry)
        skill_registry = SkillRegistry()
        skill_registry.load_all()
        skill_selector = SkillSelector()
        get_decision_engine(skill_registry=skill_registry)
        state_manager = StateManager()
        plan_validator = PlanValidator()
        logger = get_logger("cua_api")
        error_recovery = ErrorRecovery()
        conversation_memory = ConversationMemory()
        tool_registrar = ToolRegistrar(registry, orchestrator=tool_orchestrator)
        registry_manager = ToolRegistryManager()
        libraries_manager = PendingLibrariesManager()

        orchestrator = UpdateOrchestrator(repo_path=".")
        improvement_loop = SelfImprovementLoop(
            llm_client, orchestrator,
            max_iterations=config.improvement.max_iterations,
            libraries_manager=libraries_manager,
            registry=registry,
        )

        # Scheduler with stop event for clean shutdown
        scheduler_stop = threading.Event()
        scheduler = ImprovementScheduler()

        async def _run_scheduled_loop(max_iter: int, dry: bool):
            improvement_loop.controller.max_iterations = max_iter
            improvement_loop.dry_run = dry
            improvement_loop.continuous_mode = False
            await improvement_loop.start_loop()

        scheduler.set_callback(
            lambda max_iter, dry: asyncio.create_task(_run_scheduled_loop(max_iter, dry))
        )
        scheduler.start()

        metrics_scheduler = get_metrics_scheduler()
        metrics_scheduler.start()
        logger.info("Metrics scheduler started")

        task_planner = TaskPlanner(llm_client, registry, skill_registry=skill_registry)
        execution_engine = ExecutionEngine(registry, tool_orchestrator=tool_orchestrator, task_planner=task_planner)
        memory_system = MemorySystem()
        autonomous_agent = AutonomousAgent(
            task_planner=task_planner,
            execution_engine=execution_engine,
            memory_system=memory_system,
            llm_client=llm_client,
            skill_registry=skill_registry,
            skill_selector=skill_selector,
        )
        coordinated_autonomy_engine = CoordinatedAutonomyEngine(
            improvement_loop=improvement_loop,
            llm_client=llm_client,
            registry=registry,
        )

        # Build singleton managers once
        quality_analyzer = ToolQualityAnalyzer()
        expansion_mode = ExpansionMode(enabled=True)
        evolution_orchestrator = ToolEvolutionOrchestrator(
            quality_analyzer=quality_analyzer,
            expansion_mode=expansion_mode,
            llm_client=llm_client,
        )
        pending_evolutions_manager = PendingEvolutionsManager()
        pending_services_manager = PendingServicesManager()
        pending_skills_manager = PendingSkillsManager()

        from core.service_injector import ServiceInjector
        service_injector = ServiceInjector()

        # Wire unified memory with live instances
        from core.improvement_memory import ImprovementMemory
        from core.unified_memory import get_unified_memory
        get_unified_memory(memory_system=memory_system, improvement_memory=ImprovementMemory())

        runtime = RuntimeState(
            system_available=True,
            registry=registry,
            executor=executor,
            parser=parser,
            permission_gate=permission_gate,
            llm_client=llm_client,
            state_manager=state_manager,
            plan_validator=plan_validator,
            logger=logger,
            error_recovery=error_recovery,
            improvement_loop=improvement_loop,
            conversation_memory=conversation_memory,
            scheduler=scheduler,
            registry_manager=registry_manager,
            libraries_manager=libraries_manager,
            task_planner=task_planner,
            execution_engine=execution_engine,
            memory_system=memory_system,
            autonomous_agent=autonomous_agent,
            tool_orchestrator=tool_orchestrator,
            tool_registrar=tool_registrar,
            skill_registry=skill_registry,
            skill_selector=skill_selector,
            coordinated_autonomy_engine=coordinated_autonomy_engine,
            circuit_breaker=circuit_breaker,
            quality_analyzer=quality_analyzer,
            evolution_orchestrator=evolution_orchestrator,
            pending_evolutions_manager=pending_evolutions_manager,
            pending_services_manager=pending_services_manager,
            pending_skills_manager=pending_skills_manager,
            service_injector=service_injector,
            _scheduler_stop=scheduler_stop,
        )

        if bundle and bundle.routers_available:
            wire_router_dependencies(runtime, bundle)

        print("CUA system initialized successfully")
        return runtime

    except Exception as e:
        import traceback
        print(f"System initialization failed: {e}")
        traceback.print_exc()
        return RuntimeState(system_available=False, init_error=str(e))


def wire_router_dependencies(runtime: RuntimeState, bundle: RouterBundle) -> None:
    if not bundle.routers_available:
        return

    bundle.setters["set_evolution_dependencies"](runtime.evolution_orchestrator, runtime.pending_evolutions_manager)
    # Inject orchestrator so approve_evolution can invalidate the services cache
    runtime.pending_evolutions_manager._tool_orchestrator = runtime.tool_orchestrator
    bundle.setters["set_loop_instance"](runtime.improvement_loop)
    bundle.setters["set_llm_client"](runtime.llm_client)
    bundle.setters["set_scheduler"](runtime.scheduler)
    bundle.setters["set_task_manager"](None)
    bundle.setters["set_pending_tools_manager"](runtime.improvement_loop.pending_tools_manager)
    bundle.setters["set_tool_registrar"](runtime.tool_registrar)
    bundle.setters["set_registry_manager_for_pending"](runtime.registry_manager)
    bundle.setters["set_registry_manager"](runtime.registry_manager)
    bundle.setters["set_llm_client_for_sync"](runtime.llm_client)
    bundle.setters["set_runtime_registry"](runtime.registry)
    bundle.setters["set_tool_registrar_for_sync"](runtime.tool_registrar)
    bundle.setters["set_tool_orchestrator_for_sync"](runtime.tool_orchestrator)
    bundle.setters["set_libraries_manager"](runtime.libraries_manager)
    bundle.setters["set_agent_dependencies"](runtime.autonomous_agent, runtime.memory_system, runtime.execution_engine)
    bundle.setters["set_skill_registry"](runtime.skill_registry)
    bundle.setters["set_services_dependencies"](runtime.pending_services_manager, runtime.service_injector)
    bundle.setters["set_skills_dependencies"](runtime.pending_skills_manager, runtime.skill_registry)
    bundle.setters["set_coordinated_engine"](runtime.coordinated_autonomy_engine)
    bundle.setters["set_mcp_registry"](runtime.registry)
    bundle.setters["set_skill_registry_for_cb"](runtime.skill_registry)
