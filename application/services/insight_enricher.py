"""
Insight Enrichment Layer - Convert metrics to concrete structural facts
"""
import ast
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict

class InsightEnricher:
    def enrich_duplication_insight(self, file_path: str, duplication_score: float) -> Dict:
        """Convert duplication percentage to concrete duplicate blocks"""
        try:
            with open(file_path) as f:
                content = f.read()
                tree = ast.parse(content)
            
            # Find duplicate blocks
            duplicate_regions = self._find_duplicate_regions(content, tree)
            
            # Extract all method names for reference (including private)
            all_methods = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.name not in ['__init__', 'register_capabilities', 'execute']:
                        all_methods.append(node.name)
            
            if not duplicate_regions:
                # No specific duplicates found, return general info
                return {
                    "file": file_path,
                    "duplication_score": duplication_score,
                    "duplicate_blocks": [],
                    "methods_with_duplication": all_methods[:3],  # First 3 public methods
                    "all_methods": all_methods
                }
            
            # Build enriched insight
            enriched = {
                "file": file_path,
                "duplication_score": duplication_score,
                "duplicate_blocks": duplicate_regions[:2],  # Top 2
                "methods_with_duplication": list(set([m for r in duplicate_regions[:3] for m in r["methods"]])),
                "all_methods": all_methods
            }
            
            return enriched
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to enrich duplication insight for {file_path}: {e}", exc_info=True)
            return None
    
    def _find_duplicate_regions(self, content: str, tree: ast.AST) -> List[Dict]:
        """Find concrete duplicate code blocks with pattern analysis"""
        lines = content.split('\n')
        methods = {}
        
        # Extract method bodies
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                start = node.lineno - 1
                end = node.end_lineno
                method_lines = lines[start:end]
                methods[node.name] = {
                    "lines": method_lines,
                    "start": start,
                    "end": end,
                    "body": '\n'.join(method_lines)
                }
        
        # Find duplicate blocks (multi-line sequences)
        duplicates = []
        block_size = 5  # Look for 5+ line duplicates
        
        for method1, data1 in methods.items():
            for method2, data2 in methods.items():
                if method1 >= method2:
                    continue
                
                # Find common subsequences
                common_blocks = self._find_common_blocks(data1["lines"], data2["lines"], block_size)
                
                for block in common_blocks:
                    # Identify pattern type
                    pattern_type = self._identify_pattern_type(block)
                    
                    duplicates.append({
                        "pattern": block[:80],
                        "pattern_type": pattern_type,
                        "methods": [method1, method2],
                        "line_numbers": [data1["start"], data2["start"]],
                        "block_size": len(block.split('\n'))
                    })
        
        return duplicates[:5]  # Top 5
    
    def _find_common_blocks(self, lines1: List[str], lines2: List[str], min_size: int) -> List[str]:
        """Find common code blocks between two method bodies"""
        blocks = []
        
        for i in range(len(lines1) - min_size):
            block1 = '\n'.join(lines1[i:i+min_size])
            normalized1 = self._normalize_code(block1)
            
            for j in range(len(lines2) - min_size):
                block2 = '\n'.join(lines2[j:j+min_size])
                normalized2 = self._normalize_code(block2)
                
                if normalized1 == normalized2 and len(normalized1.strip()) > 50:
                    blocks.append(block1)
                    break
        
        return blocks[:3]
    
    def _normalize_code(self, code: str) -> str:
        """Normalize code for comparison"""
        # Remove variable names, keep structure
        import re
        normalized = re.sub(r'\b[a-z_][a-z0-9_]*\b', 'VAR', code)
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized.strip()
    
    def _identify_pattern_type(self, block: str) -> str:
        """Identify what kind of duplication this is"""
        block_lower = block.lower()
        
        if 'header' in block_lower or 'headers' in block_lower:
            return "header building"
        elif 'json' in block_lower or 'payload' in block_lower:
            return "payload encoding"
        elif 'try' in block_lower and 'except' in block_lower:
            return "exception handling"
        elif 'request' in block_lower:
            return "request preparation"
        elif 'response' in block_lower:
            return "response normalization"
        else:
            return "repeated logic"
    
    def enrich_long_method_insight(self, file_path: str, long_methods: List[Tuple[str, int]]) -> Dict:
        """Provide concrete details about long methods"""
        return {
            "file": file_path,
            "long_methods": [
                {"name": name, "lines": lines}
                for name, lines in long_methods[:3]
            ]
        }
