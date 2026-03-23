"""Service facade for generated tools - provides all necessary services."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.storage_broker import StorageBroker
from core.services.llm_service import LLMService
from core.services.http_service import HTTPService
from core.services.filesystem_service import FileSystemService
from core.services.json_service import JSONService
from core.services.shell_service import ShellService
from core.services.credential_service import CredentialService


class BrowserService:
    """Browser automation service using Selenium with Brave (Singleton)."""
    
    _instance = None
    _driver = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.brave_path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    
    @property
    def driver(self):
        return BrowserService._driver
    
    @driver.setter
    def driver(self, value):
        BrowserService._driver = value
    
    def is_available(self) -> bool:
        """Check if Brave browser is available."""
        from pathlib import Path
        return Path(self.brave_path).exists()
    
    def open_browser(self):
        """Open Brave browser."""
        if self.driver:
            try:
                if getattr(self.driver, "window_handles", None):
                    self.driver.switch_to.window(self.driver.window_handles[0])
            except Exception:
                pass
            return self.driver
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            
            options = Options()
            options.binary_location = self.brave_path
            options.add_argument('--start-maximized')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--ignore-ssl-errors')
            
            self.driver = webdriver.Chrome(options=options)
            return self.driver
        except Exception as e:
            raise RuntimeError(f"Failed to open browser: {e}")
    
    def navigate(self, url: str):
        """Navigate to URL."""
        if not self.driver:
            self.open_browser()
        try:
            if getattr(self.driver, "window_handles", None):
                self.driver.switch_to.window(self.driver.window_handles[0])
            self.driver.get(url)
        except Exception as e:
            # Session lost, reopen browser
            if 'invalid session id' in str(e).lower():
                self.driver = None
                self.open_browser()
                if getattr(self.driver, "window_handles", None):
                    self.driver.switch_to.window(self.driver.window_handles[0])
                self.driver.get(url)
            else:
                raise
    
    def find_element(self, by: str, value: str):
        """Find element on page."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        from selenium.webdriver.common.by import By
        by_map = {
            'id': By.ID,
            'name': By.NAME,
            'xpath': By.XPATH,
            'css': By.CSS_SELECTOR,
            'class': By.CLASS_NAME
        }
        try:
            return self.driver.find_element(by_map.get(by, By.CSS_SELECTOR), value)
        except Exception as e:
            if 'invalid session id' in str(e).lower():
                raise RuntimeError("Browser session lost. Please open browser again.")
            raise
    
    def get_page_text(self) -> str:
        """Get visible text from page."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        try:
            from selenium.webdriver.common.by import By
            return self.driver.find_element(By.TAG_NAME, 'body').text
        except Exception as e:
            if 'invalid session id' in str(e).lower():
                raise RuntimeError("Browser session lost. Please open browser again.")
            raise

    def get_current_url(self) -> str:
        """Get current browser URL."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        try:
            return self.driver.current_url
        except Exception as e:
            if 'invalid session id' in str(e).lower():
                raise RuntimeError("Browser session lost. Please open browser again.")
            raise

    def get_page_title(self) -> str:
        """Get current page title."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        try:
            return self.driver.title
        except Exception as e:
            if 'invalid session id' in str(e).lower():
                raise RuntimeError("Browser session lost. Please open browser again.")
            raise

    def get_page_source(self) -> str:
        """Get current page HTML source."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        try:
            return self.driver.page_source
        except Exception as e:
            if 'invalid session id' in str(e).lower():
                raise RuntimeError("Browser session lost. Please open browser again.")
            raise
    
    def find_elements(self, by: str, value: str) -> list:
        """Find all matching elements on page."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        from selenium.webdriver.common.by import By
        by_map = {'id': By.ID, 'name': By.NAME, 'xpath': By.XPATH, 'css': By.CSS_SELECTOR, 'class': By.CLASS_NAME, 'tag': By.TAG_NAME, 'text': By.LINK_TEXT, 'partial_text': By.PARTIAL_LINK_TEXT}
        try:
            return self.driver.find_elements(by_map.get(by, By.CSS_SELECTOR), value)
        except Exception as e:
            if 'invalid session id' in str(e).lower():
                raise RuntimeError("Browser session lost.")
            raise

    def click(self, by: str, value: str):
        """Click an element."""
        element = self.find_element(by, value)
        if not element:
            raise RuntimeError(f"Element not found: {by}={value}")
        try:
            element.click()
        except Exception:
            self.execute_js("arguments[0].click();", element)

    def type_text(self, by: str, value: str, text: str, clear_first: bool = True):
        """Type text into an input element."""
        element = self.find_element(by, value)
        if not element:
            raise RuntimeError(f"Element not found: {by}={value}")
        if clear_first:
            element.clear()
        element.send_keys(text)

    def wait_for_element(self, by: str, value: str, timeout: int = 10):
        """Wait for element to be present and visible."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        by_map = {'id': By.ID, 'name': By.NAME, 'xpath': By.XPATH, 'css': By.CSS_SELECTOR, 'class': By.CLASS_NAME}
        locator = (by_map.get(by, By.CSS_SELECTOR), value)
        return WebDriverWait(self.driver, timeout).until(EC.visibility_of_element_located(locator))

    def wait_for_page_load(self, timeout: int = 15):
        """Wait for document.readyState to be complete."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self.driver.execute_script("return document.readyState")
            if state == "complete":
                return True
            time.sleep(0.3)
        return False

    def scroll(self, direction: str = "down", amount: int = 500):
        """Scroll the page. direction: up/down/top/bottom."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        if direction == "top":
            self.driver.execute_script("window.scrollTo(0, 0);")
        elif direction == "bottom":
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        elif direction == "up":
            self.driver.execute_script(f"window.scrollBy(0, -{amount});")
        else:
            self.driver.execute_script(f"window.scrollBy(0, {amount});")

    def scroll_to_element(self, by: str, value: str):
        """Scroll element into view."""
        element = self.find_element(by, value)
        if element:
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)

    def execute_js(self, script: str, *args):
        """Execute JavaScript in the browser."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        return self.driver.execute_script(script, *args)

    def new_tab(self, url: str = "") -> int:
        """Open a new tab and return its index."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        self.driver.execute_script("window.open(arguments[0], '_blank');", url)
        handles = self.driver.window_handles
        self.driver.switch_to.window(handles[-1])
        return len(handles) - 1

    def switch_tab(self, index: int):
        """Switch to tab by index."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        handles = self.driver.window_handles
        if index < 0 or index >= len(handles):
            raise RuntimeError(f"Tab index {index} out of range (0-{len(handles)-1})")
        self.driver.switch_to.window(handles[index])

    def close_tab(self):
        """Close current tab and switch to previous."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        self.driver.close()
        handles = self.driver.window_handles
        if handles:
            self.driver.switch_to.window(handles[-1])
        else:
            self.driver = None

    def list_tabs(self) -> list:
        """List all open tab handles."""
        if not self.driver:
            return []
        return list(self.driver.window_handles)

    def get_cookies(self) -> list:
        """Get all cookies for current page."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        return self.driver.get_cookies()

    def set_cookie(self, name: str, value: str, domain: str = None):
        """Set a cookie."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        cookie = {"name": name, "value": value}
        if domain:
            cookie["domain"] = domain
        self.driver.add_cookie(cookie)

    def clear_cookies(self):
        """Clear all cookies."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        self.driver.delete_all_cookies()

    def hover(self, by: str, value: str):
        """Hover over an element."""
        from selenium.webdriver.common.action_chains import ActionChains
        element = self.find_element(by, value)
        if not element:
            raise RuntimeError(f"Element not found: {by}={value}")
        ActionChains(self.driver).move_to_element(element).perform()

    def select_option(self, by: str, value: str, option_text: str):
        """Select an option from a <select> dropdown by visible text."""
        from selenium.webdriver.support.ui import Select
        element = self.find_element(by, value)
        if not element:
            raise RuntimeError(f"Select element not found: {by}={value}")
        Select(element).select_by_visible_text(option_text)

    def switch_to_iframe(self, by: str, value: str):
        """Switch context into an iframe."""
        element = self.find_element(by, value)
        if not element:
            raise RuntimeError(f"Iframe not found: {by}={value}")
        self.driver.switch_to.frame(element)

    def switch_to_default(self):
        """Switch back to main document from iframe."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        self.driver.switch_to.default_content()

    def press_key(self, key: str):
        """Press a keyboard key on the active element. key: Enter, Tab, Escape, etc."""
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains
        key_map = {
            'enter': Keys.ENTER, 'tab': Keys.TAB, 'escape': Keys.ESCAPE, 'esc': Keys.ESCAPE,
            'space': Keys.SPACE, 'backspace': Keys.BACKSPACE, 'delete': Keys.DELETE,
            'up': Keys.ARROW_UP, 'down': Keys.ARROW_DOWN, 'left': Keys.ARROW_LEFT, 'right': Keys.ARROW_RIGHT,
            'home': Keys.HOME, 'end': Keys.END, 'pageup': Keys.PAGE_UP, 'pagedown': Keys.PAGE_DOWN,
            'f5': Keys.F5, 'ctrl+a': (Keys.CONTROL, 'a'), 'ctrl+c': (Keys.CONTROL, 'c'),
            'ctrl+v': (Keys.CONTROL, 'v'), 'ctrl+z': (Keys.CONTROL, 'z'),
        }
        mapped = key_map.get(key.lower(), key)
        ac = ActionChains(self.driver)
        if isinstance(mapped, tuple):
            ac.key_down(mapped[0]).send_keys(mapped[1]).key_up(mapped[0]).perform()
        else:
            ac.send_keys(mapped).perform()

    def get_element_attribute(self, by: str, value: str, attr: str) -> str:
        """Get an attribute value from an element."""
        element = self.find_element(by, value)
        if not element:
            raise RuntimeError(f"Element not found: {by}={value}")
        return element.get_attribute(attr)

    def get_element_text(self, by: str, value: str) -> str:
        """Get visible text of an element."""
        element = self.find_element(by, value)
        if not element:
            raise RuntimeError(f"Element not found: {by}={value}")
        return element.text

    def is_element_visible(self, by: str, value: str) -> bool:
        """Check if element exists and is visible."""
        try:
            element = self.find_element(by, value)
            return element is not None and element.is_displayed()
        except Exception:
            return False

    def go_back(self):
        """Navigate back in browser history."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        self.driver.back()

    def go_forward(self):
        """Navigate forward in browser history."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        self.driver.forward()

    def refresh(self):
        """Refresh current page."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        self.driver.refresh()

    def take_screenshot(self, filename: str) -> str:
        """Take screenshot and save to file."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        from pathlib import Path
        Path("output").mkdir(exist_ok=True)
        filepath = f"output/{filename}"
        self.driver.save_screenshot(filepath)
        return filepath

    def close(self):
        """Close browser."""
        if self.driver:
            self.driver.quit()
            self.driver = None


