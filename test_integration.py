"""
Integration Test - Verify CUA system is ready
"""

import sys
import requests
import time

API_URL = "http://localhost:8000"

def test_backend():
    """Test backend is running"""
    print("🔍 Testing backend connection...")
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Backend is running")
            return True
        else:
            print(f"❌ Backend returned {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Backend not running - Start with: python start.py")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_tools_registered():
    """Test tools are registered"""
    print("\n🔍 Testing tool registration...")
    try:
        response = requests.get(f"{API_URL}/status", timeout=5)
        data = response.json()
        tool_count = data.get('tools', 0)
        
        if tool_count >= 4:
            print(f"✅ {tool_count} tools registered")
            return True
        else:
            print(f"⚠️  Only {tool_count} tools registered (expected 4+)")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_chat_endpoint():
    """Test chat endpoint"""
    print("\n🔍 Testing chat endpoint...")
    try:
        response = requests.post(
            f"{API_URL}/chat",
            json={"message": "hello"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('response'):
                print("✅ Chat endpoint working")
                return True
        
        print(f"❌ Chat failed: {response.status_code}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_registry_sync():
    """Test registry sync endpoint"""
    print("\n🔍 Testing registry sync endpoint...")
    try:
        response = requests.post(f"{API_URL}/api/tools/sync", timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                synced = len(data.get('synced', []))
                print(f"✅ Registry sync working ({synced} tools synced)")
                return True
        
        print(f"❌ Sync failed: {response.status_code}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_improvement_status():
    """Test self-improvement endpoint"""
    print("\n🔍 Testing self-improvement status...")
    try:
        response = requests.get(f"{API_URL}/improvement/status", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Self-improvement ready (status: {data.get('status', 'unknown')})")
            return True
        
        print(f"❌ Status check failed: {response.status_code}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("=" * 60)
    print("CUA INTEGRATION TEST")
    print("=" * 60)
    
    tests = [
        ("Backend Connection", test_backend),
        ("Tool Registration", test_tools_registered),
        ("Chat Endpoint", test_chat_endpoint),
        ("Registry Sync", test_registry_sync),
        ("Self-Improvement", test_improvement_status)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Test crashed: {e}")
            results.append((name, False))
        time.sleep(1)
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! CUA is ready to use.")
        print("\nNext steps:")
        print("1. Open UI: http://localhost:3000")
        print("2. Click 'Registry' tab and sync tools")
        print("3. Try chat: 'What can you do?'")
        print("4. Try tool: 'Make GET request to https://api.github.com'")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
