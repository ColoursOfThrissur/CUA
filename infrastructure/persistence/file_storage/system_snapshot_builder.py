"""
Infrastructure: System Snapshot Builder
Reads filesystem and registry to build system state snapshot.
"""
from pathlib import Path
import json
from typing import Set, List


class SystemSnapshotBuilder:
    """Builds system snapshot from filesystem and registry."""
    
    def __init__(self, registry=None):
        self.registry = registry
    
    def build_snapshot(self):
        """Build complete system snapshot."""
        from domain.services.gap_analysis_service import SystemSnapshot, SkillSnapshot
        
        skills = self._load_skills()
        existing_tools = self._scan_tools()
        covered_caps = self._extract_capabilities()
        
        return SystemSnapshot(
            skills=skills,
            existing_tools=existing_tools,
            covered_capabilities=covered_caps
        )
    
    def _load_skills(self) -> List:
        """Load all skill definitions from filesystem."""
        from domain.services.gap_analysis_service import SkillSnapshot
        
        skills = []
        skills_dir = Path("skills")
        if not skills_dir.exists():
            return skills
        
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_json = skill_dir / "skill.json"
            if not skill_json.exists():
                continue
            try:
                skill_def = json.loads(skill_json.read_text())
                skills.append(SkillSnapshot(
                    name=skill_def.get("name", skill_dir.name),
                    description=skill_def.get("description", ""),
                    preferred_tools=skill_def.get("preferred_tools", []),
                    capabilities_needed=skill_def.get("capabilities", [])
                ))
            except Exception:
                pass
        
        return skills
    
    def _scan_tools(self) -> List[str]:
        """Scan filesystem for existing tools."""
        existing_tools = []
        for tools_path in [Path("tools"), Path("tools/experimental")]:
            if not tools_path.exists():
                continue
            for tf in tools_path.glob("*.py"):
                if not tf.name.startswith("__"):
                    existing_tools.append(tf.stem)
        return existing_tools
    
    def _extract_capabilities(self) -> Set[str]:
        """Extract covered capabilities from registry."""
        covered_caps = set()
        if not self.registry:
            return covered_caps
        
        try:
            tools = getattr(self.registry, "tools", [])
            for tool in tools:
                try:
                    caps = tool.get_capabilities() or {}
                    for cap_name in caps:
                        covered_caps.add(cap_name.lower())
                    covered_caps.add(tool.__class__.__name__.lower().replace("tool", ""))
                except Exception:
                    pass
        except Exception:
            pass
        
        return covered_caps
