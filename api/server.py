import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Clear any cached bad imports
if 'core.permission_gate' in sys.modules:
    del sys.modules['core.permission_gate']

from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
import asyncio
import json
import time
from typing import Optional, Dict, Any, List
from uuid import uuid4

# Import CUA system components
try:
    from tools.capability_registry import CapabilityRegistry
    from tools.enhanced_filesystem_tool import FilesystemTool
    from tools.http_tool import HTTPTool
    from tools.json_tool import JSONTool
    from tools.shell_tool import ShellTool
    from core.secure_executor import SecureExecutor
    from planner.plan_parser import PlanParser, ExecutionPlan, PlanStep
    from core.session_permissions import PermissionGate
    from core.plan_schema import validate_plan_json, ExecutionPlanSchema
    from planner.llm_client import LLMClient
    from core.state_machine import StateManager, StateMachineExecutor
    from core.plan_validator import PlanValidator
    from core.sqlite_logging import get_logger
    from core.error_recovery import ErrorRecovery, RecoveryConfig
    from updater.orchestrator import UpdateOrchestrator
    from core.improvement_loop import SelfImprovementLoop
    from core.conversation_memory import ConversationMemory
    from core.improvement_scheduler import ImprovementScheduler
    SYSTEM_AVAILABLE = True
except ImportError as e:
    print(f"System components not available: {e}")
    SYSTEM_AVAILABLE = False

try:
    from updater.api import router as update_router
    from api.improvement_api import router as improvement_router, set_loop_instance
    from api.settings_api import router as settings_router, set_llm_client
    from api.scheduler_api import router as scheduler_router, set_scheduler
    from api.task_manager_api import router as task_manager_router, set_task_manager
    from api.pending_tools_api import router as pending_tools_router, set_pending_tools_manager, set_tool_registrar, set_registry_manager_for_pending
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
    from api.tool_evolution_api import router as evolution_router
    from api.observability_api import router as observability_router
    from api.observability_data_api import router as observability_data_router
    from api.cleanup_api import router as cleanup_router
    from api.tool_info_api import router as tool_info_router
    from api.tool_list_api import router as tool_list_router
    from api.tools_management_api import router as tools_management_router
    from api.metrics_api import router as metrics_router
    from api.auto_evolution_api import router as auto_evolution_router
    from api.agent_api import router as agent_router
    ROUTERS_AVAILABLE = True
except ImportError as e:
    print(f"Routers not available: {e}")
    ROUTERS_AVAILABLE = False

app = FastAPI(title="CUA Autonomous Agent API")

def _get_cors_settings():
    raw = os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000"
    )
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if not origins:
        origins = ["http://localhost:3000"]
    allow_credentials = "*" not in origins
    return origins, allow_credentials

# Include routers
if ROUTERS_AVAILABLE:
    app.include_router(update_router)
    app.include_router(improvement_router)
    app.include_router(settings_router)
    app.include_router(scheduler_router)
    app.include_router(task_manager_router)
    app.include_router(pending_tools_router)
    app.include_router(llm_logs_router)
    app.include_router(tools_router)
    app.include_router(libraries_router)
    app.include_router(hybrid_router)
    app.include_router(quality_router)
    app.include_router(evolution_router)
    app.include_router(observability_router)
    app.include_router(observability_data_router)
    app.include_router(cleanup_router)
    app.include_router(tool_info_router)
    app.include_router(tool_list_router)
    app.include_router(tools_management_router)
    app.include_router(metrics_router)
    app.include_router(auto_evolution_router)
    app.include_router(agent_router)

cors_origins, cors_allow_credentials = _get_cors_settings()

# Add correlation context middleware
from core.correlation_context import CorrelationContext, CorrelationContextManager

@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    """Add correlation ID to all requests."""
    # Get or generate correlation ID
    correlation_id = request.headers.get("X-Correlation-ID")
    
    with CorrelationContextManager(correlation_id) as corr_id:
        # Add to response headers
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = corr_id
        return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize CUA system
registry = None
executor = None
parser = None
permission_gate = None
llm_client = None
state_manager = None
plan_validator = None
logger = None
error_recovery = None
improvement_loop = None
conversation_memory = None
scheduler = None
registry_manager = None
libraries_manager = None
task_planner = None
execution_engine = None
memory_system = None
autonomous_agent = None

