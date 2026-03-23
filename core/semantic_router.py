"""
Semantic Router

Sits above the Skill Selector. Extracts:
  - domain      (e-commerce, productivity, communication, development, finance, ...)
  - entities    (orders, files, messages, repos, ...)
  - platform    (amazon, github, slack, notion, ...)
  - constraints (auth_required, captcha, rate_limit, ...)

Enriches the request context so that CapabilityResolver, TaskPlanner,
and ToolOrchestrator can make platform-aware decisions.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from core.integration_knowledge import get_integration_graph, IntegrationProfile

logger = logging.getLogger(__name__)


@dataclass
class SemanticContext:
    """Enriched context produced by the SemanticRouter."""
    domain: str = ""
    entities: List[str] = field(default_factory=list)
    platform_candidates: List[str] = field(default_factory=list)
    primary_profile: Optional[IntegrationProfile] = None
    constraints: List[str] = field(default_factory=list)
    best_access_method: str = ""
    confidence: float = 0.0
    routing_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "entities": self.entities,
            "platform_candidates": self.platform_candidates,
            "primary_platform": self.primary_profile.platform if self.primary_profile else "",
            "constraints": self.constraints,
            "best_access_method": self.best_access_method,
            "confidence": self.confidence,
            "routing_notes": self.routing_notes,
            "auth_type": self.primary_profile.auth_type if self.primary_profile else "",
            "mcp_server": self.primary_profile.mcp_server if self.primary_profile else None,
            "api_base": self.primary_profile.api_base if self.primary_profile else None,
        }


# ---------------------------------------------------------------------------
# Keyword maps — fast O(1) first-pass before LLM
# ---------------------------------------------------------------------------
_DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "e-commerce":    ["order", "orders", "cart", "checkout", "purchase", "buy", "product", "shipping", "tracking", "return", "refund", "wishlist", "amazon", "ebay", "shopify"],
    "productivity":  ["note", "notes", "page", "document", "spreadsheet", "calendar", "event", "task", "board", "card", "notion", "drive", "trello", "google docs"],
    "communication": ["email", "message", "slack", "channel", "inbox", "send", "reply", "thread", "gmail", "discord", "chat"],
    "development":   ["repo", "repository", "issue", "pull request", "pr", "commit", "branch", "pipeline", "workflow", "github", "gitlab", "jira", "bug", "deploy"],
    "finance":       ["stock", "price", "portfolio", "trade", "market", "crypto", "forex", "dividend", "earnings", "ticker"],
    "weather":       ["weather", "forecast", "temperature", "rain", "wind", "humidity", "climate"],
    "news":          ["news", "headline", "article", "breaking", "latest news", "top stories"],
    "computer":      ["file", "folder", "directory", "local", "disk", "path", "filesystem"],
    "data":          ["database", "query", "sql", "table", "json", "api", "endpoint", "parse"],
}

_ENTITY_KEYWORDS: Dict[str, List[str]] = {
    "orders":        ["order", "orders", "purchase", "bought", "tracking"],
    "files":         ["file", "files", "document", "documents", "attachment"],
    "messages":      ["message", "messages", "email", "emails", "chat", "inbox"],
    "repos":         ["repo", "repository", "repositories", "codebase"],
    "issues":        ["issue", "issues", "bug", "ticket", "task"],
    "events":        ["event", "events", "meeting", "appointment", "calendar"],
    "stocks":        ["stock", "stocks", "share", "shares", "ticker", "price"],
    "products":      ["product", "products", "item", "listing"],
    "pages":         ["page", "pages", "note", "notes", "document"],
    "channels":      ["channel", "channels", "workspace"],
    "weather":       ["weather", "forecast", "temperature"],
    "articles":      ["article", "articles", "news", "headline"],
}

_PLATFORM_KEYWORDS: Dict[str, List[str]] = {
    "amazon":           ["amazon", "amzn"],
    "ebay":             ["ebay"],
    "shopify":          ["shopify"],
    "notion":           ["notion"],
    "google_drive":     ["google drive", "gdrive", "drive"],
    "google_calendar":  ["google calendar", "gcal"],
    "trello":           ["trello"],
    "slack":            ["slack"],
    "gmail":            ["gmail", "google mail"],
    "discord":          ["discord"],
    "github":           ["github", "gh"],
    "gitlab":           ["gitlab"],
    "jira":             ["jira", "atlassian"],
    "yahoo_finance":    ["yahoo finance", "yahoo"],
    "alpha_vantage":    ["alpha vantage"],
    "openweathermap":   ["openweathermap", "openweather"],
    "newsapi":          ["newsapi", "news api"],
}


class SemanticRouter:
    """
    Extracts semantic context from a user request using keyword matching
    with optional LLM enrichment for ambiguous cases.
    """

    def __init__(self, llm_client=None):
        self._llm = llm_client
        self._graph = get_integration_graph()

    def route(self, message: str) -> SemanticContext:
        """
        Main entry point. Returns a SemanticContext enriched with
        domain, entities, platform candidates, and constraints.
        """
        msg_lower = message.lower()
        ctx = SemanticContext()

        # 1. Detect explicit platform mentions
        detected_platforms = self._detect_platforms(msg_lower)

        # 2. Detect domain
        ctx.domain = self._detect_domain(msg_lower)

        # 3. Detect entities
        ctx.entities = self._detect_entities(msg_lower)

        # 4. Query knowledge graph
        profiles = self._graph.find(
            domain=ctx.domain,
            entity=ctx.entities[0] if ctx.entities else "",
            platform=detected_platforms[0] if detected_platforms else "",
        )

        # Merge explicit platform detections to front
        for plt in reversed(detected_platforms):
            p = self._graph.get_by_platform(plt)
            if p and p not in profiles:
                profiles.insert(0, p)

        if profiles:
            ctx.primary_profile = profiles[0]
            ctx.platform_candidates = [p.platform for p in profiles[:3]]
            ctx.constraints = profiles[0].constraints
            ctx.best_access_method = self._graph.best_access_method(profiles[0])
            ctx.confidence = 0.85 if detected_platforms else 0.60
            ctx.routing_notes.append(
                f"Platform '{profiles[0].platform}' matched via {'explicit mention' if detected_platforms else 'domain/entity inference'}."
            )
            if profiles[0].constraints:
                ctx.routing_notes.append(f"Known constraints: {', '.join(profiles[0].constraints)}.")
            if profiles[0].auth_type not in ("none", ""):
                ctx.routing_notes.append(f"Auth required: {profiles[0].auth_type}.")
        else:
            # Low-confidence: try LLM enrichment
            ctx = self._llm_enrich(message, ctx)

        return ctx

    # ------------------------------------------------------------------
    # Keyword detection helpers
    # ------------------------------------------------------------------

    def _detect_platforms(self, msg: str) -> List[str]:
        found = []
        for platform, keywords in _PLATFORM_KEYWORDS.items():
            if any(kw in msg for kw in keywords):
                found.append(platform)
        return found

    def _detect_domain(self, msg: str) -> str:
        scores: Dict[str, int] = {}
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in msg)
            if score:
                scores[domain] = score
        if not scores:
            return ""
        return max(scores, key=lambda d: scores[d])

    def _detect_entities(self, msg: str) -> List[str]:
        found = []
        for entity, keywords in _ENTITY_KEYWORDS.items():
            if any(kw in msg for kw in keywords):
                found.append(entity)
        return found

    # ------------------------------------------------------------------
    # LLM enrichment for ambiguous requests
    # ------------------------------------------------------------------

    def _llm_enrich(self, message: str, ctx: SemanticContext) -> SemanticContext:
        if not self._llm:
            ctx.routing_notes.append("No platform/domain detected; LLM enrichment skipped (no client).")
            return ctx

        known_platforms = self._graph.all_platforms()
        known_domains = self._graph.all_domains()

        prompt = (
            f"Analyze this user request and extract semantic routing information.\n"
            f"Request: \"{message}\"\n\n"
            f"Known domains: {', '.join(known_domains)}\n"
            f"Known platforms: {', '.join(known_platforms)}\n\n"
            "Return JSON only:\n"
            '{"domain": "string", "entities": ["list"], "platform": "string_or_empty", "confidence": 0.0_to_1.0}'
        )
        try:
            raw = self._llm._call_llm(prompt, temperature=0.1, max_tokens=200, expect_json=True)
            parsed = self._llm._extract_json(raw) if raw else None
            if isinstance(parsed, dict):
                ctx.domain = str(parsed.get("domain", ctx.domain))
                ctx.entities = list(parsed.get("entities", ctx.entities))
                ctx.confidence = float(parsed.get("confidence", 0.3))
                platform = str(parsed.get("platform", "")).strip()
                if platform:
                    profile = self._graph.get_by_platform(platform)
                    if profile:
                        ctx.primary_profile = profile
                        ctx.platform_candidates = [profile.platform]
                        ctx.constraints = profile.constraints
                        ctx.best_access_method = self._graph.best_access_method(profile)
                        ctx.routing_notes.append(f"LLM identified platform: {platform}.")
        except Exception as e:
            logger.warning(f"SemanticRouter LLM enrichment failed: {e}")
            ctx.routing_notes.append("LLM enrichment failed; proceeding without platform context.")

        return ctx


# Singleton
_router: Optional[SemanticRouter] = None


def get_semantic_router(llm_client=None) -> SemanticRouter:
    global _router
    if _router is None:
        _router = SemanticRouter(llm_client=llm_client)
    elif llm_client and _router._llm is None:
        _router._llm = llm_client
    return _router
