"""Test autonomous agent integration."""
import requests
import json
import time

API_URL = "http://localhost:8000"

def test_agent_goal():
    """Test autonomous goal achievement."""
    
    # Test 1: Simple goal
    print("\n=== Test 1: Simple Goal ===")
    goal_request = {
        "goal": "List files in current directory and count them",
        "success_criteria": [
            "Files are listed",
            "Count is provided"
        ],
        "max_iterations": 3,
        "require_approval": False,
        "session_id": "test_session_1"
    }
    
    response = requests.post(f"{API_URL}/agent/goal", json=goal_request)
    print(f"Status: {response.status_code}")
    result = response.json()
    print(json.dumps(result, indent=2))
    
    # Test 2: Check execution state
    if result.get("execution_history"):
        print("\n=== Test 2: Check Execution State ===")
        exec_id = result["execution_history"][0]
        exec_response = requests.get(f"{API_URL}/agent/execution/{exec_id}")
        print(f"Status: {exec_response.status_code}")
        print(json.dumps(exec_response.json(), indent=2))
    
    # Test 3: Check memory
    print("\n=== Test 3: Check Memory ===")
    memory_response = requests.get(f"{API_URL}/agent/memory/test_session_1")
    print(f"Status: {memory_response.status_code}")
    print(json.dumps(memory_response.json(), indent=2))

if __name__ == "__main__":
    print("Testing Autonomous Agent Integration...")
    print("Make sure server is running on http://localhost:8000")
    
    try:
        # Check health
        health = requests.get(f"{API_URL}/health")
        if health.status_code == 200:
            print("✓ Server is healthy")
            test_agent_goal()
        else:
            print("✗ Server not responding")
    except Exception as e:
        print(f"✗ Error: {e}")
        print("Make sure to start the server first: python start.py")
