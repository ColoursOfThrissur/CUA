from tools.web_access_tool import WebAccessTool


class _FakeHTTPService:
    def __init__(self, response=None, error=None, response_by_url=None):
        self.response = response or {"status": 200, "body": "http-body"}
        self.error = error
        self.response_by_url = response_by_url or {}
        self.calls = []

    def get(self, url, headers=None, timeout=30):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if self.error:
            raise self.error
        if url in self.response_by_url:
            return self.response_by_url[url]
        return self.response


class _FakeBrowserService:
    def __init__(self, content="browser-body", content_by_url=None, html_by_url=None, title_by_url=None):
        self.content = content
        self.content_by_url = content_by_url or {}
        self.html_by_url = html_by_url or {}
        self.title_by_url = title_by_url or {}
        self.opened = False
        self.navigated = []
        self.current_url = None

    def open_browser(self):
        self.opened = True

    def navigate(self, url):
        self.navigated.append(url)
        self.current_url = url

    def get_page_text(self):
        if self.current_url and self.current_url in self.content_by_url:
            return self.content_by_url[self.current_url]
        return self.content

    def get_current_url(self):
        return self.current_url or "https://example.com/current"

    def get_page_title(self):
        if self.current_url and self.current_url in self.title_by_url:
            return self.title_by_url[self.current_url]
        return "Example Title"

    def get_page_source(self):
        if self.current_url and self.current_url in self.html_by_url:
            return self.html_by_url[self.current_url]
        return '<a href="https://example.com/a">Example A</a>'


class _FakeServices:
    def __init__(self, http=None, browser=None):
        self.http = http or _FakeHTTPService()
        self.browser = browser or _FakeBrowserService()


def _build_tool(http=None, browser=None):
    tool = WebAccessTool()
    tool.services = _FakeServices(http=http, browser=browser)
    return tool


def test_fetch_url_uses_http_for_api_like_targets():
    tool = _build_tool(http=_FakeHTTPService(response={"status": 200, "body": "{\"ok\":true}"}))

    result = tool.execute_capability("fetch_url", url="https://api.github.com/repos/openai/openai-python")

    assert result.is_success()
    assert result.data["mode"] == "http"
    assert result.data["content"] == "{\"ok\":true}"


def test_fetch_url_falls_back_to_browser_after_http_403():
    tool = _build_tool(
        http=_FakeHTTPService(response={"status": 403, "body": "forbidden"}),
        browser=_FakeBrowserService(content="browser-content"),
    )

    result = tool.execute_capability("fetch_url", url="https://example.com/protected")

    assert result.is_success()
    assert result.data["mode"] == "browser"
    assert result.data["fallback_from"] == "http"
    assert result.data["content"] == "browser-content"


def test_search_web_prefers_browser():
    browser = _FakeBrowserService(content="search-results")
    tool = _build_tool(browser=browser)

    result = tool.execute_capability("search_web", query="new AAA action games")

    assert result.is_success()
    assert result.data["mode"] == "browser"
    assert "new+AAA+action+games" in browser.navigated[0]


def test_search_web_defaults_to_duckduckgo():
    browser = _FakeBrowserService(content="search-results")
    tool = _build_tool(browser=browser)

    result = tool.execute_capability("search_web", query="new multiplayer aaa games")

    assert result.is_success()
    assert result.data["engine"] == "duckduckgo"
    assert browser.navigated[0].startswith("https://duckduckgo.com/")


def test_search_web_falls_back_to_game_sources_when_search_blocked():
    blocked_ddg = "https://duckduckgo.com/?q=new+top+multiplayer+AAA+games"
    blocked_google = "https://www.google.com/search?q=new+top+multiplayer+AAA+games"
    steam_url = "https://store.steampowered.com/search/?term=new+top+multiplayer+AAA+games"
    ign_url = "https://www.ign.com/search?q=new+top+multiplayer+AAA+games"
    gamespot_url = "https://www.gamespot.com/search/?q=new+top+multiplayer+AAA+games"
    browser = _FakeBrowserService(
        content_by_url={
            blocked_ddg: "captcha verify you are human",
            blocked_google: "unusual traffic detected",
            steam_url: "Steam results for multiplayer AAA action games",
            ign_url: "IGN results",
            gamespot_url: "GameSpot results",
        }
    )
    tool = _build_tool(browser=browser)

    result = tool.execute_capability("search_web", query="new top multiplayer AAA games")

    assert result.is_success()
    assert result.data["fallback_strategy"] == "game_sources"
    assert result.data["blocked_search"] is True
    assert result.data["sources"][0]["source"] == "store.steampowered.com"
    assert "Steam results" in result.data["content"]


def test_search_web_collects_source_pages_from_duckduckgo_html_results():
    query = "new top multiplayer AAA games"
    ddg_html_url = "https://html.duckduckgo.com/html/?q=new+top+multiplayer+AAA+games"
    source_a = "https://example.com/a"
    source_b = "https://example.com/b"
    http = _FakeHTTPService(
        response_by_url={
            ddg_html_url: {
                "status": 200,
                "body": f'<a href="{source_a}">A</a><a href="{source_b}">B</a>',
            },
            source_a: {"status": 200, "body": "Source A content"},
            source_b: {"status": 200, "body": "Source B content"},
        }
    )
    tool = _build_tool(http=http, browser=_FakeBrowserService(content="unused"))

    result = tool.execute_capability("search_web", query=query)

    assert result.is_success()
    assert result.data["mode"] == "source_collection"
    assert result.data["source_count"] == 2
    assert "Source: https://example.com/a" in result.data["content"]
    assert "Source A content" in result.data["content"]


def test_get_current_page_details_returns_structured_browser_state():
    current_url = "https://example.com/search"
    browser = _FakeBrowserService(
        content_by_url={current_url: "Visible page text"},
        html_by_url={current_url: '<a href="https://example.com/a">Alpha</a><a href="/b">Beta</a>'},
        title_by_url={current_url: "Search Results"},
    )
    browser.navigate(current_url)
    tool = _build_tool(browser=browser)

    result = tool.execute_capability("get_current_page_details")

    assert result.is_success()
    assert result.data["url"] == current_url
    assert result.data["title"] == "Search Results"
    assert result.data["content"] == "Visible page text"
    assert result.data["links"][0]["url"] == "https://example.com/a"


def test_extract_search_results_filters_search_engine_links():
    current_url = "https://duckduckgo.com/?q=test"
    browser = _FakeBrowserService(
        html_by_url={
            current_url: (
                '<a href="https://duckduckgo.com/about">About</a>'
                '<a href="https://example.com/game-a">Game A Review</a>'
                '<a href="https://example.com/game-b">Game B Review</a>'
            )
        }
    )
    browser.navigate(current_url)
    tool = _build_tool(browser=browser)

    result = tool.execute_capability("extract_search_results", limit=2)

    assert result.is_success()
    assert result.data["count"] == 2
    assert result.data["results"][0]["title"] == "Game A Review"
    assert result.data["results"][0]["url"] == "https://example.com/game-a"
