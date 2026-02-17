"""
COMPREHENSIVE SYSTEM TEST
Tests entire CUA solution end-to-end
"""

import sys
import os
import subprocess
import time
import requests

def test_entire_solution():
    print("=== TESTING ENTIRE CUA SOLUTION ===\n")
    
    results = {"passed": 0, "failed": 0, "tests": []}
    
    # Test 1: Core Components
    print("1. Testing Core Components...")
    try:
        from core.immutable_brain_stem import BrainStem
        from core.plan_validator import PlanValidator
        from core.permission_gate import PermissionGate
        from core.secure_executor import SecureExecutor
        
        # Test brain stem
        result = BrainStem.validate_path("./test.txt")
        assert result.is_valid, "Brain stem path validation failed"
        
        result = BrainStem.validate_path("C:\\Windows\\system32\\bad.exe")
        assert not result.is_valid, "Brain stem should block system paths"
        
        print("   PASS: Core safety systems working")
        results["passed"] += 1
        results["tests"].append(("Core Components", "PASS"))
    except Exception as e:
        print(f"   FAIL: {e}")
        results["failed"] += 1
        results["tests"].append(("Core Components", f"FAIL: {e}"))
    
    # Test 2: Tool System
    print("2. Testing Tool System...")
    try:
        from tools.capability_registry import CapabilityRegistry
        from tools.enhanced_filesystem_tool import FilesystemTool
        
        registry = CapabilityRegistry()
        fs_tool = FilesystemTool()
        registry.register_tool(fs_tool)
        
        assert len(registry.tools) == 1, "Tool registration failed"
        assert len(registry.get_all_capabilities()) == 3, "Expected 3 capabilities"
        
        # Test actual file operation
        result = fs_tool.execute("write_file", {
            "path": "./output/test_solution.txt",
            "content": "Solution test"
        })
        assert result.status.value == "success", "File write failed"
        assert os.path.exists("./output/test_solution.txt"), "File not created"
        
        # Cleanup
        os.remove("./output/test_solution.txt")
        
        print("   PASS: Tool system working with real file operations")
        results["passed"] += 1
        results["tests"].append(("Tool System", "PASS"))
    except Exception as e:
        print(f"   FAIL: {e}")
        results["failed"] += 1
        results["tests"].append(("Tool System", f"FAIL: {e}"))
    
    # Test 3: API Server
    print("3. Testing API Server...")
    try:
        # Start server
        server = subprocess.Popen(
            [sys.executable, "api/server.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        time.sleep(3)
        
        # Test status endpoint
        response = requests.get("http://localhost:8000/status", timeout=5)
        assert response.status_code == 200, "Status endpoint failed"
        data = response.json()
        assert data["status"] == "online", "Server not online"
        assert data["system_available"] == True, "System not available"
        
        # Test chat endpoint with real operation
        response = requests.post(
            "http://localhost:8000/chat",
            json={"message": "list files in current directory"},
            timeout=10
        )
        assert response.status_code == 200, "Chat endpoint failed"
        chat_data = response.json()
        assert "Directory listing:" in chat_data["response"], "Not executing real operations"
        
        server.terminate()
        server.wait()
        
        print("   PASS: API server working with real operations")
        results["passed"] += 1
        results["tests"].append(("API Server", "PASS"))
    except Exception as e:
        print(f"   FAIL: {e}")
        if 'server' in locals():
            server.terminate()
        results["failed"] += 1
        results["tests"].append(("API Server", f"FAIL: {e}"))
    
    # Test 4: File Structure
    print("4. Testing File Structure...")
    try:
        required_files = [
            "core/immutable_brain_stem.py",
            "tools/capability_registry.py",
            "tools/enhanced_filesystem_tool.py",
            "api/server.py",
            "ui/src/App.js",
            "requirements.txt",
            "start.py"
        ]
        
        for file in required_files:
            assert os.path.exists(file), f"Missing: {file}"
        
        print("   PASS: All required files present")
        results["passed"] += 1
        results["tests"].append(("File Structure", "PASS"))
    except Exception as e:
        print(f"   FAIL: {e}")
        results["failed"] += 1
        results["tests"].append(("File Structure", f"FAIL: {e}"))
    
    # Test 5: UI Files
    print("5. Testing UI Files...")
    try:
        assert os.path.exists("ui/src/App.js"), "Missing App.js"
        assert os.path.exists("ui/package.json"), "Missing package.json"
        
        with open("ui/src/App.js", "r", encoding="utf-8") as f:
            content = f.read()
            assert "WebSocket" in content, "WebSocket integration missing"
            assert "webkitSpeechRecognition" in content, "Voice recognition missing"
        
        print("   PASS: UI files complete with voice integration")
        results["passed"] += 1
        results["tests"].append(("UI Files", "PASS"))
    except Exception as e:
        print(f"   FAIL: {e}")
        results["failed"] += 1
        results["tests"].append(("UI Files", f"FAIL: {e}"))
    
    # Summary
    print(f"\n=== TEST SUMMARY ===")
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"Total:  {results['passed'] + results['failed']}")
    
    print(f"\nDetailed Results:")
    for test_name, status in results["tests"]:
        print(f"  {test_name}: {status}")
    
    if results["failed"] == 0:
        print(f"\n*** ALL TESTS PASSED ***")
        print(f"CUA Autonomous Agent System is fully functional!")
        return True
    else:
        print(f"\n*** SOME TESTS FAILED ***")
        return False

if __name__ == "__main__":
    success = test_entire_solution()
    sys.exit(0 if success else 1)
