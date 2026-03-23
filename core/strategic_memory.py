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
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

_STORE_FILE = Path("data/strategic_memory.json")
_MAX_RECORDS = 200   # cap to avoid unbounded growth
_MIN_SIMILARITY = 0.30  # Jaccard threshold for "similar enough"


@dataclass
class PlanRecord:
    fingerprint: str
    goal_sample: str
    skill_name: str
    steps: List[Dict]          # [{tool, operation, domain}]
    tokens: List[str]
    success_count: int = 0
    fail_count: int = 0
    last_used: str = field(default_factory=lambda: datetime.utcnow().isoformat())
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
        self.last_used = datetime.utcnow().isoformat()


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

        if fp in self._records:
            rec = self._records[fp]
            rec.record_outcome(success, duration_s)
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
            )
            rec.record_outcome(success, duration_s)
            self._records[fp] = rec

        self._evict()
        self._save()

    def retrieve(
        self,
        goal: str,
        skill_name: str = "",
        top_k: int = 3,
        min_win_rate: float = 0.5,
    ) -> List[PlanRecord]:
        """
        Return up to top_k records similar to *goal* that have a good win rate.
        Similarity = Jaccard on goal tokens.
        """
        query_tokens = set(self._tokenize(goal))
        if not query_tokens:
            return []

        scored: List[tuple[float, PlanRecord]] = []
        for rec in self._records.values():
            if rec.win_rate() < min_win_rate:
                continue
            rec_tokens = set(rec.tokens)
            if not rec_tokens:
                continue
            jaccard = len(query_tokens & rec_tokens) / len(query_tokens | rec_tokens)
            if jaccard < _MIN_SIMILARITY:
                continue
            # Slight boost for same skill
            if skill_name and rec.skill_name == skill_name:
                jaccard = min(1.0, jaccard + 0.10)
            scored.append((jaccard, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [rec for _, rec in scored[:top_k]]

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
        stopwords = {"the", "and", "for", "with", "this", "that", "from", "have",
                     "will", "can", "you", "are", "was", "not", "but", "all"}
        return [t for t in re.findall(r"[a-z0-9]+", text.lower())
                if len(t) > 2 and t not in stopwords]

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

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for fp, rec in self._records.items():
            d = asdict(rec)
            d.pop("_duration_total", None)
            data[fp] = d
        self._file.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            raw = json.loads(self._file.read_text())
            for fp, d in raw.items():
                d.pop("_duration_total", None)
                try:
                    self._records[fp] = PlanRecord(**d)
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
