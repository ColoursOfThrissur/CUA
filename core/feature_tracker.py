"""
Feature Tracker - Track features added to tools for intelligent improvement selection
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class FeatureCategory(Enum):
    SAFETY = "safety"  # Validation, sanitization, error handling
    CORE = "core"  # Basic functionality, CRUD operations
    ROBUSTNESS = "robustness"  # Retry, timeout, logging
    PERFORMANCE = "performance"  # Caching, batching, async
    POLISH = "polish"  # Docs, examples, type hints

@dataclass
class FeatureRecord:
    file: str
    feature_added: str
    category: str
    iteration: int
    result: str  # success, failure
    methods_modified: List[str]
    cooldown_until: int

class FeatureTracker:
    def __init__(self):
        self.history: Dict[str, List[FeatureRecord]] = {}
        self.current_iteration = 0
    
    def set_iteration(self, iteration: int):
        """Update current iteration counter"""
        self.current_iteration = iteration
    
    def add_feature(self, file: str, feature: str, category: str, iteration: int, 
                   result: str, methods: List[str] = None):
        """Record a feature addition"""
        if file not in self.history:
            self.history[file] = []
        
        self.current_iteration = max(self.current_iteration, iteration)
        
        # Calculate cooldown
        if result == "success":
            cooldown = iteration + 3  # 3 iterations after success
        elif result == "failure":
            cooldown = iteration + 5  # 5 iterations after failure
        else:
            cooldown = iteration + 1  # 1 iteration for duplicates
        
        record = FeatureRecord(
            file=file,
            feature_added=feature,
            category=category,
            iteration=iteration,
            result=result,
            methods_modified=methods or [],
            cooldown_until=cooldown
        )
        
        self.history[file].append(record)
    
    def is_in_cooldown(self, file: str, current_iteration: int, feature_category: str = None) -> Tuple[bool, Optional[int]]:
        """Check if file/feature is in cooldown period"""
        if file not in self.history:
            return False, None
        
        records = self.history[file]
        if not records:
            return False, None
        
        # If feature_category specified, check category-specific cooldown
        if feature_category:
            category_records = [r for r in records if r.category == feature_category]
            if category_records:
                latest = max(category_records, key=lambda r: r.iteration)
                if current_iteration < latest.cooldown_until:
                    return True, latest.cooldown_until
        
        # Check file-level cooldown (any recent failure)
        latest = max(records, key=lambda r: r.iteration)
        if latest.result == "failure" and current_iteration < latest.cooldown_until:
            return True, latest.cooldown_until
        
        return False, None
    
    def get_added_features(self, file: str) -> List[str]:
        """Get list of features already added to file"""
        if file not in self.history:
            return []
        
        # Only return successful features
        return [r.feature_added for r in self.history[file] if r.result == "success"]
    
    def get_covered_categories(self, file: str) -> List[str]:
        """Get categories that have been successfully implemented"""
        if file not in self.history:
            return []
        
        categories = set()
        for record in self.history[file]:
            if record.result == "success":
                categories.add(record.category)
        
        return list(categories)
    
    def get_file_maturity(self, file: str, method_count: int) -> Tuple[str, int]:
        """
        Calculate file maturity level and priority score
        Returns: (maturity_level, priority_score)
        Higher score = higher priority for improvement
        """
        successful_features = len([r for r in self.history.get(file, []) if r.result == "success"])
        
        # Maturity based on method count and feature count
        if method_count < 5 and successful_features < 3:
            return "immature", 100  # Highest priority
        elif method_count < 10 and successful_features < 6:
            return "growing", 50
        elif method_count < 15 and successful_features < 10:
            return "mature", 20
        else:
            return "complete", 5  # Lowest priority
    
    def clear_history(self):
        """Clear all history (for new loop sessions)"""
        self.history = {}
        self.current_iteration = 0
    
    def get_summary(self, file: str) -> Dict:
        """Get summary of file's improvement history"""
        if file not in self.history:
            return {
                "total_attempts": 0,
                "successful_features": 0,
                "failed_attempts": 0,
                "categories_covered": []
            }
        
        records = self.history[file]
        return {
            "total_attempts": len(records),
            "successful_features": len([r for r in records if r.result == "success"]),
            "failed_attempts": len([r for r in records if r.result == "failure"]),
            "categories_covered": self.get_covered_categories(file)
        }
