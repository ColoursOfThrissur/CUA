from typing import Dict, List, Optional, Tuple
from core.skills.execution_context import SkillExecutionContext, ToolVersion
from core.decision_engine import get_decision_engine

# Minimum reputation score below which a tool is treated as degraded
_DEGRADED_THRESHOLD = 0.25
# Score gap required to prefer a fallback over the primary tool
_SWAP_THRESHOLD = 0.20


class ContextAwareToolSelector:

    def __init__(self, tool_registry, circuit_breaker_manager=None, skill_registry=None):
        self.tool_registry = tool_registry
        self.circuit_breaker = circuit_breaker_manager
        self.skill_registry = skill_registry

    def select_tools(self, context: SkillExecutionContext) -> SkillExecutionContext:
        available_tools: Dict[str, ToolVersion] = {}
        scored: List[Tuple[str, float]] = []  # (tool_name, composite_score)

        for tool_name in context.preferred_tools:
            tool = self.tool_registry.get_tool_by_name(tool_name)
            if not tool:
                # Try class name lookup as fallback
                if hasattr(self.tool_registry, 'tools'):
                    tool = next(
                        (t for t in self.tool_registry.tools
                         if t.__class__.__name__ == tool_name),
                        None
                    )
            if not tool:
                context.warnings.append(f"Preferred tool {tool_name} not found in registry")
                continue

            cb_state = "CLOSED"
            healthy = True
            if self.circuit_breaker:
                cb_state = self.circuit_breaker.get_state(tool_name)
                # Accept CLOSED and HALF_OPEN; reject OPEN
                healthy = (str(cb_state).upper() not in ("OPEN", "CircuitState.OPEN"))

            available_tools[tool_name] = ToolVersion(
                name=tool_name, version="v1",
                healthy=healthy, circuit_breaker_state=str(cb_state)
            )

            if not healthy:
                context.warnings.append(f"{tool_name} circuit OPEN — excluded from selection")
                continue

            score = self._reputation_score(tool_name)
            scored.append((tool_name, score))

        # Delegate final ranking to Decision Engine
        if scored:
            engine = get_decision_engine(self.skill_registry)
            tool_scores_raw = {name: {"score": s} for name, s in scored}
            scored = engine.score_tool_candidates([n for n, _ in scored], tool_scores_raw)

        selected_tool: Optional[str] = None
        fallback_tools: List[str] = []

        if scored:
            best_name, best_score = scored[0]
            # If the best tool is severely degraded, warn but still use it
            if best_score < _DEGRADED_THRESHOLD:
                context.warnings.append(
                    f"{best_name} reputation low ({best_score:.2f}) — consider evolution"
                )
            selected_tool = best_name
            fallback_tools = [t for t, _ in scored[1:]]
        elif available_tools:
            # All preferred tools have open circuits — pick least-bad
            selected_tool = list(available_tools.keys())[0]
            fallback_tools = list(available_tools.keys())[1:]
            context.warnings.append(
                f"All preferred tools unhealthy, using {selected_tool} as best available"
            )

        # Build human-readable reasoning
        if scored:
            rep_summary = ", ".join(
                f"{t}={s:.2f}" for t, s in scored[:3]
            )
            reasoning = f"{selected_tool} selected (scores: {rep_summary})"
        else:
            reasoning = f"{selected_tool} selected (no healthy preferred tools)"

        context.selected_tool = selected_tool
        context.available_tools = available_tools
        context.fallback_tools = fallback_tools
        context.tool_selection_reasoning = reasoning

        return context

    def _reputation_score(self, tool_name: str) -> float:
        """Return composite reputation score for a tool.

        Uses full ToolReputation when skill_registry is available,
        otherwise falls back to neutral 0.5.
        """
        if self.skill_registry and hasattr(self.skill_registry, "get_tool_reputation"):
            rep = self.skill_registry.get_tool_reputation(tool_name)
            return rep.score
        # Neutral score for tools with no data yet
        return 0.5
