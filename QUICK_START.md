# CUA Quick Start Guide

## 1. Start Backend
```bash
python start.py
```
Wait for: "CUA system initialized successfully"

## 2. Start UI (separate terminal)
```bash
cd ui
npm install  # First time only
npm start
```
Opens: http://localhost:3000

## 3. Run Integration Test
```bash
python test_integration.py
```
Should show: "All tests passed! CUA is ready to use."

## 4. Sync Tool Registry
1. Open UI: http://localhost:3000
2. Click **"Registry"** tab
3. Click **"🔄 Sync Tool Capabilities"** button
4. Wait ~30 seconds for LLM to analyze tools
5. See all tools with their operations

## 5. Test Chat
Try these in the chat panel:

**Conversational:**
- "What can you do?"
- "Hello"
- "Explain your capabilities"

**Tool Execution:**
- "List files in current directory"
- "Make GET request to https://api.github.com"
- "Create a file called test.txt with content Hello World"

## 6. Test Self-Improvement
1. Click **"Start Loop"** button
2. Watch Activity Log tab
3. System will analyze and improve tools
4. After improvements, click **"Sync Tool Capabilities"** again
5. New features will appear in registry

## Troubleshooting

**Backend won't start:**
- Check Ollama is running: `ollama list`
- Check port 8000 is free

**Chat not working:**
- Check backend connection indicator (top of UI)
- Verify models loaded: `ollama list`
- Check browser console for errors

**Registry sync fails:**
- Ensure Mistral model is available: `ollama pull mistral`
- Check API logs for LLM errors
- Verify tools exist in `tools/` directory

**Self-improvement not working:**
- This is separate from chat - uses different flow
- Check improvement logs in Activity Log tab
- Verify Qwen model: `ollama pull qwen2.5-coder:7b`

## Architecture

```
Chat Flow:
User → LLM Decision (TOOL/CHAT) → Plan Generation → Tool Execution → Response

Self-Improvement Flow:
Loop → Analyze Code → Generate Improvements → Test → Apply → Repeat

Registry Sync:
Button → LLM Analyzes Tool Files → Extracts Capabilities → Saves JSON → Used by Chat
```

## Key Features

✅ **LLM-Driven Chat** - Decides when to use tools vs conversation
✅ **Tool Registry** - Central capability database
✅ **Self-Improvement** - Autonomous code enhancement
✅ **Safety Validation** - BrainStem security checks
✅ **Sandbox Testing** - Safe code execution
✅ **Real-time UI** - WebSocket updates

## Next Steps

1. Test all chat commands
2. Run self-improvement loop
3. Sync registry after improvements
4. Verify new features appear in chat
5. Try complex multi-step tasks
