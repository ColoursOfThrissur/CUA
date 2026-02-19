# WebContentExtractor - Capability Expansion Test

## Purpose
Test CUA's ability to detect capability gaps, generate specs, create tools, and evolve them.

## Capability Gap
**Current State**: HTTPTool can fetch raw HTML
**Missing**: Structured content extraction from HTML

**Gap**: Raw HTML ≠ Structured Data

## Tool Specification

### Name
`WebContentExtractor`

### Domain
Web Processing

### Inputs
- `url` (string): Webpage URL to extract content from

### Outputs
- `title` (string): Page title
- `description` (string): Meta description
- `links` (list[string]): All hyperlinks (absolute URLs)
- `text_content` (string): Main text content (cleaned)
- `domain` (string): Source domain
- `link_count` (int): Total number of links found

### Dependencies
- `requests`: HTTP client
- `beautifulsoup4`: HTML parsing

### Risk Level
**0.4** (Moderate)
- Network access required
- HTML parsing complexity
- Potential for malformed HTML
- Domain whitelist enforced

### Safety Features
- Domain whitelist (HTTPS allowed, HTTP restricted)
- Content size limits (5000 chars text, 50 links)
- Timeout protection (10s)
- Error handling for malformed HTML

## Test Scenarios

### ✅ Test 1: Capability Detection
**Prompt**: "I need to extract readable content from webpages, but we only have HTTP tools. What capability are we missing?"

**Expected Response**: 
- Identifies gap: HTML parsing / content extraction
- Recognizes HTTPTool only returns raw HTML
- Suggests structured extraction capability

### ✅ Test 2: Spec Generation
**Prompt**: "Generate a tool specification for extracting structured content from web pages"

**Expected Output**:
- Tool name
- Input/output schema
- Dependencies
- Risk assessment
- Safety considerations

### ✅ Test 3: Tool Creation
**Status**: ✅ Implemented
- File: `tools/web_content_extractor.py`
- Follows BaseTool interface
- Capability-based design
- Proper error handling

### ✅ Test 4: Tool Registration
**Validation**:
```python
from tools.web_content_extractor import WebContentExtractor
tool = WebContentExtractor()
assert tool.has_capability("extract")
```

### ✅ Test 5: Functional Testing
**Test Cases**:
- Extract from Wikipedia ✅
- Handle invalid URLs ✅
- Validate missing parameters ✅
- Check capability registration ✅

## Evolution Opportunities

### Phase 1 Improvements (Current)
- ✅ Basic HTML extraction
- ✅ Title, description, links
- ✅ Text content cleaning
- ✅ Domain whitelist

### Phase 2 Improvements (Future)
- CSS selector support
- XPath queries
- Custom extraction rules
- Content density heuristics

### Phase 3 Improvements (Advanced)
- JavaScript-rendered pages (Selenium/Playwright)
- Anti-bot handling
- Rate limiting
- Caching layer
- Retry logic with exponential backoff

### Phase 4 Improvements (Enterprise)
- Proxy support
- Cookie management
- Session handling
- Custom headers
- Content type detection

## Tool Chaining Potential

### Workflow 1: Article Summarization
```
WebContentExtractor → extract text
    ↓
LLM Summarizer → generate summary
    ↓
File Tool → save summary
```

### Workflow 2: Link Analysis
```
WebContentExtractor → extract links
    ↓
Link Validator → check status
    ↓
JSON Tool → export report
```

### Workflow 3: Content Monitoring
```
WebContentExtractor → extract content
    ↓
Diff Tool → compare with previous
    ↓
Alert Tool → notify if changed
```

### Workflow 4: Knowledge Base Building
```
WebContentExtractor → extract articles
    ↓
Entity Extractor → identify entities
    ↓
Vector DB → store embeddings
    ↓
RAG System → enable Q&A
```

## Success Metrics

### Capability Detection
- ✅ Identifies gap between raw HTTP and structured data
- ✅ Recognizes need for HTML parsing

### Spec Generation
- ✅ Defines clear inputs/outputs
- ✅ Identifies dependencies
- ✅ Assesses risk level

### Tool Creation
- ✅ Follows BaseTool interface
- ✅ Implements capability registration
- ✅ Proper error handling
- ✅ Safety validation

### Tool Registration
- ✅ Auto-discovered by registry
- ✅ Capabilities exposed to LLM
- ✅ Executable via API

### Evolution Potential
- ✅ Clear improvement path
- ✅ Modular design for enhancements
- ✅ Backward compatible changes

## Why This Tool Tests Hybrid Architecture

### 1. Multi-Step Reasoning
- Fetch page (network)
- Parse HTML (parsing)
- Extract fields (data extraction)
- Clean content (text processing)

### 2. Error Surface
- Network failures
- Malformed HTML
- Missing elements
- Encoding issues
- Timeout scenarios

**Perfect for improvement engine to learn from**

### 3. Measurable Quality
- Extraction accuracy
- Performance metrics
- Error rates
- Coverage statistics

### 4. Clear Evolution Path
- Start simple (basic extraction)
- Add features (CSS selectors)
- Improve robustness (retry logic)
- Scale up (JS rendering)

## Testing Instructions

### Install Dependencies
```bash
pip install beautifulsoup4==4.12.2
```

### Run Tests
```bash
python tools/test_web_content_extractor.py
```

### Manual Test
```python
from tools.web_content_extractor import WebContentExtractor

tool = WebContentExtractor()
result = tool.execute("extract", {
    "url": "https://en.wikipedia.org/wiki/Python_(programming_language)"
})

print(result.data["title"])
print(f"Found {result.data['link_count']} links")
print(result.data["text_content"][:200])
```

### API Test
```bash
# Start server
python start.py

# Test via API
curl -X POST http://localhost:8000/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "web_content_extractor",
    "operation": "extract",
    "parameters": {"url": "https://en.wikipedia.org/wiki/Python"}
  }'
```

## Conclusion

WebContentExtractor is the **perfect capability expansion test** because:

1. **Real Gap**: HTTPTool → Structured extraction is a genuine need
2. **Not Trivial**: Requires parsing, cleaning, validation
3. **Evolvable**: Clear path from basic → advanced
4. **Chainable**: Enables complex workflows
5. **Measurable**: Success/failure is objective
6. **Safe**: Whitelisted, limited, validated

This tool validates that CUA can:
- ✅ Detect missing capabilities
- ✅ Generate proper specs
- ✅ Create functional tools
- ✅ Register them correctly
- ✅ Evolve them iteratively
