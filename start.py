#!/usr/bin/env python3
import subprocess
import sys
import os


def _check_ollama(url: str):
    """Fail fast if Ollama is not reachable."""
    try:
        import requests
        r = requests.get(url, timeout=5)
        if r.status_code not in (200, 404):  # 404 = running but no model loaded yet — still OK
            raise Exception(f"Unexpected status {r.status_code}")
    except Exception as e:
        print(f"\n❌ Ollama not reachable at {url}: {e}")
        print("   Start Ollama first:  ollama serve")
        sys.exit(1)


def _validate_config(config):
    """Warn on common config mistakes before starting the server."""
    issues = []
    for srv in (config.mcp_servers or []):
        if srv.enabled and getattr(srv, 'transport', 'stdio') == 'http':
            if not srv.url.startswith(("http://", "https://")):
                issues.append(f"MCP server '{srv.name}' has invalid url: {srv.url!r}")
        if srv.enabled and getattr(srv, 'transport', 'stdio') == 'stdio':
            if not getattr(srv, 'command', ''):
                issues.append(f"MCP server '{srv.name}' has transport=stdio but no command set")
    if config.llm.provider not in ("ollama", "openai", "gemini"):
        issues.append(f"Unknown LLM provider: {config.llm.provider!r}")
    if config.api.port < 1024 or config.api.port > 65535:
        issues.append(f"API port {config.api.port} is out of valid range 1024-65535")
    if issues:
        print("\n⚠️  Config warnings:")
        for issue in issues:
            print(f"   - {issue}")
        print()


def _rotate_logs(keep: int = 50):
    """Keep only the most recent LLM session logs to prevent unbounded growth."""
    from pathlib import Path
    llm_dir = Path("logs/llm")
    if not llm_dir.exists():
        return
    files = sorted(llm_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except Exception:
            pass


def start_cua():
    from core.config_manager import get_config
    config = get_config()
    
    print("Starting CUA Autonomous Agent System...")

    # Rotate old logs before starting
    _rotate_logs(keep=50)

    # Validate config before anything else
    _validate_config(config)

    # Validate Ollama is up before starting the server
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    print(f"Checking Ollama at {ollama_url}...")
    _check_ollama(ollama_url)
    print("✓ Ollama reachable")

    # MCP servers with stdio transport are started by MCPAdapterTool during bootstrap.
    # Just get the manager reference for clean shutdown.
    mcp_manager = None
    try:
        from core.mcp_process_manager import get_mcp_process_manager
        mcp_manager = get_mcp_process_manager()
    except Exception:
        pass

    # Start API server
    print(f"Starting API server on port {config.api.port}...")
    
    try:
        api_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", str(config.api.port), "--reload"],
        )
        
        # Wait briefly and check if process started
        import time
        time.sleep(config.timeouts.startup_wait)
        
        if api_process.poll() is not None:
            print(f"ERROR: API server failed to start")
            mcp_manager.stop_all()
            sys.exit(1)
        
        # Verify API is responding
        try:
            import requests
            response = requests.get(f"{config.api.url}/health", timeout=config.timeouts.health_check)
            if response.status_code != 200:
                raise Exception("Health check failed")
        except:
            print("WARNING: API server started but not responding to health checks")
        
        print("\nCUA System Running!")
        print(f"API: {config.api.url}")
        print("UI: cd ui && npm start")
        print("\nPress Ctrl+C to stop")
        
        api_process.wait()
        
    except KeyboardInterrupt:
        print("\nStopping CUA system...")
        api_process.terminate()
        api_process.wait(timeout=5)
        mcp_manager.stop_all()
        print("Stopped.")
    except Exception as e:
        print(f"ERROR: {e}")
        if 'api_process' in locals():
            api_process.terminate()
        mcp_manager.stop_all()
        sys.exit(1)

if __name__ == "__main__":
    start_cua()
