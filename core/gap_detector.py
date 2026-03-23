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
    gap_type: str = "missing_capability"
    suggested_action: str = "create_tool"
    selected_skill: Optional[str] = None
    selected_category: Optional[str] = None
    fallback_mode: Optional[str] = None
    target_tool: Optional[str] = None
    example_task: Optional[str] = None
    example_error: Optional[str] = None

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
    
    def analyze_failed_task(self, task: str, error: str, skill_selection: Optional[Dict] = None) -> Optional[CapabilityGap]:
        """Analyze failed task for capability gaps."""
        if skill_selection:
            classified = self._classify_with_skill_context(task, error, skill_selection)
            if classified:
                return classified

        # Try error-based detection first (higher confidence)
        gap = self.detect_gap_from_error(error, task)
        if gap:
            gap.gap_type = "missing_capability"
            gap.suggested_action = "create_tool"
            return gap
        
        # Fall back to task-based detection
        gap = self.detect_gap_from_task(task)
        if gap:
            gap.gap_type = "missing_capability"
            gap.suggested_action = "create_tool"
        return gap

    def _classify_with_skill_context(self, task: str, error: str, skill_selection: Dict) -> Optional[CapabilityGap]:
        matched = bool(skill_selection.get("matched"))
        skill_name = skill_selection.get("skill_name")
        category = skill_selection.get("category") or self._infer_domain(task)
        fallback_mode = skill_selection.get("fallback_mode")
        error_lower = (error or "").lower()

        if not matched:
            # FIXED: Don't create gaps for conversational requests
            if self._is_conversational_request(task):
                return None  # These should be handled by conversation skill, not tool creation
            
            domain = category or self._infer_domain(task)
            return CapabilityGap(
                capability=f"skill:{domain}",
                confidence=0.82,
                reason="No matching skill for an actionable request",
                domain=domain,
                gap_type="no_matching_skill",
                suggested_action="improve_skill_routing",
                selected_category=category,
                fallback_mode=fallback_mode,
                example_task=task,
                example_error=error or None,
            )

        if any(
            marker in error_lower
            for marker in [
                "don't have the capability",
                "do not have the capability",
                "not found",
                "unsupported operation",
                "unexpected keyword argument",
                "missing required parameter",
            ]
        ):
            base_gap = self.detect_gap_from_error(error, task) or self.detect_gap_from_task(task)
            capability = base_gap.capability if base_gap else f"{skill_name}:missing_tool"
            suggested_library = base_gap.suggested_library if base_gap else None
            domain = category or (base_gap.domain if base_gap else "unknown")
            return CapabilityGap(
                capability=capability,
                confidence=max(0.75, getattr(base_gap, "confidence", 0.0)),
                reason=f"Matched skill '{skill_name}' but required tool capability was unavailable",
                suggested_library=suggested_library,
                domain=domain,
                gap_type="matched_skill_missing_tool",
                suggested_action="create_tool",
                selected_skill=skill_name,
                selected_category=category,
                fallback_mode=fallback_mode,
                example_task=task,
                example_error=error or None,
            )

        if "no_tool_calls_for_actionable_request" in error_lower:
            return CapabilityGap(
                capability=f"{skill_name or category}:action-routing",
                confidence=0.9,
                reason="Actionable request produced no tool calls despite available execution paths",
                domain=category or "unknown",
                gap_type="actionable_request_no_tool_call",
                suggested_action="improve_skill_routing",
                selected_skill=skill_name,
                selected_category=category,
                fallback_mode=fallback_mode,
                example_task=task,
                example_error=error or None,
            )

        workflow_markers = [
            "playback",
            "navigate",
            "navigation",
            "click play",
            "browser workflow",
            "workflow missing",
            "planned fallback",
        ]
        if any(marker in error_lower for marker in workflow_markers):
            return CapabilityGap(
                capability=f"{skill_name or category}:workflow",
                confidence=0.84,
                reason=f"Matched skill '{skill_name or category}' but the workflow path was incomplete for the requested action",
                domain=category or "unknown",
                gap_type="matched_skill_missing_workflow",
                suggested_action="improve_skill_workflow",
                selected_skill=skill_name,
                selected_category=category,
                fallback_mode=fallback_mode,
                example_task=task,
                example_error=error or None,
            )

        if error:
            return CapabilityGap(
                capability=f"{skill_name}:workflow",
                confidence=0.72,
                reason=f"Matched skill '{skill_name}' but execution failed within the skill workflow",
                domain=category or "unknown",
                gap_type="matched_skill_execution_failed",
                suggested_action="improve_skill_routing",
                selected_skill=skill_name,
                selected_category=category,
                fallback_mode=fallback_mode,
                example_task=task,
                example_error=error or None,
            )

        return None

    def _is_conversational_request(self, task: str) -> bool:
        """Check if a request is conversational and should not trigger tool creation"""
        task_lower = task.lower().strip()
        
        # Direct conversational patterns
        conversation_patterns = [
            r'^(hi|hello|hey)\s*$',
            r'^(hi|hello|hey)\s+(how\s+are\s+you|there)\s*$',
            r'^(good\s+)?(morning|afternoon|evening)\s*$',
            r'^(thanks?|thank\s+you)\s*$',
            r'^(bye|goodbye)\s*$',
            r'^what[\s\']*s\s+up\s*$',
            r'^how\s+are\s+you\s*(doing)?\s*$'
        ]
        
        for pattern in conversation_patterns:
            if re.match(pattern, task_lower):
                return True
        
        # Simple conversational keywords
        if len(task.split()) <= 5 and any(word in task_lower for word in 
            ['hi', 'hello', 'hey', 'thanks', 'bye', 'morning', 'afternoon', 'evening']):
            return True
            
        return False

    def _infer_domain(self, task_description: str) -> str:
        task_lower = (task_description or "").lower()
        
        # Check for conversational first
        if self._is_conversational_request(task_description):
            return "conversation"
            
        keyword_domains = {
            "web": ["web", "website", "url", "research", "source", "browse", "crawl"],
            "computer": ["file", "directory", "folder", "command", "local", "computer", "shell"],
            "development": ["code", "repo", "repository", "test", "bug", "feature", "refactor"],
        }
        for domain, words in keyword_domains.items():
            if any(word in task_lower for word in words):
                return domain
        return "general"
