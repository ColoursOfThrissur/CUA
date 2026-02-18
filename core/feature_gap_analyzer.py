"""
Feature Gap Analyzer - Detect missing features in tool files
"""
import re
from typing import List, Dict, Tuple
from pathlib import Path

class FeatureGapAnalyzer:
    """Analyze tool files to identify missing features by category"""
    
    # Feature patterns to detect in code
    FEATURE_PATTERNS = {
        "safety": [
            (r'if not \w+:', "input validation"),
            (r'raise \w+Error', "error raising"),
            (r'try:', "exception handling"),
            (r'isinstance\(', "type checking"),
        ],
        "core": [
            (r'def \w+\(', "methods"),
        ],
        "robustness": [
            (r'timeout=', "timeout parameter"),
            (r'retry|retries', "retry logic"),
            (r'logger\.|logging\.', "logging"),
            (r'except \w+Error:', "specific error handling"),
        ],
        "performance": [
            (r'cache|Cache', "caching"),
            (r'async def|await', "async operations"),
            (r'batch|Batch', "batching"),
        ],
        "polish": [
            (r'""".*"""', "docstrings"),
            (r'# Example:', "examples"),
            (r': \w+\s*=', "type hints"),
        ]
    }
    
    def analyze_gaps(self, file_path: str, file_content: str, covered_categories: List[str]) -> List[Tuple[str, int]]:
        """
        Analyze file and return missing feature categories with priority
        Returns: [(category, priority), ...] sorted by priority (higher = more important)
        """
        gaps = []
        
        # Priority order
        priority_map = {
            "safety": 100,
            "core": 80,
            "robustness": 60,
            "performance": 40,
            "polish": 20
        }
        
        for category, patterns in self.FEATURE_PATTERNS.items():
            # Skip if category already covered
            if category in covered_categories:
                continue
            
            # Check if category features are missing
            missing_count = 0
            for pattern, feature_name in patterns:
                if not re.search(pattern, file_content, re.MULTILINE):
                    missing_count += 1
            
            # If more than half of features in category are missing, it's a gap
            if missing_count > len(patterns) / 2:
                gaps.append((category, priority_map[category]))
        
        # Sort by priority (highest first)
        gaps.sort(key=lambda x: x[1], reverse=True)
        
        return gaps
    
    def get_category_suggestions(self, category: str, file_content: str) -> List[str]:
        """Get specific feature suggestions for a category"""
        suggestions = {
            "safety": [
                "Add input validation for all parameters",
                "Add type checking for parameters",
                "Add comprehensive error handling with specific exceptions",
                "Add parameter sanitization to prevent injection attacks"
            ],
            "core": [
                "Add missing CRUD operations",
                "Add batch operations support",
                "Add filtering and search capabilities",
                "Add data transformation methods"
            ],
            "robustness": [
                "Add timeout parameter to all operations",
                "Add retry logic with exponential backoff",
                "Add comprehensive logging for debugging",
                "Add circuit breaker for failure handling"
            ],
            "performance": [
                "Add caching mechanism with TTL",
                "Add async/await support for I/O operations",
                "Add batch processing to reduce overhead",
                "Add connection pooling"
            ],
            "polish": [
                "Add comprehensive docstrings to all methods",
                "Add usage examples in docstrings",
                "Add type hints to all parameters and returns",
                "Add inline comments for complex logic"
            ]
        }
        
        category_suggestions = suggestions.get(category, [])
        
        # Filter out suggestions that are already implemented - STRICT checking
        filtered = []
        for suggestion in category_suggestions:
            # Check if feature is FULLY implemented, not just mentioned
            key_checks = {
                "timeout": lambda c: bool(re.search(r'timeout\s*[=:]', c)) and bool(re.search(r'timeout\s*=\s*\w+', c)),
                "retry": lambda c: bool(re.search(r'for.*in range.*retry|while.*retry|@retry', c, re.DOTALL)),
                "caching": lambda c: bool(re.search(r'cache\[|cache\.get|@cache|lru_cache', c)),
                "async": lambda c: bool(re.search(r'async def \w+', c)),
                "type hints": lambda c: len(re.findall(r'def \w+\([^)]*:\s*\w+', c)) > 2,
                "docstrings": lambda c: len(re.findall(r'"""[^"]+"""', c, re.DOTALL)) > 2,
                "logging": lambda c: bool(re.search(r'logger\.(debug|info|warning|error)', c)),
                "validation": lambda c: bool(re.search(r'if not \w+.*raise|raise.*if not', c, re.DOTALL))
            }
            
            # Check if suggestion's key feature is FULLY implemented
            is_missing = True
            for term, check_func in key_checks.items():
                if term.lower() in suggestion.lower():
                    if check_func(file_content):
                        is_missing = False
                        break
            
            if is_missing:
                filtered.append(suggestion)
        
        return filtered[:3]  # Return top 3 suggestions
    
    def get_priority_gap(self, file_path: str, file_content: str, covered_categories: List[str]) -> Tuple[str, List[str]]:
        """
        Get the highest priority gap and its suggestions
        Returns: (category, [suggestions])
        """
        gaps = self.analyze_gaps(file_path, file_content, covered_categories)
        
        if not gaps:
            return None, []
        
        # Get highest priority gap
        top_category, _ = gaps[0]
        suggestions = self.get_category_suggestions(top_category, file_content)
        
        return top_category, suggestions
