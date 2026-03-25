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
        "productivity": {"snippet", "snippets", "note", "notes", "save", "store", "library", "knowledge", "organize", "search", "retrieve", "tag", "tags"},
        "finance": {"stock", "stocks", "ticker", "portfolio", "invest", "investing", "investment", "investments", "market", "markets", "trading", "trade", "shares", "equity", "finance", "financial", "aapl", "nvda", "msft", "tsla", "amzn", "googl", "meta", "spy", "etf", "rsi", "macd", "bullish", "bearish", "dividend", "earnings", "pe", "ratio", "sharpe", "drawdown", "sector", "exposure", "hedge", "rebalance", "trim", "position", "holdings", "yfinance", "nasdaq", "nyse", "sp500", "crypto", "bitcoin", "btc", "eth"}
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

        # Fast path: dead-obvious greetings/farewells only (no LLM needed)
        for pattern in self._CONVERSATION_PATTERNS:
            if re.match(pattern, message_lower):
                skill = registry.get("conversation")
                if skill:
                    return SkillSelection(
                        matched=True, skill_name="conversation", category="conversation",
                        confidence=0.95, reason="direct_conversation_pattern",
                        fallback_mode="direct_response", candidate_skills=["conversation"]
                    )

        # LLM-first: ask the LLM to classify before keyword scoring
        if llm_client:
            llm_result = self._llm_fallback(message, registry, llm_client, [], minimum_confidence=0.4)
            if llm_result.matched:
                return llm_result

        # Keyword scoring fallback (LLM unavailable or low confidence)
        tokens = self._tokenize(message)
        scored = []

        for skill in registry.list_all():
            score = self._score_skill(skill, tokens, message_lower, registry)
            scored.append((skill, min(score, 0.98)))

        scored.sort(key=lambda x: x[1], reverse=True)
        candidates = [s.name for s, _ in scored[:3]]

        # Re-rank via Decision Engine
        if scored:
            engine = get_decision_engine(registry if hasattr(registry, 'get_tool_reputation') else None)
            raw_scores = {s.name: sc for s, sc in scored}
            adjusted = engine.score_skill_candidates(raw_scores)
            scored = sorted([(s, adjusted.get(s.name, sc)) for s, sc in scored], key=lambda x: x[1], reverse=True)

        # Negative signal: if top-2 are within 0.05, penalise the runner-up slightly
        if len(scored) >= 2 and (scored[0][1] - scored[1][1]) < 0.05:
            scored[1] = (scored[1][0], max(0.0, scored[1][1] - 0.05))
            scored.sort(key=lambda x: x[1], reverse=True)

        if not scored or scored[0][1] < 0.15:
            return SkillSelection(matched=False, reason="no_confident_skill_match",
                                  fallback_mode="direct_tool_routing", candidate_skills=candidates)

        best_skill, confidence = scored[0]
        return SkillSelection(
            matched=True,
            skill_name=best_skill.name,
            category=best_skill.category,
            confidence=confidence,
            reason="keyword_match",
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
            return SkillSelection(matched=False, reason="no_llm_available",
                                  fallback_mode="direct_tool_routing", candidate_skills=candidates)

        # Build compact skill summary from actual definitions
        skill_lines = []
        for s in registry.to_routing_context():
            examples = ", ".join(f'"{e}"' for e in (s.get("trigger_examples") or [])[:3])
            tools = ", ".join((s.get("preferred_tools") or [])[:3])
            skill_lines.append(
                f'- {s["name"]} ({s["category"]}): {s["description"]}'
                + (f' | examples: {examples}' if examples else '')
                + (f' | tools: {tools}' if tools else '')
            )
        skills_summary = "\n".join(skill_lines)

        prompt = (
            'Pick the best skill for this request. Return JSON only: {"skill_name": string, "confidence": 0.0-1.0}\n'
            f'SKILLS:\n{skills_summary}\n'
            f'REQUEST: "{message}"'
        )
        try:
            raw = llm_client._call_llm(prompt, temperature=0.1, max_tokens=80, expect_json=True)
            parsed = llm_client._extract_json(raw) if raw else None
            skill_name = str((parsed or {}).get("skill_name", "")).strip()
            confidence = float((parsed or {}).get("confidence", 0.0) or 0.0)
            skill = registry.get(skill_name)
            if skill and confidence >= minimum_confidence:
                return SkillSelection(
                    matched=True, skill_name=skill.name, category=skill.category,
                    confidence=confidence, reason="llm_primary",
                    fallback_mode=skill.fallback_strategy, candidate_skills=candidates,
                )
        except Exception:
            pass

        return SkillSelection(matched=False, reason="no_confident_skill_match",
                              fallback_mode="direct_tool_routing", candidate_skills=candidates)

    def _tokenize(self, text: str) -> set:
        tokens = set(re.findall(r"[a-z0-9_]+", text.lower()))
        # Minimal suffix stemming — no external deps
        stemmed = set()
        for t in tokens:
            for suffix in ("ing", "ed", "er", "ly", "s"):
                if t.endswith(suffix) and len(t) - len(suffix) >= 3:
                    stemmed.add(t[: -len(suffix)])
                    break
        return tokens | stemmed
