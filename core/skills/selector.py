from __future__ import annotations

import re
from typing import Any, Optional

from core.skills.models import SkillSelection
from core.decision_engine import get_decision_engine


class SkillSelector:
    """Select the most appropriate skill for a request."""

    KEYWORD_HINTS = {
        "conversation": {"what", "is", "how", "does", "why", "explain", "tell", "me", "about", "help", "understand", "think", "opinion", "suggest", "recommend", "hi", "hello", "thanks", "thank", "you", "goodbye", "bye", "morning", "afternoon", "evening", "are", "whats", "up", "good", "hey", "there", "doing"},
        "web": {"web", "website", "page", "pages", "url", "urls", "research", "source", "sources", "summarize", "extract", "crawl", "browse", "search", "google", "bing", "fetch", "scrape", "content", "information", "findings", "summary", "agi", "development", "topic"},
        "computer": {"file", "files", "folder", "folders", "directory", "directories", "local", "machine", "computer", "command", "shell", "move", "create", "list", "read", "write", "benchmark", "performance", "system"},
        "development": {"code", "repo", "repository", "bug", "feature", "refactor", "test", "tests", "implement", "module", "function", "class", "method", "debug", "analyze"},
        "automation": {"automate", "automation", "browser", "click", "form", "button", "element", "screenshot", "interact", "selenium", "headless", "scrape", "fill", "open", "type", "login", "navigate", "chatgpt", "website", "tab", "input", "submit", "scroll", "hover", "iframe", "dropdown", "keyboard", "cookie", "cookies", "javascript"},
        "data": {"api", "http", "json", "database", "query", "sql", "transform", "parse", "endpoint", "request", "response", "data", "structure"},
        "productivity": {"snippet", "snippets", "note", "notes", "save", "store", "library", "knowledge", "organize", "search", "retrieve", "tag", "tags"}
    }

    _CONVERSATION_PATTERNS = [
        r'^(hi|hello|hey)\s*$',
        r'^(hi|hello|hey)\s+(how\s+are\s+you|there)\s*$',
        r'^(good\s+)?(morning|afternoon|evening)\s*$',
        r'^(thanks?|thank\s+you)\s*$',
        r'^(bye|goodbye)\s*$',
        r'^what[\s\']*s\s+up\s*$',
        r'^how\s+are\s+you\s*(doing)?\s*$',
    ]

    def select_skill(self, user_message: str, registry, llm_client: Optional[Any] = None, runtime_context=None) -> SkillSelection:
        message = (user_message or "").strip()
        if not message:
            return SkillSelection(matched=False, reason="empty_request", fallback_mode="direct_tool_routing")

        message_lower = message.lower()

        # Fast path: direct conversation patterns
        for pattern in self._CONVERSATION_PATTERNS:
            if re.match(pattern, message_lower):
                skill = registry.get("conversation")
                if skill:
                    return SkillSelection(
                        matched=True, skill_name="conversation", category="conversation",
                        confidence=0.95, reason="direct_conversation_pattern",
                        fallback_mode="direct_response", candidate_skills=["conversation"]
                    )

        tokens = self._tokenize(message)
        scored = []

        for skill in registry.list_all():
            score = self._score_skill(skill, tokens, message_lower, registry)
            scored.append((skill, min(score, 0.98)))

        scored.sort(key=lambda x: x[1], reverse=True)
        candidates = [s.name for s, _ in scored[:3]]

        # Re-rank via Decision Engine (blends tool reputation into skill scores)
        if scored:
            engine = get_decision_engine(registry if hasattr(registry, 'get_tool_reputation') else None)
            raw_scores = {s.name: sc for s, sc in scored}
            adjusted = engine.score_skill_candidates(raw_scores)
            scored = sorted([(s, adjusted.get(s.name, sc)) for s, sc in scored], key=lambda x: x[1], reverse=True)

        if not scored or scored[0][1] < 0.15:
            return self._llm_fallback(message, registry, llm_client, candidates)

        best_skill, confidence = scored[0]

        # Too close to call — use LLM to break the tie
        if len(scored) > 1 and abs(scored[0][1] - scored[1][1]) < 0.05:
            llm_choice = self._llm_fallback(message, registry, llm_client, candidates, minimum_confidence=confidence)
            if llm_choice.matched:
                return llm_choice

        return SkillSelection(
            matched=True,
            skill_name=best_skill.name,
            category=best_skill.category,
            confidence=confidence,
            reason="heuristic_match",
            fallback_mode=best_skill.fallback_strategy,
            candidate_skills=candidates,
        )

    def _score_skill(self, skill, tokens: set, message_lower: str, registry) -> float:
        """Score a skill against the request using static + learned + live tool health signals."""
        score = 0.0

        # --- Static signal: keyword overlap ---
        candidates = {skill.name.lower(), skill.category.lower()}
        candidates.update(self._tokenize(skill.description))
        for example in skill.trigger_examples:
            candidates.update(self._tokenize(example))
        for t in skill.input_types + skill.output_types:
            candidates.update(self._tokenize(t))
        candidates.update(self.KEYWORD_HINTS.get(skill.category, set()))

        overlap = tokens.intersection(candidates)
        if overlap:
            score += min(0.55, 0.10 * len(overlap))

        hint_overlap = tokens.intersection(self.KEYWORD_HINTS.get(skill.category, set()))
        score += min(0.20, 0.07 * len(hint_overlap))

        # Trigger example phrase matching
        for example in skill.trigger_examples:
            if example.lower() in message_lower:
                score += 0.35
            elif any(w in message_lower for w in example.lower().split() if len(w) > 3):
                score += 0.10

        # --- Learned signal: tokens from past successful executions ---
        if hasattr(registry, "get_learned_triggers"):
            learned = registry.get_learned_triggers(skill.name)
            learned_overlap = tokens.intersection(learned)
            if learned_overlap:
                score += min(0.20, 0.06 * len(learned_overlap))

        # --- Live signal: preferred tool health + usage score ---
        if hasattr(registry, "get_tool_score"):
            tool_scores = [
                registry.get_tool_score(t) for t in skill.preferred_tools
            ]
            if tool_scores:
                avg_tool_score = sum(tool_scores) / len(tool_scores)
                # Boost up to +0.10 for healthy/high-performing tools
                score += 0.10 * avg_tool_score

        return score

    def _llm_fallback(self, message: str, registry, llm_client: Optional[Any], candidates, minimum_confidence: float = 0.25) -> SkillSelection:
        if not llm_client:
            if len(message.split()) <= 3 and any(w in message.lower() for w in ['hi', 'hello', 'hey', 'thanks', 'bye']):
                skill = registry.get("conversation")
                if skill:
                    return SkillSelection(
                        matched=True, skill_name="conversation", category="conversation",
                        confidence=0.8, reason="fallback_conversation_detection",
                        fallback_mode="direct_response", candidate_skills=candidates,
                    )
            return SkillSelection(matched=False, reason="no_confident_skill_match",
                                  fallback_mode="direct_tool_routing", candidate_skills=candidates)

        prompt = (
            "Select the best skill for the request. Return JSON only with keys "
            '{"skill_name": string, "confidence": number, "reason": string}. '
            "If no skill fits, return skill_name as empty string.\n"
            "IMPORTANT: For greetings (hi, hello, thanks, bye) or simple questions, use 'conversation' skill.\n"
            f"Request: {message}\n"
            f"Skills: {registry.to_routing_context()}"
        )
        try:
            raw = llm_client._call_llm(prompt, temperature=0.1, max_tokens=250, expect_json=True)
            parsed = llm_client._extract_json(raw) if raw else None
            skill_name = str((parsed or {}).get("skill_name", "")).strip()
            confidence = float((parsed or {}).get("confidence", 0.0) or 0.0)
            reason = str((parsed or {}).get("reason", "llm_selection")).strip()
            skill = registry.get(skill_name)
            if skill and confidence >= minimum_confidence:
                return SkillSelection(
                    matched=True, skill_name=skill.name, category=skill.category,
                    confidence=confidence, reason=f"llm_match:{reason}",
                    fallback_mode=skill.fallback_strategy, candidate_skills=candidates,
                )
        except Exception:
            pass

        # Final safety net — only for pure conversational messages (greetings/thanks/bye)
        if len(message.split()) <= 5 and any(w in message.lower() for w in ['hi', 'hello', 'hey', 'thanks', 'bye']):
            skill = registry.get("conversation")
            if skill:
                return SkillSelection(
                    matched=True, skill_name="conversation", category="conversation",
                    confidence=0.7, reason="final_fallback_conversation",
                    fallback_mode="direct_response", candidate_skills=candidates,
                )

        return SkillSelection(matched=False, reason="no_confident_skill_match",
                              fallback_mode="direct_tool_routing", candidate_skills=candidates)

    def _tokenize(self, text: str) -> set:
        return set(re.findall(r"[a-z0-9_]+", text.lower()))
