# Agentic Self-Evolution Architecture

## Problem Analysis

**Current Issues:**
- Self-evolution is hardcoded, not intelligent
- No integration with observability data
- No conversational flow with user
- No step-by-step confirmation
- Different from tool creation (which works well)

**Requirements:**
1. Conversational agent that chats with user
2. Uses observability data to identify weak tools
3. Shows actual tool code and proposes changes
4. Confirms each major step:
   - Tool selection
   - Current code review
   - Recommended changes
   - Validation results
   - Final push
5. Works for both:
   - System-initiated (scheduled, capability gaps)
   - User-initiated (custom prompts)

---

## Architecture Design

### Core Concept: Conversation-Driven Evolution

```
User/System Trigger
    ↓
AgenticEvolutionChat (LLM-powered conversation)
    ↓
[Step 1] Tool Selection (with observability data)
    ↓ [User confirms]
[Step 2] Code Analysis (show current code)
    ↓ [User confirms issues]
[Step 3] Change Proposal (show diff)
    ↓ [User confirms changes]
[Step 4] Validation (run tests)
    ↓ [User confirms results]
[Step 5] Apply Changes (push to file)
    ↓ [User confirms]
Done
```

### Key Components

#### 1. AgenticEvolutionChat
- LLM-powered conversational agent
- Maintains conversation state
- Asks questions, waits for user responses
- Shows code, diffs, test results
- Guides user through evolution process

#### 2. EvolutionContext
- Combines observability data + tool code + user intent
- Provides rich context to LLM
- Tracks conversation history

#### 3. EvolutionSteps (5 major steps)
- **SELECT**: Choose tool (from observability or user request)
- **ANALYZE**: Show current code, identify issues
- **PROPOSE**: Generate changes with diff
- **VALIDATE**: Run tests, show results
- **APPLY**: Push changes to file

#### 4. Integration Points
- **Observability**: Get weak tools from ToolQualityAnalyzer
- **Tool Code**: Read actual tool file
- **LLM**: Generate analysis, proposals, explanations
- **Validation**: Run tests like tool creation does
- **UI**: WebSocket for real-time chat

---

## Detailed Flow

### System-Initiated Evolution

```python
# Scheduled job finds weak tool
weak_tools = analyzer.get_weak_tools()
tool = weak_tools[0]  # BrokenTool

# Start conversation
chat = AgenticEvolutionChat(llm_client)
chat.start_system_evolution(tool_name="BrokenTool")

# Chat sends to UI:
"""
🤖 I've identified BrokenTool needs improvement:
- Success rate: 0%
- Risk score: 1.0
- Issues: timeout errors, slow execution

Would you like me to analyze and fix it? (yes/no)
"""

# User: "yes"

# Step 1: Show code
"""
🤖 Here's the current code:

```python
def execute(self, operation, **kwargs):
    time.sleep(10)  # This is causing timeouts!
    return {"result": None}
```

I see the problem: 10 second sleep causing timeouts.
Shall I propose a fix? (yes/no)
"""

# User: "yes"

# Step 2: Propose changes
"""
🤖 Recommended changes:

--- a/tools/broken_tool.py
+++ b/tools/broken_tool.py
@@ -5,7 +5,7 @@
 def execute(self, operation, **kwargs):
-    time.sleep(10)  # This is causing timeouts!
+    # Removed blocking sleep
     return {"result": "processed"}

This will:
- Remove timeout issue
- Return actual result
- Improve success rate to ~100%

Apply these changes? (yes/no/modify)
"""

# User: "yes"

# Step 3: Validate
"""
🤖 Running tests...
✓ Syntax valid
✓ Tests passed (3/3)
✓ No regressions

Push changes to file? (yes/no)
"""

# User: "yes"

# Step 4: Apply
"""
🤖 Changes applied successfully!
✓ File updated: tools/broken_tool.py
✓ New health score: 85/100 (was 6.9)

Evolution complete! 🎉
"""
```

### User-Initiated Evolution

```python
# User in UI: "improve the http_tool to handle retries better"

chat = AgenticEvolutionChat(llm_client)
chat.start_user_evolution(user_prompt="improve http_tool retries")

# Chat:
"""
🤖 I'll help improve http_tool's retry handling.

Current retry logic:
```python
def get(self, url, **kwargs):
    response = requests.get(url)  # No retries!
    return response.json()
