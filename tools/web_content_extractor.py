"""
WebContentExtractor - Structured web scraping capability
Extracts title, description, links, and clean text from HTML pages
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebContentExtractor(BaseTool):
    """Extract structured content from web pages"""
    ALLOWED_DOMAINS = ['localhost', '127.0.0.1', 'wikipedia.org', 'en.wikipedia.org', 'github.com', 'stackoverflow.com', 'medium.com', 'dev.to']

    def __init__(self, orchestrator=None):
        self.description = 'Extract structured content from web pages'
        self.capabilities = ['extract']
        super().__init__()
        if orchestrator:
            self.services = orchestrator.get_services(self.__class__.__name__)

    def register_capabilities(self):
        """Register web content extraction capability"""
        from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
        extract_cap = ToolCapability(name='extract', description='Extract title, description, links, and text from webpage', parameters=[Parameter('url', ParameterType.STRING, 'URL to extract content from')], returns='Structured content: title, description, links, text', safety_level=SafetyLevel.MEDIUM, examples=[{'url': 'https://en.wikipedia.org/wiki/Python'}])
        self.add_capability(extract_cap, self._extract)

    def execute(self, operation: str, parameters: dict) -> ToolResult:
        if operation == 'extract':
            return self._extract(parameters)
        return ToolResult(tool_name=self.name, capability_name=operation, status=ResultStatus.FAILURE, error_message='Unknown operation')

    def _extract(self, params: dict) -> ToolResult:
        url = params.get('url')
        if not url:
            return ToolResult(tool_name=self.name, capability_name='extract', status=ResultStatus.FAILURE, error_message='URL required')
        if not self._is_allowed_url(url):
            return ToolResult(tool_name=self.name, capability_name='extract', status=ResultStatus.FAILURE, error_message=f"URL not allowed. Allowed domains: {', '.join(self.ALLOWED_DOMAINS)}")
        try:
            logger.info(f'Extracting content from: {url}')
            headers = self._build_request_header()
            response = requests.get(url, timeout=10, headers=headers)
            if response.status_code != 200:
                return ToolResult(tool_name=self.name, capability_name='extract', status=ResultStatus.FAILURE, error_message=f'HTTP {response.status_code}')
            soup = BeautifulSoup(response.content, 'html.parser')
            title = soup.find('title')
            title_text = title.get_text().strip() if title else ''
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            description = meta_desc.get('content', '').strip() if meta_desc else ''
            links = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                absolute_url = urljoin(url, href)
                links.append(absolute_url)
            for script in soup(['script', 'style', 'nav', 'footer', 'header']):
                script.decompose()
            text_content = soup.get_text(separator=' ', strip=True)
            text_content = ' '.join(text_content.split())[:5000]
            parsed = urlparse(url)
            domain = parsed.netloc
            result_data = {'name': 'WebContentExtractor', 'domain': domain, 'title': title_text, 'description': description, 'links': links[:50], 'text_content': text_content, 'link_count': len(links)}
            logger.info(f'Successfully extracted content from {url}')
            return ToolResult(tool_name=self.name, capability_name='extract', status=ResultStatus.SUCCESS, data=result_data)
        except requests.exceptions.RequestException as e:
            logger.error(f'Request failed for {url}: {str(e)}')
            return ToolResult(tool_name=self.name, capability_name='extract', status=ResultStatus.FAILURE, error_message=str(e))
        except Exception as e:
            logger.error(f'Extraction failed for {url}: {str(e)}')
            return ToolResult(tool_name=self.name, capability_name='extract', status=ResultStatus.FAILURE, error_message=str(e))

    def _is_allowed_url(self, url: str) -> bool:
        """Validate URL against whitelist"""
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                return False
            if parsed.scheme == 'https':
                return True
            return any((parsed.netloc == domain or parsed.netloc.endswith('.' + domain) for domain in self.ALLOWED_DOMAINS))
        except Exception:
            return False

    def _build_request_header(self):
        return {'User-Agent': 'CUA-Agent/1.0'}