if SYSTEM_AVAILABLE:
    try:
        from core.config_manager import get_config
        from core.tool_registrar import ToolRegistrar
        from core.tool_registry_manager import ToolRegistryManager
        from core.pending_libraries_manager import PendingLibrariesManager
        config = get_config()
        
        registry = CapabilityRegistry()
        
        # Initialize tool orchestrator first
        from core.tool_orchestrator import ToolOrchestrator
        tool_orchestrator = ToolOrchestrator(registry=registry)
        
        # Register core tools
        fs_tool = FilesystemTool()
        http_tool = HTTPTool()
        json_tool = JSONTool()
        shell_tool = ShellTool()
        registry.register_tool(fs_tool)
        registry.register_tool(http_tool)
        registry.register_tool(json_tool)
        registry.register_tool(shell_tool)
        
        # Load approved experimental tools
        try:
            from tools.experimental.LocalRunNoteTool import LocalRunNoteTool
            local_run_note_tool = LocalRunNoteTool(orchestrator=tool_orchestrator)
            registry.register_tool(local_run_note_tool)
        except Exception as e:
            print(f"Warning: Could not load LocalRunNoteTool: {e}")
        
        try:
            from tools.experimental.ContextSummarizerTool import ContextSummarizerTool
            context_summarizer_tool = ContextSummarizerTool(orchestrator=tool_orchestrator)
            registry.register_tool(context_summarizer_tool)
            print(f"[DEBUG] ContextSummarizerTool loaded successfully")
        except Exception as e:
            print(f"Warning: Could not load ContextSummarizerTool: {e}")
        
        try:
            from tools.experimental.DatabaseQueryTool import DatabaseQueryTool
            database_query_tool = DatabaseQueryTool(orchestrator=tool_orchestrator)
            registry.register_tool(database_query_tool)
            print(f"[DEBUG] DatabaseQueryTool loaded successfully")
        except Exception as e:
            print(f"Warning: Could not load DatabaseQueryTool: {e}")
        executor = SecureExecutor(registry)
        parser = PlanParser()
        permission_gate = PermissionGate()
        llm_client = LLMClient(registry=registry)
        state_manager = StateManager()
        plan_validator = PlanValidator()
        logger = get_logger("cua_api")
        error_recovery = ErrorRecovery()
        conversation_memory = ConversationMemory()
        
        # Initialize tool registrar with orchestrator injection
        tool_registrar = ToolRegistrar(registry, orchestrator=tool_orchestrator)
        
        # Initialize tool registry manager
        registry_manager = ToolRegistryManager()
        
        # Initialize pending libraries manager
        libraries_manager = PendingLibrariesManager()
        
        # Initialize self-improvement loop
        orchestrator = UpdateOrchestrator(repo_path=".")
        improvement_loop = SelfImprovementLoop(llm_client, orchestrator, max_iterations=config.improvement.max_iterations, libraries_manager=libraries_manager)
        
        # Subscribe to event bus
        from core.event_bus import get_event_bus
        event_bus = get_event_bus()
        
        # Initialize scheduler
        scheduler = ImprovementScheduler()

        # Initialize autonomous agent components
        from core.task_planner import TaskPlanner
        from core.execution_engine import ExecutionEngine
        from core.memory_system import MemorySystem
        from core.autonomous_agent import AutonomousAgent
        
        task_planner = TaskPlanner(llm_client, registry)
        execution_engine = ExecutionEngine(registry)
        memory_system = MemorySystem()
        autonomous_agent = AutonomousAgent(
            task_planner=task_planner,
            execution_engine=execution_engine,
            memory_system=memory_system,
            llm_client=llm_client
        )
        
        print("Autonomous agent initialized successfully")

        async def _run_scheduled_loop(max_iter: int, dry: bool):
            improvement_loop.controller.max_iterations = max_iter
            improvement_loop.dry_run = dry
            improvement_loop.continuous_mode = False
            await improvement_loop.start_loop()

        scheduler.set_callback(
            lambda max_iter, dry: asyncio.create_task(_run_scheduled_loop(max_iter, dry))
        )
        scheduler.start()
        
        # Initialize metrics scheduler
        from core.metrics_scheduler import get_metrics_scheduler
        metrics_scheduler = get_metrics_scheduler()
        metrics_scheduler.start()
        logger.info("Metrics scheduler started")
        
        # Set instances for routers
        if ROUTERS_AVAILABLE:
            from api.tool_evolution_api import set_evolution_dependencies
            from core.tool_evolution.flow import ToolEvolutionOrchestrator
            from core.pending_evolutions_manager import PendingEvolutionsManager
            from core.tool_quality_analyzer import ToolQualityAnalyzer
            from core.expansion_mode import ExpansionMode
            
            quality_analyzer = ToolQualityAnalyzer()
            expansion_mode = ExpansionMode(enabled=True)
            evolution_orchestrator = ToolEvolutionOrchestrator(
                quality_analyzer=quality_analyzer,
                expansion_mode=expansion_mode,
                llm_client=llm_client
            )
            pending_evolutions_manager = PendingEvolutionsManager()
            set_evolution_dependencies(evolution_orchestrator, pending_evolutions_manager)
            
            print(f"[DEBUG] Setting loop instance: {improvement_loop is not None}")
            set_loop_instance(improvement_loop)
            set_llm_client(llm_client)
            set_scheduler(scheduler)
            set_task_manager(None)
            set_pending_tools_manager(improvement_loop.pending_tools_manager)
            set_tool_registrar(tool_registrar)
            set_registry_manager_for_pending(registry_manager)
            set_registry_manager(registry_manager)
            set_llm_client_for_sync(llm_client)
            set_runtime_registry(registry)
            set_tool_registrar_for_sync(tool_registrar)
            set_tool_orchestrator_for_sync(tool_orchestrator)
            set_libraries_manager(libraries_manager)
            
            # Set agent dependencies
            from api.agent_api import set_agent_dependencies
            set_agent_dependencies(autonomous_agent, memory_system, execution_engine)
        
        print("CUA system initialized successfully")
    except Exception as e:
        import traceback
        print(f"System initialization failed: {e}")
        traceback.print_exc()
        SYSTEM_AVAILABLE = False

