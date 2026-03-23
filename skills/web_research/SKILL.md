# Web Research

## Purpose

Use this skill when the user wants information gathered, compared, summarized, or extracted from web sources.

This skill is for:

- finding information on websites
- collecting content from one or more pages
- summarizing findings
- comparing sources
- extracting structured facts from web content

This skill is not primarily for:

- local file automation
- repository editing
- broad desktop control

## Trigger Guidance

Use this skill when the request includes patterns like:

- research this topic
- compare these sources
- summarize this page
- gather information from websites
- extract details from a site
- crawl multiple pages

## Workflow Guidance

1. Clarify the scope if the user’s research target is vague.
2. Prefer safe source gathering first.
3. Prefer `WebAccessTool` for web access so transport choice is handled internally.
4. Use multi-step web plans when needed: search, open, extract current page, then summarize.
5. Prefer lower-friction discovery sources before brittle search flows.
6. If generic search is blocked, fall back to direct source browsing for the domain.
7. Use light crawling only when the user needs a small set of related pages from the same site.
4. Collect raw content before summarization when possible.
5. Preserve source attribution in results.
6. Summarize into structured findings when appropriate.

## Preferred Execution Surfaces

- `WebAccessTool`
- `ContextSummarizerTool`

## Verification Guidance

Success is strongest when at least one of the following is true:

- requested sources were reached
- expected content was extracted
- summary or comparison includes source-backed findings
- structured fields requested by the user were produced

## Failure Interpretation

Common failure modes:

- no relevant source could be accessed
- browser capability missing or weak
- extraction failed on page structure
- summarization produced incomplete output
- request is too broad and needs clarification

## Output Expectations

Prefer outputs such as:

- research summary
- findings list
- source comparison
- extracted structured data
- page content summary

## Fallback Strategy

If no web skill route is feasible:

- fall back to direct capability/tool routing
- record the missing web capability or weak execution path
