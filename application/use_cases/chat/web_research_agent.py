"""Reactive web research agent — browser-use style loop for web_research and browser_automation skills."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_ACTIONS = ["search", "navigate", "read_page", "click", "fill", "scroll", "extract", "done"]


def _sanitize_answer(text: Optional[str]) -> str:
    """Remove chain-of-thought style prefixes from synthesized answers."""
    if not text:
        return ""

    cleaned = str(text).strip()
    for marker in ("Thinking Process:", "Reasoning:", "Chain of Thought:", "Internal Analysis:"):
        if marker in cleaned:
            trailing = cleaned.split(marker, 1)[1].strip()
            paragraphs = [p.strip() for p in trailing.split("\n\n") if p.strip()]
            if paragraphs:
                cleaned = paragraphs[-1]
    if "\n## References" in cleaned:
        cleaned = cleaned.split("\n## References", 1)[0].strip()
    if "\nReferences:" in cleaned:
        cleaned = cleaned.split("\nReferences:", 1)[0].strip()
    return cleaned.strip()


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

    def __init__(self, llm_client, tool_registry=None, orchestrator=None):
        self.llm = llm_client
        self.registry = tool_registry
        self._orchestrator = orchestrator
        self._tool_map: Dict[str, Any] = {}

    def _get_orchestrator(self):
        if self._orchestrator:
            return self._orchestrator
        from application.use_cases.tool_lifecycle.tool_orchestrator import ToolOrchestrator
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
            return {"ok": False, "error": f"{tool_name} not available", "_tool": tool_name, "_operation": operation}
        try:
            orch = self._get_orchestrator()
            result = orch.execute_tool_step(
                tool=tool, tool_name=tool_name,
                operation=operation, parameters=params,
            )
            if result.success:
                return {"ok": True, "data": result.data, "_tool": tool_name, "_operation": operation}
            return {"ok": False, "error": result.error or "unknown error", "_tool": tool_name, "_operation": operation}
        except Exception as e:
            return {"ok": False, "error": str(e), "_tool": tool_name, "_operation": operation}

    def _page_state(self, history: List[Dict] = None) -> Dict[str, str]:
        """Get current browser page state + interactive elements, or last fetched page from history."""
        # First check if we have a recent navigate/read_page result in history (from WebAccessTool)
        if history:
            for h in reversed(history[-3:]):
                if h.get("action") in ("navigate", "read_page") and h.get("ok"):
                    result = h.get("result")
                    # Handle both direct result dict and nested data dict
                    if isinstance(result, dict):
                        data = result if result.get("content") or result.get("text") else result.get("data", {})
                        if isinstance(data, dict) and (data.get("content") or data.get("text")):
                            return {
                                "title": data.get("title", ""),
                                "url": data.get("url") or h.get("params", {}).get("url", ""),
                                "content": (data.get("content") or data.get("text", ""))[:3000],
                                "elements": [],
                                "elements_str": "",
                                "_via": data.get("_via", "fetch"),
                            }
        
        # Fallback to browser state
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
            # Always prefer WebAccessTool for search - it's more reliable than browser automation
            result = self._call("WebAccessTool", "search_web", query=query)
            if result["ok"]:
                return result
            # Only fallback to browser if WebAccessTool completely fails
            from urllib.parse import quote_plus
            result = self._call("BrowserAutomationTool", "navigate",
                                url=f"https://duckduckgo.com/?q={quote_plus(query)}")
            return result

        elif action == "navigate":
            url = params.get("url", "")
            # Validate URL
            if not url or not (url.startswith("http://") or url.startswith("https://")):
                return {"ok": False, "error": f"Invalid URL: {url}"}
            # Use BrowserAutomationTool so the action is visible to the user
            result = self._call("BrowserAutomationTool", "navigate", url=url)
            return result

        elif action == "read_page":
            # First check if we have content from recent navigation in history
            state = self._page_state(history)
            if state.get("content"):
                return {"ok": True, "data": state}
            
            # If no content from history, try to get current browser state
            bt = self._get_tool("BrowserAutomationTool")
            if bt and getattr(bt, "services", None) and getattr(bt.services, "browser", None):
                try:
                    svc = bt.services.browser
                    if svc.driver:
                        browser_state = {
                            "title": svc.get_page_title(),
                            "url": svc.get_current_url(),
                            "content": svc.get_page_text()[:3000],
                        }
                        if browser_state["content"]:
                            return {"ok": True, "data": browser_state}
                except Exception as e:
                    logger.debug(f"[WRA] Browser state read failed: {e}")
            
            # Last resort: try to re-fetch the last navigated URL from history
            last_nav = next(
                (h for h in reversed(history or []) if h["action"] == "navigate" and h.get("ok")),
                None,
            )
            if last_nav:
                url = last_nav.get("params", {}).get("url", "")
                if url:
                    return self._call("WebAccessTool", "fetch_url", url=url)
            
            return {"ok": False, "error": "No page content available"}

        elif action == "click":
            # Support index-based click (browser-use style) or legacy selector
            index = params.get("index")
            if index is not None:
                elements = (history or [{}])[-1].get("_elements", []) if history else []
                # Find element by index from last page_state stored in history
                el = next((e for e in elements if e.get("index") == int(index)), None)
                if el and el.get("href"):
                    href = el["href"]
                    # Validate URL before navigation
                    if href and (href.startswith("http://") or href.startswith("https://")):
                        # Trigger visible browser navigation
                        return self._call("BrowserAutomationTool", "navigate", url=href)
                    else:
                        # Invalid or relative href - try clicking instead
                        pass
                # Try to click by text or use browser click
                if el:
                    text = el.get("text", "").strip()
                    if text and len(text) < 100:  # Reasonable text length for XPath
                        # Use XPath contains for more reliable text matching
                        return self._call("BrowserAutomationTool", "click_element",
                                          selector=f"//*[contains(text(), '{text[:50]}')]",
                                          by="xpath")
                return {"ok": False, "error": f"Element with index {index} not found or not clickable"}
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
            # Get current page state (from history if fetched, or from browser)
            state = self._page_state(history)
            # If we have content from a fetched page, return it directly
            if state.get("content"):
                return {"ok": True, "data": {
                    "content": state["content"],
                    "title": state.get("title", ""),
                    "url": state.get("url", ""),
                    "extracting": params.get("what", ""),
                }}
            # Try browser-based structured extraction if browser is open
            bt = self._get_tool("BrowserAutomationTool")
            if bt and getattr(bt, "services", None) and getattr(bt.services, "browser", None) and bt.services.browser.driver:
                result = self._call("BrowserAutomationTool", "get_structured_content")
                if result["ok"]:
                    return result
            # No content available
            return {"ok": False, "error": "No page content available to extract"}

        return {"ok": False, "error": f"unknown action: {action}"}

    def _build_prompt(self, goal: str, page_state: Dict, history: List[Dict]) -> str:
        output_schema = _infer_output_schema(goal)
        
        # Check if last action was API-based search (no browser page)
        last_was_api_search = False
        if history and history[-1].get("action") == "search" and history[-1].get("ok"):
            # If no browser content, search was via API
            if not page_state.get("content") and not page_state.get("url"):
                last_was_api_search = True
        
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
        )
        
        if last_was_api_search:
            system += (
                "- IMPORTANT: After search returns results, use 'navigate' action with the URL from search results.\n"
                "- Do NOT use 'click' after search - there is no browser page open yet.\n"
                "- Example: If search returned URL https://example.com/article, use: {\"action\": \"navigate\", \"params\": {\"url\": \"https://example.com/article\"}}\n"
                "- Copy the exact URL from the search results shown in ACTION HISTORY.\n"
            )
        else:
            system += (
                "- After a successful navigate, use 'extract' to get structured data or 'done' if you have enough.\n"
                "- Use 'click' with the element INDEX number, not a CSS selector.\n"
            )
        
        system += (
            "- Use 'read_page' ONLY if navigate failed or page content is missing.\n"
            "- Use 'done' as soon as you have enough information to answer the goal.\n"
            "- Never repeat the same action+params twice.\n"
        )
        # Show search results in history with URLs for easy navigation
        history_str = ""
        for i, h in enumerate(history[-6:], 1):
            ok = "OK" if h.get("ok") else "FAIL"
            # Format result preview based on action type for readability
            result = h.get("result", "")
            if h["action"] == "search" and isinstance(result, dict):
                items = result.get("results") or result.get("links") or []
                # Show URLs clearly so LLM can use navigate action
                if items:
                    history_str += f"Step {i} [{ok}]: {h['action']}({h.get('params', {})})\n"
                    history_str += "  Search returned these URLs (use 'navigate' action to visit):\n"
                    for idx, r in enumerate(items[:5]):
                        url = r.get('url') or r.get('link', '')
                        title = r.get('title', '')[:80]
                        history_str += f"    {idx+1}. {title}\n       URL: {url}\n"
                    # Add explicit example
                    if items:
                        first_url = items[0].get('url') or items[0].get('link', '')
                        history_str += f"\n  Next action example: {{\"action\": \"navigate\", \"params\": {{\"url\": \"{first_url}\"}}}}\n"
                else:
                    history_str += f"Step {i} [{ok}]: {h['action']}({h.get('params', {})}) -> {str(result)[:200]}\n"
            elif h["action"] in ("navigate", "read_page") and isinstance(result, dict):
                preview = f"title={result.get('title','')} url={result.get('url','')}"
                history_str += f"Step {i} [{ok}]: {h['action']}({h.get('params', {})}) -> {preview}\n"
            elif h["action"] == "extract" and isinstance(result, dict):
                tables = result.get("tables") or []
                preview = f"{len(tables)} tables, headings={[x.get('text') for x in (result.get('headings') or [])[:3]]}"
                history_str += f"Step {i} [{ok}]: {h['action']}({h.get('params', {})}) -> {preview}\n"
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
        # Only show interactive elements if we have a live browser page
        if page_state.get("elements_str") and not page_state.get("_via"):
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
            "Write a concise answer (3-5 sentences max) that directly addresses the goal.\n"
            "Include the most important information from the data.\n"
            "If sources are available, cite them as [N] at the end.\n"
            "Be direct and specific. No meta-commentary or filler.\n"
            "Return ONLY the answer text."
        )

        try:
            return _sanitize_answer(self.llm.generate_response(prompt, [], max_tokens=800))
        except Exception:
            return _sanitize_answer(parts[0] if parts else "Could not complete the research task.")

    def run(self, goal: str, session_id: str = "", conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Run the reactive loop. Returns dict compatible with AutonomousAgent.achieve_goal()."""
        logger.info(f"[WRA] Starting reactive loop for: '{goal[:80]}'")

        history: List[Dict] = []
        collected_data: List[str] = []
        final_answer: Optional[str] = None
        _conv_history = conversation_history or []

        for step in range(self.MAX_STEPS):
            page_state = self._page_state(history)
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
                final_answer = _sanitize_answer(params.get("answer") or reason or "Task completed.")
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
                    collected_data.append({"sources": sources[:8]})
                break

            if action not in _ACTIONS:
                logger.warning(f"[WRA] Unknown action '{action}', stopping")
                break

            # Dedup guard — only block consecutive identical actions.
            action_key = f"{action}:{params}"
            if history and f"{history[-1]['action']}:{history[-1].get('params')}" == action_key:
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
                                 "_urls": [r.get("url") or r.get("link", "") for r in items if r.get("url") or r.get("link")],
                                 "_tool": result.get("_tool"),
                                 "_operation": result.get("_operation")})
            else:
                # Store the actual result data, not just the outer wrapper
                stored_result = result_data
                if action in ("navigate", "read_page") and isinstance(result_data, dict):
                    # Ensure we store the content properly for page_state detection
                    stored_result = result_data
                
                history.append({"action": action, "params": params,
                                 "ok": result["ok"],
                                 "result": stored_result,
                                 "_elements": page_state.get("elements", []),
                                 "_urls": [page_state.get("url", "")] if page_state.get("url") else [],
                                 "_tool": result.get("_tool"),
                                 "_operation": result.get("_operation")})

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
        final_answer = _sanitize_answer(final_answer)

        logger.info(f"[WRA] Done in {len(history)} steps")

        tool_history = []
        for entry in history:
            tool_name = entry.get("_tool")
            operation = entry.get("_operation")
            if not tool_name or not operation:
                continue
            tool_history.append({
                "tool": tool_name,
                "operation": operation,
                "success": bool(entry.get("ok")),
                "data": entry.get("result"),
                "error": None if entry.get("ok") else str(entry.get("result") or ""),
                "execution_time": 0.0,
            })

        # Record outcome into strategic memory so web research is learned like any other goal
        try:
            from infrastructure.persistence.file_storage.strategic_memory import get_strategic_memory
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
            "tool_history": tool_history,
            "raw_data": collected_data,   # list of raw strings/dicts for OutputAnalyzer
            "goal": goal,
        }
