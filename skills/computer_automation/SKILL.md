# Computer Automation

## Purpose

Use this skill for local computer operations and desktop automation with visual feedback.

This skill is for:

- **Interactive desktop automation** (open apps, type text, click UI elements)
- **File operations** (read, write, move, delete)
- **Directory inspection** (list, search, organize)
- **Local command execution** (shell commands, scripts)
- **System control** (window management, process control)
- **Screen capture and analysis** (screenshots, UI detection)

This skill is not primarily for:

- web research or browser-based tasks
- repository-focused code workflows
- external integration setup unless clearly local

## Trigger Guidance

Use this skill when the request includes patterns like:

- **Desktop automation**: "open notepad", "launch calculator", "type in application"
- **File operations**: "list files", "create file", "move files"
- **System control**: "list windows", "focus window", "kill process"
- **Screen interaction**: "take screenshot", "click at coordinates", "get mouse position"
- **Local commands**: "run command", "execute script"

## Workflow Guidance

### For Interactive Desktop Tasks (open apps, type text, click UI)

Default to the smallest tool set that can solve the task:

- `SystemControlTool` for launching/focusing apps and windows
- `InputAutomationTool` for typing, clicking, and key presses
- `ScreenPerceptionTool` for screenshots, OCR, and UI inspection

Use `ComputerUseController` only when the task is genuinely multi-step, visually uncertain, or likely to need retries and replanning.

Example: "open notepad and type hello world"
- Prefer: `SystemControlTool` + `InputAutomationTool`
- Use `ComputerUseController.automate_task(...)` if the target app/state is uncertain
- Do not default to `ComputerUseController` for every desktop action

### For Simple File/Command Operations

Use direct tools:

- `FilesystemTool` for file operations
- `ShellTool` for command execution

### For Complex Desktop Workflows

Use `ComputerUseController` when you need:

- visual feedback loops
- retry/adaptation on uncertain UI state
- multi-step interaction across screens/windows
- verified completion instead of one-shot input actions

## Preferred Execution Surfaces

**Priority order:**
1. `FilesystemTool` / `ShellTool` for direct file and command work
2. `SystemControlTool`, `InputAutomationTool`, `ScreenPerceptionTool` for focused desktop actions
3. `ComputerUseController` for complex interactive workflows with feedback/retry needs

## Verification Guidance

Success is strongest when:

- expected file or directory changes are observed
- command execution returns expected output
- requested artifact exists at the expected path
- desktop state changed as requested
- `ComputerUseController` reports verified success with screenshot confirmation when used

## Failure Interpretation

Common failure modes:

- **Visual mismatch**: App did not open or text was not typed
- **Blocked path**: Policy restriction or missing permissions
- **Ambiguous target**: Unclear which window/element to interact with
- **Missing capability**: Required tool or feature not available
- **Command error**: Execution failed or returned error code

## Output Expectations

Prefer outputs such as:

- automation result with verification status
- file operation summary
- directory listing
- command result
- execution trace with screenshots
- change confirmation

## Fallback Strategy

If automation cannot proceed safely:

- try direct desktop primitives before escalating to the controller
- let `ComputerUseController` adapt and retry only for complex workflows
- explain the blocking condition when still failing
- fall back to direct tool routing only if policy-compliant
- record the missing or blocked capability

## Managed Tool Updates
- Added `BenchmarkRunnerTool` for operations: run_benchmark_suite, add_benchmark_case, remove_benchmark_case.

## Managed Workflow Updates
### BenchmarkRunnerTool (create_tool)
- Prefer `BenchmarkRunnerTool` when the task needs: run_benchmark_suite, add_benchmark_case, remove_benchmark_case.
- Updated `BenchmarkRunnerTool` for operations: new workflow support.

### BenchmarkRunnerTool (evolve_tool, tool_evolution)
- Reason: User request: Enhancement opportunity: Add batch processing support. Code quality: HEALTHY, Health: 50/100
- Re-evaluate `BenchmarkRunnerTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.

### BenchmarkRunnerTool (evolve_tool, tool_evolution)
- Reason: User request: Feature enhancements suggested (3 improvements). Code quality: HEALTHY, Health: 95/100
- Re-evaluate `BenchmarkRunnerTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.

### BenchmarkRunnerTool (evolve_tool, tool_evolution)
- Reason: User request: Code quality improvements needed (4 issues identified). Code quality: HEALTHY, Health: 95/100
- Re-evaluate `BenchmarkRunnerTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.

### BenchmarkRunnerTool (evolve_tool, tool_evolution)
- Reason: User request: Low health score (45.9) - Low success rate: 36.8%. Code quality: HEALTHY, Health: 50/100
- Re-evaluate `BenchmarkRunnerTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.
