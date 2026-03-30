"""Response formatting and component building for chat responses."""
from typing import List, Dict, Any
import ast


def _normalize_wra_sources(raw_sources: list) -> list:
    """Normalize WRA sources into a table-friendly shape."""
    normalized = []
    for idx, source in enumerate(raw_sources[:10], start=1):
        if isinstance(source, dict):
            url = source.get("url") or source.get("href") or source.get("link") or ""
            title = source.get("title") or source.get("text") or f"Source {idx}"
            snippet = source.get("snippet") or source.get("description") or source.get("content") or ""
        else:
            url = str(source).strip()
            title = f"Source {idx}"
            snippet = ""
        if not url:
            continue
        normalized.append({
            "title": title,
            "url": url,
            "snippet": snippet,
        })
    return normalized


def build_wra_components(answer: str, raw_data: list) -> list:
    """Build clean UI components for WRA results."""
    from infrastructure.analysis.output_analyzer import OutputAnalyzer
    
    search_results = []
    components = []

    for item in raw_data:
        if isinstance(item, dict):
            # Structured done extras
            if item.get("sources") and isinstance(item["sources"], list):
                search_results.extend(_normalize_wra_sources(item["sources"]))
                continue
            if item.get("key_facts") and isinstance(item["key_facts"], list):
                components.append({
                    "type": "list", "renderer": "list",
                    "items": item["key_facts"], "title": "Key Facts"
                })
                continue
            if item.get("items") and isinstance(item["items"], list):
                components.append({
                    "type": "list", "renderer": "list",
                    "items": item["items"], "title": "Results"
                })
                continue
            if item.get("value"):
                components.append({
                    "type": "text_content", "renderer": "text_content",
                    "content": f"{item['value']} {item.get('unit', '')}".strip(),
                    "title": "Value"
                })
                continue
            
            # Tables
            if item.get("tables"):
                for tbl in item["tables"][:5]:
                    if tbl.get("rows"):
                        components.append({
                            "type": "table", "renderer": "table",
                            "data": tbl["rows"],
                            "title": tbl.get("caption") or "Table",
                            "columns": tbl.get("headers") or OutputAnalyzer._extract_columns(tbl["rows"]),
                        })
                continue
            
            # Lists
            if item.get("lists"):
                for lst in item["lists"][:5]:
                    if lst.get("items"):
                        components.append({
                            "type": "list", "renderer": "list",
                            "items": lst["items"]
                        })
                continue
            
            # Article body
            if item.get("body") and len(str(item["body"])) > 100:
                components.append({
                    "type": "text_content", "renderer": "text_content",
                    "content": item["body"],
                    "title": item.get("title") or "Article",
                    "source_url": item.get("url", ""),
                })
                continue
            
            # Links
            if isinstance(item.get("links"), list) and item["links"] and isinstance(item["links"][0], dict) and "href" in item["links"][0]:
                components.append({
                    "type": "table", "renderer": "table",
                    "data": item["links"][:50],
                    "title": "Links", "columns": ["text", "href", "title"],
                })
                continue

        # Search results list
        if isinstance(item, list) and item and isinstance(item[0], dict):
            for r in item:
                if isinstance(r, dict) and (r.get("url") or r.get("link")):
                    search_results.append({
                        "title": r.get("title", ""),
                        "url": r.get("url") or r.get("link", ""),
                        "snippet": r.get("snippet") or r.get("description") or r.get("content", ""),
                    })
            continue

        # Stringified list fallback
        if isinstance(item, str):
            try:
                parsed = ast.literal_eval(item)
                if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                    item = parsed
            except Exception:
                pass
        if isinstance(item, list):
            for r in item:
                if isinstance(r, dict) and (r.get("url") or r.get("link")):
                    search_results.append({
                        "title": r.get("title", ""),
                        "url": r.get("url") or r.get("link", ""),
                        "snippet": r.get("snippet") or r.get("description") or r.get("content", ""),
                    })

    if search_results:
        components.append({
            "type": "table",
            "renderer": "table",
            "data": search_results[:10],
            "title": "Sources",
            "columns": ["title", "url", "snippet"],
        })
    
    return components


def format_tool_history_for_display(executed_history: List[Dict]) -> List[Dict]:
    """Format tool execution history for UI display with steps and errors visible."""
    formatted = []
    for i, step in enumerate(executed_history, 1):
        formatted.append({
            "step": i,
            "tool": step.get("tool"),
            "operation": step.get("operation"),
            "success": step.get("success"),
            "execution_time": step.get("execution_time", 0),
            "duration": f"{step.get('execution_time', 0):.2f}s",
            "error": step.get("error") if not step.get("success") else None,
            "data_preview": str(step.get("data", ""))[:200] if step.get("success") else None,
        })
    return formatted
