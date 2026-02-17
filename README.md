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
- Safety validation (brain stem)
- Secure execution
- Real-time API
- React UI with voice input

### Test Commands:
- "list files in current directory"
- "create a test file"
- "what can you do"
