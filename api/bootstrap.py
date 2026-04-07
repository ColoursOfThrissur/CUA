"""Application bootstrap helpers for router loading and runtime initialization."""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from shared.config.branding import get_platform_name

CURATED_EXPERIMENTAL_RUNTIME_TOOLS = (
    "ContextSummarizerTool",
    "DatabaseQueryTool",
    "BrowserAutomationTool",
    "LocalCodeSnippetLibraryTool",
    "LocalRunNoteTool",
    "BenchmarkRunnerTool",
    "FinancialAnalysisTool",
    "SystemHealthTool",
    "CodeAnalysisTool",
)

_EXPERIMENTAL_LOAD_TIMEOUT = 5  # seconds per tool
_MCP_LOAD_TIMEOUT = 20  # MCP servers need more time (npx download + process start + handshake)


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
    task_manager: Any = None
    session_workflow_service: Any = None
    memory_maintenance_loop: Any = None
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
        print(f"Warning: {tool_module_name} load timed out after {timeout}s - skipped")
        return None
    if exc[0]:
        print(f"Warning: Could not load {tool_module_name}: {exc[0]}")
        return None
    return result[0]


def load_router_bundle() -> RouterBundle:
    try:
        from updater.api import router as update_router
        from api.rest.system.improvement_router import router as improvement_router, set_loop_instance
        from api.rest.config.settings_router import router as settings_router, set_llm_client
        from api.rest.system.scheduler_router import router as scheduler_router, set_scheduler
        from api.rest.system.task_manager_router import router as task_manager_router, set_task_manager
        from api.rest.tools.tool_creation_router import (
            router as pending_tools_router,
            set_pending_tools_manager,
            set_tool_registrar,
            set_registry_manager_for_pending,
        )
        from api.rest.monitoring.llm_logs_router import router as llm_logs_router
        from api.rest.tools.tools_router import (
            router as tools_router,
            set_registry_manager,
            set_llm_client_for_sync,
            set_runtime_registry,
            set_tool_registrar_for_sync,
            set_tool_orchestrator_for_sync,
            refresh_runtime_registry_from_files,
        )
        from api.rest.system.libraries_router import router as libraries_router, set_libraries_manager
        from api.rest.system.hybrid_router import router as hybrid_router
        from api.rest.system.quality_router import router as quality_router
        from api.rest.evolution.evolution_router import router as evolution_router, set_evolution_dependencies
        from api.rest.evolution.evolution_chat_router import (
            router as evolution_chat_router,
            set_evolution_dependencies as set_evolution_chat_dependencies,
        )
        from api.rest.observability.observability_router import router as observability_router
        from api.rest.observability.observability_data_router import router as observability_data_router
        from api.rest.system.cleanup_router import router as cleanup_router
        from api.rest.tools.tool_info_router import router as tool_info_router
        from api.rest.tools.tool_list_router import router as tool_list_router
        from api.rest.tools.tool_management_router import router as tools_management_router
        from api.rest.monitoring.metrics_router import router as metrics_router
        from api.rest.evolution.auto_evolution_router import router as auto_evolution_router, set_coordinated_engine
        from api.rest.autonomy.autonomy_router import router as agent_router, set_agent_dependencies
        from api.rest.system.skills_router import router as skills_router, set_skill_registry
        from api.trace_ws import router as trace_router
        from api.rest.system.circuit_breaker_router import router as circuit_breaker_router, set_skill_registry_for_cb
        from api.rest.config.session_router import router as session_router
        from api.rest.system.services_router import router as services_router, set_services_dependencies
        from api.rest.system.pending_skills_router import router as pending_skills_router, set_skills_dependencies
        from api.rest.config.mcp_router import router as mcp_router, set_registry as set_mcp_registry
        from api.rest.config.credentials_router import router as credentials_router
        from api.rest.system.worktree_router import router as worktree_router

        return RouterBundle(
            routers_available=True,
            routers=[
                update_router, improvement_router, settings_router, scheduler_router,
                task_manager_router, pending_tools_router, llm_logs_router, tools_router,
                libraries_router, hybrid_router, quality_router, evolution_router,
                evolution_chat_router,
                observability_router, observability_data_router, cleanup_router,
                tool_info_router, tool_list_router, tools_management_router, metrics_router,
                auto_evolution_router, agent_router, skills_router, trace_router,
                circuit_breaker_router, session_router, services_router,
                pending_skills_router, mcp_router, credentials_router, worktree_router,
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
                "set_evolution_chat_dependencies": set_evolution_chat_dependencies,
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
        from tools.glob_tool import GlobTool
        from tools.grep_tool import GrepTool
        from tools.http_tool import HTTPTool
        from tools.json_tool import JSONTool
        from tools.shell_tool import ShellTool
        from tools.web_access_tool import WebAccessTool
        from tools.computer_use import (
            ScreenPerceptionTool,
            InputAutomationTool,
            SystemControlTool,
        )
        from infrastructure.sandbox.secure_executor import SecureExecutor
        from planner.plan_parser import PlanParser
        from domain.policies.session_permissions import PermissionGate
        from planner.llm_client import LLMClient
        from domain.value_objects.state_machine import StateManager
        from infrastructure.validation.plan_validator_core import PlanValidator
        from infrastructure.persistence.sqlite.logging import get_logger
        from infrastructure.failure_handling.error_recovery import ErrorRecovery
        from updater.orchestrator import UpdateOrchestrator
        from application.use_cases.improvement.improvement_loop import SelfImprovementLoop
        from infrastructure.persistence.file_storage.conversation_memory import ConversationMemory
        from application.use_cases.improvement.improvement_scheduler import ImprovementScheduler
        from shared.config.config_manager import get_config
        from application.use_cases.tool_lifecycle.tool_registrar import ToolRegistrar
        from application.use_cases.tool_lifecycle.tool_registry_manager import ToolRegistryManager
        from application.managers.pending_libraries_manager import PendingLibrariesManager
        from application.use_cases.tool_lifecycle.tool_orchestrator import ToolOrchestrator
        from application.use_cases.planning.task_planner import TaskPlanner
        from application.use_cases.execution.execution_engine import ExecutionEngine
        from infrastructure.persistence.file_storage.memory_system import MemorySystem
        from infrastructure.persistence.file_storage.strategic_memory import get_strategic_memory
        from application.use_cases.autonomy.autonomous_agent import AutonomousAgent
        from infrastructure.metrics.scheduler import get_metrics_scheduler
        from application.services.skill_registry import SkillRegistry
        from application.services.skill_selector import SkillSelector
        from application.use_cases.autonomy.coordinated_autonomy_engine import CoordinatedAutonomyEngine
        from infrastructure.failure_handling.circuit_breaker import get_circuit_breaker
        from domain.services.decision_engine import get_decision_engine
        from application.use_cases.tool_lifecycle.tool_evolution_flow import ToolEvolutionOrchestrator
        from application.managers.pending_evolutions_manager import PendingEvolutionsManager
        from domain.services.tool_quality_analyzer import ToolQualityAnalyzer
        from application.services.expansion_mode import ExpansionMode
        from application.managers.pending_services_manager import PendingServicesManager
        from application.managers.pending_skills_manager import PendingSkillsManager
        from application.services.task_artifact_service import TaskArtifactService
        from application.services.session_workflow_service import SessionWorkflowService
        from application.services.memory_maintenance_service import MemoryMaintenanceLoop, MemoryMaintenanceService

        config = get_config()
        circuit_breaker = get_circuit_breaker()

        registry = CapabilityRegistry()
        skill_registry = SkillRegistry()
        skill_registry.load_all()
        tool_orchestrator = ToolOrchestrator(registry=registry, skill_registry=skill_registry)
        registry.set_orchestrator(tool_orchestrator)

        for tool in (
            FilesystemTool(), 
            GlobTool(),
            GrepTool(),
            HTTPTool(), 
            JSONTool(), 
            ShellTool(), 
            WebAccessTool(orchestrator=tool_orchestrator),
            ScreenPerceptionTool(orchestrator=tool_orchestrator),
            InputAutomationTool(orchestrator=tool_orchestrator),
            SystemControlTool(orchestrator=tool_orchestrator),
        ):
            registry.register_tool(tool)

        # Load experimental tools with per-tool timeout
        for tool_module_name in CURATED_EXPERIMENTAL_RUNTIME_TOOLS:
            tool = _load_tool_with_timeout(tool_module_name, tool_orchestrator, _EXPERIMENTAL_LOAD_TIMEOUT)
            if tool:
                registry.register_tool(tool)

        # Load MCP adapters in parallel threads - each gets _MCP_LOAD_TIMEOUT seconds
        from infrastructure.external.mcp_process_manager import get_mcp_process_manager
        mcp_manager = get_mcp_process_manager()

        def _load_mcp(mcp_server):
            try:
                from tools.experimental.MCPAdapterTool import MCPAdapterTool
                adapter = MCPAdapterTool(
                    server_name=mcp_server.name,
                    transport=getattr(mcp_server, "transport", "stdio"),
                    command=getattr(mcp_server, "command", ""),
                    server_url=getattr(mcp_server, "url", ""),
                    rpc_path=getattr(mcp_server, "rpc_path", "/rpc"),
                    env_key=getattr(mcp_server, "env_key", ""),
                )
                if adapter.is_connected():
                    registry.register_tool(adapter)
                    mcp_manager.register_adapter(mcp_server.name, adapter)
                    print(f"MCP adapter loaded: {mcp_server.name} ({len(adapter._mcp_tools)} tools)")
                else:
                    err = adapter._init_error or "unknown error"
                    print(f"MCP server '{mcp_server.name}' not ready: {err}")
            except Exception as e:
                print(f"Warning: Could not load MCP adapter for '{mcp_server.name}': {e}")

        mcp_threads = []
        for mcp_server in (config.mcp_servers or []):
            if not mcp_server.enabled:
                continue
            t = threading.Thread(target=_load_mcp, args=(mcp_server,), daemon=True)
            t.start()
            mcp_threads.append((mcp_server.name, t))

        for name, t in mcp_threads:
            t.join(timeout=_MCP_LOAD_TIMEOUT)
            if t.is_alive():
                print(f"Warning: MCP server '{name}' load timed out after {_MCP_LOAD_TIMEOUT}s - skipped")

        executor = SecureExecutor(registry)
        parser = PlanParser()
        permission_gate = PermissionGate()
        llm_client = LLMClient(registry=registry)
        print(f"[BOOTSTRAP] LLM client created with default model: {llm_client.model}")
        tool_orchestrator.set_llm_client(llm_client)
        
        # Resolve model aliases to actual model names
        import yaml
        from pathlib import Path
        config_file = Path("config.yaml")
        if config_file.exists():
            with open(config_file, 'r') as f:
                raw_config = yaml.safe_load(f) or {}
                models_dict = raw_config.get('llm', {}).get('models', {})
                chat_model_alias = config.llm.chat_model
                print(f"[BOOTSTRAP] chat_model_alias from config: {chat_model_alias}")
                print(f"[BOOTSTRAP] models_dict keys: {list(models_dict.keys())}")
                if chat_model_alias in models_dict:
                    resolved_model = models_dict[chat_model_alias].get('name', chat_model_alias)
                    print(f"[BOOTSTRAP] Resolved '{chat_model_alias}' -> '{resolved_model}'")
                    print(f"[BOOTSTRAP] Calling llm_client.set_model('{resolved_model}')...")
                    llm_client.set_model(resolved_model)
                    print(f"[BOOTSTRAP] After set_model, llm_client.model = {llm_client.model}")
                    print(f"[BOOTSTRAP] LLM client initialized with model: {resolved_model} (from alias: {chat_model_alias})")
                else:
                    print(f"[BOOTSTRAP] Model alias '{chat_model_alias}' not found in models dict. Available: {list(models_dict.keys())}")
        else:
            print(f"[BOOTSTRAP] config.yaml not found at {config_file.absolute()}")
        
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
        tool_orchestrator.main_planner = task_planner
        task_manager = TaskArtifactService()
        execution_engine = ExecutionEngine(
            registry,
            tool_orchestrator=tool_orchestrator,
            task_planner=task_planner,
            task_manager=task_manager,
        )
        tool_orchestrator.set_execution_engine(execution_engine)
        memory_system = MemorySystem()
        session_workflow_service = SessionWorkflowService(
            memory_system=memory_system,
            conversation_memory=conversation_memory,
            task_manager=task_manager,
        )
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
        improvement_loop._task_manager_stub = task_manager

        # Build singleton managers once
        from infrastructure.logging.tool_execution_logger import get_execution_logger

        quality_analyzer = ToolQualityAnalyzer(get_execution_logger())
        expansion_mode = ExpansionMode(enabled=True)
        evolution_orchestrator = ToolEvolutionOrchestrator(
            quality_analyzer=quality_analyzer,
            expansion_mode=expansion_mode,
            llm_client=llm_client,
        )
        pending_evolutions_manager = PendingEvolutionsManager()
        pending_services_manager = PendingServicesManager()
        pending_skills_manager = PendingSkillsManager()

        from infrastructure.external.service_injector import ServiceInjector
        service_injector = ServiceInjector()

        # Wire unified memory with live instances
        from infrastructure.persistence.file_storage.improvement_memory import ImprovementMemory
        from infrastructure.persistence.file_storage.unified_memory import get_unified_memory
        get_unified_memory(memory_system=memory_system, improvement_memory=ImprovementMemory())
        memory_maintenance_loop = MemoryMaintenanceLoop(
            MemoryMaintenanceService(memory_system=memory_system, strategic_memory=get_strategic_memory()),
            interval_seconds=21600,
        )
        memory_maintenance_loop.start()

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
            task_manager=task_manager,
            session_workflow_service=session_workflow_service,
            memory_maintenance_loop=memory_maintenance_loop,
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

        print(f"{get_platform_name()} initialized successfully")
        return runtime

    except Exception as e:
        import traceback
        print(f"System initialization failed: {e}")
        traceback.print_exc()
        return RuntimeState(system_available=False, init_error=str(e))


def wire_router_dependencies(runtime: RuntimeState, bundle: RouterBundle) -> None:
    if not bundle.routers_available:
        return

    def _call_setter(name: str, *args):
        setter = bundle.setters.get(name)
        if setter:
            setter(*args)

    _call_setter("set_evolution_dependencies", runtime.evolution_orchestrator, runtime.pending_evolutions_manager)
    _call_setter("set_evolution_chat_dependencies", runtime.llm_client, runtime.quality_analyzer)
    # Inject orchestrator so approve_evolution can invalidate the services cache
    runtime.pending_evolutions_manager._tool_orchestrator = runtime.tool_orchestrator
    _call_setter("set_loop_instance", runtime.improvement_loop)
    _call_setter("set_llm_client", runtime.llm_client)
    _call_setter("set_scheduler", runtime.scheduler)
    _call_setter("set_task_manager", runtime.task_manager)
    _call_setter("set_pending_tools_manager", runtime.improvement_loop.pending_tools_manager)
    _call_setter("set_tool_registrar", runtime.tool_registrar)
    _call_setter("set_registry_manager_for_pending", runtime.registry_manager)
    _call_setter("set_registry_manager", runtime.registry_manager)
    _call_setter("set_llm_client_for_sync", runtime.llm_client)
    _call_setter("set_runtime_registry", runtime.registry)
    _call_setter("set_tool_registrar_for_sync", runtime.tool_registrar)
    _call_setter("set_tool_orchestrator_for_sync", runtime.tool_orchestrator)
    _call_setter("set_libraries_manager", runtime.libraries_manager)
    _call_setter("set_agent_dependencies", runtime.autonomous_agent, runtime.memory_system, runtime.execution_engine)
    _call_setter("set_skill_registry", runtime.skill_registry)
    _call_setter("set_services_dependencies", runtime.pending_services_manager, runtime.service_injector)
    _call_setter("set_skills_dependencies", runtime.pending_skills_manager, runtime.skill_registry)
    _call_setter("set_coordinated_engine", runtime.coordinated_autonomy_engine)
    _call_setter("set_mcp_registry", runtime.registry)
    _call_setter("set_skill_registry_for_cb", runtime.skill_registry)


def shutdown_runtime(runtime: Optional[RuntimeState]) -> None:
    """Stop background runtime services during app shutdown."""
    if not runtime:
        return

    try:
        scheduler = getattr(runtime, "scheduler", None)
        if scheduler and hasattr(scheduler, "stop"):
            scheduler.stop()
    except Exception as e:
        print(f"Warning: failed to stop improvement scheduler cleanly: {e}")

    try:
        memory_maintenance_loop = getattr(runtime, "memory_maintenance_loop", None)
        if memory_maintenance_loop and hasattr(memory_maintenance_loop, "stop"):
            memory_maintenance_loop.stop()
    except Exception as e:
        print(f"Warning: failed to stop memory maintenance loop cleanly: {e}")

    try:
        from infrastructure.metrics.scheduler import get_metrics_scheduler

        metrics_scheduler = get_metrics_scheduler()
        if metrics_scheduler and hasattr(metrics_scheduler, "stop"):
            metrics_scheduler.stop()
    except Exception as e:
        print(f"Warning: failed to stop metrics scheduler cleanly: {e}")