# Session storage
sessions = {}
connections = []

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    success: bool = True
    execution_result: Optional[Dict] = None
    plan: Optional[Dict] = None

def _build_capability_catalog(registry) -> Dict[str, Dict[str, Any]]:
    catalog: Dict[str, Dict[str, Any]] = {}
    for cap_name, capability in registry.get_all_capabilities().items():
        params = [p.name for p in capability.parameters]
        required = [p.name for p in capability.parameters if p.required]
        catalog[cap_name] = {
            "description": capability.description,
            "parameters": params,
            "required": required,
        }
    return catalog

def _try_simple_regex_execution(registry, message: str):
    import re
    if re.search(r'(get|fetch|scrape)\s+(https?://\S+)', message, re.I):
        url_match = re.search(r'https?://\S+', message)
        if url_match:
            return registry.execute_capability('get', url=url_match.group(0))
    elif re.search(r'(read|show|cat)\s+(.+)', message, re.I):
        file_match = re.search(r'(read|show|cat)\s+(.+)', message, re.I)
        if file_match:
            return registry.execute_capability('read_file', path=file_match.group(2).strip())
    elif re.search(r'(list|ls)\s*(.+)?', message, re.I):
        dir_match = re.search(r'(list|ls)\s*(.+)?', message, re.I)
        path = dir_match.group(2).strip() if dir_match and dir_match.group(2) else '.'
        return registry.execute_capability('list_directory', path=path)
    return None