class StorageService:
    """Simple storage interface for tools - auto-scoped to tool name."""
    
    def __init__(self, tool_name: str, storage_broker: StorageBroker):
        self.tool_name = tool_name
        self.broker = storage_broker
        self.base_dir = f"data/{tool_name.lower().replace('tool', '').replace('_', '')}"
    
    def save(self, item_id: str, data: dict) -> dict:
        """Save data with automatic timestamp."""
        # Auto-wrap non-dict data for convenience
        if not isinstance(data, dict):
            if isinstance(data, (str, int, float, bool, list, bytes)):
                # Convert bytes to base64 string for JSON storage
                if isinstance(data, bytes):
                    import base64
                    data = {"value": base64.b64encode(data).decode('utf-8'), "type": "bytes"}
                else:
                    data = {"value": data}
            else:
                # Log what type we got for debugging
                import logging
                logging.error(f"StorageService.save received unsupported type: {type(data).__name__} - {data}")
                raise ValueError(f"Data must be a dictionary or simple type (str/int/float/bool/list/bytes), got {type(data).__name__}")
        
        # Convert datetime objects to ISO strings for JSON serialization
        data = self._serialize_datetimes(data)
        
        # Add timestamps if not present
        now = TimeService.now_utc_iso()
        if "created_at_utc" not in data:
            data["created_at_utc"] = now
        data["updated_at_utc"] = now
        
        # Ensure ID is in data
        if "id" not in data and item_id:
            data["id"] = item_id
        
        path = f"{self.base_dir}/{self._safe_id(item_id)}.json"
        self.broker.write_json(path, data)
        return data
    
    def get(self, item_id: str) -> dict:
        """Get data by ID."""
        path = f"{self.base_dir}/{self._safe_id(item_id)}.json"
        return self.broker.read_json(path)
    
    def list(self, limit: int = 10, sort_by: str = "created_at_utc") -> List[dict]:
        """List items with limit and sorting."""
        files = self.broker.list_files(self.base_dir, pattern="*.json")
        
        items = []
        for file_path in files[:limit]:
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                items.append(data)
            except Exception:
                continue
        
        # Sort by field if present
        if sort_by and items:
            try:
                items.sort(key=lambda x: x.get(sort_by, ""), reverse=True)
            except Exception:
                pass
        
        return items
    
    def find(self, filter_fn=None, limit: int = 100) -> List[dict]:
        """Find items matching filter function."""
        files = self.broker.list_files(self.base_dir, pattern="*.json")
        items = []
        for file_path in files:
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                if filter_fn is None or filter_fn(data):
                    items.append(data)
                    if len(items) >= limit:
                        break
            except Exception:
                continue
        return items
    
    def count(self) -> int:
        """Count total items."""
        files = self.broker.list_files(self.base_dir, pattern="*.json")
        return len(files)
    
    def update(self, item_id: str, updates: dict) -> dict:
        """Update existing item with partial data."""
        data = self.get(item_id)
        data.update(updates)
        data["updated_at_utc"] = TimeService.now_utc_iso()
        return self.save(item_id, data)
    
    def delete(self, item_id: str) -> bool:
        """Delete item by ID."""
        path = self.broker.resolve_path(f"{self.base_dir}/{self._safe_id(item_id)}.json", write=True)
        if path.exists():
            path.unlink()
            return True
        return False
    
    def exists(self, item_id: str) -> bool:
        """Check if item exists."""
        path = self.broker.resolve_path(f"{self.base_dir}/{self._safe_id(item_id)}.json", write=False)
        return path.exists()
    
    @staticmethod
    def _safe_id(item_id: str) -> str:
        """Sanitize ID for filesystem."""
        return item_id.strip().replace("/", "_").replace("\\", "_")
    
    def _serialize_datetimes(self, data):
        """Recursively convert datetime objects to ISO strings."""
        if isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, dict):
            return {k: self._serialize_datetimes(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._serialize_datetimes(item) for item in data]
        return data


class TimeService:
    """Time and timestamp utilities."""
    
    @staticmethod
    def now_utc() -> datetime:
        """Get current UTC datetime object."""
        return datetime.now(timezone.utc)
    
    @staticmethod
    def now_local() -> datetime:
        """Get current local datetime object."""
        return datetime.now()
    
    @staticmethod
    def now_utc_iso() -> str:
        """Get current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()
    
    @staticmethod
    def now_local_iso() -> str:
        """Get current local timestamp in ISO format."""
        return datetime.now().isoformat()


class IdService:
    """ID generation utilities."""
    
    @staticmethod
    def generate(prefix: str = None) -> str:
        """Generate unique ID with optional prefix."""
        unique = str(uuid.uuid4())[:8]
        if prefix:
            return f"{prefix}_{unique}"
        return unique
    
    @staticmethod
    def uuid() -> str:
        """Generate full UUID."""
        return str(uuid.uuid4())


class LoggingService:
    """Logging service for tools."""
    
    def __init__(self, tool_name: str):
        import logging
        self.logger = logging.getLogger(f"tool.{tool_name}")
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        self.logger.info(message, extra=kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.logger.warning(message, extra=kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message."""
        self.logger.error(message, extra=kwargs)
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.logger.debug(message, extra=kwargs)


class ToolServices:
    """Aggregated services provided to tools via orchestrator."""
    
    def __init__(self, tool_name: str, storage_broker: StorageBroker, llm_client=None, allowed_roots=None, orchestrator=None, registry=None):
        self.storage = StorageService(tool_name, storage_broker)
        self.time = TimeService()
        self.ids = IdService()
        self.llm = LLMService(llm_client) if llm_client else None
        self.http = HTTPService()
        self.json = JSONService()
        self.shell = ShellService()
        self.fs = FileSystemService(allowed_roots or [".", "data", "output"])
        self.logging = LoggingService(tool_name)
        self.browser = BrowserService()
        self.credentials = CredentialService(caller_tool=tool_name)
        self.orchestrator = orchestrator
        self.registry = registry
    
    def extract_key_points(self, text: str, style: str = "bullet", language: str = "en") -> str:
        """Extract key points from text using LLM."""
        if not self.llm:
            raise RuntimeError("LLM service not available")
        prompt = f"Extract key points from the following text in {style} style:\n\n{text}"
        return self.llm.generate(prompt, temperature=0.3, max_tokens=500)
    
    def sentiment_analysis(self, text: str, language: str = "en") -> dict:
        """Analyze sentiment of text using LLM."""
        if not self.llm:
            raise RuntimeError("LLM service not available")
        prompt = f"Analyze the sentiment (positive/negative/neutral) of this text:\n\n{text}"
        result = self.llm.generate(prompt, temperature=0.3, max_tokens=200)
        return {"sentiment": result, "language": language}
    
    def detect_language(self, text: str) -> str:
        """Detect language of text using LLM."""
        if not self.llm:
            return "en"
        prompt = f"Detect the language of this text (return only language code like 'en', 'es', 'fr'):\n\n{text[:200]}"
        result = self.llm.generate(prompt, temperature=0.1, max_tokens=10)
        return result.strip().lower()[:2] or "en"
    
    def generate_json_output(self, **kwargs) -> dict:
        """Generate JSON output from provided data."""
        return kwargs
    
    def call_tool(self, tool_name: str, operation: str, **parameters):
        """Call another tool via orchestrator."""
        if not self.orchestrator or not self.registry:
            raise RuntimeError("Inter-tool calls require orchestrator and registry")
        
        tool = self.registry.get_tool_by_name(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        result = self.orchestrator.execute_tool_step(
            tool=tool,
            tool_name=tool_name,
            operation=operation,
            parameters=parameters,
            context={}
        )
        
        if not result.success:
            raise RuntimeError(f"Tool call failed: {result.error}")
        
        return result.data
    
    def list_tools(self):
        """List available tools."""
        if not self.registry:
            return []
        return [tool.__class__.__name__ for tool in self.registry.tools]
    
    def has_capability(self, capability_name: str):
        """Check if capability exists."""
        if not self.registry:
            return False
        return capability_name in self.registry.get_all_capabilities()
