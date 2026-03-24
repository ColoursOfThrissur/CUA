from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel


class BrowserAutomationTool(BaseTool):
    """Full browser automation tool — click, type, wait, scroll, JS, tabs, cookies, frames, keyboard."""

    def __init__(self, orchestrator=None):
        self.description = "Full browser automation: navigation, interaction, extraction, multi-tab, cookies, JS execution."
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        self.add_capability(ToolCapability(
            name="navigate",
            description="Open the browser and navigate to a URL. Returns page title and visible text.",
            parameters=[
                Parameter("url", ParameterType.STRING, "URL to navigate to", required=True),
                Parameter("wait_for_load", ParameterType.BOOLEAN, "Wait for page to fully load before returning", required=False),
            ],
            returns="Page title, URL, and visible text.",
            safety_level=SafetyLevel.LOW, examples=[{"url": "https://example.com"}], dependencies=[],
        ), self._handle_navigate)

        self.add_capability(ToolCapability(
            name="click_element",
            description="Click an element on the page identified by CSS selector, XPath, ID, name, or class.",
            parameters=[
                Parameter("selector", ParameterType.STRING, "Element selector value", required=True),
                Parameter("by", ParameterType.STRING, "Selector type: css, xpath, id, name, class. Default: css", required=False),
                Parameter("wait_timeout", ParameterType.INTEGER, "Seconds to wait for element before clicking. Default: 5", required=False),
            ],
            returns="Click result with element info.",
            safety_level=SafetyLevel.MEDIUM, examples=[{"selector": "#submit-btn"}], dependencies=[],
        ), self._handle_click_element)

        self.add_capability(ToolCapability(
            name="fill_input",
            description="Type text into an input field, textarea, or contenteditable element.",
            parameters=[
                Parameter("selector", ParameterType.STRING, "Element selector value", required=True),
                Parameter("text", ParameterType.STRING, "Text to type", required=True),
                Parameter("by", ParameterType.STRING, "Selector type: css, xpath, id, name, class. Default: css", required=False),
                Parameter("clear_first", ParameterType.BOOLEAN, "Clear existing content before typing. Default: true", required=False),
            ],
            returns="Fill result.",
            safety_level=SafetyLevel.MEDIUM, examples=[{"selector": "#search", "text": "hello world"}], dependencies=[],
        ), self._handle_fill_input)

        self.add_capability(ToolCapability(
            name="submit_form",
            description="Fill multiple form fields and submit. Provide fields as JSON object mapping selector to value.",
            parameters=[
                Parameter("fields", ParameterType.STRING, "JSON object: {\"#field_selector\": \"value\", ...}", required=True),
                Parameter("submit_selector", ParameterType.STRING, "CSS selector of submit button. If omitted, presses Enter on last field.", required=False),
                Parameter("by", ParameterType.STRING, "Selector type for all fields: css, xpath, id, name. Default: css", required=False),
            ],
            returns="Form submission result.",
            safety_level=SafetyLevel.MEDIUM, examples=[{"fields": "{\"#email\": \"test@test.com\", \"#password\": \"pass\"}", "submit_selector": "#login-btn"}], dependencies=[],
        ), self._handle_submit_form)

        self.add_capability(ToolCapability(
            name="wait_for_element",
            description="Wait until an element appears and is visible on the page.",
            parameters=[
                Parameter("selector", ParameterType.STRING, "Element selector value", required=True),
                Parameter("by", ParameterType.STRING, "Selector type: css, xpath, id, name, class. Default: css", required=False),
                Parameter("timeout", ParameterType.INTEGER, "Max seconds to wait. Default: 10", required=False),
            ],
            returns="Element found status and text.",
            safety_level=SafetyLevel.LOW, examples=[{"selector": ".results-loaded", "timeout": 10}], dependencies=[],
        ), self._handle_wait_for_element)

        self.add_capability(ToolCapability(
            name="scroll_page",
            description="Scroll the page or scroll to a specific element.",
            parameters=[
                Parameter("direction", ParameterType.STRING, "Scroll direction: up, down, top, bottom. Default: down", required=False),
                Parameter("amount", ParameterType.INTEGER, "Pixels to scroll for up/down. Default: 500", required=False),
                Parameter("selector", ParameterType.STRING, "If provided, scroll this element into view instead.", required=False),
                Parameter("by", ParameterType.STRING, "Selector type for element scroll. Default: css", required=False),
            ],
            returns="Scroll result.",
            safety_level=SafetyLevel.LOW, examples=[{"direction": "down", "amount": 800}], dependencies=[],
        ), self._handle_scroll_page)

        self.add_capability(ToolCapability(
            name="execute_javascript",
            description="Execute arbitrary JavaScript in the browser and return the result.",
            parameters=[
                Parameter("script", ParameterType.STRING, "JavaScript code to execute", required=True),
            ],
            returns="JavaScript return value.",
            safety_level=SafetyLevel.HIGH, examples=[{"script": "return document.title;"}], dependencies=[],
        ), self._handle_execute_javascript)

        self.add_capability(ToolCapability(
            name="take_screenshot",
            description="Take a screenshot of the current browser page.",
            parameters=[
                Parameter("filename", ParameterType.STRING, "Filename to save (saved to output/ folder). Default: screenshot.png", required=False),
            ],
            returns="Saved file path.",
            safety_level=SafetyLevel.LOW, examples=[{"filename": "result.png"}], dependencies=[],
        ), self._handle_take_screenshot)

        self.add_capability(ToolCapability(
            name="manage_tabs",
            description="Manage browser tabs: open new tab, switch to tab by index, close current tab, or list all tabs.",
            parameters=[
                Parameter("action", ParameterType.STRING, "Action: new, switch, close, list", required=True),
                Parameter("url", ParameterType.STRING, "URL for new tab action", required=False),
                Parameter("index", ParameterType.INTEGER, "Tab index for switch action", required=False),
            ],
            returns="Tab operation result with current tab count.",
            safety_level=SafetyLevel.LOW, examples=[{"action": "new", "url": "https://example.com"}], dependencies=[],
        ), self._handle_manage_tabs)

        self.add_capability(ToolCapability(
            name="manage_cookies",
            description="Get, set, or clear browser cookies for the current session.",
            parameters=[
                Parameter("action", ParameterType.STRING, "Action: get, set, clear", required=True),
                Parameter("name", ParameterType.STRING, "Cookie name (for set action)", required=False),
                Parameter("value", ParameterType.STRING, "Cookie value (for set action)", required=False),
                Parameter("domain", ParameterType.STRING, "Cookie domain (for set action)", required=False),
            ],
            returns="Cookie operation result.",
            safety_level=SafetyLevel.MEDIUM, examples=[{"action": "get"}], dependencies=[],
        ), self._handle_manage_cookies)

        self.add_capability(ToolCapability(
            name="select_dropdown",
            description="Select an option from a <select> dropdown element by visible text.",
            parameters=[
                Parameter("selector", ParameterType.STRING, "Selector for the <select> element", required=True),
                Parameter("option_text", ParameterType.STRING, "Visible text of the option to select", required=True),
                Parameter("by", ParameterType.STRING, "Selector type: css, xpath, id, name. Default: css", required=False),
            ],
            returns="Selection result.",
            safety_level=SafetyLevel.MEDIUM, examples=[{"selector": "#country", "option_text": "United States"}], dependencies=[],
        ), self._handle_select_dropdown)

        self.add_capability(ToolCapability(
            name="get_element_info",
            description="Get text, attribute value, or visibility status of an element.",
            parameters=[
                Parameter("selector", ParameterType.STRING, "Element selector value", required=True),
                Parameter("info_type", ParameterType.STRING, "What to get: text, attribute, visible, all. Default: all", required=False),
                Parameter("attribute", ParameterType.STRING, "Attribute name when info_type is attribute (e.g. href, src, value)", required=False),
                Parameter("by", ParameterType.STRING, "Selector type: css, xpath, id, name, class. Default: css", required=False),
            ],
            returns="Element info dict.",
            safety_level=SafetyLevel.LOW, examples=[{"selector": "a.main-link", "info_type": "attribute", "attribute": "href"}], dependencies=[],
        ), self._handle_get_element_info)

        self.add_capability(ToolCapability(
            name="find_elements",
            description="Find all elements matching a selector and return their text and attributes.",
            parameters=[
                Parameter("selector", ParameterType.STRING, "Selector value", required=True),
                Parameter("by", ParameterType.STRING, "Selector type: css, xpath, tag, class. Default: css", required=False),
                Parameter("limit", ParameterType.INTEGER, "Max elements to return. Default: 20", required=False),
                Parameter("attribute", ParameterType.STRING, "Optional attribute to extract from each element (e.g. href)", required=False),
            ],
            returns="List of matched elements with text and optional attribute.",
            safety_level=SafetyLevel.LOW, examples=[{"selector": "a", "by": "tag", "attribute": "href", "limit": 10}], dependencies=[],
        ), self._handle_find_elements)

        self.add_capability(ToolCapability(
            name="switch_frame",
            description="Switch browser context into an iframe or back to the main document.",
            parameters=[
                Parameter("action", ParameterType.STRING, "Action: enter or exit", required=True),
                Parameter("selector", ParameterType.STRING, "Iframe selector (required for enter action)", required=False),
                Parameter("by", ParameterType.STRING, "Selector type: css, xpath, id. Default: css", required=False),
            ],
            returns="Frame switch result.",
            safety_level=SafetyLevel.LOW, examples=[{"action": "enter", "selector": "#content-frame"}], dependencies=[],
        ), self._handle_switch_frame)

        self.add_capability(ToolCapability(
            name="keyboard_action",
            description="Press a keyboard key or shortcut on the active page element.",
            parameters=[
                Parameter("key", ParameterType.STRING, "Key to press: Enter, Tab, Escape, Space, Backspace, Delete, up, down, left, right, home, end, pageup, pagedown, F5, ctrl+a, ctrl+c, ctrl+v, ctrl+z", required=True),
            ],
            returns="Key press result.",
            safety_level=SafetyLevel.MEDIUM, examples=[{"key": "Enter"}], dependencies=[],
        ), self._handle_keyboard_action)

        self.add_capability(ToolCapability(
            name="navigate_history",
            description="Navigate browser history: go back, go forward, or refresh the current page.",
            parameters=[
                Parameter("action", ParameterType.STRING, "Action: back, forward, refresh", required=True),
            ],
            returns="Navigation result with current URL.",
            safety_level=SafetyLevel.LOW, examples=[{"action": "back"}], dependencies=[],
        ), self._handle_navigate_history)

        self.add_capability(ToolCapability(
            name="extract_tables",
            description="Extract all HTML tables from the current page as structured data with headers and rows.",
            parameters=[
                Parameter("selector", ParameterType.STRING, "CSS selector to scope table search. Default: table", required=False),
                Parameter("limit", ParameterType.INTEGER, "Max tables to extract. Default: 5", required=False),
            ],
            returns="List of tables, each with headers and rows arrays.",
            safety_level=SafetyLevel.LOW, examples=[{}], dependencies=[],
        ), self._handle_extract_tables)

        self.add_capability(ToolCapability(
            name="get_structured_content",
            description="Get structured page content: tables, headings, and clean text. Better than raw text for data extraction.",
            parameters=[],
            returns="Dict with tables list, headings list, and clean text.",
            safety_level=SafetyLevel.LOW, examples=[{}], dependencies=[],
        ), self._handle_get_structured_content)

        self.add_capability(ToolCapability(
            name="extract_links",
            description="Extract all links from the current page with their text and href. Useful for navigation, sitemaps, article lists.",
            parameters=[
                Parameter("selector", ParameterType.STRING, "CSS selector to scope link search. Default: a", required=False),
                Parameter("limit", ParameterType.INTEGER, "Max links to return. Default: 50", required=False),
                Parameter("filter_text", ParameterType.STRING, "Only return links whose text contains this string (case-insensitive)", required=False),
            ],
            returns="List of {text, href, title} dicts.",
            safety_level=SafetyLevel.LOW, examples=[{}], dependencies=[],
        ), self._handle_extract_links)

        self.add_capability(ToolCapability(
            name="extract_lists",
            description="Extract all bullet/numbered lists (ul/ol) from the page as structured arrays. Useful for rankings, features, summaries.",
            parameters=[
                Parameter("selector", ParameterType.STRING, "CSS selector to scope list search. Default: ul,ol", required=False),
                Parameter("limit", ParameterType.INTEGER, "Max lists to return. Default: 10", required=False),
            ],
            returns="List of {items, ordered} dicts.",
            safety_level=SafetyLevel.LOW, examples=[{}], dependencies=[],
        ), self._handle_extract_lists)

        self.add_capability(ToolCapability(
            name="extract_meta",
            description="Extract page metadata: title, description, Open Graph tags, canonical URL, keywords. Useful for page summaries.",
            parameters=[],
            returns="Dict of meta fields.",
            safety_level=SafetyLevel.LOW, examples=[{}], dependencies=[],
        ), self._handle_extract_meta)

        self.add_capability(ToolCapability(
            name="extract_article",
            description="Extract the main article/content body from the page — strips nav, ads, footers. Returns clean readable text and any inline data.",
            parameters=[],
            returns="Dict with title, body text, publish date if found, and author if found.",
            safety_level=SafetyLevel.LOW, examples=[{}], dependencies=[],
        ), self._handle_extract_article)

        self.add_capability(ToolCapability(
            name="get_interactive_elements",
            description="Get a numbered list of all interactive elements on the page (links, buttons, inputs, selects). LLM can reference by index for click/fill actions.",
            parameters=[
                Parameter("limit", ParameterType.INTEGER, "Max elements to return. Default: 50", required=False),
            ],
            returns="List of {index, tag, text, type, href, placeholder} dicts plus a formatted string for LLM prompt injection.",
            safety_level=SafetyLevel.LOW, examples=[{}], dependencies=[],
        ), self._handle_get_interactive_elements)

        self.add_capability(ToolCapability(
            name="hover_element",
            description="Hover the mouse over an element to trigger hover states or tooltips.",
            parameters=[
                Parameter("selector", ParameterType.STRING, "Element selector value", required=True),
                Parameter("by", ParameterType.STRING, "Selector type: css, xpath, id, name, class. Default: css", required=False),
            ],
            returns="Hover result.",
            safety_level=SafetyLevel.LOW, examples=[{"selector": ".dropdown-trigger"}], dependencies=[],
        ), self._handle_hover_element)

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_navigate(self, **kwargs) -> dict:
        url = kwargs.get("url")
        if not url:
            raise ValueError("Missing required parameter: url")
        wait = kwargs.get("wait_for_load", True)
        try:
            self.services.browser.open_browser()
            self.services.browser.navigate(url)
            if wait:
                self.services.browser.wait_for_page_load(timeout=15)
            title = self.services.browser.get_page_title()
            current_url = self.services.browser.get_current_url()
            text = self.services.browser.get_page_text()
            return {"success": True, "url": current_url, "title": title, "content": text[:8000]}
        except Exception as e:
            self.services.logging.error(f"navigate failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_click_element(self, **kwargs) -> dict:
        selector = kwargs.get("selector")
        if not selector:
            raise ValueError("Missing required parameter: selector")
        by = kwargs.get("by", "css")
        if by == "class" and selector.startswith("."):
            selector = selector[1:]
        elif by == "id" and selector.startswith("#"):
            selector = selector[1:]
        timeout = int(kwargs.get("wait_timeout") or 5)
        try:
            if timeout > 0:
                self.services.browser.wait_for_element(by, selector, timeout=timeout)
            self.services.browser.click(by, selector)
            return {"success": True, "selector": selector, "by": by}
        except Exception as e:
            self.services.logging.error(f"click_element failed: {e}")
            return {"success": False, "selector": selector, "error": str(e)}

    def _handle_fill_input(self, **kwargs) -> dict:
        selector = kwargs.get("selector")
        text = kwargs.get("text")
        if not selector or text is None:
            raise ValueError("Missing required parameters: selector, text")
        by = kwargs.get("by", "css")
        if by == "class" and selector.startswith("."):
            selector = selector[1:]
        elif by == "id" and selector.startswith("#"):
            selector = selector[1:]
        clear_first = kwargs.get("clear_first", True)
        try:
            self.services.browser.type_text(by, selector, str(text), clear_first=bool(clear_first))
            return {"success": True, "selector": selector, "text": str(text)}
        except Exception as e:
            self.services.logging.error(f"fill_input failed: {e}")
            return {"success": False, "selector": selector, "error": str(e)}

    def _handle_submit_form(self, **kwargs) -> dict:
        fields_json = kwargs.get("fields", "{}")
        submit_selector = kwargs.get("submit_selector")
        by = kwargs.get("by", "css")
        try:
            fields = self.services.json.parse(fields_json) if isinstance(fields_json, str) else fields_json
        except Exception as e:
            return {"success": False, "error": f"Invalid fields JSON: {e}"}
        try:
            last_element = None
            for sel, val in fields.items():
                self.services.browser.type_text(by, sel, str(val), clear_first=True)
                last_element = (by, sel)
            if submit_selector:
                self.services.browser.click(by, submit_selector)
            elif last_element:
                from selenium.webdriver.common.keys import Keys
                elem = self.services.browser.find_element(last_element[0], last_element[1])
                if elem:
                    elem.send_keys(Keys.ENTER)
            self.services.browser.wait_for_page_load(timeout=10)
            return {"success": True, "fields_filled": len(fields), "submitted": True}
        except Exception as e:
            self.services.logging.error(f"submit_form failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_wait_for_element(self, **kwargs) -> dict:
        selector = kwargs.get("selector")
        if not selector:
            raise ValueError("Missing required parameter: selector")
        by = kwargs.get("by", "css")
        if by == "class" and selector.startswith("."):
            selector = selector[1:]
        elif by == "id" and selector.startswith("#"):
            selector = selector[1:]
        timeout = int(kwargs.get("timeout") or 10)
        try:
            element = self.services.browser.wait_for_element(by, selector, timeout=timeout)
            text = element.text if element else ""
            return {"success": True, "found": True, "selector": selector, "text": text}
        except Exception as e:
            # Soft failure — element not found is informational, not a hard error
            # Allows agent to detect login walls or missing elements and report to user
            return {"success": True, "found": False, "selector": selector, "text": "", "note": str(e)}

    def _handle_scroll_page(self, **kwargs) -> dict:
        selector = kwargs.get("selector")
        by = kwargs.get("by", "css")
        try:
            if selector:
                self.services.browser.scroll_to_element(by, selector)
                return {"success": True, "action": "scroll_to_element", "selector": selector}
            direction = kwargs.get("direction", "down")
            amount = int(kwargs.get("amount") or 500)
            self.services.browser.scroll(direction=direction, amount=amount)
            return {"success": True, "action": "scroll", "direction": direction, "amount": amount}
        except Exception as e:
            self.services.logging.error(f"scroll_page failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_execute_javascript(self, **kwargs) -> dict:
        script = kwargs.get("script")
        if not script:
            raise ValueError("Missing required parameter: script")
        try:
            result = self.services.browser.execute_js(script)
            # None is valid for void JS (e.g. click(), scroll()) — use empty string so verifier doesn't reject
            return {"success": True, "result": result if result is not None else ""}
        except Exception as e:
            self.services.logging.error(f"execute_javascript failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_take_screenshot(self, **kwargs) -> dict:
        filename = kwargs.get("filename") or "screenshot.png"
        try:
            filepath = self.services.browser.take_screenshot(filename)
            # Also encode as base64 so the UI can render it directly
            import base64, os
            b64 = None
            if filepath and os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
            return {"success": True, "filepath": filepath, "screenshot_b64": b64}
        except Exception as e:
            self.services.logging.error(f"take_screenshot failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_manage_tabs(self, **kwargs) -> dict:
        action = kwargs.get("action", "").lower()
        try:
            if action == "new":
                url = kwargs.get("url", "")
                index = self.services.browser.new_tab(url)
                return {"success": True, "action": "new", "tab_index": index, "tab_count": len(self.services.browser.list_tabs())}
            elif action == "switch":
                index = int(kwargs.get("index") or 0)
                self.services.browser.switch_tab(index)
                return {"success": True, "action": "switch", "tab_index": index}
            elif action == "close":
                self.services.browser.close_tab()
                return {"success": True, "action": "close", "tab_count": len(self.services.browser.list_tabs())}
            elif action == "list":
                tabs = self.services.browser.list_tabs()
                return {"success": True, "action": "list", "tab_count": len(tabs), "tabs": tabs}
            else:
                return {"success": False, "error": f"Unknown action: {action}. Use: new, switch, close, list"}
        except Exception as e:
            self.services.logging.error(f"manage_tabs failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_manage_cookies(self, **kwargs) -> dict:
        action = kwargs.get("action", "").lower()
        try:
            if action == "get":
                cookies = self.services.browser.get_cookies()
                return {"success": True, "action": "get", "count": len(cookies), "cookies": cookies}
            elif action == "set":
                name = kwargs.get("name")
                value = kwargs.get("value")
                if not name or value is None:
                    return {"success": False, "error": "name and value required for set action"}
                self.services.browser.set_cookie(name, str(value), domain=kwargs.get("domain"))
                return {"success": True, "action": "set", "name": name}
            elif action == "clear":
                self.services.browser.clear_cookies()
                return {"success": True, "action": "clear"}
            else:
                return {"success": False, "error": f"Unknown action: {action}. Use: get, set, clear"}
        except Exception as e:
            self.services.logging.error(f"manage_cookies failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_select_dropdown(self, **kwargs) -> dict:
        selector = kwargs.get("selector")
        option_text = kwargs.get("option_text")
        if not selector or not option_text:
            raise ValueError("Missing required parameters: selector, option_text")
        by = kwargs.get("by", "css")
        if by == "class" and selector.startswith("."):
            selector = selector[1:]
        elif by == "id" and selector.startswith("#"):
            selector = selector[1:]
        try:
            self.services.browser.select_option(by, selector, option_text)
            return {"success": True, "selector": selector, "selected": option_text}
        except Exception as e:
            self.services.logging.error(f"select_dropdown failed: {e}")
            return {"success": False, "selector": selector, "error": str(e)}

    def _handle_get_element_info(self, **kwargs) -> dict:
        selector = kwargs.get("selector")
        if not selector:
            raise ValueError("Missing required parameter: selector")
        by = kwargs.get("by", "css")
        # Strip leading dot/hash when by=class or by=id (LLM often passes CSS syntax)
        if by == "class" and selector.startswith("."):
            selector = selector[1:]
        elif by == "id" and selector.startswith("#"):
            selector = selector[1:]
        info_type = kwargs.get("info_type", "all")
        attribute = kwargs.get("attribute")
        try:
            result = {"success": True, "selector": selector}
            if info_type in ("text", "all"):
                result["text"] = self.services.browser.get_element_text(by, selector)
            if info_type in ("visible", "all"):
                result["visible"] = self.services.browser.is_element_visible(by, selector)
            if info_type == "attribute" or (info_type == "all" and attribute):
                if not attribute:
                    return {"success": False, "error": "attribute name required for info_type=attribute"}
                result["attribute"] = attribute
                result["value"] = self.services.browser.get_element_attribute(by, selector, attribute)
            return result
        except Exception as e:
            self.services.logging.error(f"get_element_info failed: {e}")
            return {"success": False, "selector": selector, "error": str(e)}

    def _handle_find_elements(self, **kwargs) -> dict:
        selector = kwargs.get("selector")
        if not selector:
            raise ValueError("Missing required parameter: selector")
        by = kwargs.get("by", "css")
        if by == "class" and selector.startswith("."):
            selector = selector[1:]
        elif by == "id" and selector.startswith("#"):
            selector = selector[1:]
        limit = int(kwargs.get("limit") or 20)
        attribute = kwargs.get("attribute")
        try:
            elements = self.services.browser.find_elements(by, selector)[:limit]
            items = []
            for el in elements:
                item = {"text": el.text}
                if attribute:
                    item[attribute] = el.get_attribute(attribute)
                items.append(item)
            return {"success": True, "selector": selector, "count": len(items), "elements": items}
        except Exception as e:
            self.services.logging.error(f"find_elements failed: {e}")
            return {"success": False, "selector": selector, "error": str(e)}

    def _handle_switch_frame(self, **kwargs) -> dict:
        action = kwargs.get("action", "").lower()
        try:
            if action == "enter":
                selector = kwargs.get("selector")
                if not selector:
                    return {"success": False, "error": "selector required for enter action"}
                by = kwargs.get("by", "css")
                if by == "class" and selector.startswith("."):
                    selector = selector[1:]
                elif by == "id" and selector.startswith("#"):
                    selector = selector[1:]
                self.services.browser.switch_to_iframe(by, selector)
                return {"success": True, "action": "enter", "selector": selector}
            elif action == "exit":
                self.services.browser.switch_to_default()
                return {"success": True, "action": "exit"}
            else:
                return {"success": False, "error": f"Unknown action: {action}. Use: enter, exit"}
        except Exception as e:
            self.services.logging.error(f"switch_frame failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_keyboard_action(self, **kwargs) -> dict:
        key = kwargs.get("key")
        if not key:
            raise ValueError("Missing required parameter: key")
        try:
            self.services.browser.press_key(key)
            return {"success": True, "key": key}
        except Exception as e:
            self.services.logging.error(f"keyboard_action failed: {e}")
            return {"success": False, "key": key, "error": str(e)}

    def _handle_navigate_history(self, **kwargs) -> dict:
        action = kwargs.get("action", "").lower()
        try:
            if action == "back":
                self.services.browser.go_back()
            elif action == "forward":
                self.services.browser.go_forward()
            elif action == "refresh":
                self.services.browser.refresh()
            else:
                return {"success": False, "error": f"Unknown action: {action}. Use: back, forward, refresh"}
            self.services.browser.wait_for_page_load(timeout=10)
            return {"success": True, "action": action, "url": self.services.browser.get_current_url()}
        except Exception as e:
            self.services.logging.error(f"navigate_history failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_extract_tables(self, **kwargs) -> dict:
        selector = kwargs.get("selector", "table")
        limit = int(kwargs.get("limit") or 5)
        try:
            script = """
            var tables = document.querySelectorAll(arguments[0]);
            var result = [];
            for (var t = 0; t < Math.min(tables.length, arguments[1]); t++) {
                var table = tables[t];
                var headers = [];
                var rows = [];
                var ths = table.querySelectorAll('thead th, thead td, tr:first-child th');
                if (ths.length === 0) ths = table.querySelectorAll('tr:first-child td');
                for (var h = 0; h < ths.length; h++) headers.push(ths[h].innerText.trim());
                var trs = table.querySelectorAll('tbody tr, tr');
                var start = (ths.length > 0 && table.querySelectorAll('thead').length === 0) ? 1 : 0;
                for (var r = start; r < trs.length; r++) {
                    var cells = trs[r].querySelectorAll('td, th');
                    var row = [];
                    for (var c = 0; c < cells.length; c++) row.push(cells[c].innerText.trim());
                    if (row.some(function(v){ return v !== ''; })) rows.push(row);
                }
                if (rows.length > 0) result.push({headers: headers, rows: rows, caption: (table.caption ? table.caption.innerText.trim() : '')});
            }
            return result;
            """
            raw = self.services.browser.execute_js(script, selector, limit)
            tables = []
            for t in (raw or []):
                headers = t.get("headers") or []
                rows = t.get("rows") or []
                # Convert rows to list-of-dicts if headers available
                if headers:
                    dicts = [dict(zip(headers, row + [""] * max(0, len(headers) - len(row)))) for row in rows]
                else:
                    dicts = [{str(i): v for i, v in enumerate(row)} for row in rows]
                tables.append({"caption": t.get("caption", ""), "headers": headers, "rows": dicts})
            return {"success": True, "table_count": len(tables), "tables": tables}
        except Exception as e:
            self.services.logging.error(f"extract_tables failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_get_structured_content(self, **kwargs) -> dict:
        try:
            script = """
            var result = {headings: [], tables: [], text: ''};
            var hs = document.querySelectorAll('h1,h2,h3,h4');
            for (var i = 0; i < Math.min(hs.length, 20); i++) {
                var t = hs[i].innerText.trim();
                if (t) result.headings.push({level: hs[i].tagName, text: t});
            }
            var tables = document.querySelectorAll('table');
            for (var t = 0; t < Math.min(tables.length, 5); t++) {
                var table = tables[t];
                var headers = [];
                var rows = [];
                var ths = table.querySelectorAll('thead th, thead td, tr:first-child th');
                if (ths.length === 0) ths = table.querySelectorAll('tr:first-child td');
                for (var h = 0; h < ths.length; h++) headers.push(ths[h].innerText.trim());
                var trs = table.querySelectorAll('tbody tr, tr');
                var start = (ths.length > 0 && table.querySelectorAll('thead').length === 0) ? 1 : 0;
                for (var r = start; r < Math.min(trs.length, 50); r++) {
                    var cells = trs[r].querySelectorAll('td, th');
                    var row = [];
                    for (var c = 0; c < cells.length; c++) row.push(cells[c].innerText.trim());
                    if (row.some(function(v){ return v !== ''; })) rows.push(row);
                }
                if (rows.length > 0) result.tables.push({headers: headers, rows: rows, caption: (table.caption ? table.caption.innerText.trim() : '')});
            }
            result.text = document.body.innerText.slice(0, 3000);
            return result;
            """
            raw = self.services.browser.execute_js(script)
            tables = []
            for t in (raw.get("tables") or []):
                headers = t.get("headers") or []
                rows = t.get("rows") or []
                dicts = [dict(zip(headers, row + [""] * max(0, len(headers) - len(row)))) for row in rows] if headers else [{str(i): v for i, v in enumerate(row)} for row in rows]
                tables.append({"caption": t.get("caption", ""), "headers": headers, "rows": dicts})
            return {
                "success": True,
                "url": self.services.browser.get_current_url(),
                "title": self.services.browser.get_page_title(),
                "headings": raw.get("headings", []),
                "tables": tables,
                "text": raw.get("text", ""),
            }
        except Exception as e:
            self.services.logging.error(f"get_structured_content failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_extract_links(self, **kwargs) -> dict:
        selector = kwargs.get("selector", "a")
        limit = int(kwargs.get("limit") or 50)
        filter_text = (kwargs.get("filter_text") or "").lower()
        try:
            script = """
            var els = document.querySelectorAll(arguments[0]);
            var result = [];
            for (var i = 0; i < els.length && result.length < arguments[1]; i++) {
                var el = els[i];
                var href = el.href || el.getAttribute('href') || '';
                var text = el.innerText.trim() || el.getAttribute('aria-label') || '';
                if (!href || href.startsWith('javascript:') || href === '#') continue;
                if (arguments[2] && text.toLowerCase().indexOf(arguments[2]) === -1) continue;
                result.push({text: text, href: href, title: el.getAttribute('title') || ''});
            }
            return result;
            """
            links = self.services.browser.execute_js(script, selector, limit, filter_text) or []
            return {"success": True, "count": len(links), "links": links}
        except Exception as e:
            self.services.logging.error(f"extract_links failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_extract_lists(self, **kwargs) -> dict:
        selector = kwargs.get("selector", "ul,ol")
        limit = int(kwargs.get("limit") or 10)
        try:
            script = """
            var els = document.querySelectorAll(arguments[0]);
            var result = [];
            for (var i = 0; i < Math.min(els.length, arguments[1]); i++) {
                var el = els[i];
                var items = [];
                var lis = el.querySelectorAll(':scope > li');
                for (var j = 0; j < lis.length; j++) {
                    var t = lis[j].innerText.trim();
                    if (t) items.push(t);
                }
                if (items.length > 0) result.push({items: items, ordered: el.tagName === 'OL'});
            }
            return result;
            """
            lists = self.services.browser.execute_js(script, selector, limit) or []
            return {"success": True, "count": len(lists), "lists": lists}
        except Exception as e:
            self.services.logging.error(f"extract_lists failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_extract_meta(self, **kwargs) -> dict:
        try:
            script = """
            var m = {};
            m.title = document.title || '';
            m.url = window.location.href;
            var desc = document.querySelector('meta[name="description"]');
            m.description = desc ? desc.getAttribute('content') : '';
            var kw = document.querySelector('meta[name="keywords"]');
            m.keywords = kw ? kw.getAttribute('content') : '';
            var canon = document.querySelector('link[rel="canonical"]');
            m.canonical = canon ? canon.getAttribute('href') : '';
            var ogTitle = document.querySelector('meta[property="og:title"]');
            m.og_title = ogTitle ? ogTitle.getAttribute('content') : '';
            var ogDesc = document.querySelector('meta[property="og:description"]');
            m.og_description = ogDesc ? ogDesc.getAttribute('content') : '';
            var ogImage = document.querySelector('meta[property="og:image"]');
            m.og_image = ogImage ? ogImage.getAttribute('content') : '';
            var ogType = document.querySelector('meta[property="og:type"]');
            m.og_type = ogType ? ogType.getAttribute('content') : '';
            return m;
            """
            meta = self.services.browser.execute_js(script) or {}
            return {"success": True, **meta}
        except Exception as e:
            self.services.logging.error(f"extract_meta failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_extract_article(self, **kwargs) -> dict:
        try:
            script = """
            var result = {title: '', body: '', author: '', date: ''};
            result.title = document.title || '';
            // Try common article selectors
            var bodyEl = document.querySelector('article, [role="main"], main, .article-body, .post-content, .entry-content, #content, .content');
            if (!bodyEl) bodyEl = document.body;
            // Clone and strip noise
            var clone = bodyEl.cloneNode(true);
            var noise = clone.querySelectorAll('nav, header, footer, aside, .ad, .ads, .advertisement, .sidebar, .menu, .nav, script, style, iframe, .cookie, .popup, .modal, .share, .social');
            for (var i = 0; i < noise.length; i++) noise[i].remove();
            result.body = clone.innerText.trim().slice(0, 8000);
            // Author
            var authorEl = document.querySelector('[rel="author"], .author, .byline, [itemprop="author"]');
            result.author = authorEl ? authorEl.innerText.trim() : '';
            // Date
            var dateEl = document.querySelector('time, [itemprop="datePublished"], .date, .published, .post-date');
            result.date = dateEl ? (dateEl.getAttribute('datetime') || dateEl.innerText.trim()) : '';
            return result;
            """
            article = self.services.browser.execute_js(script) or {}
            return {"success": True, **article}
        except Exception as e:
            self.services.logging.error(f"extract_article failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_get_interactive_elements(self, **kwargs) -> dict:
        limit = int(kwargs.get("limit") or 50)
        try:
            script = """
            var limit = arguments[0];
            var seen = new Set();
            var result = [];
            var selectors = 'a[href], button, input, select, textarea, [role="button"], [role="link"], [onclick], [tabindex]';
            var els = document.querySelectorAll(selectors);
            for (var i = 0; i < els.length && result.length < limit; i++) {
                var el = els[i];
                if (!el.offsetParent && el.tagName !== 'INPUT') continue;
                var tag = el.tagName.toLowerCase();
                var text = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim().slice(0, 80);
                var href = el.getAttribute('href') || '';
                var placeholder = el.getAttribute('placeholder') || '';
                var type = el.getAttribute('type') || '';
                var key = tag + '|' + text + '|' + href;
                if (seen.has(key) || (!text && !href && !placeholder)) continue;
                seen.add(key);
                result.push({index: result.length + 1, tag: tag, text: text, type: type, href: href, placeholder: placeholder});
            }
            return result;
            """
            elements = self.services.browser.execute_js(script, limit) or []
            # Build a compact string for LLM prompt injection
            lines = []
            for el in elements:
                label = el.get("text") or el.get("placeholder") or el.get("href", "")[:40]
                extra = f" [{el['type']}]" if el.get("type") else ""
                extra += f" -> {el['href'][:60]}" if el.get("href") else ""
                lines.append(f"[{el['index']}] <{el['tag']}>{extra} \"{label}\"")
            return {
                "success": True,
                "count": len(elements),
                "elements": elements,
                "formatted": "\n".join(lines),
            }
        except Exception as e:
            self.services.logging.error(f"get_interactive_elements failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_hover_element(self, **kwargs) -> dict:
        selector = kwargs.get("selector")
        if not selector:
            raise ValueError("Missing required parameter: selector")
        by = kwargs.get("by", "css")
        if by == "class" and selector.startswith("."):
            selector = selector[1:]
        elif by == "id" and selector.startswith("#"):
            selector = selector[1:]
        try:
            self.services.browser.hover(by, selector)
            return {"success": True, "selector": selector}
        except Exception as e:
            self.services.logging.error(f"hover_element failed: {e}")
            return {"success": False, "selector": selector, "error": str(e)}

    def execute(self, operation: str, **kwargs):
        handlers = {
            "navigate": self._handle_navigate,
            "click_element": self._handle_click_element,
            "fill_input": self._handle_fill_input,
            "submit_form": self._handle_submit_form,
            "wait_for_element": self._handle_wait_for_element,
            "scroll_page": self._handle_scroll_page,
            "execute_javascript": self._handle_execute_javascript,
            "take_screenshot": self._handle_take_screenshot,
            "manage_tabs": self._handle_manage_tabs,
            "manage_cookies": self._handle_manage_cookies,
            "select_dropdown": self._handle_select_dropdown,
            "get_element_info": self._handle_get_element_info,
            "find_elements": self._handle_find_elements,
            "switch_frame": self._handle_switch_frame,
            "keyboard_action": self._handle_keyboard_action,
            "navigate_history": self._handle_navigate_history,
            "get_interactive_elements": self._handle_get_interactive_elements,
            "hover_element": self._handle_hover_element,
            "extract_tables": self._handle_extract_tables,
            "get_structured_content": self._handle_get_structured_content,
            "extract_links": self._handle_extract_links,
            "extract_lists": self._handle_extract_lists,
            "extract_meta": self._handle_extract_meta,
            "extract_article": self._handle_extract_article,
            # legacy aliases
            "open_and_navigate": self._handle_navigate,
            "get_page_content": lambda **kw: {"success": True, "content": self.services.browser.get_page_text()},
            "find_element": self._handle_get_element_info,
        }
        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")
        return handler(**kwargs)
