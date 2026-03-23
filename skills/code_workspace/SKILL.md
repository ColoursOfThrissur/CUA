# Code Workspace

## Purpose

Use this skill when the user wants repository-aware coding work performed.

This skill is for:

- reading and understanding code
- editing source files
- generating or evolving implementation
- running validations and tests
- summarizing code changes or diffs

This skill is not primarily for:

- open web research unless it directly supports a coding task
- general local automation unrelated to code work

## Trigger Guidance

Use this skill when the request includes patterns like:

- inspect this codebase
- fix this bug
- implement this feature
- refactor this module
- explain this file
- run tests and update code

## Workflow Guidance

1. Inspect relevant code before proposing changes.
2. Preserve existing architecture where possible.
3. Prefer minimal edits that satisfy the task.
4. Validate with tests or compile checks when feasible.
5. Report risks, gaps, or unverified assumptions clearly.

## Preferred Execution Surfaces

- `FilesystemTool`
- `ShellTool`

This skill also has privileged conceptual linkage to:

- tool creation flow
- tool evolution flow
- validation and testing subsystems

## Verification Guidance

Success is strongest when:

- target files changed as intended
- tests or validation checks pass
- diffs match the requested behavior
- regressions are not introduced in the critical path tested

## Failure Interpretation

Common failure modes:

- incomplete understanding of existing code
- failing validation or tests
- missing project-specific capability
- weak planning for code edits
- dependency or runtime mismatch

## Output Expectations

Prefer outputs such as:

- code summary
- change summary
- diff-oriented explanation
- validation result
- test result

## Fallback Strategy

If full implementation cannot be completed:

- provide the strongest partial result available
- record the missing capability or weak execution area
- preserve enough context for later evolution or follow-up
