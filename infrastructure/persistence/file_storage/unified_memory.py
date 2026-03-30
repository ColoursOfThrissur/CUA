"""
UnifiedMemory — single search interface across all CUA memory stores.

Stores searched:
  1. StrategicMemory   — past execution plans (Jaccard similarity)
  2. MemorySystem      — conversation messages + learned patterns
  3. ImprovementMemory — past improvement attempts by file/description

Usage:
    from infrastructure.persistence.file_storage.unified_memory import get_unified_memory
    results = get_unified_memory().search("web scraping python")
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_STOPWORDS = {"the", "and", "for", "with", "this", "that", "from", "have",
              "will", "can", "you", "are", "was", "not", "but", "all", "how"}


def _tokenize(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower())
            if len(t) > 2 and t not in _STOPWORDS}


def _score(query_tokens: set, text: str) -> float:
    """Jaccard similarity between query tokens and text tokens."""
    doc_tokens = _tokenize(text)
    if not doc_tokens:
        return 0.0
    return len(query_tokens & doc_tokens) / len(query_tokens | doc_tokens)


class UnifiedMemory:
    """Facade that searches all memory stores and returns ranked results."""

    def __init__(self, memory_system=None, improvement_memory=None):
        self._ms = memory_system
        self._im = improvement_memory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.10,
    ) -> List[Dict[str, Any]]:
        """
        Search all memory stores for content relevant to *query*.

        Returns list of dicts sorted by relevance score (descending):
          {source, score, content, metadata}
        """
        if not query or not query.strip():
            return []

        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        results: List[Dict[str, Any]] = []

        results.extend(self._search_strategic(q_tokens))
        results.extend(self._search_patterns(q_tokens))
        results.extend(self._search_improvements(q_tokens, query))
        if session_id:
            results.extend(self._search_conversation(q_tokens, session_id))

        # Deduplicate by content hash, keep highest score
        seen: Dict[int, Dict] = {}
        for r in results:
            key = hash(r["content"][:120])
            if key not in seen or r["score"] > seen[key]["score"]:
                seen[key] = r

        ranked = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
        return [r for r in ranked[:top_k] if r["score"] >= min_score]

    def search_for_planning(self, goal: str, skill_name: str = "") -> str:
        """
        Returns a compact string summary of relevant memory for LLM prompt injection.
        Used by TaskPlanner as a richer alternative to strategic_memory.retrieve().
        """
        results = self.search(goal, top_k=5)
        if not results:
            return "No relevant memory found."

        lines = []
        for r in results:
            src = r["source"]
            score = r["score"]
            content = r["content"][:200]
            lines.append(f"[{src} | relevance={score:.2f}] {content}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Per-store search helpers
    # ------------------------------------------------------------------

    def _search_strategic(self, q_tokens: set) -> List[Dict]:
        try:
            from infrastructure.persistence.file_storage.strategic_memory import get_strategic_memory
            sm = get_strategic_memory()
            # Use public retrieve() — pass reconstructed query string from tokens
            query = " ".join(q_tokens)
            records = sm.retrieve(query, top_k=10, min_win_rate=0.0)
            results = []
            for rec in records:
                score = _score(q_tokens, rec.goal_sample)
                if score > 0:
                    step_summary = ", ".join(
                        f"{s.get('tool','?')}.{s.get('operation','?')}"
                        for s in rec.steps[:4]
                    )
                    results.append({
                        "source": "strategic_plan",
                        "score": score,
                        "content": f"Goal: {rec.goal_sample} | Steps: {step_summary} | Win: {rec.win_rate():.0%}",
                        "metadata": {
                            "skill": rec.skill_name,
                            "win_rate": rec.win_rate(),
                            "success_count": rec.success_count,
                        },
                    })
            return results
        except Exception:
            return []

    def _search_patterns(self, q_tokens: set) -> List[Dict]:
        if not self._ms:
            return []
        try:
            results = []
            for ptype in ("successful_goals", "failed_attempts", "tool_usage"):
                for pattern in self._ms.get_patterns(ptype, limit=20):
                    text = pattern.get("goal", "") or str(pattern)
                    score = _score(q_tokens, text)
                    if score > 0:
                        results.append({
                            "source": f"pattern:{ptype}",
                            "score": score,
                            "content": text[:200],
                            "metadata": {"pattern_type": ptype},
                        })
            return results
        except Exception:
            return []

    def _search_improvements(self, q_tokens: set, query: str) -> List[Dict]:
        if not self._im:
            return []
        try:
            results = []

            # Failed attempts — cautionary, downweighted
            failed = self._im.get_failed_attempts(days=30)
            for attempt in failed:
                text = f"{attempt.get('description', '')} {attempt.get('file_path', '')}"
                score = _score(q_tokens, text)
                if score > 0:
                    results.append({
                        "source": "improvement_memory",
                        "score": score * 0.8,
                        "content": f"[FAILED] {attempt.get('description', '')} in {attempt.get('file_path', '')}",
                        "metadata": {
                            "change_type": attempt.get("change_type"),
                            "error": attempt.get("error_message", "")[:100],
                        },
                    })

            # Successful improvements — positive signal, full weight
            if hasattr(self._im, 'get_successful_attempts'):
                for attempt in self._im.get_successful_attempts(days=30):
                    text = f"{attempt.get('description', '')} {attempt.get('file_path', '')}"
                    score = _score(q_tokens, text)
                    if score > 0:
                        results.append({
                            "source": "improvement_memory",
                            "score": score,
                            "content": f"[SUCCESS] {attempt.get('description', '')} in {attempt.get('file_path', '')}",
                            "metadata": {"change_type": attempt.get("change_type")},
                        })

            return results
        except Exception:
            return []

    def _search_conversation(self, q_tokens: set, session_id: str) -> List[Dict]:
        if not self._ms:
            return []
        try:
            messages = self._ms.get_recent_messages(session_id, limit=30)
            results = []
            for msg in messages:
                if msg.role == "system":
                    continue
                score = _score(q_tokens, msg.content)
                if score > 0:
                    results.append({
                        "source": f"conversation:{msg.role}",
                        "score": score * 0.7,  # downweight — conversation is context, not knowledge
                        "content": msg.content[:200],
                        "metadata": {"role": msg.role, "timestamp": msg.timestamp},
                    })
            return results
        except Exception:
            return []


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_instance: Optional[UnifiedMemory] = None


def get_unified_memory(memory_system=None, improvement_memory=None) -> UnifiedMemory:
    global _instance
    if _instance is None:
        _instance = UnifiedMemory(memory_system, improvement_memory)
    elif memory_system and _instance._ms is None:
        _instance._ms = memory_system
    elif improvement_memory and _instance._im is None:
        _instance._im = improvement_memory
    return _instance
