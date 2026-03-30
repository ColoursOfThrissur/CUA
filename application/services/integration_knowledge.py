"""
Integration Knowledge Graph

Maps user intent domains/entities to platforms, their capabilities,
access methods, auth requirements, and known constraints.

Used by SemanticRouter and CapabilityResolver to make platform-aware decisions
instead of blind tool/MCP catalogue lookups.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class IntegrationProfile:
    platform: str
    domain: str                        # e-commerce, productivity, communication, etc.
    entities: List[str]                # orders, files, messages, events, repos...
    capabilities: List[str]            # what actions are possible
    access_methods: List[str]          # api, browser, mcp, scraping
    auth_type: str                     # oauth2, api_key, cookie, none
    constraints: List[str]             # captcha, rate_limit, bot_detection, login_required
    mcp_server: Optional[str] = None   # preferred MCP server if available
    api_base: Optional[str] = None     # REST API base URL if available
    reliability: float = 0.8           # 0-1, used by resolver to rank methods
    notes: str = ""


# ---------------------------------------------------------------------------
# The knowledge graph — extend freely
# ---------------------------------------------------------------------------
_PROFILES: List[IntegrationProfile] = [

    # ── E-Commerce ──────────────────────────────────────────────────────────
    IntegrationProfile(
        platform="amazon", domain="e-commerce",
        entities=["orders", "tracking", "returns", "products", "cart", "wishlist", "reviews"],
        capabilities=["track_order", "list_orders", "search_products", "get_product_details", "manage_returns"],
        access_methods=["browser", "scraping"],
        auth_type="cookie",
        constraints=["captcha", "bot_detection", "login_required", "2fa"],
        reliability=0.65,
        notes="No public API. Browser automation with session cookies is the only reliable path.",
    ),
    IntegrationProfile(
        platform="ebay", domain="e-commerce",
        entities=["orders", "listings", "bids", "feedback"],
        capabilities=["list_orders", "search_listings", "get_item", "place_bid"],
        access_methods=["api", "browser"],
        auth_type="oauth2",
        api_base="https://api.ebay.com",
        constraints=["rate_limit", "oauth_required"],
        reliability=0.85,
    ),
    IntegrationProfile(
        platform="shopify", domain="e-commerce",
        entities=["orders", "products", "customers", "inventory"],
        capabilities=["list_orders", "get_order", "list_products", "update_inventory"],
        access_methods=["api"],
        auth_type="api_key",
        api_base="https://{shop}.myshopify.com/admin/api",
        constraints=["rate_limit", "shop_specific_url"],
        reliability=0.92,
    ),

    # ── Productivity ─────────────────────────────────────────────────────────
    IntegrationProfile(
        platform="notion", domain="productivity",
        entities=["pages", "databases", "blocks", "comments"],
        capabilities=["read_page", "create_page", "update_page", "query_database", "search"],
        access_methods=["api", "mcp"],
        auth_type="api_key",
        api_base="https://api.notion.com/v1",
        mcp_server="mcp-notion",
        constraints=["rate_limit"],
        reliability=0.90,
    ),
    IntegrationProfile(
        platform="google_drive", domain="productivity",
        entities=["files", "folders", "documents", "spreadsheets"],
        capabilities=["list_files", "read_file", "upload_file", "create_folder", "share"],
        access_methods=["api", "mcp"],
        auth_type="oauth2",
        api_base="https://www.googleapis.com/drive/v3",
        mcp_server="mcp-gdrive",
        constraints=["oauth_required", "rate_limit"],
        reliability=0.92,
    ),
    IntegrationProfile(
        platform="google_calendar", domain="productivity",
        entities=["events", "calendars", "reminders"],
        capabilities=["list_events", "create_event", "update_event", "delete_event"],
        access_methods=["api"],
        auth_type="oauth2",
        api_base="https://www.googleapis.com/calendar/v3",
        constraints=["oauth_required", "rate_limit"],
        reliability=0.90,
    ),
    IntegrationProfile(
        platform="trello", domain="productivity",
        entities=["boards", "cards", "lists", "members"],
        capabilities=["list_boards", "get_cards", "create_card", "move_card"],
        access_methods=["api"],
        auth_type="api_key",
        api_base="https://api.trello.com/1",
        constraints=["rate_limit"],
        reliability=0.88,
    ),

    # ── Communication ────────────────────────────────────────────────────────
    IntegrationProfile(
        platform="slack", domain="communication",
        entities=["messages", "channels", "users", "files", "threads"],
        capabilities=["send_message", "list_channels", "read_messages", "upload_file", "search"],
        access_methods=["api", "mcp"],
        auth_type="oauth2",
        api_base="https://slack.com/api",
        mcp_server="mcp-slack",
        constraints=["oauth_required", "rate_limit", "workspace_scoped"],
        reliability=0.93,
    ),
    IntegrationProfile(
        platform="gmail", domain="communication",
        entities=["emails", "threads", "labels", "drafts", "attachments"],
        capabilities=["list_emails", "read_email", "send_email", "search_emails", "manage_labels"],
        access_methods=["api"],
        auth_type="oauth2",
        api_base="https://gmail.googleapis.com/gmail/v1",
        constraints=["oauth_required", "rate_limit"],
        reliability=0.91,
    ),
    IntegrationProfile(
        platform="discord", domain="communication",
        entities=["messages", "channels", "servers", "users"],
        capabilities=["send_message", "read_messages", "list_channels"],
        access_methods=["api"],
        auth_type="api_key",
        api_base="https://discord.com/api/v10",
        constraints=["rate_limit", "bot_token_required"],
        reliability=0.88,
    ),

    # ── Development ──────────────────────────────────────────────────────────
    IntegrationProfile(
        platform="github", domain="development",
        entities=["repos", "issues", "pull_requests", "commits", "files", "actions"],
        capabilities=["list_repos", "create_issue", "get_file", "create_pr", "list_commits", "trigger_workflow"],
        access_methods=["api", "mcp"],
        auth_type="api_key",
        api_base="https://api.github.com",
        mcp_server="mcp-github",
        constraints=["rate_limit", "token_required"],
        reliability=0.95,
    ),
    IntegrationProfile(
        platform="gitlab", domain="development",
        entities=["repos", "issues", "merge_requests", "pipelines", "files"],
        capabilities=["list_projects", "create_issue", "get_file", "create_mr", "trigger_pipeline"],
        access_methods=["api"],
        auth_type="api_key",
        api_base="https://gitlab.com/api/v4",
        constraints=["rate_limit", "token_required"],
        reliability=0.90,
    ),
    IntegrationProfile(
        platform="jira", domain="development",
        entities=["issues", "projects", "sprints", "boards", "comments"],
        capabilities=["list_issues", "create_issue", "update_issue", "get_sprint", "add_comment"],
        access_methods=["api"],
        auth_type="api_key",
        api_base="https://{instance}.atlassian.net/rest/api/3",
        constraints=["rate_limit", "instance_specific_url"],
        reliability=0.88,
    ),

    # ── Finance ──────────────────────────────────────────────────────────────
    IntegrationProfile(
        platform="yahoo_finance", domain="finance",
        entities=["stocks", "prices", "charts", "news", "fundamentals"],
        capabilities=["get_price", "get_history", "get_news", "get_fundamentals"],
        access_methods=["api", "scraping"],
        auth_type="none",
        api_base="https://query1.finance.yahoo.com/v8/finance",
        constraints=["rate_limit", "unofficial_api"],
        reliability=0.75,
        notes="Unofficial API — may break. Scraping as fallback.",
    ),
    IntegrationProfile(
        platform="alpha_vantage", domain="finance",
        entities=["stocks", "forex", "crypto", "indicators"],
        capabilities=["get_price", "get_history", "get_indicator", "get_forex"],
        access_methods=["api"],
        auth_type="api_key",
        api_base="https://www.alphavantage.co/query",
        constraints=["rate_limit", "free_tier_limited"],
        reliability=0.85,
    ),

    # ── Weather ──────────────────────────────────────────────────────────────
    IntegrationProfile(
        platform="openweathermap", domain="weather",
        entities=["current_weather", "forecast", "alerts", "air_quality"],
        capabilities=["get_current", "get_forecast", "get_alerts"],
        access_methods=["api"],
        auth_type="api_key",
        api_base="https://api.openweathermap.org/data/2.5",
        constraints=["rate_limit", "free_tier_limited"],
        reliability=0.92,
    ),

    # ── News ─────────────────────────────────────────────────────────────────
    IntegrationProfile(
        platform="newsapi", domain="news",
        entities=["articles", "headlines", "sources"],
        capabilities=["get_headlines", "search_articles", "list_sources"],
        access_methods=["api"],
        auth_type="api_key",
        api_base="https://newsapi.org/v2",
        constraints=["rate_limit", "free_tier_limited"],
        reliability=0.88,
    ),

    # ── Local / Filesystem ───────────────────────────────────────────────────
    IntegrationProfile(
        platform="local_filesystem", domain="computer",
        entities=["files", "folders", "directories"],
        capabilities=["read_file", "write_file", "list_directory", "delete_file"],
        access_methods=["local_tool"],
        auth_type="none",
        constraints=["path_restrictions"],
        reliability=0.99,
    ),
    IntegrationProfile(
        platform="local_database", domain="data",
        entities=["tables", "rows", "queries"],
        capabilities=["query", "insert", "update", "delete"],
        access_methods=["local_tool", "mcp"],
        auth_type="none",
        mcp_server="mcp-sqlite",
        constraints=[],
        reliability=0.97,
    ),
]

# Build lookup indices at module load time
_BY_PLATFORM: Dict[str, IntegrationProfile] = {p.platform: p for p in _PROFILES}
_BY_DOMAIN: Dict[str, List[IntegrationProfile]] = {}
_BY_ENTITY: Dict[str, List[IntegrationProfile]] = {}

for _p in _PROFILES:
    _BY_DOMAIN.setdefault(_p.domain, []).append(_p)
    for _e in _p.entities:
        _BY_ENTITY.setdefault(_e, []).append(_p)


class IntegrationKnowledgeGraph:
    """
    Query interface over the static integration profiles.
    All lookups are O(1) or O(n) over small lists — no DB needed.
    """

    def get_by_platform(self, platform: str) -> Optional[IntegrationProfile]:
        return _BY_PLATFORM.get(platform.lower().replace(" ", "_"))

    def get_by_domain(self, domain: str) -> List[IntegrationProfile]:
        return _BY_DOMAIN.get(domain.lower(), [])

    def get_by_entity(self, entity: str) -> List[IntegrationProfile]:
        return _BY_ENTITY.get(entity.lower(), [])

    def find(self, domain: str = "", entity: str = "", platform: str = "") -> List[IntegrationProfile]:
        """
        Return profiles matching any of the provided hints, ranked by reliability.
        At least one hint must be non-empty.
        """
        seen: Dict[str, IntegrationProfile] = {}

        if platform:
            p = self.get_by_platform(platform)
            if p:
                seen[p.platform] = p

        if domain:
            for p in self.get_by_domain(domain):
                seen[p.platform] = p

        if entity:
            for p in self.get_by_entity(entity):
                seen[p.platform] = p

        return sorted(seen.values(), key=lambda x: x.reliability, reverse=True)

    def best_access_method(self, profile: IntegrationProfile) -> str:
        """Return the highest-reliability access method for a profile."""
        priority = ["api", "mcp", "local_tool", "browser", "scraping"]
        for method in priority:
            if method in profile.access_methods:
                return method
        return profile.access_methods[0] if profile.access_methods else "unknown"

    def all_platforms(self) -> List[str]:
        return list(_BY_PLATFORM.keys())

    def all_domains(self) -> List[str]:
        return list(_BY_DOMAIN.keys())


# Singleton
_graph: Optional[IntegrationKnowledgeGraph] = None


def get_integration_graph() -> IntegrationKnowledgeGraph:
    global _graph
    if _graph is None:
        _graph = IntegrationKnowledgeGraph()
    return _graph
