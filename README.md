# CUA Autonomous Agent System

## Clean Minimal Structure

### Directory Structure:
```
cua_clean/
├── core/          # Safety and execution engine
├── tools/         # Tool system and registry
├── planner/       # LLM integration
├── api/           # FastAPI server
├── ui/            # React frontend
├── requirements.txt
└── start.py       # Single startup script
```

### Quick Start:
```bash
# Install dependencies
pip install -r requirements.txt

# Start system
python start.py

# Start UI (separate terminal)
cd ui && npm install && npm start
```

### What Works:
- File operations (read, write, list)
- HTTP requests (GET, POST, PUT, DELETE)
- Web content extraction (structured HTML parsing)
- Safety validation (brain stem)
- Secure execution
- Real-time API
- React UI with voice input
- Hybrid self-improvement engine (80% success rate)
- Error-driven targeting
- Automated test validation

### Test Commands:
- "list files in current directory"
- "create a test file"
- "what can you do"
- "extract content from https://en.wikipedia.org/wiki/Python"

### Capability Expansion Test:
See [docs/CAPABILITY_GAP_TEST_PROMPTS.md](docs/CAPABILITY_GAP_TEST_PROMPTS.md) for testing CUA's ability to:
- ✅ Detect missing capabilities
- ✅ Generate tool specifications
- ✅ Create and register new tools
- ✅ Plan tool evolution

**Test Tool**: WebContentExtractor - Extracts structured content from web pages

```bash
# Test the new tool
python tools/test_web_content_extractor.py
```
