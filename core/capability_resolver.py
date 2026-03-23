"""
Capability Resolution Layer

Resolution order for a detected gap:
  1. Local tool exists but wasn't selected → suggest re-routing
  2. Platform-aware resolution via IntegrationKnowledgeGraph
  3. MCP server (live adapters first, then static catalogue)
  4. Public API wrap
  5. Nothing found → create_tool (last resort)
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from core.gap_detector import CapabilityGap
from core.integration_knowledge import get_integration_graph
from core.decision_engine import get_decision_engine


@dataclass
class ResolutionResult:
    resolved: bool
    action: str  # "reroute" | "mcp" | "api_wrap" | "create_tool"
    reason: str
    target: Optional[str] = None          # existing tool / MCP server / API name
    confidence: float = 0.0
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Static MCP server catalogue (extend as real MCP servers are added)
# ---------------------------------------------------------------------------
_MCP_CATALOGUE: Dict[str, Dict] = {
    "web_scraping":       {"server": "mcp-puppeteer",   "ops": ["navigate", "scrape", "screenshot"]},
    "html_parsing":       {"server": "mcp-puppeteer",   "ops": ["get_content"]},
    "browser_automation": {"server": "mcp-puppeteer",   "ops": ["click", "fill", "navigate"]},
    "github":             {"server": "mcp-github",      "ops": ["list_repos", "create_issue", "get_file"]},
    "filesystem":         {"server": "mcp-filesystem",  "ops": ["read", "write", "list"]},
    "database":           {"server": "mcp-sqlite",      "ops": ["query", "execute"]},
    "slack":              {"server": "mcp-slack",       "ops": ["send_message", "list_channels"]},
    "google_drive":       {"server": "mcp-gdrive",      "ops": ["list_files", "read_file", "upload"]},
}

# ---------------------------------------------------------------------------
# Static API-wrap catalogue (thin HTTPTool wrappers that could be auto-created)
# ---------------------------------------------------------------------------
_API_CATALOGUE: Dict[str, Dict] = {
    "weather":            {"api": "OpenWeatherMap",  "base_url": "https://api.openweathermap.org"},
    "geocoding":          {"api": "Nominatim",       "base_url": "https://nominatim.openstreetmap.org"},
    "currency":           {"api": "ExchangeRate-API","base_url": "https://api.exchangerate-api.com"},
    "news":               {"api": "NewsAPI",         "base_url": "https://newsapi.org"},
    "translation":        {"api": "LibreTranslate",  "base_url": "https://libretranslate.com"},
    "pdf_processing":     {"api": "PDFco",           "base_url": "https://api.pdf.co"},
    "image_processing":   {"api": "Cloudinary",      "base_url": "https://api.cloudinary.com"},
    "data_visualization": {"api": "QuickChart",      "base_url": "https://quickchart.io"},
}


class CapabilityResolver:
    """
    Resolves a CapabilityGap through the cheapest available path before
    recommending tool creation.
    """

    def __init__(self, registry=None):
        self._registry = registry
        self._graph = get_integration_graph()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, gap: CapabilityGap, semantic_context: Optional[Dict] = None) -> ResolutionResult:
        """Return the cheapest resolution for *gap*, platform-aware when semantic_context provided."""
        capability = (gap.capability or "").lower()
        domain = (gap.domain or "").lower()

        # 1. Local tool re-route
        result = self._check_local(capability, domain, gap)
        if result.resolved:
            result.confidence = self._de_score(result)
            return result

        # 2. Platform-aware resolution via knowledge graph
        if semantic_context:
            result = self._check_knowledge_graph(capability, semantic_context)
            if result.resolved:
                result.confidence = self._de_score(result)
                return result

        # 3. MCP server
        result = self._check_mcp(capability, domain)
        if result.resolved:
            result.confidence = self._de_score(result)
            return result

        # 4. API wrap
        result = self._check_api(capability, domain)
        if result.resolved:
            result.confidence = self._de_score(result)
            return result

        # 5. Last resort
        return ResolutionResult(
            resolved=False,
            action="create_tool",
            reason="No existing local tool, MCP server, or public API covers this capability.",
            confidence=gap.confidence,
        )

    def _de_score(self, result: ResolutionResult) -> float:
        """Run result through Decision Engine to get a unified confidence score."""
        engine = get_decision_engine()
        decision = engine.score(
            resolution_hints={"action": result.action, "confidence": result.confidence}
        )
        return decision.confidence

    # ------------------------------------------------------------------
    # Step 2 – knowledge graph platform-aware check
    # ------------------------------------------------------------------

    def _check_knowledge_graph(self, capability: str, semantic_context: Dict) -> ResolutionResult:
        platform = semantic_context.get("primary_platform", "")
        domain = semantic_context.get("domain", "")
        entities = semantic_context.get("entities", [])
        constraints = semantic_context.get("constraints", [])
        auth_type = semantic_context.get("auth_type", "")
        mcp_server = semantic_context.get("mcp_server")
        api_base = semantic_context.get("api_base")
        best_method = semantic_context.get("best_access_method", "")

        if not platform and not domain:
            return ResolutionResult(resolved=False, action="create_tool", reason="no knowledge graph match")

        # Find best matching profile
        profiles = self._graph.find(domain=domain, entity=entities[0] if entities else "", platform=platform)
        if not profiles:
            return ResolutionResult(resolved=False, action="create_tool", reason="no profile found")

        profile = profiles[0]
        notes = []
        if constraints:
            notes.append(f"Known constraints: {', '.join(constraints)}")
        if auth_type and auth_type != "none":
            notes.append(f"Auth required: {auth_type} — ensure credentials are stored via credential store")

        # Route to best access method
        if best_method == "api" and api_base:
            return ResolutionResult(
                resolved=True,
                action="api_wrap",
                reason=f"Knowledge graph: platform '{profile.platform}' supports API access.",
                target=profile.platform,
                confidence=profile.reliability,
                notes=[f"Base URL: {api_base}"] + notes,
            )
        if best_method == "mcp" and mcp_server:
            return ResolutionResult(
                resolved=True,
                action="mcp",
                reason=f"Knowledge graph: platform '{profile.platform}' has MCP server '{mcp_server}'.",
                target=mcp_server,
                confidence=profile.reliability,
                notes=notes,
            )
        if best_method in ("browser", "scraping"):
            return ResolutionResult(
                resolved=True,
                action="reroute",
                reason=f"Knowledge graph: platform '{profile.platform}' requires browser/scraping access.",
                target="BrowserAutomationTool",
                confidence=profile.reliability,
                notes=[f"No public API available for {profile.platform}."] + notes,
            )

        return ResolutionResult(resolved=False, action="create_tool", reason="no suitable access method in profile")

    # ------------------------------------------------------------------
    # Step 1 – local tool check
    # ------------------------------------------------------------------

    def _check_local(self, capability: str, domain: str, gap: CapabilityGap) -> ResolutionResult:
        if not self._registry:
            return ResolutionResult(resolved=False, action="create_tool", reason="no registry")

        try:
            all_caps = self._registry.get_all_capabilities()
        except Exception:
            return ResolutionResult(resolved=False, action="create_tool", reason="registry error")

        # Fuzzy match: does any registered capability name contain the gap keyword?
        keywords = set(capability.replace(":", "_").replace("-", "_").split("_"))
        keywords.discard("")
        for cap_name in all_caps:
            cap_lower = cap_name.lower()
            if any(kw in cap_lower for kw in keywords if len(kw) > 3):
                tool_name = getattr(all_caps[cap_name], "tool_name", None) or cap_name
                return ResolutionResult(
                    resolved=True,
                    action="reroute",
                    reason=f"Capability '{cap_name}' already exists in local tool '{tool_name}'.",
                    target=str(tool_name),
                    confidence=0.80,
                    notes=["Skill selector may need re-routing to include this tool."],
                )
        return ResolutionResult(resolved=False, action="create_tool", reason="no local match")

    # ------------------------------------------------------------------
    # Step 2 – MCP catalogue check
    # ------------------------------------------------------------------

    def _check_mcp(self, capability: str, domain: str) -> ResolutionResult:
        # First: check live MCP adapters already loaded in the registry
        if self._registry:
            try:
                for tool in self._registry.tools:
                    if tool.__class__.__name__.startswith("MCPAdapterTool"):
                        server_info = tool.get_server_info()
                        if not server_info.get("connected"):
                            continue
                        for mcp_tool_name in server_info.get("tools", []):
                            if capability in mcp_tool_name.lower() or mcp_tool_name.lower() in capability:
                                return ResolutionResult(
                                    resolved=True,
                                    action="mcp",
                                    reason=f"Live MCP adapter '{server_info['server_name']}' has tool '{mcp_tool_name}'.",
                                    target=server_info["server_name"],
                                    confidence=0.85,
                                    notes=[f"Use capability '{mcp_tool_name}' directly."],
                                )
            except Exception:
                pass

        # Fallback: static catalogue
        for key, entry in _MCP_CATALOGUE.items():
            if key in capability or key in domain or capability in key:
                return ResolutionResult(
                    resolved=True,
                    action="mcp",
                    reason=f"MCP server '{entry['server']}' covers '{key}'.",
                    target=entry["server"],
                    confidence=0.75,
                    notes=[
                        f"Available ops: {', '.join(entry['ops'])}",
                        "Install MCP adapter and wire into ContextAwareToolSelector.",
                    ],
                )
        return ResolutionResult(resolved=False, action="create_tool", reason="no MCP match")

    # ------------------------------------------------------------------
    # Step 3 – API wrap catalogue check
    # ------------------------------------------------------------------

    def _check_api(self, capability: str, domain: str) -> ResolutionResult:
        for key, entry in _API_CATALOGUE.items():
            if key in capability or key in domain or capability in key:
                return ResolutionResult(
                    resolved=True,
                    action="api_wrap",
                    reason=f"Public API '{entry['api']}' covers '{key}'.",
                    target=entry["api"],
                    confidence=0.65,
                    notes=[
                        f"Base URL: {entry['base_url']}",
                        "Create a thin HTTPTool wrapper; no new service needed.",
                    ],
                )
        return ResolutionResult(resolved=False, action="create_tool", reason="no API match")
