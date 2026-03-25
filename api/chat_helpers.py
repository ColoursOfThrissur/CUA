"""Chat endpoint handler — /chat and /chat/stop."""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    success: bool = True
    execution_result: Optional[Dict] = None
    plan: Optional[Dict] = None


_stop_requested = False

_SIMPLE_PATTERNS = {
    "hi", "hello", "hey", "thanks", "thank you", "bye", "goodbye",
    "how are you", "what's up", "good morning", "good afternoon", "good evening",
    "ok", "okay", "yes", "no", "sure", "great", "nice", "cool", "awesome",
}


def _is_simple_message(message: str) -> bool:
    lower = message.lower().strip()
    words = lower.split()
    return (
        lower in _SIMPLE_PATTERNS
        or (
            len(message.strip()) < 20
            and not any(k in lower for k in [
                "?", "what", "how", "when", "where", "why", "can you", "please",
                "help", "do", "get", "find", "search", "open", "run", "execute",
                "create", "make", "build", "write", "read", "list", "show",
            ])
        )
        or (len(words) <= 3 and all(w in _SIMPLE_PATTERNS or len(w) <= 4 for w in words))
    )


def _simple_reply(message: str) -> str:
    lower = message.lower()
    if any(g in lower for g in ["hi", "hello", "hey"]):
        return "Hello! How can I assist you today?"
    if any(t in lower for t in ["thanks", "thank you"]):
        return "You're welcome! Let me know if you need anything else."
    if any(b in lower for b in ["bye", "goodbye"]):
        return "Goodbye! Feel free to come back anytime."
    if lower in ("ok", "okay", "yes", "sure"):
        return "Great! What would you like to do next?"
    if lower == "no":
        return "No problem. Let me know if you change your mind."
    return "I'm here to help! What can I do for you?"


def _attempt_planning_fallback(
    request_message, session_id, skill_selection,
    task_planner, sessions, conv_mem,
):
    if not task_planner:
        return None
    plan = task_planner.plan_task(request_message, context=build_planner_context(skill_selection))
    plan.requires_approval = True
    sessions[session_id]["pending_agent_plan"] = plan
    sessions[session_id]["pending_agent_plan_iteration"] = None
    plan_dict = asdict(plan) if hasattr(plan, "__dataclass_fields__") else plan
    response_text = "I identified this as an executable task and prepared a plan. Review it and reply 'go ahead' to run it."
    sessions[session_id]["messages"].append({
        "role": "assistant", "content": response_text, "timestamp": time.time(),
        "skill": skill_selection.get("skill_name"), "category": skill_selection.get("category"),
    })
    if conv_mem:
        conv_mem.save_message(session_id, "assistant", response_text)
    return ChatResponse(
        response=response_text, session_id=session_id, success=True,
        execution_result={
            "success": False, "mode": "planned_fallback", "status": "awaiting_approval",
            "plan": plan_dict,
            "selected_skill": skill_selection.get("skill_name"),
            "selected_category": skill_selection.get("category"),
            "skill_confidence": skill_selection.get("confidence"),
            "fallback_used": False,
            "ui_renderer": selected_ui_renderer(skill_selection),
        },
    )


def select_skill_for_message(message: str, skill_reg, skill_sel, llm, reg) -> Dict:
    if not skill_reg or not skill_sel:
        return {"matched": False, "skill_name": None, "category": None, "confidence": 0.0,
                "reason": "skill_system_unavailable", "fallback_mode": "direct_tool_routing", "candidate_skills": []}
    try:
        result = skill_sel.select_skill(message, skill_reg, llm)
        return {
            "matched": bool(result.matched), "skill_name": result.skill_name,
            "category": result.category, "confidence": result.confidence,
            "reason": getattr(result, "reason", ""),
            "fallback_mode": getattr(result, "fallback_mode", None),
            "candidate_skills": getattr(result, "candidate_skills", []),
            "planning_context": getattr(result, "planning_context", None),
        }
    except Exception as e:
        print(f"[WARN] Skill selection failed: {e}")
        return {"matched": False, "skill_name": None, "category": None, "confidence": 0.0,
                "reason": f"error:{e}", "fallback_mode": "direct_tool_routing", "candidate_skills": []}


def build_planner_context(skill_selection: Dict, skill_reg=None) -> Optional[Dict]:
    if not skill_selection.get("matched"):
        return None

    skill_name = skill_selection.get("skill_name")
    base = {
        "skill_name": skill_name,
        "category": skill_selection.get("category"),
        "confidence": skill_selection.get("confidence"),
        "planning_context": skill_selection.get("planning_context"),
    }

    # Enrich with full skill definition so planner gets preferred_tools,
    # verification_mode, output_types, instructions_summary, constraints.
    if skill_reg and skill_name:
        skill_def = skill_reg.get(skill_name)
        if skill_def:
            instructions_summary = ""
            try:
                from pathlib import Path
                md = Path(skill_def.instructions_path).read_text(encoding="utf-8")
                # First non-empty paragraph after the heading
                lines = [l.strip() for l in md.splitlines() if l.strip() and not l.startswith("#")]
                instructions_summary = " ".join(lines[:3])[:300]
            except Exception:
                pass
            base["skill_context"] = {
                "skill_name": skill_name,
                "category": skill_def.category,
                "preferred_tools": skill_def.preferred_tools,
                "required_tools": skill_def.required_tools,
                "verification_mode": skill_def.verification_mode,
                "output_types": skill_def.output_types,
                "ui_renderer": skill_def.ui_renderer,
                "instructions_summary": instructions_summary,
                "skill_constraints": [],
            }
    return base