```

I can add:
- Exponential backoff
- Configurable retry count
- Better error handling

Shall I proceed? (yes/no)
"""
```

---

## Implementation Structure

### File: `core/agentic_evolution_chat.py`

```python
class AgenticEvolutionChat:
    """Conversational agent for tool evolution."""
    
    def __init__(self, llm_client, quality_analyzer):
        self.llm = llm_client
        self.analyzer = quality_analyzer
        self.state = EvolutionState()
        self.conversation = []
    
    async def start_system_evolution(self, tool_name: str):
        """System-initiated: weak tool detected."""
        # Get observability data
        report = self.analyzer.analyze_tool(tool_name)
        
        # Build context
        context = {
            "tool_name": tool_name,
            "health_score": report.health_score,
            "issues": report.issues,
            "trigger": "system"
        }
        
        # Start conversation
        await self._step_select(context)
    
    async def start_user_evolution(self, user_prompt: str):
        """User-initiated: custom improvement request."""
        # LLM extracts tool name from prompt
        tool_name = await self._extract_tool_name(user_prompt)
        
        context = {
            "tool_name": tool_name,
            "user_prompt": user_prompt,
            "trigger": "user"
        }
        
        await self._step_select(context)
    
    async def _step_select(self, context):
        """Step 1: Tool selection with confirmation."""
        self.state.current_step = "SELECT"
        
        # Get tool code
        tool_code = self._read_tool_file(context["tool_name"])
        context["tool_code"] = tool_code
        
        # LLM generates selection message
        message = await self._llm_generate_message(
            step="select",
            context=context
        )
        
        # Send to UI, wait for confirmation
        await self._send_and_wait(message, next_step="_step_analyze")
    
    async def _step_analyze(self, context):
        """Step 2: Code analysis with issues."""
        self.state.current_step = "ANALYZE"
        
        # LLM analyzes code
        analysis = await self._llm_analyze_code(
            tool_code=context["tool_code"],
            issues=context.get("issues", [])
        )
        
        context["analysis"] = analysis
        
        message = await self._llm_generate_message(
            step="analyze",
            context=context
        )
        
        await self._send_and_wait(message, next_step="_step_propose")
    
    async def _step_propose(self, context):
        """Step 3: Generate and show changes."""
        self.state.current_step = "PROPOSE"
        
        # LLM generates changes
        changes = await self._llm_generate_changes(
            tool_code=context["tool_code"],
            analysis=context["analysis"],
            user_prompt=context.get("user_prompt")
        )
        
        context["changes"] = changes
        
        message = await self._llm_generate_message(
            step="propose",
            context=context,
            include_diff=True
        )
        
        await self._send_and_wait(message, next_step="_step_validate")
    
    async def _step_validate(self, context):
        """Step 4: Run tests and show results."""
        self.state.current_step = "VALIDATE"
        
        # Apply changes to temp file
        temp_file = self._apply_to_temp(
            context["tool_code"],
            context["changes"]
        )
        
        # Run validation
        validation = await self._run_validation(temp_file)
        context["validation"] = validation
        
        message = await self._llm_generate_message(
            step="validate",
            context=context
        )
        
        await self._send_and_wait(message, next_step="_step_apply")
    
    async def _step_apply(self, context):
        """Step 5: Apply changes to actual file."""
        self.state.current_step = "APPLY"
        
        # Write to actual file
        self._write_tool_file(
            context["tool_name"],
            context["changes"]
        )
        
        # Get new health score
        new_score = self.analyzer.analyze_tool(context["tool_name"])
        
        message = await self._llm_generate_message(
            step="complete",
            context={**context, "new_score": new_score}
        )
        
        await self._send_final(message)
    
    async def _llm_generate_message(self, step: str, context: dict, **kwargs):
        """LLM generates conversational message for each step."""
        prompt = f"""You are an AI assistant helping improve a tool.

Current step: {step}
Context: {context}

Generate a friendly, clear message explaining:
- What you found
- What you recommend
- What the user should confirm

Be conversational, use emojis, show code snippets.
"""
        return await self.llm.generate_response(prompt)
```

### File: `api/evolution_chat_api.py`

