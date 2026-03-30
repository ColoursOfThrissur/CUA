"""
Decision Engine — unified scoring across planner, tool selector, and capability resolver.

Replaces fragmented confidence values with a single scored decision:
  score(context) → DecisionResult(best_strategy, confidence, fallback_plan, reasoning)

Scoring inputs (all optional — engine degrades gracefully on missing data):
  - intent_signals   : keyword/semantic signals from the request
  - skill_scores     : {skill_name: float} from SkillSelector
  - tool_reputations : {tool_name: ToolReputation} from SkillRegistry
  - history_signals  : {win_rate, avg_duration, sample_count} from StrategicMemory
  - resolution_hints : {action, confidence} from CapabilityResolver
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weights — tunable without touching logic
# ---------------------------------------------------------------------------
_W_SKILL      = 0.35   # skill match confidence
_W_TOOL_REP   = 0.25   # best tool reputation score
_W_HISTORY    = 0.25   # historical win-rate for similar goals
_W_RESOLUTION = 0.15   # capability resolver confidence

_CONFIDENCE_THRESHOLD_HIGH   = 0.70
_CONFIDENCE_THRESHOLD_MEDIUM = 0.45


@dataclass
class DecisionResult:
    best_strategy: str          # "direct_tool" | "autonomous_agent" | "reroute" | "create_tool" | "conversation"
    confidence: float           # 0.0–1.0 composite
    fallback_plan: str          # what to do if best_strategy fails
    reasoning: List[str] = field(default_factory=list)
    component_scores: Dict[str, float] = field(default_factory=dict)


class DecisionEngine:
    """
    Centralised scoring engine.  Instantiated once at bootstrap and injected
    into SkillSelector, ContextAwareToolSelector, and CapabilityResolver.
    """

    def __init__(self, skill_registry=None):
        self._skill_registry = skill_registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(
        self,
        intent_signals: Optional[Dict[str, Any]] = None,
        skill_scores: Optional[Dict[str, float]] = None,
        tool_reputations: Optional[Dict[str, Any]] = None,
        history_signals: Optional[Dict[str, Any]] = None,
        resolution_hints: Optional[Dict[str, Any]] = None,
    ) -> DecisionResult:
        """
        Compute a unified decision from all available signals.
        Any signal can be None — the engine weights only what it has.
        """
        scores: Dict[str, float] = {}
        reasoning: List[str] = []
        active_weight = 0.0

        # --- Skill signal ---
        skill_score, skill_name = self._score_skill(skill_scores)
        if skill_score is not None:
            scores["skill"] = skill_score
            active_weight += _W_SKILL
            reasoning.append(f"skill '{skill_name}' score={skill_score:.2f}")

        # --- Tool reputation signal ---
        tool_score, best_tool = self._score_tools(tool_reputations)
        if tool_score is not None:
            scores["tool_rep"] = tool_score
            active_weight += _W_TOOL_REP
            reasoning.append(f"best tool '{best_tool}' rep={tool_score:.2f}")

        # --- History signal ---
        history_score = self._score_history(history_signals)
        if history_score is not None:
            scores["history"] = history_score
            active_weight += _W_HISTORY
            reasoning.append(f"history win_rate={history_score:.2f}")

        # --- Resolution signal ---
        resolution_score = self._score_resolution(resolution_hints)
        if resolution_score is not None:
            scores["resolution"] = resolution_score
            active_weight += _W_RESOLUTION
            reasoning.append(f"resolution confidence={resolution_score:.2f}")

        # Composite — re-normalise by active weight so missing signals don't penalise
        if active_weight == 0.0:
            composite = 0.5
            reasoning.append("no signals available — neutral confidence")
        else:
            raw = (
                scores.get("skill", 0.0)      * _W_SKILL
                + scores.get("tool_rep", 0.0) * _W_TOOL_REP
                + scores.get("history", 0.0)  * _W_HISTORY
                + scores.get("resolution", 0.0) * _W_RESOLUTION
            )
            composite = round(raw / active_weight, 3)

        strategy, fallback = self._pick_strategy(
            composite, skill_name, resolution_hints, intent_signals
        )

        return DecisionResult(
            best_strategy=strategy,
            confidence=composite,
            fallback_plan=fallback,
            reasoning=reasoning,
            component_scores=scores,
        )

    def score_skill_candidates(
        self, candidates: Dict[str, float], tool_reputations: Optional[Dict[str, Any]] = None
    ) -> Dict[str, float]:
        """
        Re-rank skill candidates by blending their raw scores with live tool
        reputation for each skill's preferred tools.  Returns adjusted scores.
        """
        adjusted: Dict[str, float] = {}
        for skill_name, raw_score in candidates.items():
            tool_boost = 0.0
            if self._skill_registry and tool_reputations:
                skill = self._skill_registry.get(skill_name)
                if skill:
                    rep_scores = [
                        tool_reputations.get(t, {}).get("score", 0.5)
                        for t in skill.preferred_tools
                    ]
                    if rep_scores:
                        tool_boost = (sum(rep_scores) / len(rep_scores) - 0.5) * 0.10
            adjusted[skill_name] = round(min(0.99, raw_score + tool_boost), 3)
        return adjusted

    def score_tool_candidates(
        self, candidates: List[str], tool_reputations: Optional[Dict[str, Any]] = None
    ) -> List[tuple]:
        """
        Score a list of tool names using reputation data.
        Returns [(tool_name, score)] sorted descending.
        """
        scored = []
        for tool_name in candidates:
            if tool_reputations and tool_name in tool_reputations:
                rep = tool_reputations[tool_name]
                score = rep.get("score", 0.5) if isinstance(rep, dict) else getattr(rep, "score", 0.5)
            elif self._skill_registry and hasattr(self._skill_registry, "get_tool_reputation"):
                score = self._skill_registry.get_tool_reputation(tool_name).score
            else:
                score = 0.5
            scored.append((tool_name, round(score, 3)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    # ------------------------------------------------------------------
    # Internal scoring helpers
    # ------------------------------------------------------------------

    def _score_skill(self, skill_scores: Optional[Dict[str, float]]):
        if not skill_scores:
            return None, None
        best = max(skill_scores.items(), key=lambda x: x[1])
        return best[1], best[0]

    def _score_tools(self, tool_reputations: Optional[Dict[str, Any]]):
        if not tool_reputations:
            return None, None
        best_name, best_score = None, -1.0
        for name, rep in tool_reputations.items():
            s = rep.get("score", 0.5) if isinstance(rep, dict) else getattr(rep, "score", 0.5)
            if s > best_score:
                best_score, best_name = s, name
        return (round(best_score, 3), best_name) if best_name else (None, None)

    def _score_history(self, history_signals: Optional[Dict[str, Any]]):
        if not history_signals:
            return None
        win_rate = history_signals.get("win_rate")
        sample_count = history_signals.get("sample_count", 0)
        if win_rate is None:
            return None
        # Discount low-sample history (< 3 samples = half weight)
        if sample_count < 3:
            return round(float(win_rate) * 0.5, 3)
        return round(float(win_rate), 3)

    def _score_resolution(self, resolution_hints: Optional[Dict[str, Any]]):
        if not resolution_hints:
            return None
        return round(float(resolution_hints.get("confidence", 0.5)), 3)

    def _pick_strategy(
        self,
        confidence: float,
        skill_name: Optional[str],
        resolution_hints: Optional[Dict[str, Any]],
        intent_signals: Optional[Dict[str, Any]],
    ):
        # Conversation shortcut
        if skill_name == "conversation":
            return "conversation", "direct_llm_response"

        # Resolution action overrides when resolver has a clear answer
        if resolution_hints:
            action = resolution_hints.get("action", "")
            if action == "reroute":
                return "direct_tool", "autonomous_agent"
            if action in ("mcp", "api_wrap"):
                return "direct_tool", "create_tool"
            if action == "create_tool":
                return "create_tool", "scaffold_and_queue"

        # Confidence-based routing
        if confidence >= _CONFIDENCE_THRESHOLD_HIGH:
            return "direct_tool", "autonomous_agent"
        if confidence >= _CONFIDENCE_THRESHOLD_MEDIUM:
            return "autonomous_agent", "direct_tool"

        # Low confidence — still attempt autonomous but flag it
        return "autonomous_agent", "conversation"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_instance: Optional[DecisionEngine] = None


def get_decision_engine(skill_registry=None) -> DecisionEngine:
    global _instance
    if _instance is None:
        _instance = DecisionEngine(skill_registry=skill_registry)
    elif skill_registry and _instance._skill_registry is None:
        _instance._skill_registry = skill_registry
    return _instance