def needs_runtime_refresh(message: str) -> bool:
    lower = message.lower()
    return any(k in lower for k in ["tool", "capability", "create", "evolve", "new tool"])


def has_referenced_tools_loaded(reg, message: str) -> bool:
    if not reg:
        return False
    lower = message.lower()
    return any(lower in t.__class__.__name__.lower() for t in reg.tools)


def execute_tool_calls(tool_calls: List[Dict], session_id: str, reg, sessions: Dict, refresh_registry) -> tuple:
    from core.tool_orchestrator import ToolOrchestrator
    import time as _time
    orchestrator = ToolOrchestrator(registry=reg)
    results: List[Any] = []
    errors: List[str] = []
    executed: List[Dict[str, Any]] = []
    last_tool = None
    last_op = None
    for call in tool_calls:
        tool_name = call.get("tool") or call.get("name", "")
        operation = call.get("operation") or call.get("function", "")
        parameters = call.get("parameters") or call.get("arguments") or {}
        t0 = _time.time()
        try:
            tool_obj = None
            if reg:
                if hasattr(reg, 'get_tool'):
                    tool_obj = reg.get_tool(tool_name)
                if tool_obj is None and hasattr(reg, 'tools'):
                    tool_obj = next(
                        (t for t in reg.tools
                         if t.__class__.__name__ == tool_name
                         or (getattr(t, 'name', None) == tool_name)),
                        None
                    )
            if tool_obj is None:
                raise ValueError(f"Tool not found: {tool_name}")
            orch_result = orchestrator.execute_tool_step(
                tool=tool_obj, tool_name=tool_name, operation=operation, parameters=parameters
            )
            success, data, error = orch_result.success, orch_result.data, orch_result.error
            elapsed = _time.time() - t0
            record = {"tool": tool_name, "operation": operation, "parameters": parameters,
                      "success": success, "data": data, "error": error, "execution_time": elapsed}
            executed.append(record)
            if success:
                results.append({"tool": tool_name, "operation": operation, "data": data})
                last_tool = tool_name
                last_op = operation
            else:
                errors.append(f"{tool_name}.{operation}: {error}")
        except Exception as e:
            elapsed = _time.time() - t0
            executed.append({"tool": tool_name, "operation": operation, "parameters": parameters,
                             "success": False, "data": None, "error": str(e), "execution_time": elapsed})
            errors.append(f"{tool_name}.{operation}: {e}")
    return results, errors, executed, last_tool, last_op


def continue_tool_calling(tool_caller, message: str, history: List[Dict], executed_batch: List[Dict],
                          skill_selection: Dict, execution_context) -> tuple:
    try:
        # Build structured result entries so LLM sees actual outputs, not a truncated summary
        result_lines = []
        for c in executed_batch:
            status = "ok" if c["success"] else "err"
            preview = str(c.get("data") or c.get("error") or "")[:300]
            result_lines.append(f"[{status}] {c['tool']}.{c['operation']}: {preview}")
        tool_results_block = "\n".join(result_lines)
        continuation_msg = (
            f"Tool results:\n{tool_results_block}\n\n"
            f"Original request: {message}\n"
            "Do you need to call more tools to fully answer the request? "
            "If yes, call them. If no, provide a final answer."
        )
        allowed_tools = None
        if execution_context and execution_context.available_tools:
            allowed_tools = list(execution_context.available_tools.keys())
        success, calls, response = tool_caller.call_with_tools(
            continuation_msg, history,
            skill_context=skill_selection.get("planning_context"),
            allowed_tools=allowed_tools,
        )
        return success, calls, response
    except Exception as e:
        print(f"[WARN] continue_tool_calling failed: {e}")
        return False, None, None


def selected_ui_renderer(skill_selection: Dict) -> str:
    skill_name = (skill_selection or {}).get("skill_name") or ""
    renderers = {"web_research": "web_results", "browser_automation": "screenshot",
                 "data_operations": "table", "code_workspace": "code", "knowledge_management": "markdown"}
    return renderers.get(skill_name, "default")


def selected_output_types(skill_selection: Dict) -> List[str]:
    skill_name = (skill_selection or {}).get("skill_name") or ""
    output_map = {
        "web_research": ["text", "url", "summary"], "browser_automation": ["screenshot", "text"],
        "data_operations": ["json", "table"], "code_workspace": ["code", "text"],
        "knowledge_management": ["text", "markdown"], "computer_automation": ["text", "file"],
    }
    return output_map.get(skill_name, [])


def validate_output_against_skill(result_data: Any, execution_context) -> Optional[str]:
    try:
        if not execution_context or not result_data:
            return None
        if isinstance(result_data, dict) and result_data.get("error") and not result_data.get("success", True):
            return f"Tool returned error: {result_data['error']}"
        return None
    except Exception:
        return None


