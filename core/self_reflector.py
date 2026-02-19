"""
Self-reflection layer for strategic improvements
"""
from dataclasses import dataclass
from typing import List, Dict, Set, Optional
from pathlib import Path
import ast

@dataclass
class ReflectionInsight:
    category: str  # redundancy, duplication, gap, bottleneck, abstraction
    severity: float  # 0.0-1.0
    description: str
    affected_files: List[str]
    suggested_action: str
    enriched_data: Optional[Dict] = None  # Concrete structural facts

class SelfReflector:
    def __init__(self, tools_dir: str = "tools"):
        self.tools_dir = Path(tools_dir)
        from core.insight_enricher import InsightEnricher
        from core.capability_mapper import CapabilityMapper
        from core.gap_detector import GapDetector
        from core.gap_tracker import GapTracker
        
        self.enricher = InsightEnricher()
        self.capability_mapper = CapabilityMapper(tools_dir)
        self.gap_detector = GapDetector(self.capability_mapper)
        self.gap_tracker = GapTracker()
    
    def analyze_system(self) -> List[ReflectionInsight]:
        """Analyze system for strategic improvements"""
        insights = []
        
        insights.extend(self._detect_redundancy())
        insights.extend(self._detect_code_duplication())
        insights.extend(self._detect_capability_gaps())
        insights.extend(self._detect_missing_abstraction())
        
        return sorted(insights, key=lambda x: x.severity, reverse=True)
    
    def _detect_redundancy(self) -> List[ReflectionInsight]:
        """Find redundant tools with overlapping capabilities"""
        insights = []
        tool_capabilities = self._extract_tool_capabilities()
        
        for tool1, caps1 in tool_capabilities.items():
            for tool2, caps2 in tool_capabilities.items():
                if tool1 >= tool2:
                    continue
                overlap = caps1 & caps2
                if len(overlap) > 2:
                    insights.append(ReflectionInsight(
                        category="redundancy",
                        severity=len(overlap) / max(len(caps1), len(caps2)),
                        description=f"Tools {tool1} and {tool2} have {len(overlap)} overlapping capabilities",
                        affected_files=[tool1, tool2],
                        suggested_action="Consider merging or refactoring"
                    ))
        
        return insights
    
    def _detect_code_duplication(self) -> List[ReflectionInsight]:
        """Find duplicated code patterns"""
        insights = []
        code_blocks = {}
        
        for tool_file in self.tools_dir.glob("*.py"):
            try:
                with open(tool_file) as f:
                    tree = ast.parse(f.read())
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        code = ast.unparse(node)
                        if code not in code_blocks:
                            code_blocks[code] = []
                        code_blocks[code].append(str(tool_file))
            except:
                continue
        
        for code, files in code_blocks.items():
            if len(files) > 1 and len(code) > 200:
                # Enrich with method list from first file
                enriched = None
                if files:
                    try:
                        with open(files[0]) as f:
                            tree = ast.parse(f.read())
                        all_methods = [node.name for node in ast.walk(tree) 
                                     if isinstance(node, ast.FunctionDef) 
                                     and node.name not in ['__init__', 'register_capabilities', 'execute']]
                        enriched = {"all_methods": all_methods}
                    except:
                        pass
                
                insights.append(ReflectionInsight(
                    category="duplication",
                    severity=0.6,
                    description=f"Duplicated code block found in {len(files)} files",
                    affected_files=files,
                    suggested_action="Extract to shared utility",
                    enriched_data=enriched
                ))
        
        return insights
    
    def _detect_capability_gaps(self) -> List[ReflectionInsight]:
        """Identify missing capabilities based on usage patterns"""
        # Placeholder - would analyze logs for failed operations
        return []
    
    def _detect_missing_abstraction(self) -> List[ReflectionInsight]:
        """Find opportunities for abstraction with quantitative metrics"""
        insights = []
        
        for tool_file in self.tools_dir.glob("*.py"):
            try:
                with open(tool_file) as f:
                    content = f.read()
                    lines = content.split('\n')
                    tree = ast.parse(content)
                
                # Analyze method lengths
                long_methods = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        method_lines = node.end_lineno - node.lineno
                        if method_lines > 80:
                            long_methods.append((node.name, method_lines))
                
                # Detect duplication patterns
                duplication_score = self._calculate_duplication_score(content)
                
                if long_methods or duplication_score > 0.3:
                    # Enrich with concrete facts
                    enriched = None
                    if duplication_score > 0.3:
                        enriched = self.enricher.enrich_duplication_insight(str(tool_file), duplication_score)
                    elif long_methods:
                        enriched = self.enricher.enrich_long_method_insight(str(tool_file), long_methods)
                    
                    description = f"File has "
                    if long_methods:
                        description += f"{len(long_methods)} methods >80 lines "
                    if duplication_score > 0.3:
                        description += f"(duplication: {duplication_score:.1%})"
                    
                    insights.append(ReflectionInsight(
                        category="abstraction",
                        severity=0.6 if long_methods else 0.4,
                        description=description,
                        affected_files=[str(tool_file)],
                        suggested_action=f"Extract helper methods from: {', '.join([m[0] for m in long_methods[:3]])}",
                        enriched_data=enriched
                    ))
            except:
                continue
        
        return insights
    
    def _calculate_duplication_score(self, content: str) -> float:
        """Simple duplication detection"""
        lines = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('#')]
        if len(lines) < 10:
            return 0.0
        
        # Count repeated lines
        from collections import Counter
        line_counts = Counter(lines)
        duplicates = sum(count - 1 for count in line_counts.values() if count > 1)
        
        return duplicates / len(lines)
    
    def _extract_tool_capabilities(self) -> Dict[str, Set[str]]:
        """Extract capabilities from each tool"""
        capabilities = {}
        
        for tool_file in self.tools_dir.glob("*.py"):
            try:
                with open(tool_file) as f:
                    tree = ast.parse(f.read())
                
                caps = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                        caps.add(node.name)
                
                capabilities[tool_file.name] = caps
            except:
                continue
        
        return capabilities
