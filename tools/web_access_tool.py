"""Unified web access tool that chooses HTTP or browser transport internally."""
from __future__ import annotations

import re
from urllib.parse import quote_plus, urljoin, urlparse

from tools.tool_capability import Parameter, ParameterType, SafetyLevel, ToolCapability
from tools.tool_interface import BaseTool


class WebAccessTool(BaseTool):
    """Higher-level web access facade over HTTP and browser services."""

    BROWSER_FIRST_DOMAINS = (
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "gamespot.com",
        "www.gamespot.com",
        "ign.com",
        "www.ign.com",
        "store.steampowered.com",
        "google.com",
        "www.google.com",
    )
    GAME_DISCOVERY_SOURCES = (
        "https://store.steampowered.com/search/?term={query}",
        "https://www.ign.com/search?q={query}",
        "https://www.gamespot.com/search/?q={query}",
    )

    def __init__(self, orchestrator=None):
        self.description = "Unified web access for fetching, searching, and opening pages."
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        self.add_capability(
            ToolCapability(
                name="fetch_url",
                description="Fetch page content from a URL. Automatically chooses HTTP or browser navigation based on the target and task.",
                parameters=[
                    Parameter("url", ParameterType.STRING, "The URL to fetch", required=True),
                    Parameter(
                        "mode",
                        ParameterType.STRING,
                        "Access mode: auto, http, or browser. Prefer auto unless you explicitly need one.",
                        required=False,
                    ),
                ],
                returns="Fetched page content and access metadata.",
                safety_level=SafetyLevel.MEDIUM,
                examples=[{"url": "https://en.wikipedia.org/wiki/Agentic_AI"}],
                dependencies=[],
            ),
            self._handle_fetch_url,
        )
        self.add_capability(
            ToolCapability(
                name="search_web",
                description="Search the web in a browser and return the visible content of the results page.",
                parameters=[
                    Parameter("query", ParameterType.STRING, "Search query to run", required=True),
                    Parameter(
                        "engine",
                        ParameterType.STRING,
                        "Search engine to use. Supported: duckduckgo or google. Defaults to duckduckgo.",
                        required=False,
                    ),
                ],
                returns="Search results page content and search metadata.",
                safety_level=SafetyLevel.LOW,
                examples=[{"query": "new AAA action games"}],
                dependencies=[],
            ),
            self._handle_search_web,
        )
        self.add_capability(
            ToolCapability(
                name="open_page",
                description="Open a page in a browser for interactive tasks and return the visible page content.",
                parameters=[
                    Parameter("url", ParameterType.STRING, "The URL to open in the browser", required=True),
                ],
                returns="Browser navigation result with visible page text.",
                safety_level=SafetyLevel.LOW,
                examples=[{"url": "https://www.youtube.com/results?search_query=expedition+33+trailer"}],
                dependencies=[],
            ),
            self._handle_open_page,
        )
        self.add_capability(
            ToolCapability(
                name="get_current_page",
                description="Get the visible text from the currently open browser page after prior web automation steps.",
                parameters=[],
                returns="Visible content from the active browser page.",
                safety_level=SafetyLevel.LOW,
                examples=[],
                dependencies=[],
            ),
            self._handle_get_current_page,
        )
        self.add_capability(
            ToolCapability(
                name="get_current_page_details",
                description="Get structured details about the currently open browser page including URL, title, visible text, and extracted links.",
                parameters=[],
                returns="Structured current page details for iterative planning.",
                safety_level=SafetyLevel.LOW,
                examples=[],
                dependencies=[],
            ),
            self._handle_get_current_page_details,
        )
        self.add_capability(
            ToolCapability(
                name="extract_links",
                description="Extract links from the currently open browser page or provided HTML content.",
                parameters=[
                    Parameter("html", ParameterType.STRING, "Optional HTML content to extract links from. If omitted, uses the current page.", required=False),
                    Parameter("base_url", ParameterType.STRING, "Optional base URL for resolving relative links. Defaults to the current page URL.", required=False),
                    Parameter("limit", ParameterType.INTEGER, "Maximum number of links to return.", required=False),
                ],
                returns="Extracted links with labels when available.",
                safety_level=SafetyLevel.LOW,
                examples=[],
                dependencies=[],
            ),
            self._handle_extract_links,
        )
        self.add_capability(
            ToolCapability(
                name="extract_search_results",
                description="Extract structured search results from the current browser page or provided HTML content.",
                parameters=[
                    Parameter("html", ParameterType.STRING, "Optional HTML content to inspect. If omitted, uses the current page.", required=False),
                    Parameter("base_url", ParameterType.STRING, "Optional base URL for resolving relative links. Defaults to the current page URL.", required=False),
                    Parameter("limit", ParameterType.INTEGER, "Maximum number of results to return.", required=False),
                ],
                returns="Structured search results with titles and URLs.",
                safety_level=SafetyLevel.LOW,
                examples=[],
                dependencies=[],
            ),
            self._handle_extract_search_results,
        )
        self.add_capability(
            ToolCapability(
                name="crawl_site",
                description="Collect content from a starting page and a small number of linked pages on the same site.",
                parameters=[
                    Parameter("start_url", ParameterType.STRING, "The first URL to crawl", required=True),
                    Parameter(
                        "max_pages",
                        ParameterType.INTEGER,
                        "Maximum number of pages to collect, including the starting page.",
                        required=False,
                    ),
                    Parameter(
                        "mode",
                        ParameterType.STRING,
                        "Access mode: auto, http, or browser. Prefer auto unless you explicitly need one.",
                        required=False,
                    ),
                ],
                returns="Collected pages with URL, access mode, and content.",
                safety_level=SafetyLevel.MEDIUM,
                examples=[{"start_url": "https://example.com", "max_pages": 3}],
                dependencies=[],
            ),
            self._handle_crawl_site,
        )

    def _handle_fetch_url(self, **kwargs):
        url = kwargs.get("url")
        mode = (kwargs.get("mode") or "auto").strip().lower()
        if not url:
            raise ValueError("Missing required parameter: url")
        if mode not in {"auto", "http", "browser"}:
            raise ValueError("mode must be one of: auto, http, browser")

        chosen_mode = self._choose_mode(url, requested_mode=mode)
        if chosen_mode == "browser":
            return self._fetch_with_browser(url, reason="browser_selected")

        http_result = self._fetch_with_http(url)
        if http_result["success"]:
            return http_result

        if mode == "auto" and self._should_fallback_to_browser(url, http_result):
            browser_result = self._fetch_with_browser(url, reason="http_fallback")
            browser_result["fallback_from"] = "http"
            browser_result["initial_error"] = http_result.get("error")
            return browser_result

        return http_result

    def _handle_search_web(self, **kwargs):
        query = kwargs.get("query")
        engine = (kwargs.get("engine") or "duckduckgo").strip().lower()
        if not query:
            raise ValueError("Missing required parameter: query")

        source_result = self._search_and_collect_sources(query, engine)
        if source_result:
            return source_result

        encoded_query = quote_plus(query)
        if engine == "duckduckgo":
            url = f"https://duckduckgo.com/?q={encoded_query}"
        else:
            url = f"https://www.google.com/search?q={encoded_query}"

        result = self._fetch_with_browser(url, reason="search")
        result["query"] = query
        result["engine"] = engine
        if result.get("success"):
            try:
                current_url = self.services.browser.get_current_url()
                page_title = self.services.browser.get_page_title()
                page_source = self.services.browser.get_page_source()
                extracted_results = self._extract_search_results_from_html(page_source, base_url=current_url, limit=8)
                extracted_links = self._extract_links_from_html(page_source, base_url=current_url, limit=12)
                if extracted_results:
                    result["results"] = extracted_results
                if extracted_links:
                    result["links"] = extracted_links
                result["url"] = current_url
                result["title"] = page_title
            except Exception:
                pass
        if result.get("success") and not self._is_blocked_search_result(result.get("content", "")):
            return result

        fallback_results = []
        for fallback_engine in self._fallback_search_engines(engine):
            fallback_url = self._build_search_url(query, fallback_engine)
            fallback_result = self._fetch_with_browser(fallback_url, reason="search_fallback")
            fallback_result["query"] = query
            fallback_result["engine"] = fallback_engine
            fallback_results.append(fallback_result)
            if fallback_result.get("success") and not self._is_blocked_search_result(fallback_result.get("content", "")):
                fallback_result["fallback_from"] = engine
                fallback_result["attempts"] = [engine, fallback_engine]
                return fallback_result

        if self._looks_like_game_discovery_query(query):
            source_results = self._search_game_sources(query)
            successful_sources = [item for item in source_results if item.get("success")]
            return {
                "success": bool(successful_sources),
                "mode": "browser",
                "reason": "source_fallback",
                "query": query,
                "engine": engine,
                "attempts": [engine] + [item.get("engine") for item in fallback_results],
                "blocked_search": True,
                "fallback_strategy": "game_sources",
                "sources": source_results,
                "content": "\n\n".join(
                    f"{item.get('source')}: {(item.get('content') or '')[:2000]}"
                    for item in successful_sources
                )[:10000],
                "error": None if successful_sources else "Search backends blocked and source fallback returned no successful pages.",
            }

        result["blocked_search"] = True
        result["attempts"] = [engine] + [item.get("engine") for item in fallback_results]
        result["error"] = result.get("error") or "Search backend blocked or returned anti-bot response."
        return result

    def _handle_open_page(self, **kwargs):
        url = kwargs.get("url")
        if not url:
            raise ValueError("Missing required parameter: url")
        return self._fetch_with_browser(url, reason="interactive_open")

    def _handle_get_current_page(self, **kwargs):
        try:
            content = self.services.browser.get_page_text()
            return {
                "success": True,
                "mode": "browser",
                "reason": "current_page",
                "content": content[:10000],
            }
        except Exception as exc:
            return {
                "success": False,
                "mode": "browser",
                "reason": "current_page",
                "error": str(exc),
            }

    def _handle_get_current_page_details(self, **kwargs):
        try:
            current_url = self.services.browser.get_current_url()
            title = self.services.browser.get_page_title()
            content = self.services.browser.get_page_text()
            html = self.services.browser.get_page_source()
            links = self._extract_links_from_html(html, base_url=current_url, limit=20)
            return {
                "success": True,
                "mode": "browser",
                "reason": "current_page_details",
                "url": current_url,
                "title": title,
                "content": content[:10000],
                "links": links,
            }
        except Exception as exc:
            return {
                "success": False,
                "mode": "browser",
                "reason": "current_page_details",
                "error": str(exc),
            }

    def _handle_extract_links(self, **kwargs):
        html = kwargs.get("html")
        limit = int(kwargs.get("limit") or 20)
        base_url = kwargs.get("base_url")
        if not html:
            html = self.services.browser.get_page_source()
        if not base_url:
            base_url = self.services.browser.get_current_url()
        links = self._extract_links_from_html(html, base_url=base_url, limit=limit)
        return {
            "success": True,
            "mode": "browser",
            "reason": "extract_links",
            "base_url": base_url,
            "count": len(links),
            "links": links,
        }

    def _handle_extract_search_results(self, **kwargs):
        html = kwargs.get("html")
        limit = int(kwargs.get("limit") or 10)
        base_url = kwargs.get("base_url")
        if not html:
            html = self.services.browser.get_page_source()
        if not base_url:
            base_url = self.services.browser.get_current_url()
        results = self._extract_search_results_from_html(html, base_url=base_url, limit=limit)
        return {
            "success": True,
            "mode": "browser",
            "reason": "extract_search_results",
            "base_url": base_url,
            "count": len(results),
            "results": results,
        }

    def _handle_crawl_site(self, **kwargs):
        start_url = kwargs.get("start_url")
        max_pages = int(kwargs.get("max_pages") or 3)
        mode = (kwargs.get("mode") or "auto").strip().lower()
        if not start_url:
            raise ValueError("Missing required parameter: start_url")

        max_pages = max(1, min(max_pages, 5))
        visited = []
        queue = [start_url]
        seen = {start_url}
        host = (urlparse(start_url).netloc or "").lower()

        while queue and len(visited) < max_pages:
            url = queue.pop(0)
            page_result = self._handle_fetch_url(url=url, mode=mode)
            visited.append(
                {
                    "url": url,
                    "mode": page_result.get("mode"),
                    "success": page_result.get("success", False),
                    "content": page_result.get("content", ""),
                    "error": page_result.get("error"),
                }
            )
            if not page_result.get("success"):
                continue

            for link in self._extract_links(page_result.get("content", ""), base_url=url):
                parsed = urlparse(link)
                if (parsed.netloc or "").lower() != host:
                    continue
                if link in seen:
                    continue
                seen.add(link)
                queue.append(link)
                if len(queue) + len(visited) >= max_pages:
                    break

        return {
            "success": True,
            "mode": "crawl",
            "start_url": start_url,
            "page_count": len(visited),
            "pages": visited,
        }

    def _choose_mode(self, url: str, requested_mode: str = "auto") -> str:
        if requested_mode in {"http", "browser"}:
            return requested_mode

        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").lower()

        if host.startswith("localhost") or host.startswith("127.0.0.1"):
            return "http"
        if "/api/" in path or path.endswith(".json") or host.startswith("api."):
            return "http"
        if any(host == domain or host.endswith(f".{domain}") for domain in self.BROWSER_FIRST_DOMAINS):
            return "browser"
        return "http"

    def _fetch_with_http(self, url: str) -> dict:
        try:
            response = self.services.http.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                },
                timeout=20,
            )
            status = response.get("status", 0)
            body = (response.get("body") or "")[:10000]
            if status >= 400:
                return {
                    "success": False,
                    "mode": "http",
                    "url": url,
                    "status": status,
                    "error": f"HTTP Error: {status}",
                    "content": body,
                }
            return {
                "success": True,
                "mode": "http",
                "url": url,
                "status": status,
                "content": body,
            }
        except Exception as exc:
            return {
                "success": False,
                "mode": "http",
                "url": url,
                "error": str(exc),
            }

    def _fetch_with_browser(self, url: str, reason: str) -> dict:
        try:
            self.services.browser.open_browser()
            self.services.browser.navigate(url)
            content = self.services.browser.get_page_text()
            return {
                "success": True,
                "mode": "browser",
                "url": url,
                "reason": reason,
                "content": content[:10000],
            }
        except Exception as exc:
            return {
                "success": False,
                "mode": "browser",
                "url": url,
                "reason": reason,
                "error": str(exc),
            }

    def _should_fallback_to_browser(self, url: str, http_result: dict) -> bool:
        if not http_result or http_result.get("success"):
            return False

        status = http_result.get("status")
        error = (http_result.get("error") or "").lower()
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()

        if status in {401, 403, 405, 429}:
            return True
        if "forbidden" in error or "blocked" in error or "captcha" in error:
            return True
        return any(host == domain or host.endswith(f".{domain}") for domain in self.BROWSER_FIRST_DOMAINS)

    def _build_search_url(self, query: str, engine: str) -> str:
        encoded_query = quote_plus(query)
        if engine == "google":
            return f"https://www.google.com/search?q={encoded_query}"
        return f"https://duckduckgo.com/?q={encoded_query}"

    def _fallback_search_engines(self, primary_engine: str) -> list[str]:
        ordered = ["duckduckgo", "google"]
        return [engine for engine in ordered if engine != primary_engine]

    def _is_blocked_search_result(self, content: str) -> bool:
        text = (content or "").lower()
        if not text:
            return True

        blocked_markers = (
            "unusual traffic",
            "detected unusual traffic",
            "not a robot",
            "captcha",
            "verify you are human",
            "automated queries",
            "access denied",
        )
        return any(marker in text for marker in blocked_markers)

    def _looks_like_game_discovery_query(self, query: str) -> bool:
        text = (query or "").lower()
        game_markers = ("game", "games", "aaa", "multiplayer", "action", "steam", "shooter")
        return any(marker in text for marker in game_markers)

    def _search_game_sources(self, query: str) -> list[dict]:
        results = []
        encoded_query = quote_plus(query)
        for template in self.GAME_DISCOVERY_SOURCES:
            source_url = template.format(query=encoded_query)
            result = self._fetch_with_browser(source_url, reason="game_source_fallback")
            result["source"] = urlparse(source_url).netloc
            result["url"] = source_url
            results.append(result)
        return results

    def _search_and_collect_sources(self, query: str, engine: str) -> dict | None:
        if engine != "duckduckgo":
            return None

        search_html = self._fetch_search_results_html(query)
        if not search_html:
            return None

        links = self._extract_search_result_links(search_html, max_links=3)
        if not links:
            return None

        sources = []
        for link in links:
            page = self._handle_fetch_url(url=link, mode="auto")
            sources.append(
                {
                    "url": link,
                    "mode": page.get("mode"),
                    "success": page.get("success", False),
                    "content": page.get("content", ""),
                    "error": page.get("error"),
                }
            )

        successful_sources = [item for item in sources if item.get("success") and item.get("content")]
        if not successful_sources:
            return None

        combined_content = "\n\n".join(
            f"Source: {item['url']}\n{item['content'][:2500]}" for item in successful_sources
        )[:10000]
        return {
            "success": True,
            "mode": "source_collection",
            "reason": "search_then_fetch",
            "query": query,
            "engine": engine,
            "source_count": len(successful_sources),
            "sources": sources,
            "content": combined_content,
        }

    def _fetch_search_results_html(self, query: str) -> str:
        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            response = self.services.http.get(
                search_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                timeout=20,
            )
        except Exception:
            return ""

        if int(response.get("status", 0)) >= 400:
            return ""
        return response.get("body") or ""

    def _extract_search_result_links(self, html: str, max_links: int = 3) -> list[str]:
        if not html:
            return []

        links = []
        patterns = [
            r'href="(https?://[^"]+)"',
            r'nofollow" class="[^"]*" href="(https?://[^"]+)"',
            r'uddg=(https?%3A%2F%2F[^&"]+)',
        ]
        for pattern in patterns:
            for match in re.findall(pattern, html, flags=re.IGNORECASE):
                link = match
                if link.startswith("https%3A") or link.startswith("http%3A"):
                    from urllib.parse import unquote
                    link = unquote(link)
                if "duckduckgo.com" in link:
                    continue
                if link in links:
                    continue
                links.append(link)
                if len(links) >= max_links:
                    return links
        return links

    def _extract_links(self, content: str, base_url: str) -> list[str]:
        if not content:
            return []

        hrefs = re.findall(r'href=[\'"]([^\'"#]+)', content, flags=re.IGNORECASE)
        links = []
        for href in hrefs:
            absolute = urljoin(base_url, href)
            if absolute.startswith("http://") or absolute.startswith("https://"):
                links.append(absolute)
        return links

    def _extract_links_from_html(self, html: str, base_url: str, limit: int = 20) -> list[dict]:
        if not html:
            return []

        matches = re.findall(
            r'<a[^>]+href=[\'"]([^\'"#]+)[\'"][^>]*>(.*?)</a>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        links = []
        for href, label_html in matches:
            absolute = urljoin(base_url, href)
            
            parsed_url = urlparse(absolute)
            host = (parsed_url.netloc or "").lower()
            if host in {"www.google.com", "google.com"} and parsed_url.path == "/url":
                from urllib.parse import parse_qs
                qs = parse_qs(parsed_url.query)
                if "q" in qs and qs["q"]:
                    absolute = qs["q"][0]
            elif host in {"duckduckgo.com"} and parsed_url.path == "/l/":
                from urllib.parse import parse_qs
                qs = parse_qs(parsed_url.query)
                if "uddg" in qs and qs["uddg"]:
                    absolute = qs["uddg"][0]
                    
            if not (absolute.startswith("http://") or absolute.startswith("https://")):
                continue
            label = re.sub(r"<[^>]+>", " ", label_html)
            label = re.sub(r"\s+", " ", label).strip()
            if any(existing["url"] == absolute for existing in links):
                continue
            links.append({"url": absolute, "label": label})
            if len(links) >= limit:
                break
        return links

    def _extract_search_results_from_html(self, html: str, base_url: str, limit: int = 10) -> list[dict]:
        links = self._extract_links_from_html(html, base_url=base_url, limit=max(limit * 3, 10))
        results = []
        ignored_hosts = {"duckduckgo.com", "www.google.com", "google.com"}
        for link in links:
            host = (urlparse(link["url"]).netloc or "").lower()
            if host in ignored_hosts:
                continue
            if not link.get("label"):
                continue
            results.append({"title": link["label"], "url": link["url"]})
            if len(results) >= limit:
                break
        return results