def _infer_capability_call(llm_client, catalog: Dict[str, Dict[str, Any]], message: str) -> Optional[Dict[str, Any]]:
    import re
    
    # Extract quoted text and additional parameters
    quoted_match = re.search(r'["\'](.+?)["\']', message)
    quoted_text = quoted_match.group(1) if quoted_match else None
    
    # Check for summarize/summary keywords
    if quoted_text and re.search(r'\b(summarize|summary)\b', message, re.I):
        args = {"input_text": quoted_text}
        # Extract summary_length if present
        length_match = re.search(r'summary_length[:\s]+([0-9]+)', message, re.I)
        if length_match:
            args["summary_length"] = int(length_match.group(1))
        # Extract tone if present (for future use)
        tone_match = re.search(r'tone[:\s]+(\w+)', message, re.I)
        if tone_match:
            args["tone"] = tone_match.group(1)
        return {"capability": "summarize_text", "arguments": args}
    
    capabilities = []
    for cap_name, meta in catalog.items():
        capabilities.append({
            "name": cap_name,
            "description": meta["description"],
            "parameters": meta["parameters"],
            "required": meta["required"],
        })

    prompt = (
        "Select exactly one capability for the user message and return JSON only.\n"
        "If no capability applies, return {\"capability\": \"\", \"arguments\": {}}.\n"
        f"User message: {message}\n"
        f"Capabilities: {json.dumps(capabilities)}\n"
        "Output schema: {\"capability\": \"name\", \"arguments\": {\"key\": \"value\"}}"
    )
    try:
        raw = llm_client._call_llm(prompt, temperature=0.1, max_tokens=300, expect_json=True)
        parsed = llm_client._extract_json(raw) if raw else None
        if not isinstance(parsed, dict):
            return None
        return parsed
    except Exception:
        return None

def _execute_dynamic_capability(registry, llm_client, message: str):
    catalog = _build_capability_catalog(registry)
    if not catalog:
        return None

    inferred = _infer_capability_call(llm_client, catalog, message)
    if not inferred:
        return None

    capability = str(inferred.get("capability", "")).strip()
    arguments = inferred.get("arguments", {})
    if capability not in catalog or not isinstance(arguments, dict):
        return None

    missing_required = [k for k in catalog[capability]["required"] if k not in arguments]
    if missing_required:
        return None

    return registry.execute_capability(capability, **arguments)

def _needs_runtime_refresh(message: str) -> bool:
    text = (message or "")
    lower = text.lower()
    if "contact_id" in lower or ("create" in lower and "contact" in lower):
        return True
    return bool(_extract_referenced_tool_names(text))

def _extract_referenced_tool_names(message: str) -> List[str]:
    import re
    names = re.findall(r"\b([A-Za-z][A-Za-z0-9_]*Tool(?:V\d+)?)\b", message or "")
    # Preserve order while removing duplicates.
    ordered = list(dict.fromkeys(names))
    return ordered

def _has_referenced_tools_loaded(registry, message: str) -> bool:
    referenced = _extract_referenced_tool_names(message)
    if not referenced:
        return True
    loaded = {tool.__class__.__name__ for tool in registry.tools}
    return all(name in loaded for name in referenced)

def _decision_tool_summary(registry) -> str:
    lines = []
    for tool in registry.tools:
        caps = sorted((tool.get_capabilities() or {}).keys())
        if caps:
            lines.append(f"- {tool.__class__.__name__}: {', '.join(caps)}")
    return "\n".join(lines) if lines else "- no tools loaded"

