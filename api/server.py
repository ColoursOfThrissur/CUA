import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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

if SYSTEM_AVAILABLE:
    try:
        from core.config_manager import get_config
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
        
        # Initialize self-improvement loop
        orchestrator = UpdateOrchestrator(repo_path=".")
        improvement_loop = SelfImprovementLoop(llm_client, orchestrator, max_iterations=config.improvement.max_iterations)
        
        # Initialize scheduler
        scheduler = ImprovementScheduler()
        scheduler.set_callback(lambda max_iter, dry: asyncio.create_task(
            improvement_loop.start_loop() if not dry else improvement_loop.start_loop()
        ))
        scheduler.start()
        
        # Set instances for routers
        if ROUTERS_AVAILABLE:
            set_loop_instance(improvement_loop)
            set_llm_client(llm_client)
            set_scheduler(scheduler)
        
        print("CUA system initialized successfully")
    except Exception as e:
        print(f"System initialization failed: {e}")
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
        # Load conversation history if available
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
    
    # Log request
    if logger:
        logger.log_request(session_id, request.message)
    
    try:
        if SYSTEM_AVAILABLE and registry:
            message_lower = request.message.lower()
            
            # Detect task intent
            task_keywords = ['plan', 'list', 'create', 'write', 'read', 'delete', 'execute', 'run', 'make', 'generate']
            is_task = any(keyword in message_lower for keyword in task_keywords)
            
            if is_task and 'plan' in message_lower:
                # Complex planning mode
                success, plan, error = llm_client.generate_plan(request.message)
                
                if not success:
                    if logger:
                        logger.log_error("plan_generation_failed", error)
                    response_text = f"Failed to generate plan: {error}"
                    execution_result = {"success": False, "error": error}
                else:
                    # Log plan generation
                    if logger:
                        logger.log_plan_generation(plan.plan_id, len(plan.steps), plan.confidence)
                    
                    # Validate plan
                    validation = plan_validator.validate_plan(plan)
                    
                    if not validation.is_approved:
                        if logger:
                            logger.log_error("plan_validation_failed", ", ".join(validation.reasons))
                        response_text = f"Plan rejected: {', '.join(validation.reasons)}"
                        execution_result = {"success": False, "validation_failed": True}
                    else:
                        # Execute plan with state machine
                        exec_id = str(uuid4())
                        sm_executor = StateMachineExecutor(registry, state_manager)
                        exec_state = sm_executor.execute_plan(plan, exec_id)
                        
                        progress = sm_executor.get_progress(exec_state)
                        
                        # Log execution
                        if logger:
                            logger.log_execution(exec_id, exec_state.overall_state, 
                                               progress['completed_steps'], progress['total_steps'])
                        
                        response_text = f"Plan executed: {progress['completed_steps']}/{progress['total_steps']} steps completed"
                        execution_result = {"success": True, "progress": progress}
                        
                        sessions[session_id]["messages"].append({
                            "role": "assistant",
                            "content": response_text,
                            "timestamp": time.time()
                        })
                        
                        return ChatResponse(
                            response=response_text,
                            session_id=session_id,
                            success=True,
                            execution_result=execution_result,
                            plan={"plan_id": plan.plan_id, "steps": len(plan.steps)}
                        )
            elif is_task:
                # Simple task execution (list, create, etc.)
                if "list" in message_lower and "file" in message_lower:
                    # Check permission first
                    perm_result = permission_gate.check_permission(
                        session_id, "filesystem_tool", "list_directory", {"path": "."}
                    )
                
                    if not perm_result.is_valid:
                        response_text = f"Permission denied: {perm_result.reason}"
                        execution_result = {"success": False, "error": perm_result.reason}
                    else:
                        # Execute real directory listing
                        tool = registry.get_tool_by_name("filesystem_tool")
                        if tool:
                            result = tool.execute("list_directory", {"path": "."})
                            if result.status.value == "success":
                                permission_gate.record_operation(session_id, "filesystem_tool", "list_directory", True)
                                file_list = result.data[:10]  # First 10 files
                                response_text = f"Directory listing: {', '.join(file_list)}"
                                execution_result = {"success": True, "files_found": len(result.data)}
                            else:
                                permission_gate.record_operation(session_id, "filesystem_tool", "list_directory", False)
                                response_text = f"Failed to list directory: {result.error_message}"
                                execution_result = {"success": False, "error": result.error_message}
                        else:
                            response_text = "Filesystem tool not available"
                            execution_result = {"success": False, "error": "Tool not found"}
                    
                elif "create" in message_lower or "write" in message_lower:
                    # Check permission first
                    test_content = f"Created by CUA at {time.time()}: {request.message}"
                    perm_result = permission_gate.check_permission(
                        session_id, "filesystem_tool", "write_file", 
                        {"path": "./output/cua_response.txt", "content": test_content}
                    )
                
                    if not perm_result.is_valid:
                        response_text = f"Permission denied: {perm_result.reason}"
                        execution_result = {"success": False, "error": perm_result.reason}
                    else:
                        # Execute real file creation
                        tool = registry.get_tool_by_name("filesystem_tool")
                        if tool:
                            result = tool.execute("write_file", {
                                "path": "./output/cua_response.txt",
                                "content": test_content
                            })
                            if result.status.value == "success":
                                permission_gate.record_operation(session_id, "filesystem_tool", "write_file", True)
                                response_text = f"File created successfully: {result.data}"
                                execution_result = {"success": True, "file_created": True}
                            else:
                                permission_gate.record_operation(session_id, "filesystem_tool", "write_file", False)
                                response_text = f"Failed to create file: {result.error_message}"
                                execution_result = {"success": False, "error": result.error_message}
                        else:
                            response_text = "Filesystem tool not available"
                            execution_result = {"success": False, "error": "Tool not found"}
                
                else:
                    # Conversational mode - no task detected
                    conversation_history = sessions[session_id]["messages"][-10:]  # Last 10 messages
                    response_text = llm_client.generate_response(request.message, conversation_history)
                    execution_result = {"success": True, "mode": "conversation"}
            else:
                # Conversational mode - no task detected
                conversation_history = sessions[session_id]["messages"][-10:]  # Last 10 messages
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
        
        # Save assistant response
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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)
    
    try:
        last_log_count = 0
        while True:
            if improvement_loop:
                status = improvement_loop.get_status()
                current_logs = status.get('logs', [])
                
                # Send new logs immediately
                if len(current_logs) > last_log_count:
                    new_logs = current_logs[last_log_count:]
                    for log in new_logs:
                        await websocket.send_text(json.dumps({
                            "type": "new_log",
                            "data": log,
                            "timestamp": time.time()
                        }))
                    last_log_count = len(current_logs)
                
                # Send full status update
                pending = {}
                if hasattr(improvement_loop, 'pending_approvals'):
                    pending = improvement_loop.pending_approvals or {}
                
                await websocket.send_text(json.dumps({
                    "type": "improvement_status",
                    "data": {
                        **status,
                        "pending_approvals": pending
                    },
                    "timestamp": time.time()
                }))
                
                await asyncio.sleep(0.5)  # Check every 500ms
            else:
                await asyncio.sleep(2)
    except Exception as e:
        print(f"WebSocket error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if websocket in connections:
            connections.remove(websocket)

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
    uvicorn.run(app, host="0.0.0.0", port=8000)