def select_primary_result(results: List[Any], executed_history: List[Dict]) -> tuple:
    if not results:
        return None, None, None
    best = results[0]
    best_tool = executed_history[0].get("tool") if executed_history else None
    best_op = executed_history[0].get("operation") if executed_history else None
    for i, r in enumerate(results):
        data = r.get("data") if isinstance(r, dict) else r
        best_data = best.get("data") if isinstance(best, dict) else best
        if data and len(str(data)) > len(str(best_data)):
            best = r
            if i < len(executed_history):
                best_tool = executed_history[i].get("tool")
                best_op = executed_history[i].get("operation")
    data = best.get("data") if isinstance(best, dict) else best
    return data, best_tool, best_op


def truncate_for_history(executed_batch: List[Dict], limit: int = 1500) -> str:
    parts = []
    for c in executed_batch:
        status = "ok" if c.get("success") else "err"
        preview = str(c.get("data") or c.get("error") or "")[:200]
        parts.append(f"{status} {c.get('tool')}.{c.get('operation')}: {preview}")
    return "\n".join(parts)[:limit]


def _build_wra_components(_answer: str, raw_data: list) -> list:
    """Build clean UI components for WRA results — structured search results as table, skip raw HTML."""
    import ast
    from core.output_analyzer import OutputAnalyzer
    search_results = []
    components = []

    for item in raw_data:
        # Structured content dict from get_structured_content / extract_* operations
        if isinstance(item, dict):
            # done_extras from CrewAI-style structured done action
            if item.get("key_facts") and isinstance(item["key_facts"], list):
                components.append({"type": "list", "renderer": "list",
                                    "items": item["key_facts"], "title": "Key Facts"})
                continue
            if item.get("items") and isinstance(item["items"], list):
                components.append({"type": "list", "renderer": "list",
                                    "items": item["items"], "title": "Results"})
                continue
            if item.get("value"):
                components.append({"type": "text_content", "renderer": "text_content",
                                    "content": f"{item['value']} {item.get('unit', '')}".strip(),
                                    "title": "Value"})
                continue
            if item.get("tables"):
                for tbl in item["tables"][:5]:
                    if tbl.get("rows"):
                        components.append({
                            "type": "table", "renderer": "table",
                            "data": tbl["rows"],
                            "title": tbl.get("caption") or "Table",
                            "columns": tbl.get("headers") or OutputAnalyzer._extract_columns(tbl["rows"]),
                        })
                continue
            if item.get("lists"):
                for lst in item["lists"][:5]:
                    if lst.get("items"):
                        components.append({"type": "list", "renderer": "list", "items": lst["items"]})
                continue
            if item.get("body") and len(str(item["body"])) > 100:
                components.append({
                    "type": "text_content", "renderer": "text_content",
                    "content": item["body"],
                    "title": item.get("title") or "Article",
                    "source_url": item.get("url", ""),
                })
                continue
            if isinstance(item.get("links"), list) and item["links"] and isinstance(item["links"][0], dict) and "href" in item["links"][0]:
                components.append({
                    "type": "table", "renderer": "table",
                    "data": item["links"][:50],
                    "title": "Links", "columns": ["text", "href", "title"],
                })
                continue

        # Raw list of search result dicts (stored directly, not stringified)
        if isinstance(item, list) and item and isinstance(item[0], dict):
            for r in item:
                if isinstance(r, dict) and (r.get("url") or r.get("link")):
                    search_results.append({
                        "title": r.get("title", ""),
                        "url": r.get("url") or r.get("link", ""),
                        "snippet": r.get("snippet") or r.get("description") or r.get("content", ""),
                    })
            continue

        # Stringified list of search result dicts (legacy fallback)
        if isinstance(item, str):
            try:
                parsed = ast.literal_eval(item)
                if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                    item = parsed
            except Exception:
                pass
        if isinstance(item, list):
            for r in item:
                if isinstance(r, dict) and (r.get("url") or r.get("link")):
                    search_results.append({
                        "title": r.get("title", ""),
                        "url": r.get("url") or r.get("link", ""),
                        "snippet": r.get("snippet") or r.get("description") or r.get("content", ""),
                    })

    if search_results:
        components.append({
            "type": "table",
            "renderer": "table",
            "data": search_results[:10],
            "title": "Sources",
            "columns": ["title", "url", "snippet"],
        })
    return components


def record_capability_gap(message: str, error: str, skill_selection: Dict, llm, reg) -> None:
    try:
        from core.gap_detector import GapDetector
        from core.gap_tracker import GapTracker
        from core.capability_mapper import CapabilityMapper

        gap = GapDetector(CapabilityMapper()).analyze_failed_task(message, error, skill_selection)
        if gap and gap.confidence >= 0.6:
            # Skip if already resolved in cua.db
            try:
                from core.cua_db import get_conn as _gc
                with _gc() as _c:
                    row = _c.execute(
                        "SELECT id FROM resolved_gaps WHERE capability=? LIMIT 1",
                        (gap.capability,)
                    ).fetchone()
                if row:
                    return
            except Exception:
                pass
            GapTracker().record_gap(gap)
    except Exception as e:
        print(f"[WARN] Gap recording failed: {e}")


