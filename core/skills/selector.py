from __future__ import annotations

import re
from typing import Any, Optional

from core.skills.models import SkillSelection


class SkillSelector:
    """Select the most appropriate skill for a request."""

    KEYWORD_HINTS = {
        "conversation": {"what", "is", "how", "does", "why", "explain", "tell", "me", "about", "help", "understand", "think", "opinion", "suggest", "recommend", "hi", "hello", "thanks", "thank", "you", "goodbye", "bye", "morning", "afternoon", "evening", "are", "whats", "up", "good", "hey", "there", "doing"},
        "web": {"web", "website", "page", "pages", "url", "urls", "research", "source", "sources", "summarize", "extract", "crawl", "browse", "search", "google", "bing", "fetch", "scrape", "content", "information", "findings", "summary", "agi", "development", "topic"},
        "computer": {"file", "files", "folder", "folders", "directory", "directories", "local", "machine", "computer", "command", "shell", "move", "create", "list", "read", "write", "benchmark", "performance", "system"},
        "development": {"code", "repo", "repository", "bug", "feature", "refactor", "test", "tests", "implement", "module", "function", "class", "method", "debug", "analyze"},
        "automation": {"automate", "automation", "browser", "click", "form", "button", "element", "screenshot", "interact", "selenium", "headless", "scrape", "fill"},
        "data": {"api", "http", "json", "database", "query", "sql", "transform", "parse", "endpoint", "request", "response", "data", "structure"},
        "productivity": {"snippet", "snippets", "note", "notes", "save", "store", "library", "knowledge", "organize", "search", "retrieve", "tag", "tags"}
    }

    def select_skill(self, user_message: str, registry, llm_client: Optional[Any] = None, runtime_context=None) -> SkillSelection:
        message = (user_message or "").strip()
        if not message:
            return SkillSelection(matched=False, reason="empty_request", fallback_mode="direct_tool_routing")

        # PRIORITY FIX: Direct conversation pattern matching
        conversation_patterns = [
            r'^(hi|hello|hey)\s*$',
            r'^(hi|hello|hey)\s+(how\s+are\s+you|there)\s*$',
            r'^(good\s+)?(morning|afternoon|evening)\s*$',
            r'^(thanks?|thank\s+you)\s*$',
            r'^(bye|goodbye)\s*$',
            r'^what[\s\']*s\s+up\s*$',
            r'^how\s+are\s+you\s*(doing)?\s*$'
        ]
        
        message_lower = message.lower()
        for pattern in conversation_patterns:
            if re.match(pattern, message_lower):
                conversation_skill = registry.get("conversation")
                if conversation_skill:
                    return SkillSelection(
                        matched=True,
                        skill_name="conversation",
                        category="conversation",
                        confidence=0.95,
                        reason="direct_conversation_pattern",
                        fallback_mode="direct_response",
                        candidate_skills=["conversation"]
                    )

        tokens = self._tokenize(message)
        scored = []
        for skill in registry.list_all():
            score = 0.0
            candidates = {skill.name.lower(), skill.category.lower()}
            candidates.update(self._tokenize(skill.description))
            for example in skill.trigger_examples:
                candidates.update(self._tokenize(example))
            for input_type in skill.input_types:
                candidates.update(self._tokenize(input_type))
            for output_type in skill.output_types:
                candidates.update(self._tokenize(output_type))
            candidates.update(self.KEYWORD_HINTS.get(skill.category, set()))

            overlap = tokens.intersection(candidates)
            if overlap:
                score += min(0.75, 0.12 * len(overlap))
            if skill.category in self.KEYWORD_HINTS:
                hint_overlap = tokens.intersection(self.KEYWORD_HINTS[skill.category])
                score += min(0.3, 0.08 * len(hint_overlap))  # Increased weight for category hints
            
            # Enhanced trigger example matching
            for example in skill.trigger_examples:
                if example.lower() in message.lower():
                    score += 0.4  # Strong boost for exact trigger matches
                elif any(word in message_lower for word in example.lower().split()):
                    score += 0.15  # Partial boost for word matches
            
            # Special boost for web research patterns
            if skill.category == "web":
                web_patterns = [
                    "search.*and.*summary", "search.*and.*give.*summary", "search.*development.*summary",
                    "research.*and.*summarize", "find.*information.*about", "look.*up.*and.*summarize"
                ]
                if any(re.search(pattern, message.lower()) for pattern in web_patterns):
                    score += 0.4  # Strong boost for web research + summary patterns

            scored.append((skill, min(score, 0.98), sorted(overlap)))

        scored.sort(key=lambda item: item[1], reverse=True)
        candidates = [skill.name for skill, _, _ in scored[:3]]
        if not scored or scored[0][1] < 0.15:  # Lowered threshold further
            return self._llm_fallback(message, registry, llm_client, candidates)

        best_skill, confidence, overlap = scored[0]
        if len(scored) > 1 and abs(scored[0][1] - scored[1][1]) < 0.05:  # Tighter threshold for LLM fallback
            llm_choice = self._llm_fallback(message, registry, llm_client, candidates, minimum_confidence=confidence)
            if llm_choice.matched:
                return llm_choice

        return SkillSelection(
            matched=True,
            skill_name=best_skill.name,
            category=best_skill.category,
            confidence=confidence,
            reason=f"heuristic_match:{','.join(overlap[:5])}" if overlap else "heuristic_match",
            fallback_mode=best_skill.fallback_strategy,
            candidate_skills=candidates,
        )

    def _llm_fallback(self, message: str, registry, llm_client: Optional[Any], candidates, minimum_confidence: float = 0.25) -> SkillSelection:
        if not llm_client:
            # FALLBACK: Try conversation skill for simple messages
            if len(message.split()) <= 3 and any(word in message.lower() for word in ['hi', 'hello', 'hey', 'thanks', 'bye']):
                conversation_skill = registry.get("conversation")
                if conversation_skill:
                    return SkillSelection(
                        matched=True,
                        skill_name="conversation",
                        category="conversation",
                        confidence=0.8,
                        reason="fallback_conversation_detection",
                        fallback_mode="direct_response",
                        candidate_skills=candidates,
                    )
            
            return SkillSelection(
                matched=False,
                reason="no_confident_skill_match",
                fallback_mode="direct_tool_routing",
                candidate_skills=candidates,
            )

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
                    matched=True,
                    skill_name=skill.name,
                    category=skill.category,
                    confidence=confidence,
                    reason=f"llm_match:{reason}",
                    fallback_mode=skill.fallback_strategy,
                    candidate_skills=candidates,
                )
        except Exception:
            pass

        # FINAL FALLBACK: Check for conversation patterns one more time
        if len(message.split()) <= 5 and any(word in message.lower() for word in ['hi', 'hello', 'hey', 'thanks', 'bye', 'what', 'how', 'why']):
            conversation_skill = registry.get("conversation")
            if conversation_skill:
                return SkillSelection(
                    matched=True,
                    skill_name="conversation",
                    category="conversation",
                    confidence=0.7,
                    reason="final_fallback_conversation",
                    fallback_mode="direct_response",
                    candidate_skills=candidates,
                )

        return SkillSelection(
            matched=False,
            reason="no_confident_skill_match",
            fallback_mode="direct_tool_routing",
            candidate_skills=candidates,
        )

    def _tokenize(self, text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9_]+", text.lower()))
