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


class BrowserService:
    """Browser automation service using Selenium with Brave."""
    
    def __init__(self):
        self.driver = None
        self.brave_path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    
    def is_available(self) -> bool:
        """Check if Brave browser is available."""
        from pathlib import Path
        return Path(self.brave_path).exists()
    
    def open_browser(self):
        """Open Brave browser."""
        if self.driver:
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
        self.driver.get(url)
    
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
        return self.driver.find_element(by_map.get(by, By.CSS_SELECTOR), value)
    
    def get_page_text(self) -> str:
        """Get visible text from page."""
        if not self.driver:
            raise RuntimeError("Browser not open")
        return self.driver.find_element('tag name', 'body').text
    
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
