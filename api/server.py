import sys
import os
import logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Clear any cached bad imports
if 'core.permission_gate' in sys.modules:
    del sys.modules['core.permission_gate']

# ── Logging setup ─────────────────────────────────────────────────────────────
# Configure root logger so all logger.info/debug calls across every module
# (planner, agent, execution_engine, etc.) appear in the terminal.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,  # override any prior basicConfig calls
)
# Keep noisy third-party loggers quieter
for _noisy in ("httpx", "httpcore", "urllib3", "requests", "uvicorn.access", "multipart"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
# ──────────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
import asyncio
import json
import time
from typing import Optional, Dict, Any, List
from uuid import uuid4
from api.bootstrap import build_runtime, include_router_bundle, load_router_bundle
from core.artifact_policy import (
    allowed_tools_for_artifacts,
    build_artifacts,
    choose_web_next_action,
    summarize_artifacts_for_prompt,
)
from core.skills import build_domain_catalog, build_skill_planning_context

router_bundle = load_router_bundle()
ROUTERS_AVAILABLE = router_bundle.routers_available

app = FastAPI(title="CUA Autonomous Agent API")

# Add CORS middleware FIRST, before anything else
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

include_router_bundle(app, router_bundle)

# Add input size limit middleware
from core.input_validation import InputSizeLimitMiddleware
app.add_middleware(InputSizeLimitMiddleware, max_body_size=10 * 1024 * 1024)  # 10MB

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



runtime = build_runtime(router_bundle)
SYSTEM_AVAILABLE = runtime.system_available
registry = runtime.registry
executor = runtime.executor
parser = runtime.parser
permission_gate = runtime.permission_gate
llm_client = runtime.llm_client
state_manager = runtime.state_manager
plan_validator = runtime.plan_validator
logger = runtime.logger
error_recovery = runtime.error_recovery
improvement_loop = runtime.improvement_loop
conversation_memory = runtime.conversation_memory
scheduler = runtime.scheduler
registry_manager = runtime.registry_manager
libraries_manager = runtime.libraries_manager
task_planner = runtime.task_planner
execution_engine = runtime.execution_engine
memory_system = runtime.memory_system
autonomous_agent = runtime.autonomous_agent
tool_orchestrator = runtime.tool_orchestrator
refresh_runtime_registry_from_files = router_bundle.refresh_runtime_registry_from_files or (lambda: None)
skill_registry = runtime.skill_registry
skill_selector = runtime.skill_selector

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


def _selected_ui_renderer(skill_selection: Optional[Dict[str, Any]]) -> Optional[str]:
    planning_context = (skill_selection or {}).get("planning_context") or {}
    return planning_context.get("ui_renderer")


def _selected_output_types(skill_selection: Optional[Dict[str, Any]]) -> List[str]:
    planning_context = (skill_selection or {}).get("planning_context") or {}
    return planning_context.get("output_types") or []


def _truncate_for_history(value: Any, limit: int = 1200) -> str:
    text = json.dumps(value, default=str) if not isinstance(value, str) else value
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def _select_primary_result(results: List[Any], executed_history: List[Dict[str, Any]]) -> tuple[Any, Optional[str], Optional[str]]:
    if not results:
        return None, None, None

    best_index = 0
    best_score = -1
    for idx, item in enumerate(results):
        score = 0
        if isinstance(item, dict):
            if isinstance(item.get("sources"), list):
                score += 6
            if isinstance(item.get("links"), list):
                score += 5
            if isinstance(item.get("results"), list):
                score += 4
            if item.get("mode") in {"source_collection", "browser", "crawl"}:
                score += 3
            if item.get("content"):
                score += 1
        if score > best_score:
            best_index = idx
            best_score = score

    history_entry = executed_history[best_index] if best_index < len(executed_history) else {}
    return (
        results[best_index],
        history_entry.get("tool"),
        history_entry.get("operation"),
    )


def _execute_tool_calls(tool_calls: List[Dict[str, Any]], session_id: str) -> tuple[List[Any], List[str], List[Dict[str, Any]], Optional[str], Optional[str]]:
    results: List[Any] = []
    errors: List[str] = []
    executed_calls: List[Dict[str, Any]] = []
    last_tool_name: Optional[str] = None
    last_operation: Optional[str] = None

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
            last_tool_name = tool_name
            last_operation = operation

            # Check if tool exists, if not try refreshing registry
            if not registry.get_tool_by_name(tool_name):
                print(f"[DEBUG] Tool {tool_name} not found, attempting registry refresh...")
                try:
                    refresh_runtime_registry_from_files()
                    print(f"[DEBUG] Registry refreshed, rechecking tool {tool_name}...")
                except Exception as e:
                    print(f"[DEBUG] Registry refresh failed: {e}")

            step_msg = f"Step {idx}/{len(tool_calls)}: {operation.replace('_', ' ')}..."
            print(f"[DEBUG] {step_msg}")

            if len(tool_calls) > 1:
                sessions[session_id]["messages"].append({
                    "role": "assistant",
                    "content": step_msg,
                    "timestamp": time.time(),
                    "metadata": {"type": "progress", "step": idx, "total": len(tool_calls)}
                })

            print(f"[DEBUG] Executing: {operation} with params: {parameters}")

            result = registry.execute_tool_capability(
                tool_name,
                operation,
                **parameters
            )

            print(f"[DEBUG] Result status: {result.status if result else 'None'}")

            if result and result.status.value == "success":
                results.append(result.data)
                executed_calls.append({
                    "tool": tool_name,
                    "operation": operation,
                    "parameters": parameters,
                    "success": True,
                    "data": result.data,
                })
            else:
                error_message = result.error_message if result else "failed"
                errors.append(f"{operation}: {error_message}")
                executed_calls.append({
                    "tool": tool_name,
                    "operation": operation,
                    "parameters": parameters,
                    "success": False,
                    "error": error_message,
                })
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
            executed_calls.append({
                "tool": call.get("tool"),
                "operation": call.get("operation"),
                "parameters": call.get("parameters", {}),
                "success": False,
                "error": error_msg,
            })

    return results, errors, executed_calls, last_tool_name, last_operation


def _continue_tool_calling(
    tool_caller,
    original_message: str,
    base_history: List[Dict[str, Any]],
    executed_calls: List[Dict[str, Any]],
    skill_selection: Dict[str, Any],
    execution_context: Optional[Any] = None,
):
    executed_summary = _truncate_for_history(executed_calls, limit=3000)
    planning_context = skill_selection.get("planning_context") or {}
    preferred_tools = planning_context.get("preferred_tools") or []
    category = skill_selection.get("category")
    artifacts = build_artifacts(executed_calls)
    allowed_tools = allowed_tools_for_artifacts(category, preferred_tools, executed_calls, artifacts)
    if category == "web":
        synthetic_follow_up = choose_web_next_action(artifacts)
        if synthetic_follow_up:
            return True, synthetic_follow_up, None

    # Refresh skill_context with live execution state for better LLM guidance
    refreshed_skill_context = dict(planning_context)
    if execution_context:
        refreshed_skill_context["completed_steps"] = len(getattr(execution_context, "step_history", []))
        refreshed_skill_context["errors_so_far"] = len(getattr(execution_context, "errors_encountered", []))
        refreshed_skill_context["selected_tool"] = getattr(execution_context, "selected_tool", None)
        refreshed_skill_context["fallback_tools"] = getattr(execution_context, "fallback_tools", [])
        refreshed_skill_context["warnings"] = getattr(execution_context, "warnings", [])[-3:]
        # Narrow allowed_tools to healthy tools from refreshed context
        if execution_context.available_tools:
            healthy = [n for n, tv in execution_context.available_tools.items() if getattr(tv, "healthy", True)]
            if healthy:
                allowed_tools = healthy

    continuation_history = list(base_history)
    continuation_history.append({"role": "user", "content": original_message})
    continuation_history.append({
        "role": "assistant",
        "content": (
            "Tool execution results from the previous step:\n"
            f"{executed_summary}\n\n"
            "Current artifact state:\n"
            f"{summarize_artifacts_for_prompt(artifacts)}\n\n"
            "Continue only if the original user task still needs more work.\n"
            "Stay on the user's task domain and use task-relevant tools only.\n"
            f"Prefer these tools for continuation: {', '.join(preferred_tools) or 'same-family tools as before'}.\n"
            "Choose next steps from the artifact state. For web research:\n"
            "- If artifacts are only search results or links, fetch the MOST RELEVANT specific article URL (not homepage)\n"
            "- If you have fetched content but no summary, use ContextSummarizerTool to summarize\n"
            "- Look for specific article URLs like '/wiki/Artificial_general_intelligence' not just domain homepages\n"
            "Do not use internal diagnostics, observability, metrics, database, registry, or improvement tools unless the user explicitly asked about the system itself.\n"
            "If the task is complete, answer the user directly."
        ),
    })
    success, tool_calls, response = tool_caller.call_with_tools(
        "Review the previous tool results and continue only if needed.",
        continuation_history,
        skill_context=refreshed_skill_context,
        allowed_tools=allowed_tools or None,
    )
    if category == "web" and (not success or not tool_calls):
        synthetic_follow_up = choose_web_next_action(artifacts)
        if synthetic_follow_up:
            return True, synthetic_follow_up, None
    return success, tool_calls, response

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

def _record_capability_gap(task: str, error: str = "", skill_selection: Optional[Dict[str, Any]] = None) -> None:
    """Detect gap → resolve through cheapest path (platform-aware) → persist with resolution metadata."""
    try:
        from core.capability_mapper import CapabilityMapper
        from core.gap_detector import GapDetector
        from core.gap_tracker import GapTracker
        from core.capability_resolver import CapabilityResolver
        from core.semantic_router import get_semantic_router

        mapper = CapabilityMapper()
        mapper.build_capability_graph()

        detector = GapDetector(mapper)
        gap = detector.analyze_failed_task(task, error or "", skill_selection=skill_selection)
        if not gap or gap.confidence < 0.75:
            return

        # Enrich with semantic context for platform-aware resolution
        semantic_ctx = get_semantic_router(llm_client).route(task)
        semantic_dict = semantic_ctx.to_dict() if semantic_ctx else None

        resolver = CapabilityResolver(registry=registry)
        resolution = resolver.resolve(gap, semantic_context=semantic_dict)

        gap.suggested_action = resolution.action
        if resolution.target:
            gap.target_tool = resolution.target

        tracker = GapTracker()
        tracker.record_gap(gap)

        if resolution.resolved:
            tracker.mark_resolved(
                gap.capability,
                action=resolution.action,
                target=resolution.target,
                notes=resolution.notes,
            )

        print(f"[GAP] {gap.capability} → {resolution.action}"
              + (f" via {resolution.target}" if resolution.target else "")
              + (f" [{semantic_ctx.domain}/{semantic_ctx.primary_profile.platform if semantic_ctx.primary_profile else '?'}]" if semantic_ctx and semantic_ctx.domain else ""))
    except Exception:
        return


def _select_skill_for_message(message: str) -> Optional[Dict[str, Any]]:
    if not skill_registry or not skill_selector:
        return None
    
    # Quick check for simple conversational messages
    simple_greetings = {"hi", "hello", "hey", "thanks", "thank you", "bye", "goodbye"}
    if message.lower().strip() in simple_greetings:
        return {
            "matched": False,
            "skill_name": None,
            "category": None,
            "confidence": 0.0,
            "reason": "simple_greeting",
            "fallback_mode": "direct_tool_routing",
            "candidate_skills": [],
            "auto_detection_used": False,
        }
    
    # Use auto-skill detection with fallback
    from core.auto_skill_detection import detect_skill_with_fallback
    
    auto_result = detect_skill_with_fallback(
        message, skill_registry, skill_selector, llm_client,
        confidence_threshold=0.35,
        allow_manual=False  # For now, don't offer manual selection in API
    )
    
    if auto_result.mode.value == "direct_routing":
        return {
            "matched": False,
            "skill_name": None,
            "category": None,
            "confidence": auto_result.confidence,
            "reason": auto_result.reason,
            "fallback_mode": "direct_tool_routing",
            "candidate_skills": auto_result.manual_options,
            "auto_detection_used": True,
        }
    
    if auto_result.mode.value == "manual":
        # For API, fall back to direct routing instead of manual
        return {
            "matched": False,
            "skill_name": None,
            "category": None,
            "confidence": auto_result.confidence,
            "reason": f"Manual selection required: {auto_result.reason}",
            "fallback_mode": "direct_tool_routing",
            "candidate_skills": auto_result.manual_options,
            "auto_detection_used": True,
        }
    
    # Auto detection succeeded
    skill = skill_registry.get(auto_result.skill_name)
    if not skill:
        return {
            "matched": False,
            "skill_name": None,
            "category": None,
            "confidence": 0.0,
            "reason": "auto_detected_skill_not_found",
            "fallback_mode": "direct_tool_routing",
            "candidate_skills": [],
            "auto_detection_used": True,
        }
    
    planning_context = build_skill_planning_context(skill) if skill else None
    domain_catalog = build_domain_catalog(skill_registry, registry, auto_result.skill_name) if skill_registry and registry else None
    
    return {
        "matched": True,
        "skill_name": auto_result.skill_name,
        "category": skill.category,
        "confidence": auto_result.confidence,
        "reason": auto_result.reason,
        "fallback_mode": skill.fallback_strategy,
        "candidate_skills": auto_result.manual_options,
        "auto_detection_used": auto_result.fallback_used,
        "planning_context": {
            "skill_name": planning_context.skill_name,
            "category": planning_context.category,
            "instructions_summary": planning_context.instructions_summary,
            "preferred_tools": planning_context.preferred_tools,
            "required_tools": planning_context.required_tools,
            "verification_mode": planning_context.verification_mode,
            "output_types": planning_context.output_types,
            "ui_renderer": planning_context.ui_renderer,
            "skill_constraints": planning_context.skill_constraints,
            "domain_catalog": domain_catalog,
        } if planning_context else None,
    }


def _build_planner_context(skill_selection: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    planning_context = (skill_selection or {}).get("planning_context")
    context = {}
    if planning_context:
        context["skill_context"] = planning_context
        context["domain_catalog"] = planning_context.get("domain_catalog")
    return context


def _attempt_actionable_planning_fallback(request_message: str, session_id: str, skill_selection: Dict[str, Any]):
    from dataclasses import asdict

    if not task_planner:
        return None

    plan = task_planner.plan_task(request_message, context=_build_planner_context(skill_selection))
    plan.requires_approval = True
    sessions[session_id]["pending_agent_plan"] = plan
    sessions[session_id]["pending_agent_plan_iteration"] = None
    plan_dict = asdict(plan) if hasattr(plan, "__dataclass_fields__") else plan
    response_text = "I identified this as an executable task and prepared a plan. Review it and reply 'go ahead' to run it."

    sessions[session_id]["messages"].append({
        "role": "assistant",
        "content": response_text,
        "timestamp": time.time(),
        "skill": skill_selection.get("skill_name"),
        "category": skill_selection.get("category"),
    })
    if conversation_memory:
        conversation_memory.save_message(session_id, "assistant", response_text)

    return ChatResponse(
        response=response_text,
        session_id=session_id,
        success=True,
        execution_result={
            "success": False,
            "mode": "planned_fallback",
            "status": "awaiting_approval",
            "plan": plan_dict,
            "selected_skill": skill_selection.get("skill_name"),
            "selected_category": skill_selection.get("category"),
            "skill_confidence": skill_selection.get("confidence"),
            "fallback_used": False,
            "ui_renderer": _selected_ui_renderer(skill_selection),
        }
    )

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

def _validate_output_against_skill(data: Any, execution_context: Any) -> Optional[str]:
    """Validate output matches skill verification_mode requirements."""
    verification_mode = getattr(execution_context, 'verification_mode', None)
    
    if not verification_mode or not isinstance(data, dict):
        return None
    
    if verification_mode == "source_backed":
        if "sources" not in data or not data["sources"]:
            return "Output missing 'sources' field required by skill verification_mode"
        if "summary" not in data and "content" not in data:
            return "Output missing 'summary' or 'content' field required by skill verification_mode"
    
    elif verification_mode == "side_effect_observed":
        if "file_path" not in data and "path" not in data:
            return "Output missing 'file_path' or 'path' field required by skill verification_mode"
    
    # Validate expected_output_types if specified
    expected_types = getattr(execution_context, 'expected_output_types', [])
    if expected_types:
        # Check if output has any of the expected type indicators
        output_keys = set(data.keys())
        type_indicators = {
            "research_summary": ["sources", "summary"],
            "page_summary": ["content", "url"],
            "file_list": ["files", "paths"],
            "execution_result": ["output", "result"]
        }
        
        matched = False
        for expected_type in expected_types:
            indicators = type_indicators.get(expected_type, [])
            if any(ind in output_keys for ind in indicators):
                matched = True
                break
        
        if not matched and expected_types:
            return f"Output type doesn't match expected types: {expected_types}"
    
    return None

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

# Cancellation flag for active agent runs
_stop_requested = False

@app.post("/chat/stop")
async def stop_chat():
    global _stop_requested
    _stop_requested = True
    return {"success": True, "message": "Stop requested"}


@app.post("/chat")
async def chat(request: ChatRequest):
    global _stop_requested
    _stop_requested = False  # reset on each new request
    from core.input_validation import validate_text_input
    from dataclasses import asdict
    
    # Validate input size
    try:
        validate_text_input(request.message, max_length=50000, field_name="message")
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))
    
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
    
    # Initialize execution_result early to avoid uninitialized variable errors
    execution_result: Optional[Dict] = {"success": False, "error": "Unknown error"}
    response_text = ""
    
    try:
        if SYSTEM_AVAILABLE and registry and llm_client:
            # Enhanced early return for simple conversational messages
            message_lower = request.message.lower().strip()
            message_words = message_lower.split()
            
            # Expanded simple patterns
            simple_patterns = {
                "hi", "hello", "hey", "thanks", "thank you", "bye", "goodbye", 
                "how are you", "what's up", "good morning", "good afternoon", "good evening",
                "ok", "okay", "yes", "no", "sure", "great", "nice", "cool", "awesome"
            }
            
            # Check for simple conversational patterns
            is_simple_message = (
                message_lower in simple_patterns or
                (len(request.message.strip()) < 20 and 
                 not any(keyword in message_lower for keyword in [
                     '?', 'what', 'how', 'when', 'where', 'why', 'can you', 'please', 
                     'help', 'do', 'get', 'find', 'search', 'open', 'run', 'execute',
                     'create', 'make', 'build', 'write', 'read', 'list', 'show'
                 ])) or
                (len(message_words) <= 3 and all(word in simple_patterns or len(word) <= 4 for word in message_words))
            )
            
            # For simple messages, skip ALL expensive processing
            if is_simple_message:
                # Generate appropriate response based on message
                if any(greeting in message_lower for greeting in ["hi", "hello", "hey"]):
                    response_text = "Hello! How can I assist you today?"
                elif any(thanks in message_lower for thanks in ["thanks", "thank you"]):
                    response_text = "You're welcome! Let me know if you need anything else."
                elif any(bye in message_lower for bye in ["bye", "goodbye"]):
                    response_text = "Goodbye! Feel free to come back anytime."
                elif message_lower in ["ok", "okay", "yes", "sure"]:
                    response_text = "Great! What would you like to do next?"
                elif message_lower == "no":
                    response_text = "No problem. Let me know if you change your mind."
                else:
                    response_text = "I'm here to help! What can I do for you?"
                
                execution_result = {"success": True, "mode": "conversation", "simple_greeting": True}
                
                sessions[session_id]["messages"].append({
                    "role": "assistant",
                    "content": response_text,
                    "timestamp": time.time(),
                })
                
                if conversation_memory:
                    conversation_memory.save_message(session_id, "assistant", response_text)
                
                return ChatResponse(
                    response=response_text,
                    session_id=session_id,
                    success=True,
                    execution_result=execution_result
                )
            
            skill_selection = _select_skill_for_message(request.message) or {
                "matched": False,
                "skill_name": None,
                "category": None,
                "confidence": 0.0,
                "reason": "skill_system_unavailable",
                "fallback_mode": "direct_tool_routing",
                "candidate_skills": [],
            }
            
            # Handle conversation skill efficiently - always use full tool context
            if skill_selection.get("skill_name") == "conversation":
                conversation_history = sessions[session_id]["messages"][-5:]
                response_text = llm_client.generate_response(request.message, conversation_history)
                
                execution_result = {
                    "success": True, 
                    "mode": "conversation", 
                    "skill_optimized": True,
                    "selected_skill": "conversation",
                    "selected_category": "conversation",
                    "skill_confidence": skill_selection.get("confidence", 0.0)
                }
                
                sessions[session_id]["messages"].append({
                    "role": "assistant",
                    "content": response_text,
                    "timestamp": time.time(),
                    "skill": "conversation",
                    "category": "conversation",
                })
                
                if conversation_memory:
                    conversation_memory.save_message(session_id, "assistant", response_text)
                
                return ChatResponse(
                    response=response_text,
                    session_id=session_id,
                    success=True,
                    execution_result=execution_result
                )

            # If the previous assistant turn paused for an autonomous-agent plan approval,
            # allow the user to approve/reject that plan directly in chat.
            pending_plan = sessions[session_id].get("pending_agent_plan")
            if pending_plan is not None:
                msg_norm = (request.message or "").strip().lower()
                approve_words = {"go ahead", "approve", "approved", "yes", "ok", "okay", "continue", "proceed", "run it", "do it"}
                reject_words = {"no", "reject", "cancel", "stop", "abort"}

                if msg_norm in approve_words:
                    sessions[session_id].pop("pending_agent_plan", None)
                    sessions[session_id].pop("pending_agent_plan_iteration", None)

                    execution_id = f"{session_id}_approved_{int(time.time())}"
                    try:
                        state = execution_engine.execute_plan(pending_plan, execution_id) if execution_engine else None
                        if state and getattr(state, "error", None):
                            response_text = f"Plan approved, but execution failed: {state.error}"
                            execution_result = {"success": False, "mode": "autonomous_agent", "status": "execution_failed", "execution_id": execution_id, "error": state.error}
                        else:
                            response_text = "✓ Plan approved and executed."
                            execution_result = {"success": True, "mode": "autonomous_agent", "status": "executed", "execution_id": execution_id}
                    except Exception as e:
                        response_text = f"Plan approved, but execution failed: {str(e)}"
                        execution_result = {"success": False, "mode": "autonomous_agent", "status": "execution_failed", "error": str(e)}

                    sessions[session_id]["messages"].append({"role": "assistant", "content": response_text, "timestamp": time.time()})
                    if conversation_memory:
                        conversation_memory.save_message(session_id, "assistant", response_text)
                    execution_result.update({
                        "selected_skill": skill_selection.get("skill_name"),
                        "selected_category": skill_selection.get("category"),
                        "skill_confidence": skill_selection.get("confidence"),
                        "fallback_used": False,
                    })
                    return ChatResponse(response=response_text, session_id=session_id, success=True, execution_result=execution_result)

                if msg_norm in reject_words:
                    sessions[session_id].pop("pending_agent_plan", None)
                    sessions[session_id].pop("pending_agent_plan_iteration", None)
                    response_text = "Cancelled. I won’t execute that plan."
                    execution_result = {"success": False, "mode": "autonomous_agent", "status": "rejected"}
                    sessions[session_id]["messages"].append({"role": "assistant", "content": response_text, "timestamp": time.time()})
                    if conversation_memory:
                        conversation_memory.save_message(session_id, "assistant", response_text)
                    execution_result.update({
                        "selected_skill": skill_selection.get("skill_name"),
                        "selected_category": skill_selection.get("category"),
                        "skill_confidence": skill_selection.get("confidence"),
                        "fallback_used": False,
                    })
                    return ChatResponse(response=response_text, session_id=session_id, success=True, execution_result=execution_result)

                plan_dict = asdict(pending_plan) if hasattr(pending_plan, "__dataclass_fields__") else pending_plan
                response_text = "Plan requires user approval. Reply 'go ahead' to approve or 'cancel' to reject."
                execution_result = {"success": False, "mode": "autonomous_agent", "status": "awaiting_approval", "plan": plan_dict}
                sessions[session_id]["messages"].append({"role": "assistant", "content": response_text, "timestamp": time.time()})
                if conversation_memory:
                    conversation_memory.save_message(session_id, "assistant", response_text)
                execution_result.update({
                    "selected_skill": skill_selection.get("skill_name"),
                    "selected_category": skill_selection.get("category"),
                    "skill_confidence": skill_selection.get("confidence"),
                    "fallback_used": False,
                })
                return ChatResponse(response=response_text, session_id=session_id, success=True, execution_result=execution_result)

            # Keep runtime registry aligned when user references dynamic tools.
            if _needs_runtime_refresh(request.message) and not _has_referenced_tools_loaded(registry, request.message):
                try:
                    refresh_runtime_registry_from_files()
                except Exception:
                    pass

            # Derive intent from skill selection — no extra LLM call needed
            # Non-conversation skills with multi-word goals are treated as multi-step tasks
            skill_cat = skill_selection.get("category") or ""
            is_multi_step = (
                autonomous_agent is not None
                and skill_cat not in ("", "conversation")
                and len(request.message.split()) >= 4
            )
            
            # If multi-step task, use autonomous agent
            if is_multi_step and autonomous_agent:
                try:
                    from core.autonomous_agent import AgentGoal
                    import api.server as _srv
                    goal = AgentGoal(
                        goal_text=request.message,
                        success_criteria=[],
                        max_iterations=5,
                        require_approval=False
                    )
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(
                        None,
                        lambda: autonomous_agent.achieve_goal(
                            goal, session_id,
                            stop_check=lambda: _srv._stop_requested
                        )
                    )

                    # If the agent pauses for plan approval, surface the plan details to the UI and
                    # store it in session state so a later "go ahead" can execute the SAME plan.
                    if result.get("status") == "awaiting_approval" and result.get("plan") is not None:
                        plan_obj = result.get("plan")
                        sessions[session_id]["pending_agent_plan"] = plan_obj
                        sessions[session_id]["pending_agent_plan_iteration"] = result.get("iteration")
                        plan_dict = asdict(plan_obj) if hasattr(plan_obj, "__dataclass_fields__") else plan_obj
                        response_text = result.get("message", "Plan requires user approval")

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
                            execution_result={
                                "success": False,
                                "mode": "autonomous_agent",
                                "status": "awaiting_approval",
                                "plan": plan_dict,
                                "selected_skill": skill_selection.get("skill_name"),
                                "selected_category": skill_selection.get("category"),
                                "skill_confidence": skill_selection.get("confidence"),
                                "fallback_used": False,
                            }
                        )
                    
                    if result.get('success'):
                        final_state = result.get('final_state')
                        step_outputs = []
                        screenshot_components = []
                        if final_state and hasattr(final_state, 'step_results'):
                            for step_id, step_result in final_state.step_results.items():
                                if hasattr(step_result, 'status') and str(step_result.status.value) == 'completed':
                                    out = getattr(step_result, 'output', None)
                                    if not out or not isinstance(out, dict):
                                        continue
                                    # Screenshots → components only, never text
                                    if out.get('screenshot_b64'):
                                        screenshot_components.append({
                                            'type': 'screenshot',
                                            'renderer': 'screenshot',
                                            'src': f'data:image/png;base64,{out["screenshot_b64"]}',
                                            'filepath': out.get('filepath', ''),
                                            'alt': f'Screenshot from {step_id}',
                                        })
                                        continue  # skip text extraction for screenshot steps
                                    # search_web: flatten results list into readable snippets
                                    if out.get('results') and isinstance(out['results'], list):
                                        snippets = []
                                        for r in out['results'][:8]:
                                            if isinstance(r, dict):
                                                title = r.get('title', '')
                                                snippet = r.get('snippet') or r.get('description') or r.get('content', '')
                                                url = r.get('url') or r.get('link', '')
                                                snippets.append(f"{title}: {snippet} ({url})")
                                        if snippets:
                                            step_outputs.append({"step": step_id, "search_results": "\n".join(snippets)})
                                            continue
                                    # navigate / fetch_url: use content or elements, strip HTML
                                    for key in ('content', 'text', 'summary', 'result', 'elements', 'pages'):
                                        val = out.get(key)
                                        if val and str(val).strip():
                                            text_val = str(val)
                                            # Skip raw HTML — JS SPA pages have no useful content
                                            if text_val.lstrip().startswith('<') and '<html' in text_val.lower():
                                                continue
                                            step_outputs.append({"step": step_id, key: text_val[:1500]})
                                            break

                        if step_outputs:
                            print(f"[DEBUG] step_outputs for summary ({len(step_outputs)} steps): {[list(o.keys()) for o in step_outputs]}")
                            # Extract the actual content value from each step output dict
                            content_lines = []
                            for o in step_outputs[:6]:
                                for k, v in o.items():
                                    if k != 'step':
                                        content_lines.append(str(v)[:800])
                            summary_prompt = (
                                f"The user asked: {request.message}\n\n"
                                f"Here are the results collected:\n"
                                + "\n".join(f"- {line}" for line in content_lines)
                                + "\n\nSummarize the results clearly and directly for the user. Include the actual data. Be concise but complete."
                            )
                            try:
                                response_text = llm_client.generate_response(summary_prompt, [])
                            except Exception:
                                response_text = f"✓ {result.get('message', 'Task completed')}"
                        else:
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

                    # Clear agent plan from UI now that response is ready
                    try:
                        from core.event_bus import get_event_bus
                        get_event_bus().emit_sync("agent_plan_clear", {})
                    except Exception:
                        pass
                    
                    return ChatResponse(
                        response=response_text,
                        session_id=session_id,
                        success=True,
                        execution_result={
                            "success": bool(result.get('success')),
                            "mode": "autonomous_agent",
                            "selected_skill": skill_selection.get("skill_name"),
                            "selected_category": skill_selection.get("category"),
                            "skill_confidence": skill_selection.get("confidence"),
                            "fallback_used": False,
                            "components": screenshot_components if result.get('success') else [],
                        }
                    )
                except Exception as e:
                    print(f"[DEBUG] Autonomous agent failed: {e}, falling back to tool calling")
            
            # Skip tool calling entirely for simple conversational messages
            message_lower = request.message.lower().strip()
            simple_conversational = (
                len(request.message.strip()) < 30 and
                not any(action in message_lower for action in [
                    'open', 'search', 'find', 'get', 'fetch', 'run', 'execute', 'create', 
                    'make', 'build', 'write', 'read', 'list', 'show', 'take', 'click',
                    'navigate', 'go to', 'download', 'upload', 'delete', 'move', 'copy'
                ]) and
                not '?' in request.message  # Questions might need tools
            )
            
            if simple_conversational:
                # Use simple LLM response without tool calling
                conversation_history = sessions[session_id]["messages"][-5:]
                response_text = llm_client.generate_response(request.message, conversation_history)
                execution_result = {"success": True, "mode": "conversation", "simple_response": True}
                
                sessions[session_id]["messages"].append({
                    "role": "assistant",
                    "content": response_text,
                    "timestamp": time.time(),
                })
                
                if conversation_memory:
                    conversation_memory.save_message(session_id, "assistant", response_text)
                
                return ChatResponse(
                    response=response_text,
                    session_id=session_id,
                    success=True,
                    execution_result=execution_result
                )
            
            # Try native tool calling (Mistral function calling)
            from planner.tool_calling import ToolCallingClient
            from core.skills import SkillContextHydrator, SkillExecutionContext
            from core.skills.tool_selector import ContextAwareToolSelector
            
            tool_caller = ToolCallingClient(
                ollama_url=llm_client.ollama_url,
                model=llm_client.model,
                registry=registry
            )
            
            # Build execution context from skill selection
            execution_context = None
            allowed_tools = None
            if skill_selection.get("matched") and skill_selection.get("skill_name"):
                skill_def = skill_registry.get(skill_selection["skill_name"])
                if skill_def:
                    from core.skills.models import SkillSelection as SkillSelectionModel
                    skill_sel_obj = SkillSelectionModel(
                        matched=True,
                        skill_name=skill_selection["skill_name"],
                        category=skill_selection.get("category"),
                        confidence=skill_selection.get("confidence", 0.0)
                    )
                    execution_context = SkillContextHydrator.build_context(
                        skill_sel_obj,
                        skill_def,
                        request.message
                    )
                    
                    # Select tools based on context (pass skill_registry for usage scores)
                    tool_selector = ContextAwareToolSelector(registry, runtime.circuit_breaker, skill_registry)
                    execution_context = tool_selector.select_tools(execution_context)
                    
                    # Extract allowed tools from execution context
                    allowed_tools = list(execution_context.available_tools.keys()) if execution_context.available_tools else None
                    print(f"[DEBUG] Skill-based tool filtering: {skill_selection['skill_name']} -> {allowed_tools}")
            
            conversation_history = sessions[session_id]["messages"][-5:]
            success, tool_calls, initial_response = tool_caller.call_with_tools(
                request.message,
                conversation_history,
                skill_context=skill_selection.get("planning_context"),
                allowed_tools=allowed_tools,
            )
            
            print(f"[DEBUG] Tool calling result: success={success}, tool_calls={tool_calls}, initial_response={initial_response[:100] if initial_response else None}")
            
            response_text = None
            
            if not success:
                if initial_response == "NO_TOOL_CALLS_FOR_ACTIONABLE_REQUEST":
                    _record_capability_gap(
                        request.message,
                        "NO_TOOL_CALLS_FOR_ACTIONABLE_REQUEST",
                        skill_selection,
                    )
                    planned_response = _attempt_actionable_planning_fallback(request.message, session_id, skill_selection)
                    if planned_response is not None:
                        return planned_response
                # Tool calling failed - fallback to conversation
                response_text = llm_client.generate_response(request.message, conversation_history)
                execution_result = {"success": True, "mode": "conversation", "fallback": True}
            elif tool_calls:
                aggregated_results: List[Any] = []
                aggregated_errors: List[str] = []
                executed_history: List[Dict[str, Any]] = []
                tool_name = None
                operation = None
                final_direct_response: Optional[str] = None
                current_calls = tool_calls
                current_history = list(conversation_history)

                for round_index in range(3):
                    # Refresh execution context for each round
                    if execution_context and round_index > 0:
                        # Refresh available tools (check circuit breaker again)
                        tool_selector = ContextAwareToolSelector(registry, runtime.circuit_breaker, skill_registry)
                        execution_context = tool_selector.select_tools(execution_context)
                        
                        # Reset retry count for new round
                        execution_context.retry_count = 0
                        
                        # Add round transition info
                        execution_context.warnings.append(f"Starting continuation round {round_index + 1}")
                    
                    results, errors, executed_calls, last_tool_name, last_operation = _execute_tool_calls(
                        current_calls,
                        session_id,
                    )
                    aggregated_results.extend(results)
                    aggregated_errors.extend(errors)
                    executed_history.extend(executed_calls)
                    tool_name = last_tool_name or tool_name
                    operation = last_operation or operation
                    
                    # Update execution context with step results
                    if execution_context:
                        for call in executed_calls:
                            execution_context.add_step(
                                tool=call.get('tool', ''),
                                operation=call.get('operation', ''),
                                status='success' if call.get('success') else 'failure',
                                duration=0.0,
                                result=call.get('data') if call.get('success') else None
                            )
                            if not call.get('success'):
                                execution_context.add_error(
                                    tool=call.get('tool', ''),
                                    error=call.get('error', 'Unknown error'),
                                    retry_count=execution_context.retry_count
                                )
                        
                        # Propagate selected tool changes back to context
                        if last_tool_name and last_tool_name != execution_context.selected_tool:
                            execution_context.selected_tool = last_tool_name
                            execution_context.tool_selection_reasoning = f"Updated to {last_tool_name} in round {round_index + 1}"

                    if errors or not results:
                        # Check if we should fallback to secondary tool
                        if execution_context and execution_context.should_fallback():
                            fallback_tool = execution_context.fallback_tools[0] if execution_context.fallback_tools else None
                            if fallback_tool:
                                execution_context.warnings.append(f"Primary tool failed, trying {fallback_tool}")
                                execution_context.selected_tool = fallback_tool
                                execution_context.retry_count += 1
                                # Continue to next round with fallback tool
                                continue
                        break

                    follow_success, follow_tool_calls, follow_response = _continue_tool_calling(
                        tool_caller,
                        request.message,
                        current_history,
                        executed_calls,
                        skill_selection,
                        execution_context=execution_context,
                    )
                    print(
                        f"[DEBUG] Tool continuation round {round_index + 1}: "
                        f"success={follow_success}, tool_calls={follow_tool_calls}, "
                        f"response={follow_response[:100] if follow_response else None}"
                    )

                    # Update history with fresh context for next round
                    current_history.append({
                        "role": "assistant",
                        "content": _truncate_for_history(executed_calls, limit=1500),
                    })
                    
                    # Add execution context summary to history for better continuity
                    if execution_context:
                        context_summary = {
                            "role": "system",
                            "content": f"Execution context: {len(execution_context.step_history)} steps completed, "
                                     f"{len(execution_context.errors_encountered)} errors, "
                                     f"selected_tool: {execution_context.selected_tool}, "
                                     f"warnings: {'; '.join(execution_context.warnings[-3:])}"
                        }
                        current_history.append(context_summary)

                    if follow_success and follow_tool_calls:
                        current_calls = follow_tool_calls
                        continue

                    if follow_success and follow_response:
                        final_direct_response = follow_response
                    break

                if aggregated_results and not aggregated_errors:
                    # Success - analyze output and generate UI components
                    print(f"[DEBUG] Analyzing {len(aggregated_results)} results")
                    
                    # Mark execution context as complete
                    if execution_context:
                        execution_context.mark_complete()
                        print(f"[DEBUG] Execution context: {execution_context.execution_time_seconds}s, {execution_context.retry_count} retries")
                        # Surface verification warnings to UI
                        verify_warnings = [w for w in getattr(execution_context, 'warnings', []) if '[VERIFY' in w]
                        if verify_warnings:
                            execution_result["verification_warnings"] = verify_warnings[:5]
                    
                    primary_result, primary_tool_name, primary_operation = _select_primary_result(
                        aggregated_results,
                        executed_history,
                    )
                    result_data = primary_result if primary_result is not None else aggregated_results[0]
                    tool_name = primary_tool_name or tool_name
                    operation = primary_operation or operation
                    
                    # Validate output against skill verification_mode
                    validation_failed = False
                    if execution_context:
                        validation_error = _validate_output_against_skill(result_data, execution_context)
                        if validation_error:
                            execution_context.add_error(
                                tool=tool_name or "unknown",
                                error=f"Output validation failed: {validation_error}",
                                retry_count=execution_context.retry_count
                            )
                            print(f"[DEBUG] Output validation failed: {validation_error}")
                            
                            # Trigger recovery if validation fails
                            if execution_context.should_retry():
                                execution_context.retry_count += 1
                                execution_context.warnings.append(f"Retrying due to validation failure (attempt {execution_context.retry_count})")
                                validation_failed = True
                            elif execution_context.should_fallback():
                                fallback_tool = execution_context.fallback_tools[0]
                                execution_context.warnings.append(f"Switching to {fallback_tool} due to validation failure")
                                execution_context.selected_tool = fallback_tool
                                validation_failed = True
                    
                    # If validation failed and recovery triggered, treat as error
                    if validation_failed:
                        aggregated_errors.append(f"Output validation failed: {validation_error}")
                        # Fall through to error handling below
                    
                    # Only proceed with success path if validation passed
                    if not validation_failed:
                        # Generate natural language summary using LLM
                        tool_summary = (
                            f"Executed tools: {', '.join(f'{item['tool']}.{item['operation']}' for item in executed_history[:6])}\n"
                            f"Result: {str(result_data)[:700]}"
                        )
                        
                        summary_prompt = f"""You just executed one or more tools successfully. Explain what you did in a natural, conversational way.

Tool history: {_truncate_for_history(executed_history, 1200)}
Result summary: {str(result_data)[:500]}

Respond naturally as if you're explaining what you just did. Be concise (1-2 sentences). Don't say "I executed" - say what you DID.
Example: "I found 5 log entries from the last hour" or "I listed 12 files in the directory"""
                        
                        try:
                            if final_direct_response:
                                response_text = final_direct_response
                            else:
                                response_text = llm_client.generate_response(summary_prompt, [])
                        except Exception as e:
                            print(f"[DEBUG] LLM summary generation failed: {e}")
                            # Fallback to simple summary
                            if final_direct_response:
                                response_text = final_direct_response
                            elif isinstance(result_data, dict):
                                if "sources" in result_data and isinstance(result_data["sources"], list):
                                    response_text = f"I gathered content from {len(result_data['sources'])} sources."
                                elif 'executions' in result_data or 'performance' in result_data:
                                    count = len(result_data.get('executions') or result_data.get('performance', []))
                                    response_text = f"Found {count} results."
                                elif 'logs' in result_data:
                                    count = len(result_data.get('logs', []))
                                    response_text = f"Found {count} log entries."
                                elif "results" in result_data and isinstance(result_data["results"], list):
                                    response_text = f"I completed {len(result_data['results'])} tool steps."
                                else:
                                    response_text = "Done."
                            else:
                                response_text = "Done."
                        
                        # Ensure response_text is not None
                        if not response_text:
                            response_text = "Task completed successfully."

                        # Use output analyzer to generate components
                        from core.output_analyzer import OutputAnalyzer
                        components = OutputAnalyzer.analyze(
                            result_data,
                            tool_name,
                            operation,
                            preferred_renderer=_selected_ui_renderer(skill_selection),
                            summary=response_text,
                            skill_name=skill_selection.get("skill_name", ""),
                            category=skill_selection.get("category", ""),
                            output_types=_selected_output_types(skill_selection),
                        )
                        
                        print(f"[DEBUG] Generated {len(components)} components")
                        execution_result = {
                            "success": True, 
                            "results": aggregated_results, 
                            "primary_result": result_data,
                            "tool_history": executed_history,
                            "tool_calling": True,
                            "components": components,
                            "ui_renderer": _selected_ui_renderer(skill_selection),
                            "rounds_used": round_index + 1,
                        }
                else:
                    error_msg = "; ".join(aggregated_errors) if aggregated_errors else "Execution failed"
                    print(f"[DEBUG] Tool execution failed: {error_msg}")
                    
                    # Generate natural language error explanation using LLM
                    error_prompt = f"""A tool execution failed. Explain what went wrong in a natural, helpful way.

Error: {error_msg}

Respond naturally as if you're explaining the problem to a user. Be concise (1-2 sentences). Suggest what they might try instead if appropriate."""
                    
                    try:
                        response_text = llm_client.generate_response(error_prompt, [])
                    except Exception as e:
                        print(f"[DEBUG] LLM error explanation failed: {e}")
                        # Fallback to user-friendly error
                        if "don't have" in error_msg or "not found" in error_msg.lower():
                            response_text = f"I don't have the capability to do that yet. You can create a new tool in Tools Mode to add this functionality."
                        else:
                            response_text = f"I encountered an issue: {error_msg}"
                    
                    # Ensure response_text is not None
                    if not response_text:
                        response_text = f"Task failed: {error_msg}"
                    
                    execution_result = {"success": False, "errors": aggregated_errors, "tool_history": executed_history}
            else:
                # Pure conversation response (no tools selected)
                response_text = initial_response or "I understand your request."
                execution_result = {"success": True, "mode": "conversation"}
        else:
            response_text = f"System not available. Echo: {request.message}"
            execution_result = {"success": False, "error": "System not initialized"}
        
        # Ensure response_text is never None before final processing
        if not response_text:
            response_text = "I processed your request."
        
        if response_text:
            sessions[session_id]["messages"].append({
                "role": "assistant",
                "content": response_text,
                "timestamp": time.time(),
                "skill": skill_selection.get("skill_name"),
                "category": skill_selection.get("category"),
            })
            
            if conversation_memory:
                conversation_memory.save_message(session_id, "assistant", response_text)

        # Feed execution results back to skill registry for usage-based scoring + trigger learning
        try:
            if skill_registry and isinstance(execution_result, dict):
                import re as _re
                _success = bool(execution_result.get("success"))
                _skill_name = skill_selection.get("skill_name") if 'skill_selection' in dir() else None
                # Record per-tool stats from tool_history — include real latency
                for _call in (execution_result.get("tool_history") or []):
                    _tname = _call.get("tool")
                    if _tname:
                        # execution_time is stored in seconds on ToolResult; convert to ms
                        _latency_ms = float(_call.get("execution_time") or 0.0) * 1000
                        skill_registry.record_tool_usage(
                            _tname,
                            bool(_call.get("success")),
                            latency_ms=_latency_ms,
                        )
                # Learn triggers from successful skill executions
                if _success and _skill_name and _skill_name != "conversation":
                    _tokens = set(_re.findall(r"[a-z0-9_]+", request.message.lower()))
                    skill_registry.learn_trigger(_skill_name, _tokens)
        except Exception:
            pass

        # Feed self-directed evolution signals (capability gaps) from failures or tool-less requests.
        try:
            execution_result.update({
                "selected_skill": skill_selection.get("skill_name"),
                "selected_category": skill_selection.get("category"),
                "skill_confidence": skill_selection.get("confidence"),
                "fallback_used": not skill_selection.get("matched", False),
                "ui_renderer": _selected_ui_renderer(skill_selection),
            })
            if isinstance(execution_result, dict):
                # Attach Decision Engine score for UI visibility
                try:
                    from core.decision_engine import get_decision_engine
                    _engine = get_decision_engine()
                    _skill_scores = {skill_selection.get("skill_name", "unknown"): skill_selection.get("confidence", 0.0)} if skill_selection.get("skill_name") else None
                    _de_result = _engine.score(skill_scores=_skill_scores)
                    execution_result["decision"] = {
                        "strategy": _de_result.best_strategy,
                        "confidence": _de_result.confidence,
                        "fallback": _de_result.fallback_plan,
                        "scores": _de_result.component_scores,
                        "reasoning": _de_result.reasoning,
                    }
                except Exception:
                    pass
                if execution_result.get("success") is False:
                    err_text = "; ".join(execution_result.get("errors", [])) if execution_result.get("errors") else execution_result.get("error", "")
                    _record_capability_gap(request.message, err_text, skill_selection)
                    execution_result["gap_detected"] = True
                elif execution_result.get("mode") == "conversation":
                    _record_capability_gap(request.message, "", skill_selection)
        except Exception:
            pass
        
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
    return {
        "status": "healthy",
        "system_available": SYSTEM_AVAILABLE,
        "routers_available": ROUTERS_AVAILABLE,
        "runtime_init_error": runtime.init_error,
        "router_import_error": router_bundle.import_error,
        "cors_test": "local_only",
    }

@app.get("/status")
async def status():
    return {
        "status": "online",
        "system_available": SYSTEM_AVAILABLE,
        "routers_available": ROUTERS_AVAILABLE,
        "runtime_init_error": runtime.init_error,
        "sessions": len(sessions),
        "connections": len(connections),
        "tools": len(registry.tools) if registry else 0,
        "capabilities": len(registry.get_all_capabilities()) if registry else 0,
        "skills": len(skill_registry.list_all()) if skill_registry else 0,
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
        'pending_tool_added': send_event,
        'agent_plan': send_event,
        'agent_step_update': send_event,
        'agent_plan_clear': send_event,
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
    import os
    
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
    
    # Warm up the LLM model for faster responses
    if llm_client:
        print("Warming up LLM model...")
        llm_client.warmup_model()
    
    os.environ["CUA_RELOAD_MODE"] = "1"
    
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=True,
        reload_dirs=["."],
        reload_excludes=["test_tmp/*", "pytest_tmp/*", "data/tool_backups/*"],
    )
    server = uvicorn.Server(config)
    
    try:
        import asyncio
        asyncio.run(server.serve())
    except (KeyboardInterrupt, SystemExit):
        pass
