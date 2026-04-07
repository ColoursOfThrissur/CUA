from __future__ import annotations

import logging
import re
from typing import Any, Optional

from domain.entities.skill_models import SkillSelection
from domain.services.decision_engine import get_decision_engine
from application.services.intent_classifier import IntentClassifier


class SkillSelector:
    """Select the most appropriate skill for a request."""
    
    def __init__(self):
        self._intent_classifier = IntentClassifier()

    KEYWORD_HINTS = {
        "conversation": {"what", "is", "how", "does", "why", "explain", "tell", "me", "about", "help", "understand", "think", "opinion", "suggest", "recommend", "hi", "hello", "thanks", "thank", "you", "goodbye", "bye", "morning", "afternoon", "evening", "are", "whats", "up", "good", "hey", "there", "doing"},
        "web": {"web", "website", "page", "pages", "url", "urls", "research", "source", "sources", "summarize", "extract", "crawl", "browse", "search", "google", "bing", "fetch", "scrape", "content", "information", "findings", "summary", "agi", "development", "topic"},
        "computer": {"file", "files", "folder", "folders", "directory", "directories", "local", "machine", "computer", "command", "shell", "move", "create", "list", "read", "write", "benchmark", "performance", "system", "notepad", "calculator", "paint", "steam", "app", "application", "launch", "start", "desktop", "window", "windows", "process", "clipboard", "screenshot", "screen", "mouse", "keyboard", "click", "type", "press", "key", "games", "library", "playing", "installed"},
        "development": {"code", "repo", "repository", "bug", "feature", "refactor", "test", "tests", "implement", "module", "function", "class", "method", "debug", "analyze"},
        "automation": {"automate", "automation", "browser", "form", "button", "element", "interact", "selenium", "headless", "scrape", "fill", "login", "navigate", "chatgpt", "website", "tab", "input", "submit", "scroll", "hover", "iframe", "dropdown", "cookie", "cookies", "javascript"},
        "data": {"api", "http", "json", "database", "query", "sql", "transform", "parse", "endpoint", "request", "response", "data", "structure"},
        "productivity": {"snippet", "snippets", "note", "notes", "save", "store", "library", "knowledge", "organize", "search", "retrieve", "tag", "tags"},
        "finance": {"stock", "stocks", "ticker", "portfolio", "invest", "investing", "investment", "investments", "market", "markets", "trading", "trade", "shares", "equity", "finance", "financial", "aapl", "nvda", "msft", "tsla", "amzn", "googl", "meta", "spy", "etf", "rsi", "macd", "bullish", "bearish", "dividend", "earnings", "pe", "ratio", "sharpe", "drawdown", "sector", "exposure", "hedge", "rebalance", "trim", "position", "holdings", "yfinance", "nasdaq", "nyse", "sp500", "crypto", "bitcoin", "btc", "eth", "morning", "brief", "report", "nifty", "sensex", "canbk", "infy", "tcs", "reliance", "nsei", "bse", "midcap", "smallcap", "flexi", "elss", "mf", "mutual", "fund", "sgb", "gold", "bond"}
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
    _TRIVIAL_DIRECT_PATTERNS = [
        re.compile(r"^(open|launch|start)\s+(notepad|calculator|paint|steam|chrome|vscode|code)\s*$"),
        re.compile(r"^(take|capture)\s+(a\s+)?screenshot\s*$"),
        re.compile(r"^(check|show|get)\s+system\s+health\s*$"),
        re.compile(r"^(list|show)\s+(running\s+)?processes\s*$"),
        re.compile(r"^(get|show)\s+clipboard\s*(content)?\s*$"),
    ]
    _ACTION_WORDS = {
        "open", "launch", "start", "find", "show", "tell", "check", "click", "type",
        "press", "focus", "switch", "go", "navigate", "search", "extract", "list",
        "count", "findout", "find", "play", "played",
    }
    _COMPLEXITY_MARKERS = {
        "and", "then", "after", "before", "while", "from", "into", "inside",
        "using", "with", "how", "many", "which", "what", "where", "when",
    }

    def select_skill(self, user_message: str, registry, llm_client: Optional[Any] = None, runtime_context=None) -> SkillSelection:
        message = (user_message or "").strip()
        if not message:
            return SkillSelection(matched=False, reason="empty_request", fallback_mode="direct_tool_routing")

        message_lower = message.lower()
        logger = logging.getLogger(__name__)
        logger.info(f"[SKILL_SELECTOR] Selecting skill for: '{message[:80]}'")

        for pattern in self._CONVERSATION_PATTERNS:
            if re.match(pattern, message_lower):
                skill = registry.get("conversation")
                if skill:
                    return SkillSelection(
                        matched=True, skill_name="conversation", category="conversation",
                        confidence=0.95, reason="direct_conversation_pattern",
                        fallback_mode="direct_response", candidate_skills=["conversation"]
                    )

        candidates = [s.name for s in registry.list_all()]
        tokens = self._tokenize(message)
        trivial_direct = self._maybe_direct_route(message_lower, registry)
        if trivial_direct:
            logger.info(
                f"[SKILL_SELECTOR] Direct route: {trivial_direct.skill_name} "
                f"(confidence={trivial_direct.confidence:.2f})"
            )
            return trivial_direct

        substantive_request = self._should_use_llm_primary(message_lower, tokens)
        if substantive_request and llm_client:
            llm_result = self._llm_fallback(message, registry, llm_client, candidates, minimum_confidence=0.35)
            if llm_result.matched:
                logger.info(
                    f"[SKILL_SELECTOR] LLM primary selected: {llm_result.skill_name} "
                    f"(confidence={llm_result.confidence:.2f})"
                )
                return llm_result

        scored = []
        for skill in registry.list_all():
            score = self._score_skill(skill, tokens, message_lower, registry)
            scored.append((skill, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        best_skill, raw_confidence = scored[0] if scored else (None, 0.0)
        confidence = min(raw_confidence, 0.98)
        
        logger.info(f"[SKILL_SELECTOR] Keyword fallback: {best_skill.name if best_skill else 'none'} (confidence={confidence:.2f})")
        
        if best_skill and confidence >= 0.35:
            return SkillSelection(
                matched=True,
                skill_name=best_skill.name,
                category=best_skill.category,
                confidence=confidence,
                reason="score_primary",
                fallback_mode=best_skill.fallback_strategy,
                candidate_skills=candidates,
            )

        if llm_client and not substantive_request:
            llm_result = self._llm_fallback(message, registry, llm_client, candidates, minimum_confidence=0.35)
            if llm_result.matched:
                logger.info(f"[SKILL_SELECTOR] LLM selected: {llm_result.skill_name} (confidence={llm_result.confidence:.2f})")
                return llm_result

        return SkillSelection(matched=False, reason="no_confident_match",
                              fallback_mode="direct_tool_routing", candidate_skills=candidates)

    def _maybe_direct_route(self, message_lower: str, registry) -> Optional[SkillSelection]:
        for pattern in self._TRIVIAL_DIRECT_PATTERNS:
            match = pattern.match(message_lower)
            if not match:
                continue

            skill_name = "computer_automation"
            if "system health" in message_lower:
                skill_name = "system_health"

            skill = registry.get(skill_name)
            if not skill:
                return None

            return SkillSelection(
                matched=True,
                skill_name=skill.name,
                category=skill.category,
                confidence=0.93,
                reason="direct_obvious_request",
                fallback_mode=skill.fallback_strategy,
                candidate_skills=[s.name for s in registry.list_all()],
            )
        return None

    def _should_use_llm_primary(self, message_lower: str, tokens: set[str]) -> bool:
        token_count = len(tokens)
        action_hits = sum(1 for token in tokens if token in self._ACTION_WORDS)
        complexity_hits = sum(1 for token in tokens if token in self._COMPLEXITY_MARKERS)
        desktop_entities = any(token in tokens for token in {"steam", "notepad", "calculator", "chrome", "window"})

        if token_count >= 7:
            return True
        if action_hits >= 2 and complexity_hits >= 1:
            return True
        if desktop_entities and (complexity_hits >= 1 or action_hits >= 2):
            return True
        if " and " in message_lower:
            return True
        return False

    def _score_skill(self, skill, tokens: set, message_lower: str, registry) -> float:
        score = 0.0
        
        # Use intent classifier instead of hardcoded patterns
        intents = self._intent_classifier.get_all_intents(message_lower)
        web_intent = intents["web"]
        browser_interaction_intent = intents["browser_interaction"]
        development_intent = intents["development"]

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

        if skill.name == "web_research":
            if web_intent:
                score += 0.35
            if any(word in tokens for word in ("summarize", "research", "compare")):
                score += 0.20
            if ("webpage" in tokens or "website" in tokens or "page" in tokens) and "summarize" in tokens:
                score += 0.25
            if browser_interaction_intent and not any(word in tokens for word in ("summarize", "research", "compare")):
                score -= 0.10

        if skill.name == "browser_automation":
            if browser_interaction_intent:
                score += 0.30
            if web_intent and not browser_interaction_intent and any(word in tokens for word in ("summarize", "research", "compare")):
                score -= 0.45

        if skill.name == "code_workspace" and web_intent and not development_intent:
            score -= 0.35

        # Use intent classifier for finance detection
        if skill.name == "knowledge_management" and intents["finance"]:
            score -= 0.5

        for example in skill.trigger_examples:
            if example.lower() in message_lower:
                score += 0.35
            else:
                example_tokens = {w for w in self._tokenize(example) if len(w) > 3}
                if len(tokens.intersection(example_tokens)) >= 2:
                    score += 0.10

        if hasattr(registry, "get_learned_triggers"):
            learned = registry.get_learned_triggers(skill.name)
            learned_overlap = tokens.intersection(learned)
            if learned_overlap:
                score += min(0.20, 0.06 * len(learned_overlap))

        if hasattr(registry, "get_tool_score"):
            tool_scores = [
                registry.get_tool_score(t) for t in skill.preferred_tools
            ]
            if tool_scores:
                avg_tool_score = sum(tool_scores) / len(tool_scores)
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
            'Pick the best skill for this request. Return JSON only: {"skill_name": string, "confidence": 0.0-1.0}\n\n'
            'CRITICAL DISTINCTIONS:\n'
            '- computer_automation: Desktop apps (Steam, Notepad, Calculator), file operations, system control\n'
            '- browser_automation: Web pages, URLs, browser interactions\n'
            '- web_research: Search, fetch info from web\n\n'
            f'SKILLS:\n{skills_summary}\n\n'
            f'REQUEST: "{message}"\n\n'
            '/no_think\n\n'
            'Return ONLY JSON: {"skill_name": "...", "confidence": 0.0-1.0}'
        )
        try:
            from shared.config.model_manager import get_model_manager
            model_manager = get_model_manager(llm_client)
            model_manager.switch_to("planning")
            
            raw = llm_client._call_llm(prompt, temperature=0.1, max_tokens=80, expect_json=True)
            
            model_manager.switch_to("chat")
            
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
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"LLM fallback failed: {e}")
            try:
                from shared.config.model_manager import get_model_manager
                get_model_manager(llm_client).switch_to("chat")
            except Exception:
                pass

        return SkillSelection(matched=False, reason="no_confident_skill_match",
                              fallback_mode="direct_tool_routing", candidate_skills=candidates)

    def _tokenize(self, text: str) -> set:
        tokens = set(re.findall(r"[a-z0-9_]+", text.lower()))
        stemmed = set()
        for t in tokens:
            for suffix in ("ing", "ed", "er", "ly", "s"):
                if t.endswith(suffix) and len(t) - len(suffix) >= 3:
                    stemmed.add(t[: -len(suffix)])
                    break
        return tokens | stemmed
