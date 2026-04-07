"""Intent Classifier - Extracts intent signals from user requests."""
from typing import Set, Dict


class IntentClassifier:
    """Classifies user intent to improve skill routing accuracy."""
    
    # Intent detection patterns
    _WEB_PHRASES = {
        "search the web", "on the web", "web page", "webpage", "website", 
        "url", "source", "sources"
    }
    
    _BROWSER_INTERACTION_WORDS = {
        "click", "fill", "type", "login", "log in", "sign in", "navigate", 
        "scroll", "button", "form", "input"
    }
    
    _DEVELOPMENT_WORDS = {
        "code", "repo", "repository", "file", "files", "bug", "test", 
        "script", "module", "function", "class"
    }
    
    _FINANCE_PHRASES = {
        "morning note", "morning notes", "morning brief", "market brief",
        "full report", "investment report", "portfolio report",
        "generate report", "how is nifty", "how is sensex",
        "how is the market", "market update"
    }
    
    def __init__(self):
        pass
    
    def detect_web_intent(self, message_lower: str) -> bool:
        """Detect if user wants web search/research."""
        return any(phrase in message_lower for phrase in self._WEB_PHRASES)
    
    def detect_browser_interaction_intent(self, message_lower: str) -> bool:
        """Detect if user wants browser automation (clicking, filling forms)."""
        return any(word in message_lower for word in self._BROWSER_INTERACTION_WORDS)
    
    def detect_development_intent(self, message_lower: str) -> bool:
        """Detect if user wants code/development operations."""
        return any(word in message_lower for word in self._DEVELOPMENT_WORDS)
    
    def detect_finance_intent(self, message_lower: str) -> bool:
        """Detect if user wants financial analysis/reports."""
        return any(phrase in message_lower for phrase in self._FINANCE_PHRASES)
    
    def get_all_intents(self, message_lower: str) -> Dict[str, bool]:
        """Get all detected intents as a dict."""
        return {
            "web": self.detect_web_intent(message_lower),
            "browser_interaction": self.detect_browser_interaction_intent(message_lower),
            "development": self.detect_development_intent(message_lower),
            "finance": self.detect_finance_intent(message_lower),
        }
