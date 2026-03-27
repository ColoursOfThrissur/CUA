# Computer Automation

## Purpose

Use this skill when the user wants local computer actions performed in a controlled way.

This skill is for:

- file operations
- directory inspection
- local command execution
- local task automation
- controlled environment actions that stay within policy

This skill is not primarily for:

- web research
- repository-focused code workflows
- external integration setup unless clearly local and tool-backed

## Trigger Guidance

Use this skill when the request includes patterns like:

- list files
- create or edit a file
- move or organize files
- run a local command
- automate a local workflow
- inspect local system state

## Workflow Guidance

1. Identify whether the request is read-only or write-capable.
2. Prefer least-risk operations first.
3. Respect current permission and path restrictions.
4. Break multi-step local actions into explicit steps.
5. Ask for clarification when the target path or action is ambiguous.

## Preferred Execution Surfaces

- `FilesystemTool`
- `ShellTool`

## Verification Guidance

Success is strongest when:

- expected file or directory changes are observed
- command execution returns expected output
- requested artifact exists at the expected path

## Failure Interpretation

Common failure modes:

- blocked path or policy restriction
- ambiguous target location
- missing local capability
- command execution error
- write limit or file size restrictions

## Output Expectations

Prefer outputs such as:

- file operation summary
- directory listing
- command result
- execution trace
- change confirmation

## Fallback Strategy

If automation cannot proceed safely:

- explain the blocking condition
- fall back to direct tool routing only if still policy-compliant
- record the missing or blocked capability path

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
