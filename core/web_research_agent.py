"""Reactive web research agent — browser-use style loop for web_research and browser_automation skills."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_ACTIONS = ["search", "navigate", "read_page", "click", "fill", "scroll", "extract", "done"]


def _infer_output_schema(goal: str) -> str:
    """Infer expected output schema from goal — keep minimal for small models."""
    g = goal.lower()
    if any(k in g for k in ["table", "standing", "ranking", "leaderboard", "score", "stat"]):
        return '  done: {"answer": string, "sources": [urls]}  — answer must include the actual data/numbers found'
    if any(k in g for k in ["price", "cost", "rate", "weather", "temperature", "stock"]):
        return '  done: {"answer": string, "sources": [urls]}  — answer must include the actual numeric value'
    if any(k in g for k in ["list", "top", "best", "compare"]):
        return '  done: {"answer": string, "items": [key items, max 5], "sources": [urls]}'
    # Default — minimal schema Qwen can reliably fill in 256 tokens
    return '  done: {"answer": string, "sources": [urls]}  — answer must directly address the goal'


class WebResearchAgent:
    """Reactive loop agent for web research and browser automation tasks."""

    MAX_STEPS = 12

    def __init__(self, llm_client, tool_registry=None):
        self.llm = llm_client
        self.registry = tool_registry
        self._orchestrator = None
        self._tool_map: Dict[str, Any] = {}

    def _get_orchestrator(self):
        if self._orchestrator:
            return self._orchestrator
        from core.tool_orchestrator import ToolOrchestrator
        self._orchestrator = ToolOrchestrator(llm_client=self.llm, registry=self.registry)
        return self._orchestrator

    def _get_tool(self, name: str):
        if name in self._tool_map:
            return self._tool_map[name]
        for t in getattr(self.registry, "tools", []):
            if t.__class__.__name__ == name:
                self._tool_map[name] = t
                return t
        return None

    def _call(self, tool_name: str, operation: str, **params) -> Dict[str, Any]:
        """Call a tool through the orchestrator (services properly wired)."""
        tool = self._get_tool(tool_name)
        if not tool:
            return {"ok": False, "error": f"{tool_name} not available"}
        try:
            orch = self._get_orchestrator()
            result = orch.execute_tool_step(
                tool=tool, tool_name=tool_name,
                operation=operation, parameters=params,
            )
            if result.success:
                return {"ok": True, "data": result.data}
            return {"ok": False, "error": result.error or "unknown error"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _page_state(self) -> Dict[str, str]:
        """Get current browser page state + interactive elements via BrowserAutomationTool services."""
        bt = self._get_tool("BrowserAutomationTool")
        if not bt or not getattr(bt, "services", None):
            return {"title": "", "content": "", "url": "", "elements": [], "elements_str": ""}
        try:
            svc = bt.services.browser
            if not svc.driver:
                return {"title": "", "content": "", "url": "", "elements": [], "elements_str": ""}
            state = {
                "title": svc.get_page_title(),
                "url": svc.get_current_url(),
                "content": svc.get_page_text()[:2000],
                "elements": [],
                "elements_str": "",
            }
            el_result = self._call("BrowserAutomationTool", "get_interactive_elements", limit=25)
            if el_result["ok"] and isinstance(el_result.get("data"), dict):
                state["elements"] = el_result["data"].get("elements", [])
                # Trim formatted string to keep prompt size safe for small models
                formatted = el_result["data"].get("formatted", "")
                state["elements_str"] = "\n".join(formatted.splitlines()[:20])
            return state
        except Exception as e:
            logger.debug(f"[WRA] page_state error: {e}")
            return {"title": "", "content": "", "url": "", "elements": [], "elements_str": ""}

    def _execute_action(self, action: str, params: Dict, history: List[Dict] = None) -> Dict[str, Any]:
        """Execute one action, return result dict."""
        if action == "search":
            query = params.get("query", "")
            result = self._call("WebAccessTool", "search_web", query=query)
            if not result["ok"]:
                # fallback: browser navigate to DuckDuckGo
                from urllib.parse import quote_plus
                result = self._call("BrowserAutomationTool", "navigate",
                                    url=f"https://duckduckgo.com/?q={quote_plus(query)}")
            return result

        elif action == "navigate":
            url = params.get("url", "")
            result = self._call("BrowserAutomationTool", "navigate", url=url)
            if not result["ok"]:
                fallback = self._call("WebAccessTool", "fetch_url", url=url)
                if fallback["ok"]:
                    # Mark ok so LLM knows content is available; tag source
                    fallback["data"] = fallback.get("data") or {}
                    if isinstance(fallback["data"], dict):
                        fallback["data"]["_via"] = "fetch_url"
                    return fallback
                return fallback
            return result

        elif action == "read_page":
            state = self._page_state()
            if state["content"]:
                return {"ok": True, "data": state}
            # Browser not loaded — try to re-fetch the last navigated URL from history
            last_nav = next(
                (h for h in reversed(history or []) if h["action"] == "navigate" and h.get("ok")),
                None,
            )
            if last_nav:
                url = last_nav.get("params", {}).get("url", "")
                if url:
                    return self._call("WebAccessTool", "fetch_url", url=url)
            return self._call("WebAccessTool", "get_current_page")

        elif action == "click":
            # Support index-based click (browser-use style) or legacy selector
            index = params.get("index")
            if index is not None:
                elements = (history or [{}])[-1].get("_elements", []) if history else []
                # Find element by index from last page_state stored in history
                el = next((e for e in elements if e.get("index") == int(index)), None)
                if el and el.get("href"):
                    return self._call("BrowserAutomationTool", "navigate", url=el["href"])
                selector = el.get("text", "") if el else str(index)
                return self._call("BrowserAutomationTool", "click_element",
                                  selector=f"[aria-label='{selector}'], a:contains('{selector}')",
                                  by="css")
            return self._call("BrowserAutomationTool", "click_element",
                              selector=params.get("selector", ""))

        elif action == "fill":
            index = params.get("index")
            if index is not None:
                elements = (history or [{}])[-1].get("_elements", []) if history else []
                el = next((e for e in elements if e.get("index") == int(index)), None)
                selector = el.get("placeholder") or el.get("text") or str(index) if el else str(index)
                return self._call("BrowserAutomationTool", "fill_input",
                                  selector=f"[placeholder='{selector}']" if el and el.get("placeholder") else "input",
                                  text=params.get("text", ""))
            return self._call("BrowserAutomationTool", "fill_input",
                              selector=params.get("selector", ""),
                              text=params.get("text", ""))

        elif action == "scroll":
            return self._call("BrowserAutomationTool", "scroll_page",
                              direction=params.get("direction", "down"))

        elif action == "extract":
            # Prefer structured content (tables + headings) over flat text
            bt = self._get_tool("BrowserAutomationTool")
            if bt and getattr(bt, "services", None) and getattr(bt.services, "browser", None) and bt.services.browser.driver:
                result = self._call("BrowserAutomationTool", "get_structured_content")
                if result["ok"]:
                    return result
            state = self._page_state()
            return {"ok": True, "data": {"content": state.get("content", ""),
                                          "extracting": params.get("what", "")}}

        return {"ok": False, "error": f"unknown action: {action}"}

    def _build_prompt(self, goal: str, page_state: Dict, history: List[Dict]) -> str:
        output_schema = _infer_output_schema(goal)
        system = (
            "You are a web research agent. On each step you see the current page state, interactive elements, and action history. "
            "Pick ONE action from: search, navigate, read_page, click, fill, scroll, extract, done.\n"
            "Return ONLY JSON: {\"action\": string, \"params\": object, \"reason\": string}\n"
            "Action params:\n"
            "  search:   {\"query\": string}\n"
            "  navigate: {\"url\": string}\n"
            "  read_page: {}\n"
            "  click:    {\"index\": number}  — use element index from INTERACTIVE ELEMENTS list\n"
            "  fill:     {\"index\": number, \"text\": string}  — use element index from INTERACTIVE ELEMENTS list\n"
            "  scroll:   {\"direction\": \"down\"|\"up\"}\n"
            "  extract:  {\"what\": string}  — describe what to extract from current page\n"
            f"{output_schema}\n"
            "Rules:\n"
            "- Use 'search' first for research goals, 'navigate' for direct URLs.\n"
            "- After a successful navigate, use 'extract' to get structured data or 'done' if you have enough.\n"
            "- Use 'click' with the element INDEX number, not a CSS selector.\n"
            "- Use 'read_page' ONLY if navigate failed or page content is missing.\n"
            "- Use 'done' as soon as you have enough information to answer the goal.\n"
            "- Never repeat the same action+params twice.\n"
        )
        history_str = ""
        for i, h in enumerate(history[-6:], 1):
            ok = "OK" if h.get("ok") else "FAIL"
            # Format result preview based on action type for readability
            result = h.get("result", "")
            if h["action"] == "search" and isinstance(result, dict):
                items = result.get("results") or result.get("links") or []
                preview = " | ".join(
                    f"{r.get('title','')}: {r.get('url') or r.get('link','')}" for r in items[:4]
                ) if items else str(result)[:200]
            elif h["action"] in ("navigate", "read_page") and isinstance(result, dict):
                preview = f"title={result.get('title','')} url={result.get('url','')}"
            elif h["action"] == "extract" and isinstance(result, dict):
                tables = result.get("tables") or []
                preview = f"{len(tables)} tables, headings={[x.get('text') for x in (result.get('headings') or [])[:3]]}"
            else:
                preview = str(result)[:300]
            history_str += f"Step {i} [{ok}]: {h['action']}({h.get('params', {})}) -> {preview}\n"

        # If browser has no live content, inject last successful navigate's fetched content
        if not page_state.get("content"):
            last_nav = next(
                (h for h in reversed(history) if h["action"] == "navigate" and h.get("ok")),
                None,
            )
            if last_nav and isinstance(last_nav.get("result"), dict):
                r = last_nav["result"]
                content = str(r.get("content") or r.get("text") or "")[:3000]
                if content:
                    page_state = {
                        "url": last_nav["params"].get("url", ""),
                        "title": r.get("title", "Fetched page"),
                        "content": content,
                        "elements_str": "",
                    }

        elements_section = ""
        if page_state.get("elements_str"):
            elements_section = f"\nINTERACTIVE ELEMENTS (use index for click/fill):\n{page_state['elements_str']}\n"

        page_str = (
            f"URL: {page_state.get('url', 'none')}\n"
            f"Title: {page_state.get('title', 'none')}\n"
            f"Content (first 3000 chars):\n{page_state.get('content', '(empty)')}"
        )

        return (
            f"{system}\n\n"
            f"GOAL: {goal}\n\n"
            f"CURRENT PAGE:\n{page_str}"
            f"{elements_section}\n"
            f"ACTION HISTORY:\n{history_str or '(none yet)'}\n\n"
            "What is your next action? Return ONLY JSON."
        )

    def _synthesize_report(self, goal: str, collected_data: list, history: list, conv_history: list) -> str:
        """Synthesize collected data into a structured markdown report with numbered citations."""
        # Build numbered source list from visited URLs
        all_urls: List[str] = []
        for h in history:
            all_urls.extend(h.get("_urls") or [])
        unique_urls = list(dict.fromkeys(u for u in all_urls if u and not u.startswith("about:")))

        # Build source index: {url: index}
        source_index = {url: i + 1 for i, url in enumerate(unique_urls[:8])}
        sources_block = "\n".join(f"[{i}] {url}" for url, i in source_index.items())

        # Format collected data into readable chunks, tagging each with its source number
        parts: List[str] = []
        for d in collected_data[:6]:
            if isinstance(d, list):  # search result list
                chunk = "\n".join(
                    f"- {r.get('title', '')}: {r.get('snippet') or r.get('description', '')[:200]} ({r.get('url') or r.get('link', '')})"
                    for r in d[:8] if isinstance(r, dict)
                )
            elif isinstance(d, dict):
                text = d.get("text") or ""
                headings = " | ".join(h.get("text", "") for h in (d.get("headings") or [])[:5])
                chunk = f"{headings}\n{text[:2000]}" if headings else text[:2000]
            else:
                chunk = str(d)[:2000]
            if chunk.strip():
                parts.append(chunk)

        if not parts:
            return "Could not complete the research task."

        # Conversation context (last 4 turns)
        conv_context = ""
        if conv_history:
            conv_lines = "\n".join(
                f"{m['role'].title()}: {str(m.get('content', ''))[:200]}"
                for m in conv_history[-4:]
            )
            conv_context = f"Conversation context:\n{conv_lines}\n\n"

        sources_hint = f"\n\nNumbered sources:\n{sources_block}" if sources_block else ""

        prompt = (
            f"{conv_context}"
            f"Goal: {goal}\n\n"
            f"Collected research data:\n"
            + "\n---\n".join(parts)
            + f"{sources_hint}\n\n"
            "Write a structured research report in markdown that directly answers the goal.\n"
            "Format:\n"
            "- Start with a 1-2 sentence summary\n"
            "- Use ## sections for main topics\n"
            "- Cite sources inline as [N] where N matches the numbered sources list\n"
            "- End with a ## References section listing only the sources you actually cited\n"
            "- Be concise — no padding or filler sentences\n"
            "Return only the markdown report."
        )

        try:
            return self.llm.generate_response(prompt, [])
        except Exception:
            # Fallback: plain answer with sources appended
            plain = parts[0] if parts else "Could not complete the research task."
            if sources_block:
                plain += f"\n\n## References\n{sources_block}"
            return plain

    def run(self, goal: str, session_id: str = "", conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Run the reactive loop. Returns dict compatible with AutonomousAgent.achieve_goal()."""
        logger.info(f"[WRA] Starting reactive loop for: '{goal[:80]}'")

        history: List[Dict] = []
        collected_data: List[str] = []
        final_answer: Optional[str] = None
        _conv_history = conversation_history or []

        for step in range(self.MAX_STEPS):
            page_state = self._page_state()
            prompt = self._build_prompt(goal, page_state, history)

            try:
                raw = self.llm._call_llm(prompt, temperature=0.2, max_tokens=400, expect_json=True)
                parsed = self.llm._extract_json(raw) if raw else None
            except Exception as e:
                logger.warning(f"[WRA] LLM call failed at step {step}: {e}")
                break

            if not parsed or "action" not in parsed:
                logger.warning(f"[WRA] Bad LLM response at step {step}: {raw!r}")
                break

            action = str(parsed.get("action", "")).strip()
            params = parsed.get("params") or {}
            reason = parsed.get("reason", "")

            logger.info(f"[WRA] Step {step+1}: {action}({params}) — {reason}")

            if action == "done":
                final_answer = params.get("answer") or reason or "Task completed."
                # Extract structured fields from done params
                done_extras = {}
                for field in ("key_facts", "items", "value", "unit", "rows_found", "data_type"):
                    if params.get(field):
                        done_extras[field] = params[field]
                if done_extras:
                    collected_data.append(done_extras)
                # Build cited report if sources available
                sources = params.get("sources") or []
                if sources:
                    numbered = "\n".join(f"[{i+1}] {s}" for i, s in enumerate(sources[:8]))
                    final_answer = f"{final_answer}\n\n## References\n{numbered}"
                break

            if action not in _ACTIONS:
                logger.warning(f"[WRA] Unknown action '{action}', stopping")
                break

            # Dedup guard — don't repeat exact same action+params
            action_key = f"{action}:{params}"
            if any(f"{h['action']}:{h.get('params')}" == action_key for h in history):
                logger.warning(f"[WRA] Duplicate action detected: {action_key}, stopping loop")
                break

            result = self._execute_action(action, params, history)
            result_data = result.get("data") or result.get("error", "")
            # For search, store structured results directly (not stringified) for readable history
            if action == "search" and isinstance(result_data, dict):
                items = result_data.get("results") or result_data.get("links") or []
                history.append({"action": action, "params": params,
                                 "ok": result["ok"],
                                 "result": {"results": items},
                                 "_elements": page_state.get("elements", []),
                                 "_urls": [r.get("url") or r.get("link", "") for r in items if r.get("url") or r.get("link")]})
            else:
                history.append({"action": action, "params": params,
                                 "ok": result["ok"],
                                 "result": result_data,
                                 "_elements": page_state.get("elements", []),
                                 "_urls": [page_state.get("url", "")] if page_state.get("url") else []})

            # Collect useful data
            data = result.get("data")
            if isinstance(data, dict):
                if action == "search":
                    items = data.get("results") or data.get("links") or []
                    if items:
                        collected_data.append(items)  # keep as list of dicts
                elif action in ("navigate", "read_page"):
                    for key in ("content", "text", "summary"):
                        val = data.get(key)
                        if val and len(str(val)) > 200:
                            collected_data.append(str(val)[:4000])
                            break
                elif action == "extract":
                    if isinstance(data, dict) and (data.get("tables") or data.get("headings") or data.get("text")):
                        collected_data.append(data)
                    else:
                        for key in ("content", "text"):
                            val = data.get(key) if isinstance(data, dict) else None
                            if val and len(str(val)) > 100:
                                collected_data.append(str(val)[:3000])
                                break
            elif data:
                collected_data.append(str(data)[:2000])

        # Synthesize final answer if loop ended without "done"
        if not final_answer:
            if collected_data:
                final_answer = self._synthesize_report(goal, collected_data, history, _conv_history)
            else:
                final_answer = "Could not find relevant information for the goal."

        logger.info(f"[WRA] Done in {len(history)} steps")

        # Record outcome into strategic memory so web research is learned like any other goal
        try:
            from core.strategic_memory import get_strategic_memory
            _steps = [{"tool_name": h["action"], "operation": h["action"], "domain": "web"}
                      for h in history if h.get("ok")]
            get_strategic_memory().record(
                goal=goal, skill_name="web_research",
                steps=_steps, success=bool(final_answer),
            )
        except Exception as e:
            logger.debug(f"[WRA] strategic_memory.record failed: {e}")

        return {
            "success": True,
            "message": final_answer,
            "iterations": 1,
            "execution_history": [session_id],
            "final_state": None,
            "raw_data": collected_data,   # list of raw strings/dicts for OutputAnalyzer
            "goal": goal,
        }
