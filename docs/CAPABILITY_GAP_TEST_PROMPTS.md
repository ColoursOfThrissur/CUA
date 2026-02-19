# Capability Gap Detection Test Prompts

## Test 1: Gap Detection (Easy)
**Prompt**: 
```
I need to extract readable content from webpages, but we only have HTTP tools. What capability are we missing?
```

**Expected Behavior**:
- Identifies that HTTPTool returns raw HTML
- Recognizes need for HTML parsing
- Suggests structured content extraction
- Mentions BeautifulSoup or similar

**Success Criteria**:
- ✅ Identifies the gap
- ✅ Explains why raw HTML ≠ structured data
- ✅ Proposes solution approach

---

## Test 2: Spec Generation (Medium)
**Prompt**:
```
Generate a tool specification for extracting structured content from web pages. Include:
- Tool name
- Inputs and outputs
- Dependencies
- Risk level
- Safety considerations
```

**Expected Output**:
```json
{
  "name": "WebContentExtractor",
  "domain": "Web Processing",
  "inputs": {
    "url": "string - webpage URL"
  },
  "outputs": {
    "title": "string",
    "description": "string",
    "links": "list[string]",
    "text_content": "string"
  },
  "dependencies": ["requests", "beautifulsoup4"],
  "risk_level": 0.4,
  "safety": [
    "Domain whitelist",
    "Content size limits",
    "Timeout protection"
  ]
}
```

**Success Criteria**:
- ✅ Complete specification
- ✅ Realistic risk assessment
- ✅ Proper safety considerations

---

## Test 3: Implementation Validation (Hard)
**Prompt**:
```
Review the WebContentExtractor tool implementation and identify:
1. What it does well
2. What could be improved
3. What evolution opportunities exist
```

**Expected Analysis**:
- Strengths: Safety, error handling, clean interface
- Improvements: Caching, retry logic, better text extraction
- Evolution: CSS selectors, JS rendering, anti-bot handling

**Success Criteria**:
- ✅ Accurate assessment
- ✅ Practical suggestions
- ✅ Prioritized improvements

---

## Test 4: Workflow Composition (Advanced)
**Prompt**:
```
Design a workflow that uses WebContentExtractor to:
1. Extract article content from a URL
2. Summarize the text
3. Save the summary to a file

Show the tool chain and data flow.
```

**Expected Workflow**:
```
WebContentExtractor.extract(url) 
  → {title, text_content, links}
  
LLMTool.summarize(text_content)
  → {summary}
  
FileTool.write(filename, summary)
  → {success}
```

**Success Criteria**:
- ✅ Correct tool sequence
- ✅ Proper data passing
- ✅ Error handling considered

---

## Test 5: Evolution Planning (Expert)
**Prompt**:
```
Plan a 4-phase evolution for WebContentExtractor:
- Phase 1: Current capabilities
- Phase 2: Near-term improvements
- Phase 3: Advanced features
- Phase 4: Enterprise-grade

For each phase, specify:
- New capabilities
- Dependencies added
- Risk changes
- Backward compatibility
```

**Expected Plan**:
- Phase 1: Basic extraction ✅
- Phase 2: CSS selectors, caching
- Phase 3: JS rendering, anti-bot
- Phase 4: Proxy, sessions, monitoring

**Success Criteria**:
- ✅ Logical progression
- ✅ Realistic timeline
- ✅ Maintains compatibility
- ✅ Addresses real needs

---

## Automated Test Script

```python
# test_capability_gap_detection.py

def test_gap_detection():
    """Test if CUA can identify capability gaps"""
    prompt = "I need to extract readable content from webpages, but we only have HTTP tools. What capability are we missing?"
    
    response = cua_agent.chat(prompt)
    
    assert "HTML" in response.lower()
    assert "parsing" in response.lower() or "extraction" in response.lower()
    assert "structured" in response.lower() or "content" in response.lower()
    
    print("✅ Gap detection test passed")

def test_spec_generation():
    """Test if CUA can generate proper tool specs"""
    prompt = "Generate a tool specification for extracting structured content from web pages"
    
    response = cua_agent.chat(prompt)
    
    assert "inputs" in response.lower()
    assert "outputs" in response.lower()
    assert "dependencies" in response.lower()
    assert "beautifulsoup" in response.lower() or "bs4" in response.lower()
    
    print("✅ Spec generation test passed")

def test_tool_exists():
    """Test if WebContentExtractor was created"""
    from tools.web_content_extractor import WebContentExtractor
    
    tool = WebContentExtractor()
    assert tool.has_capability("extract")
    
    result = tool.execute("extract", {
        "url": "https://en.wikipedia.org/wiki/Python"
    })
    
    assert result.status == "SUCCESS"
    assert "title" in result.data
    assert "text_content" in result.data
    
    print("✅ Tool creation test passed")

def test_evolution_planning():
    """Test if CUA can plan tool evolution"""
    prompt = "What improvements could be made to WebContentExtractor?"
    
    response = cua_agent.chat(prompt)
    
    # Should suggest realistic improvements
    improvements = ["css", "selector", "cache", "retry", "javascript", "render"]
    found = sum(1 for imp in improvements if imp in response.lower())
    
    assert found >= 2, "Should suggest at least 2 improvements"
    
    print("✅ Evolution planning test passed")

if __name__ == "__main__":
    test_gap_detection()
    test_spec_generation()
    test_tool_exists()
    test_evolution_planning()
    
    print("\n✅ All capability gap tests passed!")
```

---

## Manual Testing Checklist

### Pre-Test Setup
- [ ] Install beautifulsoup4: `pip install beautifulsoup4==4.12.2`
- [ ] Start CUA: `python start.py`
- [ ] Open UI: `http://localhost:3000`

### Test Execution
- [ ] Test 1: Ask about capability gap
- [ ] Test 2: Request tool specification
- [ ] Test 3: Verify tool exists and works
- [ ] Test 4: Test workflow composition
- [ ] Test 5: Request evolution plan

### Validation
- [ ] Tool registered in registry
- [ ] Tool appears in UI tools panel
- [ ] Tool executes successfully
- [ ] Results are structured correctly
- [ ] Error handling works

### Evolution Test
- [ ] Trigger self-improvement on WebContentExtractor
- [ ] Check if improvements are suggested
- [ ] Validate improvements don't break interface
- [ ] Verify backward compatibility

---

## Success Indicators

### 🟢 Full Success
- Detects gap without hints
- Generates complete spec
- Tool works on first try
- Evolution suggestions are practical
- Improvements maintain compatibility

### 🟡 Partial Success
- Needs hints to detect gap
- Spec is incomplete but usable
- Tool works with minor fixes
- Evolution suggestions are generic
- Some improvements break compatibility

### 🔴 Failure
- Cannot identify gap
- Spec is unusable
- Tool doesn't work
- No evolution suggestions
- Improvements break everything

---

## Next Steps After Success

1. **Add More Complex Tools**
   - DatabaseConnector
   - VectorStoreManager
   - WorkflowComposer

2. **Test Tool Chaining**
   - Multi-step workflows
   - Error propagation
   - Data transformation

3. **Validate Evolution**
   - Trigger improvements
   - Measure success rate
   - Track quality metrics

4. **Scale Testing**
   - Multiple tools simultaneously
   - Concurrent executions
   - Performance under load
