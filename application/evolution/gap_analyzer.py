"""
Gap Analyzer - Proactively reason about the full autonomous agent platform and identify missing tools.
"""
import asyncio
from typing import Dict, List
from infrastructure.persistence.sqlite.logging import SQLiteLogger
from shared.utils.trace_bridge import broadcast_trace_sync

class GapAnalyzer:
    def __init__(self, logger: SQLiteLogger, llm_client, registry):
        self.logger = logger
        self.llm_client = llm_client
        self.registry = registry

    async def analyze_gaps(self):
        """Proactively reason about the full platform and identify missing tools.
        Reads skills, existing tools, and architecture to find capability gaps
        without waiting for user failures to trigger them.
        """
        try:
            from pathlib import Path
            from domain.services.gap_tracker import GapTracker
            from domain.services.gap_detector import CapabilityGap

            # Build system snapshot: skills and what they need
            skills_snapshot = []
            skills_dir = Path("skills")
            for skill_dir in sorted(skills_dir.iterdir()):
                skill_json = skill_dir / "skill.json"
                if not skill_json.exists():
                    continue
                try:
                    import json as _json
                    skill_def = _json.loads(skill_json.read_text())
                    skills_snapshot.append({
                        "name": skill_def.get("name", skill_dir.name),
                        "description": skill_def.get("description", ""),
                        "preferred_tools": skill_def.get("preferred_tools", []),
                        "capabilities_needed": skill_def.get("capabilities", []),
                    })
                except Exception:
                    pass

            # Build existing tool inventory
            existing_tools = []
            for tools_path in [Path("tools"), Path("tools/experimental")]:
                if not tools_path.exists():
                    continue
                for tf in tools_path.glob("*.py"):
                    if tf.name.startswith("__"):
                        continue
                    existing_tools.append(tf.stem)

            # Build covered capabilities from registry
            covered_caps = set()
            if self.registry:
                try:
                    for tool in getattr(self.registry, "tools", []):
                        for cap_name in (tool.get_capabilities() or {}):
                            covered_caps.add(cap_name.lower())
                        covered_caps.add(tool.__class__.__name__.lower().replace("tool", ""))
                except Exception:
                    pass

            import json as _json
            system_context = (
                "You are analyzing a local autonomous agent platform to find missing tool capabilities.\n"
                "This platform plans tasks, routes via skills, calls tools, creates/evolves tools.\n"
                "Desktop automation is one subsystem, not the whole product.\n\n"
                f"SKILLS: {', '.join(s['name'] for s in skills_snapshot)}\n"
                f"EXISTING TOOLS: {', '.join(existing_tools)}\n"
                f"COVERED CAPABILITIES (sample): {', '.join(sorted(covered_caps)[:30])}\n\n"
                "What tool capabilities are clearly missing for a general-purpose autonomous agent?\n"
                "Consider: what each skill needs, what gaps exist between skills and tools.\n\n"
                "Return JSON array of up to 3 gaps (most impactful first):\n"
                '[{"capability": "short_name", "confidence": 0.0-1.0, "reason": "max 8 words", '
                '"suggested_tool_name": "ToolNameTool"}]\n'
                "Only include gaps where confidence >= 0.75. Keep reason under 8 words. If nothing is missing return []"
            )

            raw = await asyncio.to_thread(
                self.llm_client._call_llm,
                system_context,
                0.1,
                800,  # was 300 — too small for JSON array with reason strings, caused truncation
                True,
            )
            import json as _json
            data = _json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(data, list):
                return

            tracker = GapTracker()
            found = 0
            for item in data:
                cap = (item.get("capability") or "").strip()
                conf = float(item.get("confidence", 0.0))
                reason = (item.get("reason") or "").strip()
                suggested_name = (item.get("suggested_tool_name") or "").strip()
                if not cap or conf < 0.75:
                    continue
                # Skip if already covered — exact match only
                cap_key = cap.lower().replace(":", "_")
                if cap_key in covered_caps:
                    continue
                # Skip if already tracked and actionable
                existing = tracker.gaps.get(cap)
                if existing and existing.resolution_attempted:
                    continue
                gap = CapabilityGap(
                    capability=cap,
                    confidence=min(conf, 0.95),
                    reason=reason,
                    domain="system_analysis",
                    gap_type="llm_identified",
                    suggested_action="create_tool",
                )
                if suggested_name:
                    gap.target_tool = suggested_name
                tracker.record_gap(gap)
                found += 1
                self.logger.info(f"System gap identified: {cap} (conf={conf:.2f}) — {reason}")
                broadcast_trace_sync("auto", f"System gap found: {cap}", "in_progress",
                                     {"stage": "system_analysis", "capability": cap, "confidence": conf})

            if found:
                self.logger.info(f"System analysis found {found} new capability gaps")
        except Exception as e:
            self.logger.warning(f"System gap analysis skipped: {e}")
