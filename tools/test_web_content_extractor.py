"""
Test WebContentExtractor tool
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.web_content_extractor import WebContentExtractor
from tools.tool_result import ResultStatus

def test_extract_wikipedia():
    """Test extracting content from Wikipedia"""
    tool = WebContentExtractor()
    
    result = tool.execute("extract", {
        "url": "https://en.wikipedia.org/wiki/Python_(programming_language)"
    })
    
    assert result.status == ResultStatus.SUCCESS, f"Failed: {result.error_message}"
    assert result.data["title"], "No title extracted"
    assert result.data["text_content"], "No text content extracted"
    assert len(result.data["links"]) > 0, "No links extracted"
    
    print("✅ Wikipedia extraction test passed")
    print(f"   Title: {result.data['title'][:50]}...")
    print(f"   Links: {result.data['link_count']}")
    print(f"   Text length: {len(result.data['text_content'])}")

def test_invalid_url():
    """Test with invalid URL"""
    tool = WebContentExtractor()
    
    result = tool.execute("extract", {
        "url": "https://malicious-site.com"
    })
    
    assert result.status == ResultStatus.FAILURE, "Should fail for non-whitelisted domain"
    print("✅ Invalid URL test passed")

def test_missing_url():
    """Test with missing URL parameter"""
    tool = WebContentExtractor()
    
    result = tool.execute("extract", {})
    
    assert result.status == ResultStatus.FAILURE, "Should fail without URL"
    assert "URL required" in result.error_message
    print("✅ Missing URL test passed")

def test_capability_registration():
    """Test that capabilities are properly registered"""
    tool = WebContentExtractor()
    
    assert tool.has_capability("extract"), "Extract capability not registered"
    
    caps = tool.get_capabilities()
    assert "extract" in caps, "Extract not in capabilities"
    
    print("✅ Capability registration test passed")

if __name__ == "__main__":
    print("Testing WebContentExtractor...\n")
    
    test_capability_registration()
    test_missing_url()
    test_invalid_url()
    test_extract_wikipedia()
    
    print("\n✅ All tests passed!")
