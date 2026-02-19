"""
Gap Detector - Identifies missing capabilities with confidence scoring
"""
from typing import Dict, List, Optional
from dataclasses import dataclass
import re

@dataclass
class CapabilityGap:
    capability: str
    confidence: float  # 0.0-1.0
    reason: str
    suggested_library: Optional[str] = None
    domain: str = "unknown"

class GapDetector:
    def __init__(self, capability_mapper):
        self.mapper = capability_mapper
        self.known_domains = {
            'web_scraping': ['beautifulsoup4', 'scrapy'],
            'html_parsing': ['beautifulsoup4', 'lxml'],
            'dom_query': ['beautifulsoup4', 'pyquery'],
            'pdf_processing': ['pypdf2', 'pdfplumber'],
            'image_processing': ['pillow', 'opencv-python'],
            'data_visualization': ['matplotlib', 'plotly'],
            'database': ['sqlalchemy', 'psycopg2'],
            'async_http': ['aiohttp', 'httpx'],
            'websocket': ['websockets', 'socketio'],
            'xml_parsing': ['lxml', 'xmltodict'],
            'yaml_parsing': ['pyyaml'],
            'csv_processing': ['pandas'],
            'excel_processing': ['openpyxl', 'xlrd']
        }
    
    def detect_gap_from_error(self, error_message: str, task_description: str = "") -> Optional[CapabilityGap]:
        """Detect capability gap from error message"""
        error_lower = error_message.lower()
        task_lower = task_description.lower()
        
        # Pattern matching for common gaps
        patterns = [
            (r'no module named [\'"](\w+)', 'missing_library', 0.9),
            (r'cannot parse (html|xml|pdf)', 'parsing_capability', 0.8),
            (r'(scrape|crawl|fetch) (web|html)', 'web_scraping', 0.7),
            (r'(image|picture|photo) (process|manipulate)', 'image_processing', 0.7),
            (r'(database|sql|query)', 'database', 0.6),
            (r'(websocket|ws|real-time)', 'websocket', 0.7),
        ]
        
        for pattern, domain, base_confidence in patterns:
            if re.search(pattern, error_lower) or re.search(pattern, task_lower):
                # Check if we already have this capability
                if self.mapper.has_capability(domain):
                    continue
                
                return CapabilityGap(
                    capability=domain,
                    confidence=base_confidence,
                    reason=f"Error pattern suggests {domain} capability needed",
                    suggested_library=self.known_domains.get(domain, [None])[0],
                    domain=domain
                )
        
        return None
    
    def detect_gap_from_task(self, task_description: str) -> Optional[CapabilityGap]:
        """Detect capability gap from task description"""
        task_lower = task_description.lower()
        
        # Keyword-based detection
        keywords = {
            'web_scraping': ['scrape', 'crawl', 'extract from website', 'parse html'],
            'pdf_processing': ['pdf', 'extract from pdf', 'read pdf'],
            'image_processing': ['image', 'picture', 'photo', 'resize', 'crop'],
            'database': ['database', 'sql', 'query', 'insert', 'select'],
            'excel_processing': ['excel', 'xlsx', 'spreadsheet'],
            'data_visualization': ['plot', 'chart', 'graph', 'visualize']
        }
        
        for domain, words in keywords.items():
            if any(word in task_lower for word in words):
                if not self.mapper.has_capability(domain):
                    confidence = 0.6 + (0.1 * sum(1 for w in words if w in task_lower))
                    confidence = min(confidence, 0.95)
                    
                    return CapabilityGap(
                        capability=domain,
                        confidence=confidence,
                        reason=f"Task requires {domain} capability",
                        suggested_library=self.known_domains.get(domain, [None])[0],
                        domain=domain
                    )
        
        return None
    
    def analyze_failed_task(self, task: str, error: str) -> Optional[CapabilityGap]:
        """Analyze failed task for capability gaps"""
        # Try error-based detection first (higher confidence)
        gap = self.detect_gap_from_error(error, task)
        if gap:
            return gap
        
        # Fall back to task-based detection
        return self.detect_gap_from_task(task)
