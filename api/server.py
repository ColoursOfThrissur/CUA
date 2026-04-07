import sys
import os
import logging
from contextlib import asynccontextmanager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if 'core.permission_gate' in sys.modules:
    del sys.modules['core.permission_gate']

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
for _noisy in ("httpx", "httpcore", "urllib3", "requests", "uvicorn.access", "multipart"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

from fastapi import FastAPI, WebSocket, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import asyncio
import json
import time
from types import MethodType

from api.bootstrap import RuntimeState, build_runtime, include_router_bundle, load_router_bundle, shutdown_runtime
from api.chat_handler import ChatRequest, ChatResponse, create_chat_handler
from shared.config.branding import get_platform_name


router_bundle = load_router_bundle()
ROUTERS_AVAILABLE = router_bundle.routers_available

runtime = RuntimeState(system_available=False, init_error="Runtime not initialized")
SYSTEM_AVAILABLE = runtime.system_available
registry = None
llm_client = None
improvement_loop = None
skill_registry = None
refresh_runtime_registry_from_files = router_bundle.refresh_runtime_registry_from_files or (lambda: None)


def _runtime_status_payload():
    system_available = bool(runtime and runtime.system_available)
    routers_available = bool(router_bundle and router_bundle.routers_available)
    runtime_init_error = getattr(runtime, "init_error", None)
    router_import_error = getattr(router_bundle, "import_error", None)

    if system_available and routers_available and not runtime_init_error and not router_import_error:
        status = "healthy"
    elif system_available:
        status = "degraded"
    else:
        status = "unhealthy"

    return {
        "status": status,
        "system_available": system_available,
        "routers_available": routers_available,
        "runtime_init_error": runtime_init_error,
        "router_import_error": router_import_error,
    }

# Session storage
sessions = {}
connections = []

async def _runtime_not_ready_stop():
    return {"success": False, "message": runtime.init_error or "Runtime not initialized"}


async def _runtime_not_ready_chat(request: ChatRequest):
    return ChatResponse(
        response=f"System not available. Echo: {request.message}",
        session_id=request.session_id or "uninitialized",
        success=False,
        execution_result={"success": False, "error": runtime.init_error or "Runtime not initialized"},
    )


stop_chat_handler = _runtime_not_ready_stop
chat_handler = _runtime_not_ready_chat


def _assign_runtime(new_runtime: RuntimeState) -> None:
    global runtime, SYSTEM_AVAILABLE, registry, llm_client, improvement_loop, skill_registry

    runtime = new_runtime
    SYSTEM_AVAILABLE = new_runtime.system_available
    registry = new_runtime.registry
    llm_client = new_runtime.llm_client
    improvement_loop = new_runtime.improvement_loop
    skill_registry = new_runtime.skill_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    global stop_chat_handler, chat_handler

    built_runtime = build_runtime(router_bundle)
    _assign_runtime(built_runtime)
    stop_chat_handler, chat_handler = create_chat_handler(
        built_runtime,
        sessions,
        refresh_runtime_registry_from_files,
    )
    app.state.runtime = built_runtime

    try:
        yield
    finally:
        shutdown_runtime(built_runtime)
        stop_chat_handler = _runtime_not_ready_stop
        chat_handler = _runtime_not_ready_chat
        _assign_runtime(RuntimeState(system_available=False, init_error="Runtime shut down"))
        app.state.runtime = runtime


app = FastAPI(title=f"{get_platform_name()} API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

include_router_bundle(app, router_bundle)

from infrastructure.validation.input_validator import InputSizeLimitMiddleware
app.add_middleware(InputSizeLimitMiddleware, max_body_size=10 * 1024 * 1024)

from shared.utils.correlation_context import CorrelationContextManager

@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID")
    with CorrelationContextManager(correlation_id) as corr_id:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = corr_id
        return response


@app.post("/chat/stop")
async def stop_chat():
    return await stop_chat_handler()


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    return await chat_handler(request)


def _build_middleware_stack_compat(self):
    """Bridge FastAPI/Starlette middleware shape differences in this environment."""
    from fastapi.middleware.asyncexitstack import AsyncExitStackMiddleware
    from starlette.middleware import Middleware
    from starlette.middleware.errors import ServerErrorMiddleware
    from starlette.middleware.exceptions import ExceptionMiddleware

    debug = self.debug
    error_handler = None
    exception_handlers = {}

    for key, value in self.exception_handlers.items():
        if key in (500, Exception):
            error_handler = value
        else:
            exception_handlers[key] = value

    middleware = (
        [Middleware(ServerErrorMiddleware, handler=error_handler, debug=debug)]
        + [
            Middleware(cls, **options) if isinstance(item, tuple) else item
            for item in self.user_middleware
            for cls, options in [
                item if isinstance(item, tuple) else (item.cls, getattr(item, "options", getattr(item, "kwargs", {})))
            ]
        ]
        + [
            Middleware(ExceptionMiddleware, handlers=exception_handlers, debug=debug),
            Middleware(AsyncExitStackMiddleware),
        ]
    )

    asgi = self.router
    for item in reversed(middleware):
        cls = item.cls
        args = getattr(item, "args", ())
        kwargs = getattr(item, "options", getattr(item, "kwargs", {}))
        asgi = cls(asgi, *args, **kwargs)
    return asgi


app.build_middleware_stack = MethodType(_build_middleware_stack_compat, app)


@app.get("/health")
async def health(response: Response):
    payload = _runtime_status_payload()
    response.status_code = 200 if payload["status"] == "healthy" else 503
    payload["cors_test"] = "local_only"
    return payload


@app.get("/status")
async def status():
    payload = _runtime_status_payload()
    return {
        **payload,
        "sessions": len(sessions),
        "connections": len(connections),
        "tools": len(registry.tools) if registry else 0,
        "capabilities": len(registry.get_all_capabilities()) if registry else 0,
        "skills": len(skill_registry.list_all()) if skill_registry else 0,
    }


@app.post("/cache/clear")
async def clear_cache():
    try:
        cleared = []
        if runtime.conversation_memory:
            runtime.conversation_memory.clear_all()
            cleared.append("conversation_memory")
        if llm_client and hasattr(llm_client, "clear_cache"):
            llm_client.clear_cache()
            cleared.append("llm_cache")
        sessions.clear()
        cleared.append("sessions")
        if registry:
            for tool in registry.tools:
                if hasattr(tool, "_cache"):
                    tool._cache.clear()
                    cleared.append(f"{tool.__class__.__name__}_cache")
        return {"success": True, "message": "Caches cleared successfully", "cleared": cleared}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/events")
async def event_stream(request: Request):
    from infrastructure.messaging.event_bus import get_event_bus
    event_bus = get_event_bus()

    async def event_generator():
        queue = asyncio.Queue()

        async def handler(event):
            await queue.put({
                "event": event.type,
                "data": json.dumps({"type": event.type, "data": event.data, "timestamp": event.timestamp}),
            })

        for et in ["log_added", "loop_started", "iteration_started", "task_completed", "loop_stopped", "worktree_event"]:
            event_bus.subscribe(et, handler)

        try:
            if improvement_loop:
                yield {"event": "initial_state", "data": json.dumps(improvement_loop.get_status())}
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield event
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            for et in ["log_added", "loop_started", "iteration_started", "task_completed", "loop_stopped", "worktree_event"]:
                try:
                    event_bus.unsubscribe(et, handler)
                except Exception:
                    pass

    return EventSourceResponse(event_generator())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)

    from infrastructure.messaging.event_bus import get_event_bus
    event_bus = get_event_bus()

    async def send_event(event):
        try:
            if websocket.client_state.name == "CONNECTED":
                await websocket.send_text(json.dumps({
                    "type": event.type, "data": event.data, "timestamp": event.timestamp,
                }))
        except Exception as e:
            print(f"Failed to send event: {e}")

    callbacks = {
        "log_added": send_event, "loop_started": send_event, "loop_stopped": send_event,
        "iteration_started": send_event, "task_completed": send_event,
        "pending_tool_added": send_event, "agent_plan": send_event,
        "agent_step_update": send_event, "agent_plan_clear": send_event,
        "worktree_event": send_event,
    }
    for et, cb in callbacks.items():
        event_bus.subscribe(et, cb)

    try:
        if improvement_loop and websocket.client_state.name == "CONNECTED":
            try:
                status = improvement_loop.get_status()
                pending_tools = []
                pending_manager = getattr(improvement_loop, "pending_tools_manager", None)
                if pending_manager:
                    pending_tools = pending_manager.get_pending_list()
                await websocket.send_text(json.dumps({
                    "type": "initial_state",
                    "data": {**status, "pending_approvals": improvement_loop.pending_approvals or {}, "pending_tools": pending_tools},
                }))
            except Exception as e:
                print(f"Failed to send initial state: {e}")
                return

        while True:
            try:
                if websocket.client_state.name != "CONNECTED":
                    break
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                break
            except Exception as e:
                print(f"WebSocket error: {e}")
                break
    finally:
        for et, cb in callbacks.items():
            try:
                event_bus.unsubscribe(et, cb)
            except (ValueError, KeyError):
                pass
        if websocket in connections:
            connections.remove(websocket)
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    import signal

    def shutdown_handler(_signum, _frame):
        print("\nShutdown signal received...")
        print("Server shutting down...")

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    print(f"Starting {get_platform_name()} API server...")
    if llm_client:
        print("Warming up LLM model...")
        llm_client.warmup_model()

    os.environ["CUA_RELOAD_MODE"] = "1"

    config = uvicorn.Config(
        app, host="0.0.0.0", port=8000, log_level="info",
        reload=True, reload_dirs=["."],
        reload_excludes=["test_tmp/*", "pytest_tmp/*", "data/tool_backups/*"],
    )
    server = uvicorn.Server(config)
    try:
        asyncio.run(server.serve())
    except (KeyboardInterrupt, SystemExit):
        pass
