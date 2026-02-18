"""Feature deduplication - detect existing implementations"""
import ast
import re
from pathlib import Path
from typing import Set, List, Dict, Tuple

class FeatureDeduplicator:
    def __init__(self):
        self.cache = {}
    
    def is_duplicate(self, file_path: str, feature_desc: str, methods: List[str] = None) -> Tuple[bool, str]:
        """Check if feature already exists by analyzing FULL implementation"""
        
        try:
            code = Path(file_path).read_text()
        except:
            return False, ""
        
        feature_lower = feature_desc.lower()
        
        # STRICT checks for common features - must be FULLY implemented
        strict_checks = {
            "timeout": lambda: bool(re.search(r'timeout\s*[=:]', code)) and bool(re.search(r'timeout\s*=\s*\w+', code)),
            "retry": lambda: bool(re.search(r'for.*in range.*retry|while.*retry|@retry', code, re.DOTALL)),
            "logging": lambda: bool(re.search(r'logger\.(debug|info|warning|error)', code)) and code.count('logger.') >= 3,
            "caching": lambda: bool(re.search(r'cache\[|cache\.get|@cache|lru_cache', code)),
            "validation": lambda: bool(re.search(r'if not \w+.*raise|raise.*if not', code, re.DOTALL)) and code.count('raise') >= 2,
            "error handling": lambda: bool(re.search(r'try:.*except', code, re.DOTALL)) and code.count('except') >= 2,
            "type hints": lambda: len(re.findall(r'def \w+\([^)]*:\s*\w+', code)) >= 3,
            "docstrings": lambda: len(re.findall(r'"""[^"]+"""', code, re.DOTALL)) >= 3
        }
        
        # Check each strict pattern
        for keyword, check_func in strict_checks.items():
            if keyword in feature_lower:
                if check_func():
                    return True, f"Feature '{keyword}' is already fully implemented"
        
        return False, ""
    
    def _get_existing_features(self, file_path: str) -> Dict:
        """Parse file and extract methods + capabilities"""
        if file_path in self.cache:
            return self.cache[file_path]
        
        try:
            code = Path(file_path).read_text()
            tree = ast.parse(code)
            
            methods = set()
            capabilities = set()
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    methods.add(node.name)
                    # Extract capability keywords from docstring
                    if node.body and isinstance(node.body[0], ast.Expr):
                        if isinstance(node.body[0].value, ast.Constant):
                            doc = node.body[0].value.value
                            if doc:
                                capabilities.update(self._extract_keywords(doc))
            
            result = {'methods': methods, 'capabilities': capabilities}
            self.cache[file_path] = result
            return result
        except:
            return {'methods': set(), 'capabilities': set()}
    
    def _extract_keywords(self, text: str) -> Set[str]:
        """Extract capability keywords from text"""
        keywords = set()
        text_lower = text.lower()
        
        # Feature keywords to detect
        feature_patterns = [
            'timeout', 'retry', 'retries', 'cache', 'caching',
            'logging', 'log', 'validation', 'validate',
            'error handling', 'exception', 'auth', 'authentication',
            'header', 'headers', 'cookie', 'session',
            'async', 'await', 'batch', 'batching',
            'pool', 'pooling', 'circuit breaker',
            'rate limit', 'throttle', 'backoff'
        ]
        
        for pattern in feature_patterns:
            if pattern in text_lower:
                # Use first word as keyword
                keywords.add(pattern.split()[0])
        
        return keywords
    
    def clear_cache(self):
        """Clear cache after file modifications"""
        self.cache.clear()
