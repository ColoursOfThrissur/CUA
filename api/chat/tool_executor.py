"""Tool execution and orchestration for chat requests."""
from typing import List, Dict, Any, Optional, Tuple
import time as _time


def execute_tool_calls(
    tool_calls: List[Dict],
    session_id: str,
    reg,
    sessions: Dict,
    refresh_registry,
    orchestrator=None,
) -> Tuple[List[Any], List[str], List[Dict[str, Any]], Optional[str], Optional[str]]:
    """Execute list of tool calls and return aggregated results."""
    from application.use_cases.tool_lifecycle.tool_orchestrator import ToolOrchestrator

    orchestrator = orchestrator or ToolOrchestrator(registry=reg)
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
                tool=tool_obj, tool_name=tool_name,
                operation=operation, parameters=parameters
            )
            success, data, error = orch_result.success, orch_result.data, orch_result.error
            elapsed = _time.time() - t0
            
            record = {
                "tool": tool_name, "operation": operation, "parameters": parameters,
                "success": success, "data": data, "error": error,
                "execution_time": elapsed
            }
            executed.append(record)
            
            if success:
                results.append({"tool": tool_name, "operation": operation, "data": data})
                last_tool = tool_name
                last_op = operation
            else:
                errors.append(f"{tool_name}.{operation}: {error}")
        except Exception as e:
            elapsed = _time.time() - t0
            executed.append({
                "tool": tool_name, "operation": operation, "parameters": parameters,
                "success": False, "data": None, "error": str(e),
                "execution_time": elapsed
            })
            errors.append(f"{tool_name}.{operation}: {e}")
    
    return results, errors, executed, last_tool, last_op


def continue_tool_calling(
    tool_caller,
    message: str,
    history: List[Dict],
    executed_batch: List[Dict],
    skill_selection: Dict,
    execution_context
) -> Tuple[bool, Optional[List], Optional[str]]:
    """Continue tool calling with results from previous batch."""
    try:
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


def select_primary_result(
    results: List[Any],
    executed_history: List[Dict]
) -> Tuple[Any, Optional[str], Optional[str]]:
    """Select the most relevant result from multiple tool executions."""
    if not results:
        return None, None, None
    
    best = results[0]
    best_tool = executed_history[0].get("tool") if executed_history else None
    best_op = executed_history[0].get("operation") if executed_history else None
    
    for i, r in enumerate(results):
        data = r.get("data") if isinstance(r, dict) else r
        best_data = best.get("data") if isinstance(best, dict) else best
        if _primary_result_score(data) > _primary_result_score(best_data):
            best = r
            if i < len(executed_history):
                best_tool = executed_history[i].get("tool")
                best_op = executed_history[i].get("operation")
    
    data = best.get("data") if isinstance(best, dict) else best
    return data, best_tool, best_op


def _primary_result_score(data: Any) -> float:
    """Rank answer-quality evidence above payload length."""
    if data is None:
        return -100.0

    score = 0.0
    if isinstance(data, dict):
        if data.get("success") is False:
            score -= 50.0
        if data.get("grounded") is True:
            score += 45.0
        elif data.get("grounding", {}).get("target_app") and data.get("grounded") is False:
            score -= 40.0
        if data.get("answer_ready") is True:
            score += 120.0
        if data.get("requested_field") and data.get("field_value") and not data.get("ambiguous", False):
            score += 90.0
        if data.get("structured_rows"):
            score += 35.0
        if data.get("items"):
            score += 20.0 + min(len(data.get("items") or []), 10)
        if data.get("summary"):
            score += 12.0
        if data.get("target"):
            score += 8.0
        if data.get("ambiguous"):
            score -= 25.0
        if data.get("error") or data.get("error_message"):
            score -= 30.0
    else:
        text = str(data)
        if text.strip():
            score += 5.0

    score += min(len(str(data)) / 250.0, 8.0)
    return score


def truncate_for_history(executed_batch: List[Dict], limit: int = 1500) -> str:
    """Truncate execution history for conversation context."""
    parts = []
    for c in executed_batch:
        status = "ok" if c.get("success") else "err"
        preview = str(c.get("data") or c.get("error") or "")[:200]
        parts.append(f"{status} {c.get('tool')}.{c.get('operation')}: {preview}")
    return "\n".join(parts)[:limit]


def validate_output_against_skill(result_data: Any, execution_context) -> Optional[str]:
    """Validate tool output matches skill expectations."""
    try:
        if not execution_context or not result_data:
            return None
        if isinstance(result_data, dict) and result_data.get("error") and not result_data.get("success", True):
            return f"Tool returned error: {result_data['error']}"
        return None
    except Exception:
        return None
