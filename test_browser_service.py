"""Quick test to verify BrowserService works with Brave browser"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.tool_services import BrowserService

def test_browser():
    print("Testing BrowserService with Brave browser...\n")
    
    browser = BrowserService()
    
    # Check if browser is available
    print("1. Checking if Brave browser is available...")
    if not browser.is_available():
        print("[FAIL] Brave browser not found at expected path")
        return False
    print("[OK] Brave browser found\n")
    
    # Try to open browser
    print("2. Opening Brave browser...")
    try:
        browser.open_browser()
        print("[OK] Browser opened successfully\n")
    except Exception as e:
        print(f"[FAIL] Failed to open browser: {e}")
        return False
    
    # Try to navigate
    print("3. Navigating to example.com...")
    try:
        browser.navigate("https://example.com")
        print("[OK] Navigation successful\n")
    except Exception as e:
        print(f"[FAIL] Navigation failed: {e}")
        browser.close()
        return False
    
    # Try to get page text
    print("4. Getting page text...")
    try:
        text = browser.get_page_text()
        print(f"[OK] Got page text ({len(text)} chars)")
        print(f"   Preview: {text[:100]}...\n")
    except Exception as e:
        print(f"[FAIL] Failed to get page text: {e}")
        browser.close()
        return False
    
    # Try to take screenshot
    print("5. Taking screenshot...")
    try:
        screenshot_path = browser.take_screenshot("test_screenshot")
        print(f"[OK] Screenshot saved: {screenshot_path}\n")
    except Exception as e:
        print(f"[FAIL] Screenshot failed: {e}")
        browser.close()
        return False
    
    # Close browser
    print("6. Closing browser...")
    try:
        browser.close()
        print("[OK] Browser closed\n")
    except Exception as e:
        print(f"[WARN] Close warning: {e}\n")
    
    print("=" * 50)
    print("SUCCESS: All tests passed! BrowserService is working.")
    print("=" * 50)
    return True

if __name__ == "__main__":
    try:
        success = test_browser()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n[FAIL] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
