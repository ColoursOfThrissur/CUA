"""Chat endpoint handler — /chat and /chat/stop."""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel

# Import organized modules
from api.chat.skill_handler import (
    select_skill_for_message, build_planner_context,
    selected_ui_renderer, selected_output_types
)
from api.chat.tool_executor import (
    execute_tool_calls, continue_tool_calling,
    select_primary_result, truncate_for_history,
    validate_output_against_skill
)
from api.chat.message_utils import (
    is_simple_message, simple_reply,
    needs_runtime_refresh, has_referenced_tools_loaded
)
from api.chat.response_formatter import (
    build_wra_components, format_tool_history_for_display
)

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


def _sanitize_llm_response_text(text: Optional[str]) -> str:
    """Strip chain-of-thought style text before sending it to the user."""
    if not text:
        return ""

    cleaned = str(text).strip()
    for marker in ("Thinking Process:", "Reasoning:", "Chain of Thought:", "Internal Analysis:"):
        if marker in cleaned:
            trailing = cleaned.split(marker, 1)[1].strip()
            paragraphs = [p.strip() for p in trailing.split("\n\n") if p.strip()]
            if paragraphs:
                cleaned = paragraphs[-1]

    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = cleaned.strip("`").strip()

    return cleaned.strip()






def record_capability_gap(message: str, error: str, skill_selection: Dict, llm, reg) -> None:
    try:
        from domain.services.gap_detector import GapDetector
        from domain.services.gap_tracker import GapTracker
        from application.services.capability_mapper import CapabilityMapper

        gap = GapDetector(CapabilityMapper()).analyze_failed_task(message, error, skill_selection)
        if gap and gap.confidence >= 0.6:
            # Skip if already resolved in cua.db
            try:
                from infrastructure.persistence.sqlite.cua_database import get_conn as _gc
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


def _build_tool_history_from_plan_state(plan, state) -> List[Dict[str, Any]]:
    """Convert a plan + execution state into tool history records."""
    if not plan or not state or not hasattr(state, "step_results"):
        return []

    registry = getattr(state, "state_registry", None)
    if registry is not None:
        history = registry.build_tool_history()
        if history:
            return history

    step_map = {step.step_id: step for step in getattr(plan, "steps", [])}
    tool_history: List[Dict[str, Any]] = []

    for step_id, step_result in state.step_results.items():
        step = step_map.get(step_id)
        if not step:
            continue
        status = getattr(getattr(step_result, "status", None), "value", str(getattr(step_result, "status", "")))
        tool_history.append({
            "tool": step.tool_name,
            "operation": step.operation,
            "success": status == "completed",
            "data": getattr(step_result, "output", None),
            "error": getattr(step_result, "error", None),
            "execution_time": getattr(step_result, "execution_time", 0.0),
        })

    return tool_history


def _apply_skill_registry_learning(skill_reg, skill_selection: Dict, request_message: str, execution_result: Optional[Dict]) -> None:
    """Record tool usage and successful trigger learning across all execution paths."""
    try:
        if not skill_reg or not isinstance(execution_result, dict):
            return

        import re as _re

        success = bool(execution_result.get("success"))
        skill_name = skill_selection.get("skill_name")
        for call in (execution_result.get("tool_history") or []):
            tool_name = call.get("tool")
            if not tool_name:
                continue
            skill_reg.record_tool_usage(
                tool_name,
                bool(call.get("success")),
                latency_ms=float(call.get("execution_time") or 0.0) * 1000,
            )

        if success and skill_name and skill_name != "conversation":
            skill_reg.learn_trigger(skill_name, set(_re.findall(r"[a-z0-9_]+", request_message.lower())))
    except Exception as e:
        print(f"[WARN] Skill registry learning failed: {e}")


