"""Normalize unified diff text into a reusable payload shape."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_diff_payload(patch: str) -> Dict[str, Any]:
    text = patch or ""
    lines: List[Dict[str, Any]] = []
    files: List[Dict[str, Any]] = []
    current_file: Optional[str] = None
    additions = 0
    deletions = 0

    for raw in text.splitlines():
        if raw.startswith("+++ b/"):
            current_file = raw[6:]
            if current_file not in {item["path"] for item in files}:
                files.append({"path": current_file})
            lines.append({"type": "meta", "content": raw, "path": current_file})
            continue
        if raw.startswith("--- a/"):
            lines.append({"type": "meta", "content": raw, "path": current_file})
            continue
        if raw.startswith("@@") or raw.startswith("diff --git"):
            lines.append({"type": "meta", "content": raw, "path": current_file})
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            additions += 1
            lines.append({"type": "add", "content": raw[1:], "path": current_file})
            continue
        if raw.startswith("-") and not raw.startswith("---"):
            deletions += 1
            lines.append({"type": "remove", "content": raw[1:], "path": current_file})
            continue
        lines.append({"type": "context", "content": raw, "path": current_file})

    return {
        "raw_patch": text,
        "files": files,
        "stats": {
            "files_changed": len(files),
            "additions": additions,
            "deletions": deletions,
            "lines_changed": additions + deletions,
        },
        "lines": lines,
    }
