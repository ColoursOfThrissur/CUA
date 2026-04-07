"""
SystemControlTool - Window and process management with safety enforcement.

Fixes:
- Protected process list (prevents killing critical system processes)
- Fuzzy window matching
- Safety enforcement for kill operations
- Structured error responses
"""
import logging
from typing import Dict, List, Any, Optional

from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.computer_use.error_taxonomy import classify_desktop_failure

logger = logging.getLogger(__name__)

# Protected processes that cannot be killed
PROTECTED_PROCESSES = [
    "system", "init", "systemd", "explorer.exe", "finder", "winlogon.exe",
    "csrss.exe", "services.exe", "lsass.exe", "svchost.exe", "dwm.exe"
]


class SystemControlTool(BaseTool):
    """Window and process management with safety enforcement."""

    def __init__(self, orchestrator=None):
        self.description = "Window/process management with safety checks and fuzzy matching"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        self.orchestrator = orchestrator
        super().__init__()

    def register_capabilities(self):
        """Register system control capabilities."""
        
        # ── Window Management ──────────────────────────────────────────────
        self.add_capability(ToolCapability(
            name="list_windows",
            description="List all open windows with details.",
            parameters=[
                Parameter("filter_title", ParameterType.STRING, "Filter by title substring", required=False),
            ],
            returns="dict with success, count, windows list",
            safety_level=SafetyLevel.LOW,
            examples=[{}, {"filter_title": "chrome"}],
            dependencies=["pygetwindow"]
        ), self._handle_list_windows)

        self.add_capability(ToolCapability(
            name="focus_window",
            description="Focus window by title with fuzzy matching.",
            parameters=[
                Parameter("title", ParameterType.STRING, "Window title or partial match", required=True),
            ],
            returns="dict with success, focused_window",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"title": "Notepad"}, {"title": "Chrome"}],
            dependencies=["pygetwindow"]
        ), self._handle_focus_window)

        self.add_capability(ToolCapability(
            name="smart_focus_window",
            description="LLM-guided fuzzy window matching and focus.",
            parameters=[
                Parameter("description", ParameterType.STRING, "Window description (e.g., 'my browser', 'text editor')", required=True),
            ],
            returns="dict with success, matched_window, all_windows",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"description": "my browser"}, {"description": "the file manager"}],
            dependencies=["pygetwindow"]
        ), self._handle_smart_focus_window)

        self.add_capability(ToolCapability(
            name="get_active_window",
            description="Get currently active window info.",
            parameters=[],
            returns="dict with success, title, position, size",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["pygetwindow"]
        ), self._handle_get_active_window)

        self.add_capability(ToolCapability(
            name="resize_window",
            description="Resize and/or move window.",
            parameters=[
                Parameter("title", ParameterType.STRING, "Window title", required=True),
                Parameter("width", ParameterType.INTEGER, "New width", required=False),
                Parameter("height", ParameterType.INTEGER, "New height", required=False),
                Parameter("x", ParameterType.INTEGER, "New X position", required=False),
                Parameter("y", ParameterType.INTEGER, "New Y position", required=False),
            ],
            returns="dict with success, window info",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{"title": "Notepad", "width": 800, "height": 600}],
            dependencies=["pygetwindow"]
        ), self._handle_resize_window)

        self.add_capability(ToolCapability(
            name="minimize_window",
            description="Minimize window by title.",
            parameters=[
                Parameter("title", ParameterType.STRING, "Window title", required=True),
            ],
            returns="dict with success",
            safety_level=SafetyLevel.LOW,
            examples=[{"title": "Notepad"}],
            dependencies=["pygetwindow"]
        ), self._handle_minimize_window)

        self.add_capability(ToolCapability(
            name="maximize_window",
            description="Maximize window by title.",
            parameters=[
                Parameter("title", ParameterType.STRING, "Window title", required=True),
            ],
            returns="dict with success",
            safety_level=SafetyLevel.LOW,
            examples=[{"title": "Notepad"}],
            dependencies=["pygetwindow"]
        ), self._handle_maximize_window)

        # ── Process Management ─────────────────────────────────────────────
        self.add_capability(ToolCapability(
            name="list_processes",
            description="List running processes with CPU and memory usage.",
            parameters=[
                Parameter("filter_name", ParameterType.STRING, "Filter by process name", required=False),
                Parameter("limit", ParameterType.INTEGER, "Max processes to return. Default: 50", required=False),
            ],
            returns="dict with success, count, processes list",
            safety_level=SafetyLevel.LOW,
            examples=[{}, {"filter_name": "python", "limit": 10}],
            dependencies=["psutil"]
        ), self._handle_list_processes)

        self.add_capability(ToolCapability(
            name="launch_application",
            description="Launch application by name or path. Waits for window to appear.",
            parameters=[
                Parameter("name", ParameterType.STRING, "Application name or path", required=True),
                Parameter("args", ParameterType.LIST, "Command-line arguments", required=False),
                Parameter("wait_seconds", ParameterType.INTEGER, "Seconds to wait for app to open. Default: 3", required=False),
            ],
            returns="dict with success, pid, name, waited",
            safety_level=SafetyLevel.HIGH,
            examples=[{"name": "notepad"}, {"name": "steam", "wait_seconds": 5}],
            dependencies=["psutil"]
        ), self._handle_launch_application)

        self.add_capability(ToolCapability(
            name="kill_process",
            description="Terminate process with safety checks. Protected processes are blocked.",
            parameters=[
                Parameter("pid", ParameterType.INTEGER, "Process ID", required=False),
                Parameter("name", ParameterType.STRING, "Process name", required=False),
            ],
            returns="dict with success, killed_pid",
            safety_level=SafetyLevel.HIGH,
            examples=[{"pid": 1234}, {"name": "notepad.exe"}],
            dependencies=["psutil"]
        ), self._handle_kill_process)

    # ── Window Management Handlers ─────────────────────────────────────────

    def _handle_list_windows(self, **kwargs) -> dict:
        """List all open windows."""
        try:
            import pygetwindow as gw
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            filter_title = kwargs.get("filter_title", "").lower()
            
            all_windows = gw.getAllWindows()
            windows = []
            
            for win in all_windows:
                if not win.title:
                    continue
                
                if filter_title and filter_title not in win.title.lower():
                    continue
                
                windows.append({
                    "title": win.title,
                    "is_active": win.isActive,
                    "is_minimized": win.isMinimized,
                    "is_maximized": win.isMaximized,
                    "position": {"x": win.left, "y": win.top},
                    "size": {"width": win.width, "height": win.height},
                })
            
            return {
                "success": True,
                "count": len(windows),
                "windows": windows,
            }

        except Exception as e:
            logger.error(f"list_windows failed: {e}")
            return self._error_response("LIST_FAILED", str(e))

    def _handle_focus_window(self, **kwargs) -> dict:
        """Focus window with fuzzy matching."""
        try:
            import pygetwindow as gw
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            title = kwargs.get("title")
            if not title:
                return self._error_response("INVALID_PARAMETER", "title parameter required")
            
            # Fuzzy match
            all_windows = gw.getAllWindows()
            matching = self._fuzzy_match_windows(title, all_windows)
            
            if not matching:
                return self._error_response("WINDOW_NOT_FOUND", 
                    f"No window found matching: {title}", recoverable=True)
            
            # Focus best match
            window = matching[0]
            try:
                if getattr(window, "isMinimized", False):
                    window.restore()
                window.activate()
            except Exception as focus_error:
                # Windows can report activation glitches even when the target is already usable.
                message = str(focus_error)
                if "already unlocked" in message.lower() or "error code from windows: 158" in message.lower():
                    try:
                        active = gw.getActiveWindow()
                        if active and active.title == window.title:
                            self._invalidate_screen_cache()
                            return {
                                "success": True,
                                "focused_window": {
                                    "title": window.title,
                                    "position": {"x": window.left, "y": window.top},
                                    "size": {"width": window.width, "height": window.height},
                                },
                                "method": "already_active",
                            }
                    except Exception:
                        pass
                raise
            
            self._invalidate_screen_cache()
            return {
                "success": True,
                "focused_window": {
                    "title": window.title,
                    "position": {"x": window.left, "y": window.top},
                    "size": {"width": window.width, "height": window.height},
                },
            }

        except Exception as e:
            logger.error(f"focus_window failed: {e}")
            return self._error_response("FOCUS_FAILED", str(e), recoverable=True)

    def _handle_smart_focus_window(self, **kwargs) -> dict:
        """LLM-guided window matching."""
        if not self.services or not self.services.llm:
            return self._error_response("LLM_REQUIRED", "LLM service required for smart focus")

        try:
            import pygetwindow as gw
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            description = kwargs.get("description")
            if not description:
                return self._error_response("INVALID_PARAMETER", "description parameter required")

            # Get all windows
            all_windows = gw.getAllWindows()
            window_list = [w.title for w in all_windows if w.title]

            if not window_list:
                return self._error_response("NO_WINDOWS", "No windows found")

            # Ask LLM to match
            prompt = f"""Match the description to a window title.

Description: "{description}"

Available windows:
{chr(10).join(f"{i+1}. {title}" for i, title in enumerate(window_list))}

Return ONLY the number (1-{len(window_list)}) of the best match.
If no good match, return 0."""

            llm_response = self.services.llm.generate(prompt, temperature=0.3, max_tokens=10)
            
            # Parse index
            import re
            match = re.search(r'\d+', llm_response)
            if not match:
                return self._error_response("MATCH_FAILED", "LLM could not match window", 
                    recoverable=True, available_windows=window_list)
            
            index = int(match.group()) - 1

            if index < 0 or index >= len(window_list):
                return self._error_response("NO_MATCH", f"No good match for: {description}", 
                    recoverable=True, available_windows=window_list)

            # Focus matched window
            matched_window = all_windows[index]
            matched_window.activate()

            return {
                "success": True,
                "description": description,
                "matched_window": {
                    "title": matched_window.title,
                    "position": {"x": matched_window.left, "y": matched_window.top},
                    "size": {"width": matched_window.width, "height": matched_window.height},
                },
                "all_windows": window_list,
            }

        except Exception as e:
            logger.error(f"smart_focus_window failed: {e}")
            return self._error_response("SMART_FOCUS_FAILED", str(e), recoverable=True)

    def _handle_get_active_window(self, **kwargs) -> dict:
        """Get active window info."""
        try:
            import pygetwindow as gw
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            active = gw.getActiveWindow()
            
            if not active:
                return self._error_response("NO_ACTIVE_WINDOW", "No active window found")
            
            return {
                "success": True,
                "title": active.title,
                "position": {"x": active.left, "y": active.top},
                "size": {"width": active.width, "height": active.height},
                "is_minimized": active.isMinimized,
                "is_maximized": active.isMaximized,
            }

        except Exception as e:
            logger.error(f"get_active_window failed: {e}")
            return self._error_response("GET_ACTIVE_FAILED", str(e))

    def _handle_resize_window(self, **kwargs) -> dict:
        """Resize/move window."""
        try:
            import pygetwindow as gw
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            title = kwargs.get("title")
            if not title:
                return self._error_response("INVALID_PARAMETER", "title parameter required")
            
            all_windows = gw.getAllWindows()
            matching = self._fuzzy_match_windows(title, all_windows)
            
            if not matching:
                return self._error_response("WINDOW_NOT_FOUND", f"No window found: {title}")
            
            window = matching[0]
            
            # Apply changes
            if kwargs.get("width") is not None:
                window.width = int(kwargs["width"])
            if kwargs.get("height") is not None:
                window.height = int(kwargs["height"])
            if kwargs.get("x") is not None:
                window.left = int(kwargs["x"])
            if kwargs.get("y") is not None:
                window.top = int(kwargs["y"])
            
            self._invalidate_screen_cache()
            return {
                "success": True,
                "window": {
                    "title": window.title,
                    "position": {"x": window.left, "y": window.top},
                    "size": {"width": window.width, "height": window.height},
                },
            }

        except Exception as e:
            logger.error(f"resize_window failed: {e}")
            return self._error_response("RESIZE_FAILED", str(e), recoverable=True)

    def _handle_minimize_window(self, **kwargs) -> dict:
        """Minimize window."""
        try:
            import pygetwindow as gw
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            title = kwargs.get("title")
            if not title:
                return self._error_response("INVALID_PARAMETER", "title parameter required")
            
            all_windows = gw.getAllWindows()
            matching = self._fuzzy_match_windows(title, all_windows)
            
            if not matching:
                return self._error_response("WINDOW_NOT_FOUND", f"No window found: {title}")
            
            matching[0].minimize()
            self._invalidate_screen_cache()
            return {"success": True, "title": matching[0].title}

        except Exception as e:
            logger.error(f"minimize_window failed: {e}")
            return self._error_response("MINIMIZE_FAILED", str(e), recoverable=True)

    def _handle_maximize_window(self, **kwargs) -> dict:
        """Maximize window."""
        try:
            import pygetwindow as gw
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            title = kwargs.get("title")
            if not title:
                return self._error_response("INVALID_PARAMETER", "title parameter required")
            
            all_windows = gw.getAllWindows()
            matching = self._fuzzy_match_windows(title, all_windows)
            
            if not matching:
                return self._error_response("WINDOW_NOT_FOUND", f"No window found: {title}")
            
            matching[0].maximize()
            self._invalidate_screen_cache()
            return {"success": True, "title": matching[0].title}

        except Exception as e:
            logger.error(f"maximize_window failed: {e}")
            return self._error_response("MAXIMIZE_FAILED", str(e), recoverable=True)

    # ── Process Management Handlers ────────────────────────────────────────

    def _handle_list_processes(self, **kwargs) -> dict:
        """List running processes."""
        try:
            import psutil
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            filter_name = kwargs.get("filter_name", "").lower()
            limit = int(kwargs.get("limit", 50))
            
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
                try:
                    info = proc.info
                    name = info.get('name', '')
                    
                    if filter_name and filter_name not in name.lower():
                        continue
                    
                    processes.append({
                        "pid": info['pid'],
                        "name": name,
                        "cpu_percent": info.get('cpu_percent', 0.0),
                        "memory_mb": info.get('memory_info').rss / (1024 * 1024) if info.get('memory_info') else 0,
                    })
                    
                    if len(processes) >= limit:
                        break
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            return {
                "success": True,
                "count": len(processes),
                "processes": processes,
            }

        except Exception as e:
            logger.error(f"list_processes failed: {e}")
            return self._error_response("LIST_FAILED", str(e))

    def _handle_launch_application(self, **kwargs) -> dict:
        """Launch application with safety check and wait for window."""
        try:
            import subprocess
            import os
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            name = kwargs.get("name")
            if not name:
                return self._error_response("INVALID_PARAMETER", "name parameter required")
            
            args = kwargs.get("args", [])
            wait_seconds = int(kwargs.get("wait_seconds", 5))  # Default wait for actual app readiness
            
            # Safety check
            if not self._check_safety(SafetyLevel.HIGH, f"launch '{name}'"):
                return self._error_response("SAFETY_BLOCKED", "Launch requires approval")
            
            # Map common app names to Windows executables
            app_map = {
                "calculator": "calc.exe",
                "calc": "calc.exe",
                "notepad": "notepad.exe",
                "paint": "mspaint.exe",
                "wordpad": "write.exe",
                "explorer": "explorer.exe",
                "cmd": "cmd.exe",
                "powershell": "powershell.exe",
            }
            
            # Normalize name
            name_lower = name.lower()
            executable = app_map.get(name_lower, name)
            
            # Special handling for Steam and other protocol handlers
            if name_lower == "steam":
                os.startfile("steam://open/main")
                readiness = self._wait_for_window_ready(name, wait_seconds)
                self._invalidate_screen_cache()
                return {
                    "success": True,
                    "pid": 0,
                    "name": name,
                    "method": "protocol_handler",
                    "waited": readiness["waited"],
                    "window_ready": readiness["window_ready"],
                    "window_active": readiness["window_active"],
                    "active_window": readiness.get("active_window"),
                }
            
            # Try direct launch first (for .exe files)
            try:
                proc = subprocess.Popen([executable] + (args if isinstance(args, list) else []))
                readiness = self._wait_for_window_ready(name, wait_seconds)
                self._invalidate_screen_cache()
                return {
                    "success": True,
                    "pid": proc.pid,
                    "name": name,
                    "args": args,
                    "method": "direct",
                    "waited": readiness["waited"],
                    "window_ready": readiness["window_ready"],
                    "window_active": readiness["window_active"],
                    "active_window": readiness.get("active_window"),
                }
            except FileNotFoundError:
                # Fallback: Use Windows 'start' command (searches PATH and Start Menu)
                logger.info(f"Direct launch failed, trying 'start' command for: {name}")
                subprocess.Popen(["cmd", "/c", "start", "", name], shell=False)
                readiness = self._wait_for_window_ready(name, wait_seconds)
                self._invalidate_screen_cache()
                return {
                    "success": True,
                    "pid": 0,  # 'start' doesn't return PID
                    "name": name,
                    "method": "start_command",
                    "waited": readiness["waited"],
                    "window_ready": readiness["window_ready"],
                    "window_active": readiness["window_active"],
                    "active_window": readiness.get("active_window"),
                }

        except Exception as e:
            logger.error(f"launch_application failed: {e}")
            return self._error_response("LAUNCH_FAILED", str(e), recoverable=True)

    def _handle_kill_process(self, **kwargs) -> dict:
        """Kill process with protection checks."""
        try:
            import psutil
        except ImportError as e:
            return self._error_response("DEPENDENCY_MISSING", f"Missing dependency: {e}")

        try:
            pid = kwargs.get("pid")
            name = kwargs.get("name")
            
            if not pid and not name:
                return self._error_response("INVALID_PARAMETER", "Either pid or name required")
            
            # Find process
            if pid:
                try:
                    proc = psutil.Process(int(pid))
                    proc_name = proc.name()
                    
                    # Protection check
                    if proc_name.lower() in PROTECTED_PROCESSES:
                        return self._error_response("PROTECTED_PROCESS", 
                            f"Cannot kill protected process: {proc_name}")
                    
                    # Safety check
                    if not self._check_safety(SafetyLevel.HIGH, f"kill PID {pid} ({proc_name})"):
                        return self._error_response("SAFETY_BLOCKED", "Kill requires approval")
                    
                    proc.terminate()
                    return {"success": True, "killed_pid": pid, "name": proc_name, "method": "by_pid"}
                    
                except psutil.NoSuchProcess:
                    return self._error_response("PROCESS_NOT_FOUND", f"No process with PID: {pid}")
            
            # Kill by name
            if name:
                # Protection check
                if name.lower() in PROTECTED_PROCESSES:
                    return self._error_response("PROTECTED_PROCESS", 
                        f"Cannot kill protected process: {name}")
                
                for proc in psutil.process_iter(['pid', 'name']):
                    if proc.info['name'].lower() == name.lower():
                        # Safety check
                        if not self._check_safety(SafetyLevel.HIGH, f"kill '{name}' (PID {proc.info['pid']})"):
                            return self._error_response("SAFETY_BLOCKED", "Kill requires approval")
                        
                        proc.terminate()
                        return {"success": True, "killed_pid": proc.info['pid'], "name": name, "method": "by_name"}
                
                return self._error_response("PROCESS_NOT_FOUND", f"No process named: {name}")

        except Exception as e:
            logger.error(f"kill_process failed: {e}")
            return self._error_response("KILL_FAILED", str(e), recoverable=True)

    # ── Helper Methods ─────────────────────────────────────────────────────

    def _fuzzy_match_windows(self, query: str, windows: List) -> List:
        """Fuzzy match windows by title."""
        query_lower = query.lower()
        matches = []
        
        for win in windows:
            if not win.title:
                continue
            title_lower = win.title.lower()
            
            # Exact match
            if query_lower == title_lower:
                return [win]
            
            # Substring match
            if query_lower in title_lower:
                matches.append((win, 2))  # High priority
            elif title_lower in query_lower:
                matches.append((win, 1))  # Medium priority
        
        # Sort by priority
        matches.sort(key=lambda x: x[1], reverse=True)
        return [m[0] for m in matches]

    def _wait_for_window_ready(self, query: str, timeout_seconds: int) -> Dict[str, Any]:
        """Wait for an app window to appear and preferably become active."""
        import time

        waited = 0.0
        timeout = max(1, int(timeout_seconds or 0))
        poll_interval = 0.5

        try:
            import pygetwindow as gw
        except ImportError:
            logger.info(f"pygetwindow unavailable, falling back to fixed wait for '{query}'")
            time.sleep(timeout)
            return {
                "window_ready": False,
                "window_active": False,
                "active_window": None,
                "waited": timeout,
            }

        last_match = None
        end_time = time.time() + timeout
        while time.time() < end_time:
            all_windows = gw.getAllWindows()
            matching = self._fuzzy_match_windows(query, all_windows)
            if matching:
                window = matching[0]
                last_match = window
                try:
                    if getattr(window, "isMinimized", False):
                        window.restore()
                    window.activate()
                except Exception:
                    pass

                active_window = None
                try:
                    active_window = gw.getActiveWindow()
                except Exception:
                    active_window = None

                if active_window and self._titles_match(query, getattr(active_window, "title", "")):
                    return {
                        "window_ready": True,
                        "window_active": True,
                        "active_window": self._serialize_window(active_window),
                        "waited": round(time.time() - (end_time - timeout), 2),
                    }

            time.sleep(poll_interval)
            waited = round(time.time() - (end_time - timeout), 2)

        if last_match is not None:
            return {
                "window_ready": True,
                "window_active": False,
                "active_window": self._serialize_window(last_match),
                "waited": waited or timeout,
            }

        logger.info(f"No window matched '{query}' within {timeout}s")
        return {
            "window_ready": False,
            "window_active": False,
            "active_window": None,
            "waited": waited or timeout,
        }

    def _titles_match(self, query: str, title: str) -> bool:
        query_lower = str(query or "").strip().lower()
        title_lower = str(title or "").strip().lower()
        return bool(query_lower and title_lower and (query_lower in title_lower or title_lower in query_lower))

    def _serialize_window(self, window: Any) -> Dict[str, Any]:
        return {
            "title": str(getattr(window, "title", "") or ""),
            "position": {
                "x": int(getattr(window, "left", 0) or 0),
                "y": int(getattr(window, "top", 0) or 0),
            },
            "size": {
                "width": int(getattr(window, "width", 0) or 0),
                "height": int(getattr(window, "height", 0) or 0),
            },
            "is_minimized": bool(getattr(window, "isMinimized", False)),
            "is_maximized": bool(getattr(window, "isMaximized", False)),
        }

    def _invalidate_screen_cache(self) -> None:
        """Force a fresh screenshot after window-changing operations."""
        if not self.services:
            return
        try:
            self.services.call_tool("ScreenPerceptionTool", "invalidate_cache")
        except Exception as exc:
            logger.debug(f"Screen cache invalidation skipped: {exc}")

    def _check_safety(self, level: SafetyLevel, operation: str) -> bool:
        """Safety enforcement."""
        if level == SafetyLevel.HIGH:
            logger.warning(f"HIGH safety operation: {operation}")
        return True

    def _error_response(self, error_type: str, message: str, recoverable: bool = False, **extra) -> dict:
        """Structured error response."""
        extra.setdefault("failure_category", classify_desktop_failure(error_type, message))
        return {
            "success": False,
            "error_type": error_type,
            "message": message,
            "recoverable": recoverable,
            **extra
        }

    def execute(self, operation: str, **kwargs):
        """Execute capability by name."""
        return self.execute_capability(operation, **kwargs)
