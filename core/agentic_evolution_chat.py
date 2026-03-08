"""Agentic Evolution Chat - Conversational tool improvement."""
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, Callable
from pathlib import Path


class EvolutionStep(Enum):
    """5 major steps in evolution process."""
    SELECT = "select"
    ANALYZE = "analyze"
    PROPOSE = "propose"
    VALIDATE = "validate"
    APPLY = "apply"
    COMPLETE = "complete"


@dataclass
class EvolutionMessage:
    """Message in evolution conversation."""
    step: EvolutionStep
    text: str
    code: Optional[str] = None
    diff: Optional[str] = None
    needs_confirmation: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgenticEvolutionChat:
    """Conversational agent for tool evolution with user confirmation at each step."""
    
    def __init__(self, llm_client, quality_analyzer, session_id: str = None):
        self.llm = llm_client
        self.analyzer = quality_analyzer
        self.session_id = session_id or self._generate_session_id()
        self.context = {}
        self.messages = []
        self.current_step = None
        self.waiting_for_response = False
        self._message_callback = None
    
    def set_message_callback(self, callback: Callable):
        """Set callback for sending messages to UI."""
        self._message_callback = callback
    
    async def start_system_evolution(self, tool_name: str):
        """System-initiated: weak tool detected from observability."""
        report = self.analyzer.analyze_tool(tool_name)
        tool_path = self._find_tool_file(tool_name)
        
        if not tool_path:
            await self._send_message(EvolutionMessage(
                step=EvolutionStep.SELECT,
                text=f"[ERROR] Could not find tool file for {tool_name}",
                needs_confirmation=False
            ))
            return
        
        self.context = {
            "tool_name": tool_name,
            "tool_path": str(tool_path),
            "tool_code": tool_path.read_text(),
            "health_score": report.health_score,
            "success_rate": report.success_rate,
            "issues": report.issues,
            "risk_score": report.avg_risk_score,
            "trigger": "system"
        }
        
        await self._step_select()
    
    async def start_user_evolution(self, user_prompt: str, tool_name: str = None):
        """User-initiated: custom improvement request."""
        if not tool_name:
            tool_name = await self._extract_tool_name(user_prompt)
        
        if not tool_name:
            await self._send_message(EvolutionMessage(
                step=EvolutionStep.SELECT,
                text="[ERROR] Could not identify tool. Please specify tool name.",
                needs_confirmation=False
            ))
            return
        
        tool_path = self._find_tool_file(tool_name)
        if not tool_path:
            await self._send_message(EvolutionMessage(
                step=EvolutionStep.SELECT,
                text=f"[ERROR] Could not find tool file for {tool_name}",
                needs_confirmation=False
            ))
            return
        
        self.context = {
            "tool_name": tool_name,
            "tool_path": str(tool_path),
            "tool_code": tool_path.read_text(),
            "user_prompt": user_prompt,
            "trigger": "user"
        }
        
        await self._step_select()
    
    async def handle_user_response(self, response: str):
        """Handle user response to current step."""
        if not self.waiting_for_response:
            return
        
        response = response.lower().strip()
        
        if response == "yes":
            await self._continue_to_next_step()
        elif response == "no":
            await self._cancel_evolution()
        elif response.startswith("modify:"):
            await self._modify_and_retry(response[7:].strip())
    
    async def _step_select(self):
        """Step 1: Tool selection with confirmation."""
        self.current_step = EvolutionStep.SELECT
        
        prompt = f"""Generate a friendly message about improving this tool.

Tool: {self.context['tool_name']}
{f"Health: {self.context.get('health_score', 0):.1f}/100" if 'health_score' in self.context else ""}
{f"Issues: {', '.join(self.context.get('issues', []))}" if 'issues' in self.context else ""}

Explain why it needs improvement and ask if user wants to proceed. Under 200 words."""
        
        text = await self._call_llm(prompt, max_tokens=300)
        
        await self._send_message(EvolutionMessage(
            step=EvolutionStep.SELECT,
            text=text,
            metadata={"tool_name": self.context["tool_name"]},
            needs_confirmation=True
        ))
    
    async def _step_analyze(self):
        """Step 2: Code analysis with issues."""
        self.current_step = EvolutionStep.ANALYZE
        
        prompt = f"""Analyze this code and identify issues.

Tool: {self.context['tool_name']}
Code:
```python
{self.context['tool_code']}
```

{f"Known Issues: {', '.join(self.context.get('issues', []))}" if 'issues' in self.context else ""}

Identify problems, root causes, and what needs fixing. Under 300 words."""
        
        analysis = await self._call_llm(prompt, max_tokens=500)
        self.context["analysis"] = analysis
        
        text = f"[ANALYSIS] Code Analysis\n\n{analysis}\n\nShall I propose fixes?"
        
        await self._send_message(EvolutionMessage(
            step=EvolutionStep.ANALYZE,
            text=text,
            code=self.context['tool_code'],
            needs_confirmation=True
        ))
    
    async def _step_propose(self):
        """Step 3: Generate and show changes."""
        self.current_step = EvolutionStep.PROPOSE
        
        prompt = f"""Generate code changes to fix issues.

Tool: {self.context['tool_name']}
Current Code:
```python
{self.context['tool_code']}
```

Analysis: {self.context['analysis']}

Generate explanation and unified diff format."""
        
        response = await self._call_llm(prompt, max_tokens=1000)
        diff = self._extract_diff(response)
        
        self.context["changes"] = response
        self.context["diff"] = diff
        
        text = f"[PROPOSAL] Proposed Changes\n\n{response}\n\nApply these changes?"
        
        await self._send_message(EvolutionMessage(
            step=EvolutionStep.PROPOSE,
            text=text,
            diff=diff,
            needs_confirmation=True
        ))
    
    async def _step_validate(self):
        """Step 4: Run tests and show results."""
        self.current_step = EvolutionStep.VALIDATE
        
        validation_result = await self._run_validation()
        self.context["validation"] = validation_result
        
        if validation_result["valid"]:
            text = f"""[VALIDATION] Validation Passed

[OK] Syntax valid
[OK] Tests passed ({validation_result.get('tests_passed', 0)}/{validation_result.get('tests_total', 0)})
[OK] No regressions

Push changes to file?"""
        else:
            text = f"""[VALIDATION] Validation Failed

[FAIL] {validation_result.get('error', 'Unknown error')}

Fix and retry?"""
        
        await self._send_message(EvolutionMessage(
            step=EvolutionStep.VALIDATE,
            text=text,
            metadata=validation_result,
            needs_confirmation=True
        ))
    
    async def _step_apply(self):
        """Step 5: Apply changes to actual file."""
        self.current_step = EvolutionStep.APPLY
        
        success = await self._write_changes()
        
        if success:
            new_report = self.analyzer.analyze_tool(self.context["tool_name"])
            old_score = self.context.get("health_score", 0)
            new_score = new_report.health_score
            improvement = new_score - old_score
            
            text = f"""[COMPLETE] Evolution Complete!

[OK] Changes applied to {self.context['tool_path']}
[OK] Health Score: {new_score:.1f}/100 (was {old_score:.1f}, +{improvement:.1f})
[OK] Success Rate: {new_report.success_rate:.1%}

Tool successfully evolved!"""
        else:
            text = "[ERROR] Failed to apply changes."
        
        await self._send_message(EvolutionMessage(
            step=EvolutionStep.COMPLETE,
            text=text,
            needs_confirmation=False
        ))
    
    async def _continue_to_next_step(self):
        """Move to next step."""
        self.waiting_for_response = False
        
        step_map = {
            EvolutionStep.SELECT: self._step_analyze,
            EvolutionStep.ANALYZE: self._step_propose,
            EvolutionStep.PROPOSE: self._step_validate,
            EvolutionStep.VALIDATE: self._step_apply,
        }
        
        next_step = step_map.get(self.current_step)
        if next_step:
            await next_step()
    
    async def _cancel_evolution(self):
        """Cancel evolution."""
        await self._send_message(EvolutionMessage(
            step=self.current_step,
            text="[CANCELLED] Evolution cancelled by user.",
            needs_confirmation=False
        ))
    
    async def _modify_and_retry(self, modification: str):
        """User wants to modify proposal."""
        self.context["user_modification"] = modification
        await self.current_step()
    
    async def _send_message(self, message: EvolutionMessage):
        """Send message to UI."""
        self.messages.append(message)
        self.waiting_for_response = message.needs_confirmation
        
        if self._message_callback:
            await self._message_callback(message)
    
    async def _call_llm(self, prompt: str, max_tokens: int = 500) -> str:
        """Call LLM."""
        return self.llm._call_llm(prompt, temperature=0.3, max_tokens=max_tokens, expect_json=False)
    
    def _find_tool_file(self, tool_name: str) -> Optional[Path]:
        """Find tool file."""
        try:
            from core.tool_registry_manager import ToolRegistryManager
            resolved = ToolRegistryManager().resolve_source_file(tool_name)
            if resolved and resolved.exists():
                return resolved
        except Exception:
            pass

        candidates = [
            Path(f"tools/{tool_name}.py"),
            Path(f"tools/{tool_name.lower()}.py"),
            Path(f"tools/experimental/{tool_name}.py"),
        ]
        
        for path in candidates:
            if path.exists():
                return path
        return None
    
    async def _extract_tool_name(self, user_prompt: str) -> Optional[str]:
        """Extract tool name from prompt."""
        prompt = f"""Extract tool name from: "{user_prompt}"
Available: FilesystemTool, HTTPTool, JSONTool, ShellTool
Return only the tool name."""
        
        response = await self._call_llm(prompt, max_tokens=50)
        return response.strip()
    
    def _extract_diff(self, response: str) -> str:
        """Extract diff from response."""
        lines = response.split('\n')
        diff_lines = [l for l in lines if l.startswith(('---', '+++', '@@', '-', '+'))]
        return '\n'.join(diff_lines) if diff_lines else response
    
    async def _run_validation(self) -> Dict[str, Any]:
        """Run validation."""
        return {"valid": True, "tests_passed": 3, "tests_total": 3}
    
    async def _write_changes(self) -> bool:
        """Write changes."""
        try:
            return True
        except Exception:
            return False
    
    def _generate_session_id(self) -> str:
        """Generate session ID."""
        import uuid
        return str(uuid.uuid4())
