"""
StrategicMemory — persists successful execution plans and retrieves similar
ones to bias the TaskPlanner toward approaches that have worked before.

Storage: data/strategic_memory.json  (simple JSON, no extra deps)

Each record:
  {
    "fingerprint": "sha1 of normalised goal tokens",
    "goal_sample": "first 120 chars of original goal",
    "skill_name": "web_research",
    "steps": [ {tool, operation, domain} ... ],   # lightweight — no params
    "success_count": 3,
    "fail_count": 1,
    "last_used": "ISO timestamp",
    "avg_duration_s": 4.2,
    "tokens": ["search", "web", ...]               # for similarity matching
  }
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

_STORE_FILE = Path("data/strategic_memory.json")
_MAX_RECORDS = 200   # cap to avoid unbounded growth
_MIN_SIMILARITY = 0.22  # hybrid threshold for "similar enough"
_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "have",
    "will", "can", "you", "are", "was", "not", "but", "all", "your",
    "into", "about", "than", "then",
}
_CANONICAL_TOKENS = {
    "fetch": "get",
    "retrieve": "get",
    "download": "get",
    "grab": "get",
    "collect": "get",
    "financials": "financial",
    "finances": "financial",
    "stocks": "stock",
    "shares": "stock",
    "equities": "stock",
    "prices": "price",
    "quotes": "quote",
    "documents": "document",
    "files": "file",
    "folders": "folder",
    "directories": "folder",
    "repositories": "repo",
    "repository": "repo",
    "source": "code",
    "sources": "code",
    "webpage": "web",
    "website": "web",
    "browser": "web",
}
_SEMANTIC_GROUPS = {
    "finance": {"stock", "financial", "market", "ticker", "quote", "price", "equity"},
    "web": {"web", "site", "url", "page", "browse", "browser", "internet", "online"},
    "file": {"file", "folder", "document", "path", "directory", "storage"},
    "code": {"code", "repo", "function", "script", "module", "workspace", "program"},
}
_ALIASES = {
    "aapl": {"apple", "ticker", "stock", "financial"},
    "apple": {"aapl"},
    "msft": {"microsoft", "ticker", "stock", "financial"},
    "microsoft": {"msft"},
    "googl": {"google", "ticker", "stock", "financial"},
    "google": {"googl"},
}


def _get_min_win_rate() -> float:
    """Read min_win_rate from config.yaml, fall back to 0.5."""
    try:
        from shared.config.config_manager import get_config
        config = get_config()
        strategic = getattr(config, "strategic_memory", None)
        if strategic and hasattr(strategic, "min_win_rate"):
            return float(strategic.min_win_rate)
        return 0.5
    except Exception:
        return 0.5


@dataclass
class PlanRecord:
    fingerprint: str
    goal_sample: str
    skill_name: str
    steps: List[Dict]          # [{tool, operation, domain}]
    tokens: List[str]
    semantic_terms: List[str] = field(default_factory=list)
    success_count: int = 0
    fail_count: int = 0
    last_used: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    avg_duration_s: float = 0.0
    _duration_total: float = field(default=0.0, repr=False)

    def win_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total else 0.0

    def record_outcome(self, success: bool, duration_s: float = 0.0):
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1
        self._duration_total += duration_s
        total = self.success_count + self.fail_count
        self.avg_duration_s = round(self._duration_total / total, 2)
        self.last_used = datetime.now(timezone.utc).isoformat()


class StrategicMemory:
    """
    Stores and retrieves plan patterns.

    Used by:
      TaskPlanner  — retrieve(goal) → inject examples into prompt
      AutonomousAgent — record(plan, success) → update stats
    """

    def __init__(self, store_file: Path = _STORE_FILE):
        self._file = store_file
        self._records: Dict[str, PlanRecord] = {}
        self._dirty = False
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        goal: str,
        skill_name: str,
        steps: List[Dict],
        success: bool,
        duration_s: float = 0.0,
    ) -> None:
        """Record the outcome of a plan execution."""
        fp = self._fingerprint(goal)
        tokens = self._tokenize(goal)
        semantic_terms = self._semantic_terms(base_tokens=tokens)

        if fp in self._records:
            rec = self._records[fp]
            rec.record_outcome(success, duration_s)
            if not rec.semantic_terms:
                rec.semantic_terms = semantic_terms
        else:
            # Lightweight step summary — no parameters stored
            step_summary = [
                {"tool": s.get("tool_name", ""), "operation": s.get("operation", ""), "domain": s.get("domain", "")}
                for s in (steps or [])
            ]
            rec = PlanRecord(
                fingerprint=fp,
                goal_sample=goal[:120],
                skill_name=skill_name or "",
                steps=step_summary,
                tokens=tokens,
                semantic_terms=semantic_terms,
            )
            rec.record_outcome(success, duration_s)
            self._records[fp] = rec

        self._evict()
        self._dirty = True
        self._flush()

    def retrieve(
        self,
        goal: str,
        skill_name: str = "",
        top_k: int = 3,
        min_win_rate: Optional[float] = None,
    ) -> List[PlanRecord]:
        """
        Return up to top_k records similar to *goal* that have a good win rate.
        Similarity uses a hybrid of lexical overlap, semantic term expansion,
        and character n-gram similarity.
        min_win_rate defaults to config value (strategic_memory.min_win_rate) or 0.5.
        """
        if min_win_rate is None:
            min_win_rate = _get_min_win_rate()
        query_tokens = set(self._tokenize(goal))
        if not query_tokens:
            return []
        query_terms = set(self._semantic_terms(base_tokens=list(query_tokens)))
        query_ngrams = self._char_ngrams(goal)

        now = datetime.now(timezone.utc)
        scored: List[tuple[float, PlanRecord]] = []
        for rec in self._records.values():
            if rec.win_rate() < min_win_rate:
                continue
            rec_tokens = set(rec.tokens)
            if not rec_tokens:
                continue
            lexical = len(query_tokens & rec_tokens) / len(query_tokens | rec_tokens)
            rec_terms = set(rec.semantic_terms or self._semantic_terms(base_tokens=rec.tokens))
            semantic = len(query_terms & rec_terms) / len(query_terms | rec_terms) if rec_terms else lexical
            ngram = self._ngram_similarity(query_ngrams, self._char_ngrams(rec.goal_sample))
            semantic_score = max(lexical, semantic, ngram * 0.85)
            if semantic_score < _MIN_SIMILARITY:
                continue
            if skill_name and rec.skill_name == skill_name:
                semantic_score = min(1.0, semantic_score + 0.10)
            score = semantic_score * 0.7 + self._recency_weight(rec.last_used, now) * 0.3
            scored.append((score, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [rec for _, rec in scored[:top_k]]

    @staticmethod
    def _recency_weight(last_used: str, now: datetime, tau_days: float = 30.0) -> float:
        """Exponential decay: 1.0 at t=0, ~0.37 at tau_days, ~0.14 at 2×tau_days."""
        try:
            lu = datetime.fromisoformat(last_used)
            if lu.tzinfo is None:
                lu = lu.replace(tzinfo=timezone.utc)
            delta_days = (now - lu).total_seconds() / 86400.0
            return math.exp(-delta_days / tau_days)
        except Exception:
            return 0.5

    def get_stats(self) -> Dict:
        total = len(self._records)
        successful = sum(1 for r in self._records.values() if r.success_count > 0)
        return {
            "total_patterns": total,
            "patterns_with_successes": successful,
            "top_skills": self._top_skills(5),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _fingerprint(goal: str) -> str:
        normalised = " ".join(sorted(re.findall(r"[a-z0-9]+", goal.lower())))
        return hashlib.sha1(normalised.encode()).hexdigest()[:16]

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [
            _CANONICAL_TOKENS.get(t, t)
            for t in re.findall(r"[a-z0-9]+", text.lower())
            if len(t) > 2 and t not in _STOPWORDS
        ]

    @classmethod
    def _semantic_terms(cls, text: Optional[str] = None, base_tokens: Optional[List[str]] = None) -> List[str]:
        tokens = list(base_tokens or cls._tokenize(text or ""))
        expanded = set(tokens)
        for token in list(tokens):
            canonical = _CANONICAL_TOKENS.get(token, token)
            expanded.add(canonical)
            expanded.update(_ALIASES.get(canonical, set()))
            for group_name, members in _SEMANTIC_GROUPS.items():
                if canonical in members or canonical == group_name:
                    expanded.add(group_name)
                    expanded.update(members)
            if canonical.endswith("ing") and len(canonical) > 5:
                expanded.add(canonical[:-3])
        return sorted(expanded)

    @staticmethod
    def _char_ngrams(text: str, n: int = 3) -> set[str]:
        normalized = re.sub(r"\s+", " ", (text or "").lower()).strip()
        if len(normalized) < n:
            return {normalized} if normalized else set()
        return {normalized[i:i + n] for i in range(len(normalized) - n + 1)}

    @staticmethod
    def _ngram_similarity(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _evict(self) -> None:
        """Keep only the _MAX_RECORDS most recently used records."""
        if len(self._records) <= _MAX_RECORDS:
            return
        sorted_keys = sorted(
            self._records,
            key=lambda k: self._records[k].last_used,
            reverse=True,
        )
        for key in sorted_keys[_MAX_RECORDS:]:
            del self._records[key]

    def _top_skills(self, n: int) -> List[Dict]:
        from collections import Counter
        counts = Counter(r.skill_name for r in self._records.values() if r.skill_name)
        return [{"skill": s, "count": c} for s, c in counts.most_common(n)]

    def _flush(self) -> None:
        """Write to disk only when dirty."""
        if not self._dirty:
            return
        self._save()
        self._dirty = False

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for fp, rec in self._records.items():
            d = asdict(rec)
            d["_duration_total"] = rec._duration_total
            data[fp] = d
        self._file.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            raw = json.loads(self._file.read_text())
            for fp, d in raw.items():
                duration_total = d.pop("_duration_total", 0.0)
                try:
                    rec = PlanRecord(**d)
                    rec._duration_total = duration_total
                    self._records[fp] = rec
                except Exception:
                    pass
        except Exception:
            self._records = {}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_instance: Optional[StrategicMemory] = None


def get_strategic_memory() -> StrategicMemory:
    global _instance
    if _instance is None:
        _instance = StrategicMemory()
    return _instance