def _attempt_planning_fallback(request_message, session_id, skill_selection, task_planner, sessions, conv_mem):
    """Fallback to task planning when tool calling fails."""
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
    tool_orchestrator = runtime.tool_orchestrator
    circuit_breaker = runtime.circuit_breaker
    logger = runtime.logger

    async def stop_chat():
        global _stop_requested
        _stop_requested = True
        return {"success": True, "message": "Stop requested"}

    async def chat(request: ChatRequest):
        global _stop_requested
        _stop_requested = False
        
        # Set up thinking callback for LLM client
        from api.trace_ws import broadcast_trace_sync
        def thinking_callback(thinking_text: str):
            broadcast_trace_sync("thinking", thinking_text, "in_progress")
        llm.set_thinking_callback(thinking_callback)
        
        try:
            return await _chat_impl(request)
        finally:
            llm.clear_thinking_callback()
    
    async def _chat_impl(request: ChatRequest):

        from infrastructure.validation.input_validator import validate_text_input
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
            if is_simple_message(request.message):
                response_text = simple_reply(request.message)
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
            print(f"[DEBUG] Skill selection: {skill_selection.get('skill_name')} (confidence={skill_selection.get('confidence'):.2f}, reason={skill_selection.get('reason')})")

            # Conversation skill
            if skill_selection.get("skill_name") == "conversation":
                # Enable streaming for conversational responses
                from api.trace_ws import broadcast_trace_sync
                accumulated_response = ""
                
                def stream_handler(chunk: str):
                    nonlocal accumulated_response
                    accumulated_response += chunk
                    broadcast_trace_sync("llm_stream", chunk, "in_progress")
                
                response_text = llm.generate_response(
                    request.message, 
                    sessions[session_id]["messages"][-5:],
                    stream=True,
                    stream_callback=stream_handler
                )
                response_text = _sanitize_llm_response_text(response_text)
                
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
                        tool_history = _build_tool_history_from_plan_state(pending_plan, state)
                        if state and getattr(state, "error", None):
                            response_text = f"Plan approved, but execution failed: {state.error}"
                            execution_result = {
                                "success": False,
                                "mode": "autonomous_agent",
                                "status": "execution_failed",
                                "error": state.error,
                                "tool_history": format_tool_history_for_display(tool_history),
                            }
                        else:
                            response_text = "✓ Plan approved and executed."
                            execution_result = {
                                "success": True,
                                "mode": "autonomous_agent",
                                "status": "executed",
                                "execution_id": execution_id,
                                "tool_history": format_tool_history_for_display(tool_history),
                            }
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
                _apply_skill_registry_learning(skill_reg, skill_selection, request.message, execution_result)
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
                    from application.use_cases.autonomy.autonomous_agent import AgentGoal
                    import api.chat_helpers as _self
                    # Resolve short follow-up references using recent conversation history
                    goal_text = request.message
                    prev_context = ""
                    recent = sessions[session_id]["messages"]
                    if len(request.message.split()) <= 8:
                        prev_assistant = next(
                            (m["content"] for m in reversed(recent[:-1]) if m["role"] == "assistant"),
                            None,
                        )
                        if prev_assistant:
                            prev_context = prev_assistant[:300]
                    goal = AgentGoal(
                        goal_text=goal_text, success_criteria=[],
                        max_iterations=5, require_approval=False,
                    )
                    _skill_context = build_planner_context(skill_selection, skill_reg) or {"skill_context": {"skill_name": skill_selection.get("skill_name", "")}}
                    if prev_context:
                        _skill_context["previous_context"] = prev_context
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
                            response_text = _sanitize_llm_response_text(result.get("message", "Task completed."))
                            # Build components from synthesized answer + any structured search results
                            agent_components = build_wra_components(response_text, wra_raw)
                            execution_result = {
                                "success": True,
                                "mode": "autonomous_agent",
                                "selected_skill": skill_selection.get("skill_name"),
                                "selected_category": skill_selection.get("category"),
                                "skill_confidence": skill_selection.get("confidence"),
                                "fallback_used": False,
                                "tool_history": format_tool_history_for_display(result.get("tool_history") or []),
                                "components": agent_components,
                                "primary_result": wra_raw[0] if wra_raw else None,
                                "ui_renderer": selected_ui_renderer(skill_selection),
                            }
                            sessions[session_id]["messages"].append({"role": "assistant", "content": response_text, "timestamp": time.time()})
                            if conv_mem:
                                conv_mem.save_message(session_id, "assistant", response_text)
                            try:
                                from infrastructure.messaging.event_bus import get_event_bus
                                get_event_bus().emit_sync("agent_plan_clear", {})
                            except Exception:
                                pass
                            _apply_skill_registry_learning(skill_reg, skill_selection, request.message, execution_result)
                            return ChatResponse(
                                response=response_text, session_id=session_id, success=True,
                                execution_result=execution_result,
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
                            has_rich = len(all_step_data) >= 2
                            
                            # Special handling for financial operations
                            primary_data = max(all_step_data, key=lambda x: len(str(x))) if all_step_data else {}
                            if isinstance(primary_data, dict):
                                # Morning note
                                if primary_data.get("one_liner") or primary_data.get("market_mood"):
                                    date_str = primary_data.get("date", "")
                                    one_liner = primary_data.get("one_liner", "")
                                    market_mood = primary_data.get("market_mood", "")
                                    response_text = f"📊 {date_str}\n\n{one_liner}\n\n{market_mood}" if one_liner or market_mood else f"Morning note for {date_str} is ready."
                                # Full report
                                elif primary_data.get("executive_summary") or primary_data.get("rating"):
                                    exec_summary = primary_data.get("executive_summary", "")
                                    rating = primary_data.get("rating", "")
                                    response_text = f"Investment report generated. Rating: {rating.upper()}\n\n{exec_summary}" if exec_summary else "Full investment report is ready."
                                # Generic financial data
                                else:
                                    word_target = "2-3 sentences"
                                    summary_prompt = (
                                        f"User request: {request.message}\n\n"
                                        f"Data: {str(primary_data)[:600]}\n\n"
                                        f"Write a {word_target} natural response highlighting key findings. "
                                        f"Be direct and specific. No meta-commentary."
                                    )
                                    try:
                                        response_text = _sanitize_llm_response_text(llm.generate_response(summary_prompt, [], max_tokens=150))
                                    except Exception:
                                        response_text = f"✓ {result.get('message', 'Task completed')}"
                            else:
                                response_text = f"✓ {result.get('message', 'Task completed')}"
                        else:
                            response_text = f"\u2713 {result.get('message', 'Task completed')}"
                    else:
                        response_text = result.get("message", "Task failed")

                    # Build rich components from agent step outputs
                    agent_components = list(screenshot_components) if 'screenshot_components' in dir() else []
                    all_step_data_safe = all_step_data if 'all_step_data' in dir() else []
                    if result.get("success") and all_step_data_safe:
                        from infrastructure.analysis.output_analyzer import OutputAnalyzer
                        # Use the richest single output (largest dict or longest string)
                        primary = max(all_step_data_safe, key=lambda x: len(str(x)))
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
                        from infrastructure.messaging.event_bus import get_event_bus
                        get_event_bus().emit_sync("agent_plan_clear", {})
                    except Exception as e:
                        print(f"[WARN] Event bus emit failed: {e}")
                    primary_data = max(all_step_data_safe, key=lambda x: len(str(x))) if all_step_data_safe else None
                    execution_result = {
                        "success": bool(result.get("success")), "mode": "autonomous_agent",
                        "selected_skill": skill_selection.get("skill_name"),
                        "selected_category": skill_selection.get("category"),
                        "skill_confidence": skill_selection.get("confidence"),
                        "fallback_used": False,
                        "tool_history": format_tool_history_for_display(result.get("tool_history") or []),
                        "components": agent_components,
                        "primary_result": primary_data,
                    }
                    _apply_skill_registry_learning(skill_reg, skill_selection, request.message, execution_result)
                    return ChatResponse(
                        response=response_text, session_id=session_id, success=True,
                        execution_result=execution_result,
                    )
                except Exception as e:
                    print(f"[DEBUG] Autonomous agent failed: {e}, falling back to tool calling")

            # Native tool calling
            from planner.tool_calling import ToolCallingClient
            from application.services.skill_context_hydrator import SkillContextHydrator
            from application.services.tool_selector import ContextAwareToolSelector

            tool_caller = ToolCallingClient(ollama_url=llm.ollama_url, model=llm.model, registry=reg)

            execution_context = None
            allowed_tools = None
            if skill_selection.get("matched") and skill_selection.get("skill_name"):
                skill_def = skill_reg.get(skill_selection["skill_name"])
                if skill_def:
                    from domain.entities.skill_models import SkillSelection as SkillSelectionModel
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
                response_text = _sanitize_llm_response_text(llm.generate_response(request.message, conversation_history))
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
                        current_calls, session_id, reg, sessions, refresh_registry, tool_orchestrator,
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
                        # Check if result is from DataVisualizationTool render_output
                        viz_output = None
                        if isinstance(result_data, dict):
                            # Check both direct format and success-wrapped format
                            output_type = result_data.get("type")
                            if output_type in ("chart_image", "table", "metrics", "code", "text"):
                                viz_output = result_data
                            # Also check if wrapped in success envelope
                            elif result_data.get("success") and result_data.get("renderer") in ("chart_image", "table", "metrics", "code", "text"):
                                viz_output = result_data
                        
                        if viz_output:
                            # DataVisualizationTool already formatted the output
                            # Build proper component structure: overview + detail
                            components = []
                            
                            # Add overview card if there's context
                            if skill_selection.get("skill_name"):
                                components.append({
                                    "type": "agent_result",
                                    "renderer": selected_ui_renderer(skill_selection) or "agent_result",
                                    "title": skill_selection.get("skill_name", "").replace("_", " ").title(),
                                    "summary": "",  # LLM summary goes in message bubble
                                    "skill": skill_selection.get("skill_name"),
                                    "category": skill_selection.get("category"),
                                    "tool_name": tool_name,
                                    "operation": operation,
                                    "output_types": selected_output_types(skill_selection),
                                    "highlights": [],
                                })
                            
                            # Add the formatted output as detail component
                            components.append(viz_output)
                            
                            # LLM generates natural language summary
                            if final_direct_response:
                                response_text = final_direct_response
                            else:
                                summary_prompt = (
                                    f"The user asked: {request.message}\n\n"
                                    f"Result type: {viz_output.get('type')}\n"
                                    f"Data summary: {str(result_data)[:500]}\n\n"
                                    f"Write a 2-3 sentence natural language response that:\n"
                                    f"- Directly answers the user's question\n"
                                    f"- Mentions what type of output is shown (chart/table/metrics)\n"
                                    f"- Highlights 1-2 key findings from the data\n"
                                    f"- Does NOT say 'I executed' or 'the tool returned'\n"
                                    f"The formatted visualization appears below your response."
                                )
                                try:
                                    response_text = _sanitize_llm_response_text(llm.generate_response(summary_prompt, [], max_tokens=150))
                                except Exception:
                                    response_text = "Here's the formatted output:"
                        else:
                            # Fallback to OutputAnalyzer for non-viz outputs
                            from infrastructure.analysis.output_analyzer import OutputAnalyzer
                            components = OutputAnalyzer.analyze(
                                result_data, tool_name, operation,
                                preferred_renderer=selected_ui_renderer(skill_selection),
                                summary="",
                                skill_name=skill_selection.get("skill_name", ""),
                                category=skill_selection.get("category", ""),
                                output_types=selected_output_types(skill_selection),
                            )
                            # LLM writes the header — length scales with output richness
                            has_rich_components = len(components) >= 2
                            if final_direct_response:
                                response_text = final_direct_response
                            else:
                                # Special handling for morning notes and reports
                                if operation == "generate_morning_note" and isinstance(result_data, dict):
                                    date_str = result_data.get("date", "")
                                    one_liner = result_data.get("one_liner", "")
                                    market_mood = result_data.get("market_mood", "")
                                    response_text = f"📊 {date_str}\n\n{one_liner}\n\n{market_mood}" if one_liner or market_mood else f"Morning note for {date_str} is ready."
                                elif operation == "generate_full_report" and isinstance(result_data, dict):
                                    exec_summary = result_data.get("executive_summary", "")
                                    rating = result_data.get("rating", "")
                                    response_text = f"Investment report generated. Rating: {rating.upper()}\n\n{exec_summary}" if exec_summary else "Full investment report is ready."
                                else:
                                    word_target = "100-200 words" if has_rich_components else "1-3 sentences"
                                    summary_prompt = (
                                        f"The user asked: {request.message}\n\n"
                                        f"Tool: {tool_name}.{operation}\n"
                                        f"Result: {str(result_data)[:800]}\n\n"
                                        f"Write a {word_target} response that:\n"
                                        f"- Directly answers the user's question\n"
                                        f"- Highlights the most important findings\n"
                                        f"- Mentions specific numbers/values from the result\n"
                                        f"- Does NOT say 'I executed' or 'the tool returned'\n"
                                        f"Structured details (charts, tables) will appear below your response."
                                    )
                                    try:
                                        response_text = _sanitize_llm_response_text(llm.generate_response(summary_prompt, [], max_tokens=200))
                                    except Exception:
                                        response_text = "Done."
                        if not response_text:
                            response_text = "Task completed."
                        execution_result = {
                            "success": True, "results": aggregated_results, "primary_result": result_data,
                            "tool_history": format_tool_history_for_display(executed_history),
                            "tool_calling": True, "components": components,
                            "ui_renderer": selected_ui_renderer(skill_selection), "rounds_used": round_index + 1,
                        }

                if aggregated_errors or not aggregated_results:
                    error_msg = "; ".join(aggregated_errors) if aggregated_errors else "Execution failed"
                    try:
                        response_text = _sanitize_llm_response_text(llm.generate_response(
                            f"A tool execution failed. Explain naturally.\nError: {error_msg}\nBe concise (1-2 sentences).", [],
                            max_tokens=100
                        ))
                    except Exception:
                        response_text = f"I encountered an issue: {error_msg}"
                    if not response_text:
                        response_text = f"Task failed: {error_msg}"
                    execution_result = {
                        "success": False, "errors": aggregated_errors,
                        "tool_history": format_tool_history_for_display(executed_history)
                    }

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

            _apply_skill_registry_learning(skill_reg, skill_selection, request.message, execution_result)

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
                    from domain.services.decision_engine import get_decision_engine
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

