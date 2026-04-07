"""Deterministic session-context compaction helpers."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List


class ContextCompactor:
    """Build compact summaries from longer chat histories without an LLM dependency."""

    def compact_messages(
        self,
        messages: List[Dict[str, Any]],
        active_goal: str | None = None,
        keep_recent: int = 8,
    ) -> Dict[str, Any]:
        keep_recent = max(2, int(keep_recent or 8))
        if len(messages) <= keep_recent + 1:
            return {
                "compacted": False,
                "summary_text": "Session is already compact enough.",
                "retained_messages": list(messages),
                "removed_count": 0,
                "retained_count": len(messages),
                "original_count": len(messages),
            }

        retained = list(messages[-keep_recent:])
        removed = list(messages[:-keep_recent])
        role_counts = Counter((msg.get("role") or "unknown") for msg in removed)

        user_highlights = self._collect_highlights(removed, role="user", limit=3)
        assistant_highlights = self._collect_highlights(removed, role="assistant", limit=2)

        lines = [
            "Compacted session context.",
            f"Earlier messages compacted: {len(removed)}",
            f"Retained recent messages: {len(retained)}",
        ]
        if active_goal:
            lines.append(f"Active goal: {active_goal[:180]}")
        if role_counts:
            lines.append(
                "Earlier role mix: "
                + ", ".join(f"{role}={count}" for role, count in sorted(role_counts.items()))
            )
        if user_highlights:
            lines.append("Earlier user requests:")
            lines.extend(f"- {item}" for item in user_highlights)
        if assistant_highlights:
            lines.append("Earlier assistant responses:")
            lines.extend(f"- {item}" for item in assistant_highlights)

        return {
            "compacted": True,
            "summary_text": "\n".join(lines),
            "retained_messages": retained,
            "removed_count": len(removed),
            "retained_count": len(retained),
            "original_count": len(messages),
        }

    def _collect_highlights(
        self,
        messages: List[Dict[str, Any]],
        role: str,
        limit: int,
    ) -> List[str]:
        highlights: List[str] = []
        seen = set()
        for message in reversed(messages):
            if message.get("role") != role:
                continue
            text = " ".join(str(message.get("content") or "").split())
            if not text:
                continue
            snippet = text[:140]
            if snippet in seen:
                continue
            seen.add(snippet)
            highlights.append(snippet)
            if len(highlights) >= limit:
                break
        highlights.reverse()
        return highlights