@app.post("/chat")
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid4())
    
    if session_id not in sessions:
        sessions[session_id] = {"messages": []}
        if conversation_memory:
            history = conversation_memory.get_history(session_id, limit=20)
            sessions[session_id]["messages"] = history
    
    # Save user message
    user_msg = {
        "role": "user", 
        "content": request.message,
        "timestamp": time.time()
    }
    sessions[session_id]["messages"].append(user_msg)
    
    if conversation_memory:
        conversation_memory.save_message(session_id, "user", request.message)
    
    if logger:
        logger.log_request(session_id, request.message)
    
    try:
        if SYSTEM_AVAILABLE and registry and llm_client:
            # Keep runtime registry aligned when user references dynamic tools.
            if _needs_runtime_refresh(request.message) and not _has_referenced_tools_loaded(registry, request.message):
                try:
                    refresh_runtime_registry_from_files()
                except Exception:
                    pass

            # Use LLM to classify intent: multi-step task vs direct answer
            intent_prompt = f"""Classify this user request:

User: {request.message}

Is this:
A) A multi-step task requiring planning (e.g., "open google and search X and take screenshot")
B) A simple direct request (e.g., "open google", "what is X?")

Respond with ONLY 'A' or 'B'."""
            
            try:
                intent_response = llm_client._call_llm(intent_prompt, temperature=0.1, max_tokens=10)
                is_multi_step = 'A' in intent_response.strip().upper()
            except:
                is_multi_step = False
            
            # If multi-step task, use autonomous agent
            if is_multi_step and autonomous_agent:
                try:
                    from core.autonomous_agent import AgentGoal
                    goal = AgentGoal(
                        goal_text=request.message,
                        success_criteria=[],
                        max_iterations=5,
                        require_approval=False
                    )
                    result = autonomous_agent.achieve_goal(goal, session_id)
                    
                    if result.get('success'):
                        response_text = f"✓ {result.get('message', 'Task completed')}"
                    else:
                        response_text = result.get('message', 'Task failed')
                    
                    sessions[session_id]["messages"].append({
                        "role": "assistant",
                        "content": response_text,
                        "timestamp": time.time()
                    })
                    
                    if conversation_memory:
                        conversation_memory.save_message(session_id, "assistant", response_text)
                    
                    return ChatResponse(
                        response=response_text,
                        session_id=session_id,
                        success=True,
                        execution_result={"success": True, "mode": "autonomous_agent"}
                    )
                except Exception as e:
                    print(f"[DEBUG] Autonomous agent failed: {e}, falling back to tool calling")
            
            # Try native tool calling (Mistral function calling)
            from planner.tool_calling import ToolCallingClient
            tool_caller = ToolCallingClient(
                ollama_url=llm_client.ollama_url,
                model=llm_client.model,
                registry=registry
            )
            
            conversation_history = sessions[session_id]["messages"][-5:]
            success, tool_calls, initial_response = tool_caller.call_with_tools(request.message, conversation_history)
            
            print(f"[DEBUG] Tool calling result: success={success}, tool_calls={tool_calls}, initial_response={initial_response[:100] if initial_response else None}")
            
            response_text = None
            
            if not success:
                # Tool calling failed - fallback to conversation
                response_text = llm_client.generate_response(request.message, conversation_history)
                execution_result = {"success": True, "mode": "conversation", "fallback": True}
            elif tool_calls:
                # Model selected tools - execute them
                results = []
                errors = []
                
                # Send progress update for multi-step
                if len(tool_calls) > 1:
                    response_text = f"I'll do this in {len(tool_calls)} steps...\n"
                    sessions[session_id]["messages"].append({
                        "role": "assistant",
                        "content": response_text,
                        "timestamp": time.time()
                    })
                
                for idx, call in enumerate(tool_calls, 1):
                    try:
                        tool_name = call["tool"]
                        operation = call["operation"]
                        parameters = call["parameters"]
                        
                        # Show progress
                        step_msg = f"Step {idx}/{len(tool_calls)}: {operation.replace('_', ' ')}..."
                        print(f"[DEBUG] {step_msg}")
                        
                        # Add step message to session
                        if len(tool_calls) > 1:
                            sessions[session_id]["messages"].append({
                                "role": "assistant",
                                "content": step_msg,
                                "timestamp": time.time(),
                                "metadata": {"type": "progress", "step": idx, "total": len(tool_calls)}
                            })
                        
                        print(f"[DEBUG] Executing: {operation} with params: {parameters}")
                        
                        result = registry.execute_capability(
                            f"{operation}",
                            **parameters
                        )
                        
                        print(f"[DEBUG] Result status: {result.status if result else 'None'}")
                        
                        if result and result.status.value == "success":
                            results.append(result.data)
                        else:
                            errors.append(f"{operation}: {result.error_message if result else 'failed'}")
                    except Exception as e:
                        print(f"[DEBUG] Exception executing tool: {e}")
                        error_msg = str(e)
                        if "got an unexpected keyword argument" in error_msg:
                            error_msg = f"I tried to use {call.get('operation', 'a tool')}, but I don't have the right capabilities for that task yet."
                        elif "missing" in error_msg.lower() and "parameter" in error_msg.lower():
                            error_msg = f"I need more information to complete this task."
                        elif "not found" in error_msg.lower():
                            error_msg = f"I don't have the capability to do that yet."
                        errors.append(f"{call.get('operation', 'Task')}: {error_msg}")
                
                if results and not errors:
                    # Success - analyze output and generate UI components
                    print(f"[DEBUG] Analyzing {len(results)} results")
                    result_data = results[0]
                    
                    # Use output analyzer to generate components
                    from core.output_analyzer import OutputAnalyzer
                    components = OutputAnalyzer.analyze(result_data, tool_name, operation)
                    
                    # Generate natural language summary using LLM
                    tool_summary = f"Tool: {tool_calls[0].get('operation', 'unknown')}\nParameters: {tool_calls[0].get('parameters', {})}\nResult: {str(result_data)[:500]}"
                    
                    summary_prompt = f"""You just executed a tool successfully. Explain what you did in a natural, conversational way.

Tool executed: {tool_calls[0].get('operation', 'unknown')}
Parameters: {tool_calls[0].get('parameters', {})}
Result summary: {str(result_data)[:500]}

Respond naturally as if you're explaining what you just did. Be concise (1-2 sentences). Don't say "I executed" - say what you DID.
Example: "I found 5 log entries from the last hour" or "I listed 12 files in the directory"""
                    
                    try:
                        response_text = llm_client.generate_response(summary_prompt, [])
                    except:
                        # Fallback to simple summary
                        if isinstance(result_data, dict):
                            if 'executions' in result_data or 'performance' in result_data:
                                count = len(result_data.get('executions') or result_data.get('performance', []))
                                response_text = f"Found {count} results."
                            elif 'logs' in result_data:
                                count = len(result_data.get('logs', []))
                                response_text = f"Found {count} log entries."
                            else:
                                response_text = "Done."
                        else:
                            response_text = "Done."
                    
                    print(f"[DEBUG] Generated {len(components)} components")
                    execution_result = {
                        "success": True, 
                        "results": results, 
                        "tool_calling": True,
                        "components": components
                    }
                else:
                    error_msg = "; ".join(errors) if errors else "Execution failed"
                    print(f"[DEBUG] Tool execution failed: {error_msg}")
                    
                    # Generate natural language error explanation using LLM
                    error_prompt = f"""A tool execution failed. Explain what went wrong in a natural, helpful way.

Error: {error_msg}

Respond naturally as if you're explaining the problem to a user. Be concise (1-2 sentences). Suggest what they might try instead if appropriate."""
                    
                    try:
                        response_text = llm_client.generate_response(error_prompt, [])
                    except:
                        # Fallback to user-friendly error
                        if "don't have" in error_msg or "not found" in error_msg.lower():
                            response_text = f"I don't have the capability to do that yet. You can create a new tool in Tools Mode to add this functionality."
                        else:
                            response_text = f"I encountered an issue: {error_msg}"
                    
                    execution_result = {"success": False, "errors": errors}
            else:
                # Pure conversation response (no tools selected)
                response_text = initial_response
                execution_result = {"success": True, "mode": "conversation"}
        else:
            response_text = f"System not available. Echo: {request.message}"
            execution_result = {"success": False, "error": "System not initialized"}
        
        if response_text:
            sessions[session_id]["messages"].append({
                "role": "assistant",
                "content": response_text,
                "timestamp": time.time()
            })
            
            if conversation_memory:
                conversation_memory.save_message(session_id, "assistant", response_text)
        
        return ChatResponse(
            response=response_text,
            session_id=session_id,
            success=True,
            execution_result=execution_result
        )
        
    except Exception as e:
        error_response = f"Error processing '{request.message}': {str(e)}"
        
        return ChatResponse(
            response=error_response,
            session_id=session_id,
            success=False,
            execution_result={"success": False, "error": str(e)}
        )

