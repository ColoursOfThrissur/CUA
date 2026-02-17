#!/usr/bin/env python3
import subprocess
import sys
import os

def start_cua():
    from core.config_manager import get_config
    config = get_config()
    
    print("Starting CUA Autonomous Agent System...")
    
    # Start API server
    print(f"Starting API server on port {config.api.port}...")
    
    try:
        api_process = subprocess.Popen(
            [sys.executable, "api/server.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait briefly and check if process started
        import time
        time.sleep(config.timeouts.startup_wait)
        
        if api_process.poll() is not None:
            # Process died
            stdout, stderr = api_process.communicate()
            print(f"ERROR: API server failed to start")
            print(f"STDOUT: {stdout.decode()}")
            print(f"STDERR: {stderr.decode()}")
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
        print("Stopped.")
    except Exception as e:
        print(f"ERROR: {e}")
        if 'api_process' in locals():
            api_process.terminate()
        sys.exit(1)

if __name__ == "__main__":
    start_cua()