def create_chat_handler(runtime, sessions: Dict, refresh_registry):
    """Returns (stop_chat, chat) handler functions bound to runtime."""

    reg = runtime.registry
    llm = runtime.llm_client
    skill_reg = runtime.skill_registry
    skill_sel = runtime.skill_selector
    conv_mem = runtime.conversation_memory
    task_planner = runtime.task_planner
    exec_engine = runtime.execution_engine
    agent = runtime.autonomous_agent
    circuit_breaker = runtime.circuit_breaker
    logger = runtime.logger

    async def stop_chat():
        global _stop_requested
        _stop_requested = True
        return {"success": True, "message": "Stop requested"}

    async def chat(request: ChatRequest):
        global _stop_requested
        _stop_requested = False

        from core.input_validation import validate_text_input
        try:
            validate_text_input(request.message, max_length=50000, field_name="message")
        except ValueError as e:
            raise HTTPException(status_code=413, detail=str(e))

        session_id = request.session_id or str(uuid4())
        if session_id not in sessions:
            sessions[session_id] = {"messages": []}
            if conv_mem:
                sessions[session_id]["messages"] = conv_mem.get_history(session_id, limit=20)

        sessions[session_id]["messages"].append({
            "role": "user", "content": request.message, "timestamp": time.time(),
        })
        if conv_mem:
            conv_mem.save_message(session_id, "user", request.message)
        if logger:
            logger.log_request(session_id, request.message)

        execution_result: Optional[Dict] = {"success": False, "error": "Unknown error"}
        response_text = ""

        try:
            if not (runtime.system_available and reg and llm):
                return ChatResponse(
                    response=f"System not available. Echo: {request.message}",
                    session_id=session_id, success=False,
                    execution_result={"success": False, "error": "System not initialized"},
                )

            # Simple message fast path
            if _is_simple_message(request.message):
                response_text = _simple_reply(request.message)
                execution_result = {"success": True, "mode": "conversation", "simple_greeting": True}
                sessions[session_id]["messages"].append({
                    "role": "assistant", "content": response_text, "timestamp": time.time(),
                })
                if conv_mem:
                    conv_mem.save_message(session_id, "assistant", response_text)
                return ChatResponse(response=response_text, session_id=session_id, success=True, execution_result=execution_result)

            skill_selection = select_skill_for_message(request.message, skill_reg, skill_sel, llm, reg) or {
                "matched": False, "skill_name": None, "category": None, "confidence": 0.0,
                "reason": "skill_system_unavailable", "fallback_mode": "direct_tool_routing",
                "candidate_skills": [],
            }

            # Conversation skill
            if skill_selection.get("skill_name") == "conversation":
                response_text = llm.generate_response(request.message, sessions[session_id]["messages"][-5:])
                execution_result = {
                    "success": True, "mode": "conversation", "skill_optimized": True,
                    "selected_skill": "conversation", "selected_category": "conversation",
                    "skill_confidence": skill_selection.get("confidence", 0.0),
                }
                sessions[session_id]["messages"].append({
                    "role": "assistant", "content": response_text, "timestamp": time.time(),
                    "skill": "conversation", "category": "conversation",
                })
                if conv_mem:
                    conv_mem.save_message(session_id, "assistant", response_text)
                return ChatResponse(response=response_text, session_id=session_id, success=True, execution_result=execution_result)

            # Pending plan approval
            pending_plan = sessions[session_id].get("pending_agent_plan")
            if pending_plan is not None:
                msg_norm = request.message.strip().lower()
                approve_words = {"go ahead", "approve", "approved", "yes", "ok", "okay", "continue", "proceed", "run it", "do it"}
                reject_words = {"no", "reject", "cancel", "stop", "abort"}

                if msg_norm in approve_words:
                    sessions[session_id].pop("pending_agent_plan", None)
                    sessions[session_id].pop("pending_agent_plan_iteration", None)
                    execution_id = f"{session_id}_approved_{int(time.time())}"
                    try:
                        state = exec_engine.execute_plan(pending_plan, execution_id) if exec_engine else None
                        if state and getattr(state, "error", None):
                            response_text = f"Plan approved, but execution failed: {state.error}"
                            execution_result = {"success": False, "mode": "autonomous_agent", "status": "execution_failed", "error": state.error}
                        else:
                            response_text = "✓ Plan approved and executed."
                            execution_result = {"success": True, "mode": "autonomous_agent", "status": "executed", "execution_id": execution_id}
                    except Exception as e:
                        response_text = f"Plan approved, but execution failed: {str(e)}"
                        execution_result = {"success": False, "mode": "autonomous_agent", "status": "execution_failed", "error": str(e)}

                elif msg_norm in reject_words:
                    sessions[session_id].pop("pending_agent_plan", None)
                    sessions[session_id].pop("pending_agent_plan_iteration", None)
                    response_text = "Cancelled. I won't execute that plan."
                    execution_result = {"success": False, "mode": "autonomous_agent", "status": "rejected"}

                else:
                    plan_dict = asdict(pending_plan) if hasattr(pending_plan, "__dataclass_fields__") else pending_plan
                    response_text = "Plan requires user approval. Reply 'go ahead' to approve or 'cancel' to reject."
                    execution_result = {"success": False, "mode": "autonomous_agent", "status": "awaiting_approval", "plan": plan_dict}

                sessions[session_id]["messages"].append({"role": "assistant", "content": response_text, "timestamp": time.time()})
                if conv_mem:
                    conv_mem.save_message(session_id, "assistant", response_text)
                execution_result.update({
                    "selected_skill": skill_selection.get("skill_name"),
                    "selected_category": skill_selection.get("category"),
                    "skill_confidence": skill_selection.get("confidence"),
                    "fallback_used": False,
                })
                return ChatResponse(response=response_text, session_id=session_id, success=True, execution_result=execution_result)

            # Registry refresh
            if needs_runtime_refresh(request.message) and not has_referenced_tools_loaded(reg, request.message):
                try:
                    refresh_registry()
                except Exception as e:
                    print(f"[WARN] Registry refresh failed: {e}")

            # Autonomous agent (multi-step)
            skill_cat = skill_selection.get("category") or ""
            is_multi_step = agent is not None and skill_cat not in ("", "conversation") and len(request.message.split()) >= 4

            if is_multi_step:
                try:
                    from core.autonomous_agent import AgentGoal
                    import api.chat_helpers as _self
                    # Resolve short follow-up references using recent conversation history
                    goal_text = request.message
                    recent = sessions[session_id]["messages"]
                    if len(request.message.split()) <= 8:
                        prev_assistant = next(
                            (m["content"] for m in reversed(recent[:-1]) if m["role"] == "assistant"),
                            None,
                        )
                        if prev_assistant:
                            goal_text = f"{request.message} (context from previous reply: {prev_assistant[:300]})"
                    goal = AgentGoal(
                        goal_text=goal_text, success_criteria=[],
                        max_iterations=5, require_approval=False,
                    )
                    _skill_context = build_planner_context(skill_selection, skill_reg) or {"skill_context": {"skill_name": skill_selection.get("skill_name", "")}}
                    conv_history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in sessions[session_id]["messages"][-8:]
                        if m.get("role") in ("user", "assistant") and m.get("content")
                    ]
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(
                        None,
                        lambda: agent.achieve_goal(goal, session_id, context={**_skill_context, "conversation_history": conv_history}, stop_check=lambda: _self._stop_requested),
                    )

                    if result.get("status") == "awaiting_approval" and result.get("plan") is not None:
                        plan_obj = result["plan"]
                        sessions[session_id]["pending_agent_plan"] = plan_obj
                        sessions[session_id]["pending_agent_plan_iteration"] = result.get("iteration")
                        plan_dict = asdict(plan_obj) if hasattr(plan_obj, "__dataclass_fields__") else plan_obj
                        response_text = result.get("message", "Plan requires user approval")
                        sessions[session_id]["messages"].append({"role": "assistant", "content": response_text, "timestamp": time.time()})
                        if conv_mem:
                            conv_mem.save_message(session_id, "assistant", response_text)
                        return ChatResponse(
                            response=response_text, session_id=session_id, success=True,
                            execution_result={
                                "success": False, "mode": "autonomous_agent", "status": "awaiting_approval",
                                "plan": plan_dict,
                                "selected_skill": skill_selection.get("skill_name"),
                                "selected_category": skill_selection.get("category"),
                                "skill_confidence": skill_selection.get("confidence"),
                                "fallback_used": False,
                            },
                        )

                    if result.get("success"):
                        final_state = result.get("final_state")

                        # WRA path: no final_state, raw_data list returned directly
                        wra_raw = result.get("raw_data")
                        if not final_state and wra_raw:
                            response_text = result.get("message", "Task completed.")
                            # Build components from synthesized answer + any structured search results
                            agent_components = _build_wra_components(response_text, wra_raw)
                            sessions[session_id]["messages"].append({"role": "assistant", "content": response_text, "timestamp": time.time()})
                            if conv_mem:
                                conv_mem.save_message(session_id, "assistant", response_text)
                            try:
                                from core.event_bus import get_event_bus
                                get_event_bus().emit_sync("agent_plan_clear", {})
                            except Exception:
                                pass
                            return ChatResponse(
                                response=response_text, session_id=session_id, success=True,
                                execution_result={
                                    "success": True, "mode": "autonomous_agent",
                                    "selected_skill": skill_selection.get("skill_name"),
                                    "selected_category": skill_selection.get("category"),
                                    "skill_confidence": skill_selection.get("confidence"),
                                    "fallback_used": False,
                                    "components": agent_components,
                                    "ui_renderer": selected_ui_renderer(skill_selection),
                                },
                            )

                        step_outputs = []
                        all_step_data = []
                        screenshot_components = []
                        if final_state and hasattr(final_state, "step_results"):
                            for step_id, step_result in final_state.step_results.items():
                                if not (hasattr(step_result, "status") and str(step_result.status.value) == "completed"):
                                    continue
                                out = getattr(step_result, "output", None)
                                if not out or not isinstance(out, dict):
                                    continue
                                if out.get("screenshot_b64"):
                                    screenshot_components.append({
                                        "type": "screenshot", "renderer": "screenshot",
                                        "src": f"data:image/png;base64,{out['screenshot_b64']}",
                                        "filepath": out.get("filepath", ""), "alt": f"Screenshot from {step_id}",
                                    })
                                    continue
                                if out.get("results") and isinstance(out["results"], list):
                                    snippets = []
                                    for r in out["results"][:8]:
                                        if isinstance(r, dict):
                                            snippets.append(
                                                f"{r.get('title','')}: {r.get('snippet') or r.get('description') or r.get('content','')} "
                                                f"({r.get('url') or r.get('link','')})"
                                            )
                                    if snippets:
                                        step_outputs.append({"step": step_id, "search_results": "\n".join(snippets)})
                                        continue
                                for key in ("content", "text", "summary", "result", "elements", "pages"):
                                    val = out.get(key)
                                    if val and str(val).strip():
                                        text_val = str(val)
                                        if text_val.lstrip().startswith("<") and "<html" in text_val.lower():
                                            continue
                                        step_outputs.append({"step": step_id, key: text_val[:1500]})
                                        break

                        # Collect all non-empty step outputs
                        if final_state and hasattr(final_state, "step_results"):
                            for step_id, step_result in final_state.step_results.items():
                                if not (hasattr(step_result, "status") and str(step_result.status.value) == "completed"):
                                    continue
                                out = getattr(step_result, "output", None)
                                if not out:
                                    continue
                                all_step_data.append(out)
                                if isinstance(out, dict):
                                    for k, v in out.items():
                                        if k in ("success", "error") or not v:
                                            continue
                                        step_outputs.append({"step": step_id, k: str(v)[:1500]})
                                        break
                                elif out:
                                    step_outputs.append({"step": step_id, "result": str(out)[:1500]})

                        if step_outputs:
                            content_lines = [f"{k}: {v}" for o in step_outputs[:6] for k, v in o.items() if k != "step"]
                            summary_prompt = (
                                f"The user asked: {request.message}\n\nHere is what was done and the results:\n"
                                + "\n".join(f"- {line}" for line in content_lines)
                                + "\n\nAnswer the user's question directly using the actual data above. Be concise but complete."
                            )
                            try:
                                response_text = llm.generate_response(summary_prompt, [])
                            except Exception:
                                response_text = f"\u2713 {result.get('message', 'Task completed')}"
                        else:
                            response_text = f"\u2713 {result.get('message', 'Task completed')}"
                    else:
                        response_text = result.get("message", "Task failed")

                    # Build rich components from agent step outputs
                    agent_components = list(screenshot_components) if 'screenshot_components' in dir() else []
                    if result.get("success") and all_step_data:
                        from core.output_analyzer import OutputAnalyzer
                        # Use the richest single output (largest dict or longest string)
                        primary = max(all_step_data, key=lambda x: len(str(x)))
                        last_tool = None
                        last_op = None
                        if final_state and hasattr(final_state, "step_results"):
                            for sr in final_state.step_results.values():
                                if hasattr(sr, "status") and str(sr.status.value) == "completed":
                                    last_tool = getattr(sr, "tool_name", None) or last_tool
                                    last_op = getattr(sr, "operation", None) or last_op
                        analyzed = OutputAnalyzer.analyze(
                            primary, last_tool or "", last_op or "",
                            preferred_renderer=selected_ui_renderer(skill_selection),
                            summary=response_text,
                            skill_name=skill_selection.get("skill_name", ""),
                            category=skill_selection.get("category", ""),
                            output_types=selected_output_types(skill_selection),
                        )
                        agent_components.extend(analyzed)

                    sessions[session_id]["messages"].append({"role": "assistant", "content": response_text, "timestamp": time.time()})
                    if conv_mem:
                        conv_mem.save_message(session_id, "assistant", response_text)
                    try:
                        from core.event_bus import get_event_bus
                        get_event_bus().emit_sync("agent_plan_clear", {})
                    except Exception as e:
                        print(f"[WARN] Event bus emit failed: {e}")
                    return ChatResponse(
                        response=response_text, session_id=session_id, success=True,
                        execution_result={
                            "success": bool(result.get("success")), "mode": "autonomous_agent",
                            "selected_skill": skill_selection.get("skill_name"),
                            "selected_category": skill_selection.get("category"),
                            "skill_confidence": skill_selection.get("confidence"),
                            "fallback_used": False,
                            "components": agent_components,
                        },
                    )
                except Exception as e:
                    print(f"[DEBUG] Autonomous agent failed: {e}, falling back to tool calling")

            # Simple conversational short-circuit
            msg_lower = request.message.lower().strip()
            if (
                len(request.message.strip()) < 30
                and not any(a in msg_lower for a in [
                    "open", "search", "find", "get", "fetch", "run", "execute",
                    "create", "make", "build", "write", "read", "list", "show",
                    "take", "click", "navigate", "go to", "download", "upload", "delete", "move", "copy",
                ])
                and "?" not in request.message
            ):
                response_text = llm.generate_response(request.message, sessions[session_id]["messages"][-5:])
                execution_result = {"success": True, "mode": "conversation", "simple_response": True}
                sessions[session_id]["messages"].append({"role": "assistant", "content": response_text, "timestamp": time.time()})
                if conv_mem:
                    conv_mem.save_message(session_id, "assistant", response_text)
                return ChatResponse(response=response_text, session_id=session_id, success=True, execution_result=execution_result)

            # Native tool calling
            from planner.tool_calling import ToolCallingClient
            from core.skills import SkillContextHydrator
            from core.skills.tool_selector import ContextAwareToolSelector

            tool_caller = ToolCallingClient(ollama_url=llm.ollama_url, model=llm.model, registry=reg)

            execution_context = None
            allowed_tools = None
            if skill_selection.get("matched") and skill_selection.get("skill_name"):
                skill_def = skill_reg.get(skill_selection["skill_name"])
                if skill_def:
                    from core.skills.models import SkillSelection as SkillSelectionModel
                    skill_sel_obj = SkillSelectionModel(
                        matched=True, skill_name=skill_selection["skill_name"],
                        category=skill_selection.get("category"),
                        confidence=skill_selection.get("confidence", 0.0),
                    )
                    execution_context = SkillContextHydrator.build_context(skill_sel_obj, skill_def, request.message)
                    tool_selector = ContextAwareToolSelector(reg, circuit_breaker, skill_reg)
                    execution_context = tool_selector.select_tools(execution_context)
                    allowed_tools = list(execution_context.available_tools.keys()) if execution_context.available_tools else None
                    # Always include connected MCP adapter tools regardless of skill filter
                    if reg:
                        mcp_tools = [t.__class__.__name__ for t in reg.tools
                                     if t.__class__.__name__.startswith("MCPAdapterTool") and t.is_connected()]
                        if mcp_tools:
                            allowed_tools = list(set(allowed_tools or []) | set(mcp_tools))
                    print(f"[DEBUG] Skill tool filter: {skill_selection['skill_name']} -> {allowed_tools}")

            conversation_history = sessions[session_id]["messages"][-5:]
            success, tool_calls, initial_response = tool_caller.call_with_tools(
                request.message, conversation_history,
                skill_context=skill_selection.get("planning_context"),
                allowed_tools=allowed_tools,
            )
            print(f"[DEBUG] Tool calling: success={success}, calls={tool_calls}, response={str(initial_response)[:100]}")

            response_text = None

            if not success:
                if initial_response == "NO_TOOL_CALLS_FOR_ACTIONABLE_REQUEST":
                    record_capability_gap(request.message, "NO_TOOL_CALLS_FOR_ACTIONABLE_REQUEST", skill_selection, llm, reg)
                    planned = _attempt_planning_fallback(request.message, session_id, skill_selection, task_planner, sessions, conv_mem)
                    if planned:
                        return planned
                response_text = llm.generate_response(request.message, conversation_history)
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
                round_index = 0

                for round_index in range(3):
                    if execution_context and round_index > 0:
                        tool_selector = ContextAwareToolSelector(reg, circuit_breaker, skill_reg)
                        execution_context = tool_selector.select_tools(execution_context)
                        execution_context.retry_count = 0
                        execution_context.warnings.append(f"Starting continuation round {round_index + 1}")

                    results, errors, executed_calls_batch, last_tool_name, last_operation = execute_tool_calls(
                        current_calls, session_id, reg, sessions, refresh_registry,
                    )
                    aggregated_results.extend(results)
                    aggregated_errors.extend(errors)
                    executed_history.extend(executed_calls_batch)
                    tool_name = last_tool_name or tool_name
                    operation = last_operation or operation

                    if execution_context:
                        for call in executed_calls_batch:
                            execution_context.add_step(
                                tool=call.get("tool", ""), operation=call.get("operation", ""),
                                status="success" if call.get("success") else "failure",
                                duration=0.0, result=call.get("data") if call.get("success") else None,
                            )
                            if not call.get("success"):
                                execution_context.add_error(
                                    tool=call.get("tool", ""), error=call.get("error", "Unknown error"),
                                    retry_count=execution_context.retry_count,
                                )
                        if last_tool_name and last_tool_name != execution_context.selected_tool:
                            execution_context.selected_tool = last_tool_name

                    if errors or not results:
                        if execution_context and execution_context.should_fallback():
                            fallback_tool = execution_context.fallback_tools[0] if execution_context.fallback_tools else None
                            if fallback_tool:
                                execution_context.warnings.append(f"Primary tool failed, trying {fallback_tool}")
                                execution_context.selected_tool = fallback_tool
                                execution_context.retry_count += 1
                                continue
                        break

                    follow_success, follow_tool_calls, follow_response = continue_tool_calling(
                        tool_caller, request.message, current_history, executed_calls_batch, skill_selection, execution_context,
                    )
                    print(f"[DEBUG] Continuation {round_index + 1}: success={follow_success}, response={str(follow_response)[:100]}")

                    current_history.append({"role": "assistant", "content": truncate_for_history(executed_calls_batch, limit=1500)})
                    if execution_context:
                        current_history.append({"role": "system", "content": (
                            f"Execution context: {len(execution_context.step_history)} steps, "
                            f"{len(execution_context.errors_encountered)} errors, "
                            f"tool: {execution_context.selected_tool}, "
                            f"warnings: {'; '.join(execution_context.warnings[-3:])}"
                        )})

                    if follow_success and follow_tool_calls:
                        current_calls = follow_tool_calls
                        continue
                    if follow_success and follow_response:
                        final_direct_response = follow_response
                    break

                if aggregated_results and not aggregated_errors:
                    if execution_context:
                        execution_context.mark_complete()
                        verify_warnings = [w for w in getattr(execution_context, "warnings", []) if "[VERIFY" in w]
                        if verify_warnings:
                            execution_result["verification_warnings"] = verify_warnings[:5]

                    primary_result, primary_tool_name, primary_operation = select_primary_result(aggregated_results, executed_history)
                    result_data = primary_result if primary_result is not None else aggregated_results[0]
                    tool_name = primary_tool_name or tool_name
                    operation = primary_operation or operation

                    validation_failed = False
                    validation_error = None
                    if execution_context:
                        validation_error = validate_output_against_skill(result_data, execution_context)
                        if validation_error:
                            execution_context.add_error(
                                tool=tool_name or "unknown",
                                error=f"Output validation failed: {validation_error}",
                                retry_count=execution_context.retry_count,
                            )
                            if execution_context.should_retry():
                                execution_context.retry_count += 1
                                validation_failed = True
                            elif execution_context.should_fallback():
                                execution_context.selected_tool = execution_context.fallback_tools[0]
                                validation_failed = True
                        if validation_failed:
                            aggregated_errors.append(f"Output validation failed: {validation_error}")

                    if not validation_failed:
                        summary_prompt = (
                            f"You just executed tools successfully. Explain what you did naturally.\n"
                            f"Tool history: {truncate_for_history(executed_history, 1200)}\n"
                            f"Result summary: {str(result_data)[:500]}\n"
                            "Be concise (1-2 sentences). Don't say 'I executed' - say what you DID."
                        )
                        try:
                            response_text = final_direct_response or llm.generate_response(summary_prompt, [])
                        except Exception:
                            response_text = final_direct_response or "Done."
                        if not response_text:
                            response_text = "Task completed successfully."

                        from core.output_analyzer import OutputAnalyzer
                        components = OutputAnalyzer.analyze(
                            result_data, tool_name, operation,
                            preferred_renderer=selected_ui_renderer(skill_selection),
                            summary=response_text,
                            skill_name=skill_selection.get("skill_name", ""),
                            category=skill_selection.get("category", ""),
                            output_types=selected_output_types(skill_selection),
                        )
                        execution_result = {
                            "success": True, "results": aggregated_results, "primary_result": result_data,
                            "tool_history": executed_history, "tool_calling": True, "components": components,
                            "ui_renderer": selected_ui_renderer(skill_selection), "rounds_used": round_index + 1,
                        }

                if aggregated_errors or not aggregated_results:
                    error_msg = "; ".join(aggregated_errors) if aggregated_errors else "Execution failed"
                    try:
                        response_text = llm.generate_response(
                            f"A tool execution failed. Explain naturally.\nError: {error_msg}\nBe concise (1-2 sentences).", []
                        )
                    except Exception:
                        response_text = f"I encountered an issue: {error_msg}"
                    if not response_text:
                        response_text = f"Task failed: {error_msg}"
                    execution_result = {"success": False, "errors": aggregated_errors, "tool_history": executed_history}

            else:
                response_text = initial_response or "I understand your request."
                execution_result = {"success": True, "mode": "conversation"}

            if not response_text:
                response_text = "I processed your request."

            sessions[session_id]["messages"].append({
                "role": "assistant", "content": response_text, "timestamp": time.time(),
                "skill": skill_selection.get("skill_name"), "category": skill_selection.get("category"),
            })
            if conv_mem:
                conv_mem.save_message(session_id, "assistant", response_text)

            # Skill registry learning
            try:
                if skill_reg and isinstance(execution_result, dict):
                    import re as _re
                    _success = bool(execution_result.get("success"))
                    _skill_name = skill_selection.get("skill_name")
                    for _call in (execution_result.get("tool_history") or []):
                        _tname = _call.get("tool")
                        if _tname:
                            skill_reg.record_tool_usage(
                                _tname, bool(_call.get("success")),
                                latency_ms=float(_call.get("execution_time") or 0.0) * 1000,
                            )
                    if _success and _skill_name and _skill_name != "conversation":
                        skill_reg.learn_trigger(_skill_name, set(_re.findall(r"[a-z0-9_]+", request.message.lower())))
            except Exception as e:
                print(f"[WARN] Skill registry learning failed: {e}")

            # Finalize execution_result metadata
            try:
                execution_result.update({
                    "selected_skill": skill_selection.get("skill_name"),
                    "selected_category": skill_selection.get("category"),
                    "skill_confidence": skill_selection.get("confidence"),
                    "fallback_used": not skill_selection.get("matched", False),
                    "ui_renderer": selected_ui_renderer(skill_selection),
                })
                try:
                    from core.decision_engine import get_decision_engine
                    _de = get_decision_engine()
                    _scores = {skill_selection.get("skill_name", "unknown"): skill_selection.get("confidence", 0.0)} if skill_selection.get("skill_name") else None
                    _r = _de.score(skill_scores=_scores)
                    execution_result["decision"] = {
                        "strategy": _r.best_strategy, "confidence": _r.confidence,
                        "fallback": _r.fallback_plan, "scores": _r.component_scores,
                        "reasoning": _r.reasoning,
                    }
                except Exception as e:
                    print(f"[WARN] Decision engine scoring failed: {e}")
                if execution_result.get("success") is False:
                    err_text = "; ".join(execution_result.get("errors", [])) if execution_result.get("errors") else execution_result.get("error", "")
                    record_capability_gap(request.message, err_text, skill_selection, llm, reg)
                    execution_result["gap_detected"] = True
                elif execution_result.get("mode") == "conversation":
                    record_capability_gap(request.message, "", skill_selection, llm, reg)
            except Exception as e:
                print(f"[WARN] Execution result finalization failed: {e}")

            return ChatResponse(
                response=response_text, session_id=session_id, success=True,
                execution_result=execution_result,
            )

        except Exception as e:
            return ChatResponse(
                response=f"Error processing '{request.message}': {str(e)}",
                session_id=session_id, success=False,
                execution_result={"success": False, "error": str(e)},
            )

    return stop_chat, chat