@app.get("/health")
async def health():
    return {"status": "healthy", "system_available": SYSTEM_AVAILABLE}

@app.get("/status")
async def status():
    return {
        "status": "online",
        "system_available": SYSTEM_AVAILABLE,
        "sessions": len(sessions),
        "connections": len(connections),
        "tools": len(registry.tools) if registry else 0,
        "capabilities": len(registry.get_all_capabilities()) if registry else 0
    }

@app.post("/cache/clear")
async def clear_cache():
    """Clear all caches (LLM, tool execution, conversation memory)"""
    try:
        cleared = []
        
        # Clear conversation memory
        if conversation_memory:
            conversation_memory.clear_all()
            cleared.append("conversation_memory")
        
        # Clear LLM cache if available
        if llm_client and hasattr(llm_client, 'clear_cache'):
            llm_client.clear_cache()
            cleared.append("llm_cache")
        
        # Clear session storage
        sessions.clear()
        cleared.append("sessions")
        
        # Clear tool caches (if tools have cache)
        if registry:
            for tool in registry.tools:
                if hasattr(tool, '_cache'):
                    tool._cache.clear()
                    cleared.append(f"{tool.__class__.__name__}_cache")
        
        return {
            "success": True,
            "message": "Caches cleared successfully",
            "cleared": cleared
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/events")
async def event_stream(request: Request):
    """SSE endpoint for real-time updates"""
    from core.event_bus import get_event_bus
    event_bus = get_event_bus()
    
    async def event_generator():
        queue = asyncio.Queue()
        
        async def handler(event):
            await queue.put({
                "event": event.type,
                "data": json.dumps({"type": event.type, "data": event.data, "timestamp": event.timestamp})
            })
        
        # Subscribe to all events
        for event_type in ['log_added', 'loop_started', 'iteration_started', 'task_completed', 'loop_stopped']:
            event_bus.subscribe(event_type, handler)
        
        try:
            # Send initial state
            if improvement_loop:
                status = improvement_loop.get_status()
                yield {
                    "event": "initial_state",
                    "data": json.dumps(status)
                }
            
            # Stream events
            while await request.is_disconnected() == False:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield event
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            for event_type in ['log_added', 'loop_started', 'iteration_started', 'task_completed', 'loop_stopped']:
                try:
                    event_bus.unsubscribe(event_type, handler)
                except: pass
    
    return EventSourceResponse(event_generator())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)
    
    # Subscribe to events
    from core.event_bus import get_event_bus
    event_bus = get_event_bus()
    
    async def send_event(event):
        try:
            if websocket.client_state.name == 'CONNECTED':
                await websocket.send_text(json.dumps({
                    "type": event.type,
                    "data": event.data,
                    "timestamp": event.timestamp
                }))
        except Exception as e:
            print(f"Failed to send event: {e}")
    
    # Store callback reference for cleanup
    callbacks = {
        'log_added': send_event,
        'loop_started': send_event,
        'loop_stopped': send_event,
        'iteration_started': send_event,
        'task_completed': send_event,
        'pending_tool_added': send_event
    }
    
    for event_type, callback in callbacks.items():
        event_bus.subscribe(event_type, callback)
    
    try:
        # Send initial state
        if improvement_loop and websocket.client_state.name == 'CONNECTED':
            try:
                status = improvement_loop.get_status()
                pending_tools = []
                pending_manager = getattr(improvement_loop, "pending_tools_manager", None)
                if pending_manager:
                    pending_tools = pending_manager.get_pending_list()
                await websocket.send_text(json.dumps({
                    "type": "initial_state",
                    "data": {
                        **status,
                        "pending_approvals": improvement_loop.pending_approvals or {},
                        "pending_tools": pending_tools
                    }
                }))
            except Exception as e:
                print(f"Failed to send initial state: {e}")
                return
        
        # Keep connection alive with ping/pong
        while True:
            try:
                if websocket.client_state.name != 'CONNECTED':
                    break
                
                # Wait for ping from client
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                msg = json.loads(data)
                
                if msg.get('type') == 'ping':
                    await websocket.send_text(json.dumps({"type": "pong"}))
                    
            except asyncio.TimeoutError:
                # No ping received, close connection
                break
            except Exception as e:
                print(f"WebSocket error: {e}")
                break
                
    finally:
        # Unsubscribe from events
        for event_type, callback in callbacks.items():
            try:
                event_bus.unsubscribe(event_type, callback)
            except (ValueError, KeyError):
                pass  # Already unsubscribed
        
        if websocket in connections:
            connections.remove(websocket)
        try:
            await websocket.close()
        except Exception:
            pass

if __name__ == "__main__":
    import uvicorn
    import signal
    
    def shutdown_handler(signum, frame):
        """Graceful shutdown handler"""
        print("\nShutdown signal received...")
        if improvement_loop and improvement_loop.state.status.value == "running":
            print("Stopping improvement loop...")
            import asyncio
            asyncio.create_task(improvement_loop.stop_loop("immediate"))
        print("Server shutting down...")
    
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    
    print("Starting CUA Autonomous Agent API Server...")
    
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info", reload=True, reload_dirs=["."])
    server = uvicorn.Server(config)
    
    try:
        import asyncio
        asyncio.run(server.serve())
    except (KeyboardInterrupt, SystemExit):
        pass