```python
@router.post("/evolution/start")
async def start_evolution(request: EvolutionRequest):
    """Start evolution conversation."""
    chat = get_evolution_chat()
    
    if request.tool_name:
        # System-initiated
        await chat.start_system_evolution(request.tool_name)
    else:
        # User-initiated
        await chat.start_user_evolution(request.prompt)
    
    return {"session_id": chat.session_id}

@router.post("/evolution/respond")
async def respond_to_evolution(request: EvolutionResponse):
    """User responds to evolution step."""
    chat = get_evolution_chat(request.session_id)
    
    if request.response == "yes":
        await chat.continue_to_next_step()
    elif request.response == "no":
        await chat.cancel_evolution()
    elif request.response.startswith("modify:"):
        await chat.modify_proposal(request.response[7:])
    
    return {"status": "ok"}

@router.websocket("/evolution/ws/{session_id}")
async def evolution_websocket(websocket: WebSocket, session_id: str):
    """Real-time evolution chat."""
    await websocket.accept()
    chat = get_evolution_chat(session_id)
    
    async for message in chat.stream_messages():
        await websocket.send_json(message)
```

---

## UI Flow

### Evolution Chat Component

```javascript
// EvolutionChat.jsx
function EvolutionChat() {
  const [messages, setMessages] = useState([]);
  const [waiting, setWaiting] = useState(false);
  
  const handleResponse = (response) => {
    fetch('/evolution/respond', {
      method: 'POST',
      body: JSON.stringify({ response })
    });
  };
  
  return (
    <div className="evolution-chat">
      {messages.map(msg => (
        <div className="message">
          <div className="avatar">🤖</div>
          <div className="content">
            {msg.text}
            {msg.code && <CodeBlock code={msg.code} />}
            {msg.diff && <DiffView diff={msg.diff} />}
          </div>
          {msg.needsConfirmation && (
            <div className="actions">
              <button onClick={() => handleResponse('yes')}>✓ Yes</button>
              <button onClick={() => handleResponse('no')}>✗ No</button>
              <button onClick={() => handleResponse('modify')}>✎ Modify</button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
```

---

## Integration with Observability

```python
# Scheduled job
async def scheduled_evolution_check():
    """Run daily to find weak tools."""
    analyzer = ToolQualityAnalyzer()
    weak_tools = analyzer.get_weak_tools(days=7, min_usage=10)
    
    for tool_report in weak_tools[:3]:  # Top 3 weakest
        if tool_report.recommendation == "QUARANTINE":
            # Auto-start evolution chat
            chat = AgenticEvolutionChat(llm_client, analyzer)
            await chat.start_system_evolution(tool_report.tool_name)
            
            # Notify user in UI
            await notify_user(
                f"🔧 {tool_report.tool_name} needs attention. "
                f"Health: {tool_report.health_score:.0f}/100. "
                f"Click to start evolution."
            )
```

---

## Key Differences from Tool Creation

| Aspect | Tool Creation | Tool Evolution |
|--------|--------------|----------------|
| Flow | Automated pipeline | Conversational chat |
| User Input | Upfront spec | Step-by-step confirmation |
| Context | Capability gap | Observability + code |
| LLM Role | Code generator | Conversational guide |
| Validation | Sandbox tests | Tests + user review |
| UI | Progress bar | Chat interface |

---

## Implementation Priority

1. **Phase 2A** (Week 1-2):
   - `AgenticEvolutionChat` core
   - 5-step conversation flow
   - Integration with ToolQualityAnalyzer
   - Basic UI chat component

2. **Phase 2B** (Week 3-4):
   - LLM message generation
   - Code analysis and diff generation
   - Validation integration
   - WebSocket real-time updates

3. **Phase 2C** (Week 5-6):
   - Scheduled evolution checks
   - User-initiated evolution
   - Modification support
   - Evolution history tracking

---

## Summary

**New Architecture:**
- Conversational agent (like ChatGPT for tool improvement)
- 5 major steps with user confirmation
- Integrates observability data
- Shows code, diffs, test results
- Works for system + user triggers
- Real-time chat UI

**Not like current self-evolution:**
- No hardcoded logic
- No silent background processing
- LLM drives conversation
- User in control at each step
- Transparent and explainable
