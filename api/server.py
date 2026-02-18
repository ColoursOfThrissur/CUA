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
from typing import Optional, Dict
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
    from core.logging_system import get_logger
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
    from api.pending_tools_api import router as pending_tools_router, set_pending_tools_manager, set_tool_registrar
    from api.llm_logs_api import router as llm_logs_router
    from api.tools_api import router as tools_router, set_registry_manager, set_llm_client_for_sync
    from api.libraries_api import router as libraries_router, set_libraries_manager
    ROUTERS_AVAILABLE = True
except ImportError as e:
    print(f"Routers not available: {e}")
    ROUTERS_AVAILABLE = False

app = FastAPI(title="CUA Autonomous Agent API")

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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

if SYSTEM_AVAILABLE:
    try:
        from core.config_manager import get_config
        from core.tool_registrar import ToolRegistrar
        from core.tool_registry_manager import ToolRegistryManager
        from core.pending_libraries_manager import PendingLibrariesManager
        config = get_config()
        
        registry = CapabilityRegistry()
        fs_tool = FilesystemTool()
        http_tool = HTTPTool()
        json_tool = JSONTool()
        shell_tool = ShellTool()
        registry.register_tool(fs_tool)
        registry.register_tool(http_tool)
        registry.register_tool(json_tool)
        registry.register_tool(shell_tool)
        executor = SecureExecutor(registry)
        parser = PlanParser()
        permission_gate = PermissionGate()
        llm_client = LLMClient(registry=registry)
        state_manager = StateManager()
        plan_validator = PlanValidator()
        logger = get_logger("cua_api")
        error_recovery = ErrorRecovery()
        conversation_memory = ConversationMemory()
        
        # Initialize tool registrar
        tool_registrar = ToolRegistrar(registry)
        
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
        scheduler.set_callback(lambda max_iter, dry: asyncio.create_task(
            improvement_loop.start_loop() if not dry else improvement_loop.start_loop()
        ))
        scheduler.start()
        
        # Set instances for routers
        if ROUTERS_AVAILABLE:
            print(f"[DEBUG] Setting loop instance: {improvement_loop is not None}")
            set_loop_instance(improvement_loop)
            set_llm_client(llm_client)
            set_scheduler(scheduler)
            set_task_manager(None)
            set_pending_tools_manager(None)
            set_tool_registrar(tool_registrar)
            set_registry_manager(registry_manager)
            set_llm_client_for_sync(llm_client)
            set_libraries_manager(libraries_manager)
        
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
            # Let LLM decide: tool execution or conversation
            decision_prompt = f"""You are CUA, an autonomous agent with tools.

Available tools:
- filesystem_tool: read_file, write_file, list_directory
- http_tool: get, post, put, delete
- json_tool: parse, validate
- shell_tool: execute_command

User request: "{request.message}"

Decide:
- If it's a SIMPLE single tool action (fetch URL, read file, list directory), respond: SIMPLE
- If it's COMPLEX multi-step task (fetch then parse then save), respond: COMPLEX
- If it's just CHAT/conversation, respond: CHAT

Respond with only one word: SIMPLE, COMPLEX, or CHAT"""
            
            decision = llm_client._call_llm(decision_prompt, temperature=0.1, max_tokens=10, expect_json=False)
            decision = decision.strip().upper() if decision else "CHAT"
            
            if decision == "SIMPLE":
                # Fast path: direct execution without planning
                import re
                
                # Parse simple commands
                if re.search(r'(get|fetch|scrape)\s+(https?://\S+)', request.message, re.I):
                    url_match = re.search(r'https?://\S+', request.message)
                    url = url_match.group(0)
                    result = registry.execute_capability('http_tool', 'get', {'url': url})
                elif re.search(r'(read|show|cat)\s+(.+)', request.message, re.I):
                    file_match = re.search(r'(read|show|cat)\s+(.+)', request.message, re.I)
                    path = file_match.group(2).strip()
                    result = registry.execute_capability('filesystem_tool', 'read_file', {'path': path})
                elif re.search(r'(list|ls)\s*(.+)?', request.message, re.I):
                    dir_match = re.search(r'(list|ls)\s*(.+)?', request.message, re.I)
                    path = dir_match.group(2).strip() if dir_match.group(2) else '.'
                    result = registry.execute_capability('filesystem_tool', 'list_directory', {'path': path})
                else:
                    result = None
                
                if result and result.status.value == "success":
                    summary_prompt = f"""User asked: {request.message}

Tool result: {result.data}

Provide a helpful, natural response. Be concise."""
                    response_text = llm_client._call_llm(summary_prompt, temperature=0.7, max_tokens=500, expect_json=False)
                    execution_result = {"success": True, "fast_path": True}
                else:
                    error = result.error_message if result else "Could not parse command"
                    response_text = f"Failed: {error}"
                    execution_result = {"success": False, "error": error}
            
            elif decision == "COMPLEX":
                # Full planning path for complex multi-step tasks
                # Switch to Mistral for planning
                original_model = llm_client.model
                try:
                    llm_client._unload_model()
                    llm_client.set_model('mistral:latest')
                
                    # Generate plan using LLM
                    success, plan, error = llm_client.generate_plan(request.message)
                    
                    if not success:
                        response_text = f"Failed to generate plan: {error}"
                        execution_result = {"success": False, "error": error}
                    else:
                        # Validate plan
                        validation = plan_validator.validate_plan(plan)
                        
                        if not validation.is_approved:
                            response_text = f"Plan rejected: {', '.join(validation.reasons)}"
                            execution_result = {"success": False, "validation_failed": True}
                        else:
                            # Execute plan
                            exec_id = str(uuid4())
                            sm_executor = StateMachineExecutor(registry, state_manager)
                            exec_state = sm_executor.execute_plan(plan, exec_id)
                            
                            # Build response from execution results
                            if exec_state.overall_state == "completed":
                                results = []
                                for step in exec_state.steps:
                                    if step.state.value == "success" and step.result:
                                        results.append(step.result)
                                
                                if results:
                                    # Use LLM to generate natural response from results
                                    summary_prompt = f"""User asked: {request.message}

Tool execution results: {results[0]}

Provide a helpful, natural response to the user based on these results. Be concise."""
                                    response_text = llm_client._call_llm(summary_prompt, temperature=0.7, max_tokens=500, expect_json=False)
                                else:
                                    response_text = "Task completed successfully."
                                execution_result = {"success": True, "results": results}
                            else:
                                # Get error details from failed steps
                                errors = []
                                for step in exec_state.steps:
                                    if step.state.value == "failed" and step.error:
                                        errors.append(f"{step.operation}: {step.error}")
                                
                                error_msg = "; ".join(errors) if errors else exec_state.overall_state
                                response_text = f"Task failed: {error_msg}"
                                execution_result = {"success": False, "state": exec_state.overall_state, "errors": errors}
                
                finally:
                    # Restore original model
                    llm_client._unload_model()
                    llm_client.set_model(original_model)
            else:
                # Conversational mode (CHAT)
                conversation_history = sessions[session_id]["messages"][-10:]
                response_text = llm_client.generate_response(request.message, conversation_history)
                execution_result = {"success": True, "mode": "conversation"}
        else:
            response_text = f"System not available. Echo: {request.message}"
            execution_result = {"success": False, "error": "System not initialized"}
        
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
                await websocket.send_text(json.dumps({
                    "type": "initial_state",
                    "data": {
                        **status,
                        "pending_approvals": improvement_loop.pending_approvals or {},
                        "pending_tools": []
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