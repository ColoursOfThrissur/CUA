"""Artifact extraction and domain policies for iterative tool use."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import re


def build_artifacts(executed_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []
    for call in executed_calls:
        tool = call.get("tool")
        operation = call.get("operation")
        data = call.get("data")
        if not isinstance(data, dict):
            continue

        if tool == "WebAccessTool":
            if isinstance(data.get("results"), list):
                artifacts.append({
                    "type": "search_results",
                    "tool": tool,
                    "operation": operation,
                    "results": [
                        {"title": item.get("title"), "url": item.get("url")}
                        for item in data["results"]
                        if isinstance(item, dict)
                    ],
                })
            if isinstance(data.get("links"), list):
                artifacts.append({
                    "type": "links",
                    "tool": tool,
                    "operation": operation,
                    "links": [
                        {"label": item.get("label"), "url": item.get("url")}
                        for item in data["links"]
                        if isinstance(item, dict)
                    ],
                })
            if isinstance(data.get("sources"), list):
                artifacts.append({
                    "type": "source_collection",
                    "tool": tool,
                    "operation": operation,
                    "sources": [
                        {"url": item.get("url"), "success": item.get("success"), "mode": item.get("mode")}
                        for item in data["sources"]
                        if isinstance(item, dict)
                    ],
                })
            if operation in {"fetch_url", "open_page", "get_current_page", "get_current_page_details"} and data.get("content"):
                artifacts.append({
                    "type": "source_page",
                    "tool": tool,
                    "operation": operation,
                    "url": data.get("url"),
                    "title": data.get("title"),
                    "content": data.get("content"),
                })
            elif operation == "search_web" and data.get("content"):
                artifacts.append({
                    "type": "search_page",
                    "tool": tool,
                    "operation": operation,
                    "url": data.get("url"),
                    "content": data.get("content"),
                })

        if tool == "ContextSummarizerTool" and operation == "summarize_text":
            artifacts.append({
                "type": "summary",
                "tool": tool,
                "operation": operation,
                "summary": data.get("summary"),
            })

    return artifacts


def build_artifact_inventory(artifacts: List[Dict[str, Any]]) -> Dict[str, int]:
    inventory: Dict[str, int] = {}
    for artifact in artifacts:
        artifact_type = artifact.get("type", "unknown")
        inventory[artifact_type] = inventory.get(artifact_type, 0) + 1
    return inventory


def summarize_artifacts_for_prompt(artifacts: List[Dict[str, Any]], limit: int = 6) -> str:
    if not artifacts:
        return "No artifacts yet."

    lines: List[str] = []
    for artifact in artifacts[:limit]:
        artifact_type = artifact.get("type", "unknown")
        if artifact_type == "search_results":
            urls = [item.get("url") for item in artifact.get("results", [])[:3] if item.get("url")]
            lines.append(f"- search_results: {len(artifact.get('results', []))} results; sample={urls}")
        elif artifact_type == "links":
            urls = [item.get("url") for item in artifact.get("links", [])[:3] if item.get("url")]
            lines.append(f"- links: {len(artifact.get('links', []))} links; sample={urls}")
        elif artifact_type == "source_page":
            lines.append(f"- source_page: url={artifact.get('url')} title={artifact.get('title')}")
        elif artifact_type == "source_collection":
            urls = [item.get("url") for item in artifact.get("sources", [])[:3] if item.get("url")]
            lines.append(f"- source_collection: {len(artifact.get('sources', []))} sources; sample={urls}")
        elif artifact_type == "summary":
            lines.append(f"- summary: {str(artifact.get('summary', ''))[:120]}")
        else:
            lines.append(f"- {artifact_type}")
    return "\n".join(lines)


def choose_web_next_action(artifacts: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    inventory = build_artifact_inventory(artifacts)
    if inventory.get("source_page", 0) > 0 or inventory.get("source_collection", 0) > 0:
        # We have content, check if we need to summarize
        has_summary = inventory.get("summary", 0) > 0
        if not has_summary:
            # Find the most recent source page content for summarization
            for artifact in reversed(artifacts):
                if artifact.get("type") == "source_page" and artifact.get("content"):
                    return [{
                        "tool": "ContextSummarizerTool",
                        "operation": "summarize_text",
                        "parameters": {
                            "input_text": artifact.get("content", "")[:8000],  # Limit input size
                            "summary_length": 150
                        },
                    }]
        return None

    candidate_urls: List[str] = []
    # Prioritize specific article URLs over generic ones
    priority_urls: List[str] = []
    
    for artifact in artifacts:
        if artifact.get("type") == "search_results":
            for item in artifact.get("results", []):
                url = item.get("url")
                title = item.get("title", "")
                if _is_actionable_source_url(url):
                    # Prioritize Wikipedia articles and specific content pages
                    if _is_priority_url(url, title):
                        if url not in priority_urls:
                            priority_urls.append(url)
                    elif url not in candidate_urls:
                        candidate_urls.append(url)
        elif artifact.get("type") == "links":
            for item in artifact.get("links", []):
                url = item.get("url")
                label = item.get("label", "")
                if _is_actionable_source_url(url):
                    if _is_priority_url(url, label):
                        if url not in priority_urls:
                            priority_urls.append(url)
                    elif url not in candidate_urls:
                        candidate_urls.append(url)
        elif artifact.get("type") == "search_page":
            for url in _extract_urls_from_text(artifact.get("content", "")):
                if _is_actionable_source_url(url):
                    if _is_priority_url(url, ""):
                        if url not in priority_urls:
                            priority_urls.append(url)
                    elif url not in candidate_urls:
                        candidate_urls.append(url)

    # Use priority URLs first, then fallback to regular candidates
    best_url = None
    if priority_urls:
        best_url = priority_urls[0]
    elif candidate_urls:
        best_url = candidate_urls[0]
    
    if not best_url:
        return None

    return [{
        "tool": "WebAccessTool",
        "operation": "fetch_url",
        "parameters": {"url": best_url, "mode": "auto"},
    }]


def allowed_tools_for_artifacts(
    category: Optional[str],
    preferred_tools: List[str],
    executed_calls: List[Dict[str, Any]],
    artifacts: List[Dict[str, Any]],
) -> List[str]:
    allowed = list(dict.fromkeys(
        (preferred_tools or []) + [call.get("tool") for call in executed_calls if call.get("tool")]
    ))
    if category == "web":
        inventory = build_artifact_inventory(artifacts)
        if inventory.get("source_page", 0) == 0 and inventory.get("source_collection", 0) == 0:
            return [tool for tool in allowed if tool == "WebAccessTool"]
    return allowed


def _extract_urls_from_text(text: str) -> List[str]:
    if not text:
        return []
    return re.findall(r'https?://[^\s)>\]]+', text)


def _is_actionable_source_url(url: Optional[str]) -> bool:
    if not url or not isinstance(url, str):
        return False
    host = (urlparse(url).netloc or "").lower()
    if not host:
        return False
    blocked_hosts = {
        "duckduckgo.com",
        "www.google.com",
        "google.com",
        "duck.ai",
        "example.com",
        "www.example.com",
    }
    return host not in blocked_hosts


def _is_priority_url(url: Optional[str], title_or_label: str = "") -> bool:
    """Check if URL should be prioritized for fetching (specific articles vs homepages)."""
    if not url:
        return False
    
    url_lower = url.lower()
    text_lower = (title_or_label or "").lower()
    
    # Wikipedia articles are high priority
    if "/wiki/" in url_lower and "wikipedia.org" in url_lower:
        # Avoid disambiguation and generic pages
        if not any(term in url_lower for term in ["disambiguation", "category:", "template:", "help:"]):
            return True
    
    # Specific article patterns
    priority_patterns = [
        "/article/", "/articles/", "/post/", "/posts/", "/blog/", "/news/",
        "/research/", "/paper/", "/papers/", "/publication/", "/publications/",
        "/guide/", "/tutorial/", "/documentation/", "/docs/"
    ]
    
    if any(pattern in url_lower for pattern in priority_patterns):
        return True
    
    # Check title/label for content indicators
    content_indicators = [
        "artificial general intelligence", "agi", "development", "research",
        "machine learning", "ai research", "artificial intelligence"
    ]
    
    if any(indicator in text_lower for indicator in content_indicators):
        return True
    
    # Avoid generic homepages
    homepage_patterns = [
        "://en.wikipedia.org$", "://www.wikipedia.org$", "://wikipedia.org$",
        "://github.com$", "://www.github.com$",
        "://reddit.com$", "://www.reddit.com$"
    ]
    
    if any(re.search(pattern, url_lower) for pattern in homepage_patterns):
        return False
    
    return False
