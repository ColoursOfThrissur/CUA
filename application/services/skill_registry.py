from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from application.services.skill_loader import SkillLoader
from domain.entities.skill_models import SkillDefinition


@dataclass
class ToolReputation:
    """Rich reputation snapshot for a single tool."""
    tool_name: str
    score: float          # 0.0–1.0 composite
    success_rate: float   # raw success / total
    avg_latency_ms: float
    latency_tier: str     # "fast" <200ms | "ok" <800ms | "slow" >=800ms
    call_volume: int      # total calls seen
    trend: str            # "improving" | "stable" | "degrading" | "unknown"
    recency_boost: float  # 0.0–1.0 how recently used


class SkillRegistry:
    """In-memory registry of skill definitions."""

    def __init__(self, loader: Optional[SkillLoader] = None):
        self.loader = loader or SkillLoader()
        self._skills: Dict[str, SkillDefinition] = {}
        # tool_name -> {success, total, total_latency_ms, last_used}
        self._tool_stats: Dict[str, Dict] = defaultdict(lambda: {
            "success": 0, "total": 0, "total_latency_ms": 0.0, "last_used": 0.0
        })
        # skill_name -> set of learned trigger tokens from real usage
        self._learned_triggers: Dict[str, Set[str]] = defaultdict(set)

    def load_all(self) -> Dict[str, SkillDefinition]:
        self._skills = self.loader.load_all()
        return dict(self._skills)

    def refresh(self) -> Dict[str, SkillDefinition]:
        return self.load_all()

    def get(self, name: str) -> Optional[SkillDefinition]:
        return self._skills.get(name)

    def list_all(self) -> List[SkillDefinition]:
        return list(self._skills.values())

    def list_by_category(self, category: str) -> List[SkillDefinition]:
        return [skill for skill in self._skills.values() if skill.category == category]

    def record_tool_usage(self, tool_name: str, success: bool, latency_ms: float = 0.0) -> None:
        """Called after every tool execution to track real performance."""
        stats = self._tool_stats[tool_name]
        stats["total"] += 1
        stats["total_latency_ms"] += latency_ms
        stats["last_used"] = time.time()
        if success:
            stats["success"] += 1
        # Track a rolling window of last 10 outcomes for trend detection
        window = stats.setdefault("window", [])
        window.append(1 if success else 0)
        if len(window) > 10:
            window.pop(0)

    def get_tool_score(self, tool_name: str) -> float:
        """Returns 0.0-1.0 composite score: success_rate weighted by recency."""
        rep = self.get_tool_reputation(tool_name)
        return rep.score

    def get_tool_avg_latency(self, tool_name: str) -> float:
        stats = self._tool_stats[tool_name]
        if stats["total"] == 0:
            return 0.0
        return stats["total_latency_ms"] / stats["total"]

    def get_tool_reputation(self, tool_name: str) -> ToolReputation:
        """Full reputation object used by ContextAwareToolSelector."""
        stats = self._tool_stats[tool_name]
        total = stats["total"]

        if total == 0:
            return ToolReputation(
                tool_name=tool_name, score=0.5, success_rate=0.5,
                avg_latency_ms=0.0, latency_tier="unknown",
                call_volume=0, trend="unknown", recency_boost=0.0,
            )

        success_rate = stats["success"] / total
        avg_latency = stats["total_latency_ms"] / total

        # Recency: decays to 0 over 1 hour
        age_seconds = time.time() - stats["last_used"]
        recency_boost = max(0.0, 1.0 - age_seconds / 3600)

        # Latency tier
        if avg_latency == 0.0:
            latency_tier = "unknown"
            latency_score = 0.5
        elif avg_latency < 200:
            latency_tier = "fast"
            latency_score = 1.0
        elif avg_latency < 800:
            latency_tier = "ok"
            latency_score = 0.6
        else:
            latency_tier = "slow"
            latency_score = 0.2

        # Trend from rolling window (last 10 calls)
        window = stats.get("window", [])
        if len(window) < 4:
            trend = "unknown"
        else:
            first_half = sum(window[:len(window)//2]) / (len(window)//2)
            second_half = sum(window[len(window)//2:]) / (len(window) - len(window)//2)
            diff = second_half - first_half
            if diff > 0.15:
                trend = "improving"
            elif diff < -0.15:
                trend = "degrading"
            else:
                trend = "stable"

        # Composite score:
        #   55% success_rate  — correctness is most important
        #   20% recency       — prefer tools used recently (warm)
        #   15% latency       — faster is better
        #   10% volume bonus  — more data = more trust (capped at 50 calls)
        volume_bonus = min(1.0, total / 50)
        score = (
            success_rate * 0.55
            + recency_boost * 0.20
            + latency_score * 0.15
            + volume_bonus * 0.10
        )
        # Trend modifier: ±5%
        if trend == "improving":
            score = min(1.0, score + 0.05)
        elif trend == "degrading":
            score = max(0.0, score - 0.05)

        return ToolReputation(
            tool_name=tool_name,
            score=round(score, 3),
            success_rate=round(success_rate, 3),
            avg_latency_ms=round(avg_latency, 1),
            latency_tier=latency_tier,
            call_volume=total,
            trend=trend,
            recency_boost=round(recency_boost, 3),
        )

    def learn_trigger(self, skill_name: str, message_tokens: Set[str]) -> None:
        """Add tokens from a successful execution to in-memory learned triggers."""
        if skill_name in self._skills:
            # only keep meaningful tokens (len > 3, not stopwords)
            stopwords = {"the", "and", "for", "with", "this", "that", "from", "have", "will"}
            useful = {t for t in message_tokens if len(t) > 3 and t not in stopwords}
            self._learned_triggers[skill_name].update(useful)

    def get_learned_triggers(self, skill_name: str) -> Set[str]:
        return self._learned_triggers.get(skill_name, set())

    def to_routing_context(self) -> List[dict]:
        return [
            {
                "name": skill.name,
                "category": skill.category,
                "description": skill.description,
                "trigger_examples": skill.trigger_examples,
                "preferred_tools": skill.preferred_tools,
                "output_types": skill.output_types,
            }
            for skill in self.list_all()
        ]
