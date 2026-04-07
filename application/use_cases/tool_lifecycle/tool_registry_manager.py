"""
Tool Registry Manager - Auto-discover tool capabilities from code
"""

import json
import ast
import inspect
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

class ToolRegistryManager:
    """Manages centralized tool registry with LLM-powered discovery"""

    DISABLED_TOOLS = {
        "LocalRunNoteTool",
        "TaskBreakdownTool",
        "ExecutionPlanEvaluatorTool",
        "IntentClassifierTool",
        "SystemIntrospectionTool",
        "UserApprovalGateTool",
        "WorkflowAutomationTool",
    }
    
    def __init__(self, registry_path: str = "data/tool_registry.json", tools_dir: str = "tools"):
        self.registry_path = Path(registry_path)
        self.tools_dir = Path(tools_dir)
        self.registry_path.parent.mkdir(exist_ok=True)
    
    def sync_from_live(self, registry) -> Dict:
        """Sync registry from live tool instances — no LLM needed, always accurate."""
        results = {"synced": [], "failed": [], "timestamp": datetime.now().isoformat()}
        for tool in getattr(registry, 'tools', []):
            try:
                tool_name = tool.__class__.__name__
                if tool_name in self.DISABLED_TOOLS:
                    continue
                # Use instance name for MCP adapters
                inst_name = getattr(tool, 'name', None)
                if callable(inst_name):
                    inst_name = tool_name
                name = inst_name or tool_name

                caps = tool.get_capabilities() or {}
                operations = {}
                for op_name, cap in caps.items():
                    operations[op_name] = {
                        "parameters": [p.name for p in cap.parameters],
                        "required": [p.name for p in cap.parameters if p.required],
                        "description": cap.description,
                        "safety_level": cap.safety_level.value.upper(),
                    }

                # Find source file
                import inspect
                try:
                    source_file = inspect.getfile(tool.__class__)
                except Exception:
                    source_file = ""

                tool_data = {
                    "name": name,
                    "description": getattr(tool, 'description', ''),
                    "operations": operations,
                    "source_file": source_file,
                    "status": "active",
                }
                self.update_tool(tool_data)
                results["synced"].append(name)
            except Exception as e:
                results["failed"].append({"tool": tool.__class__.__name__, "error": str(e)})
        results["count"] = len(results["synced"])
        return results

    def sync_all_tools(self, llm_client) -> Dict:
        """Sync all tools using LLM to analyze code"""
        results = {"synced": [], "failed": [], "timestamp": datetime.now().isoformat()}
        
        # Find all tool files — core tools/, tools/experimental/, and tools/computer_use/
        tool_files = list(self.tools_dir.glob("*_tool.py"))
        exp_dir = self.tools_dir / "experimental"
        if exp_dir.exists():
            tool_files += list(exp_dir.glob("*.py"))
        computer_use_dir = self.tools_dir / "computer_use"
        if computer_use_dir.exists():
            tool_files += list(computer_use_dir.glob("*_tool.py"))
        
        registry = {"tools": {}, "last_sync": results["timestamp"]}
        
        for tool_file in tool_files:
            try:
                tool_name = tool_file.stem
                tool_data = self._analyze_tool_with_llm(tool_file, llm_client)
                
                if tool_data:
                    registry["tools"][tool_name] = tool_data
                    results["synced"].append(tool_name)
                else:
                    results["failed"].append({"tool": tool_name, "error": "Analysis failed"})
            except Exception as e:
                results["failed"].append({"tool": tool_name, "error": str(e)})
        
        # Save registry
        with open(self.registry_path, 'w') as f:
            json.dump(registry, f, indent=2)
        
        return results
    
    def _analyze_tool_with_llm(self, tool_file: Path, llm_client) -> Optional[Dict]:
        """Use LLM to analyze tool code and extract capabilities"""
        
        # Read tool code
        code = tool_file.read_text(encoding='utf-8')
        
        # Build analysis prompt
        prompt = f"""Analyze this Python tool class and extract its capabilities.

Tool file: {tool_file.name}

Code:
```python
{code}
```

Extract:
1. All public methods (operations)
2. For each method: parameters, required parameters, description from docstring
3. Tool version if present

Output JSON format:
{{
  "name": "tool_name",
  "version": "1.0.0",
  "description": "Brief description",
  "operations": {{
    "method_name": {{
      "parameters": ["param1", "param2"],
      "required": ["param1"],
      "description": "What this operation does"
    }}
  }}
}}

Respond with only valid JSON."""

        # Call LLM
        response = llm_client._call_llm(prompt, temperature=0.1, max_tokens=2048, expect_json=True)
        
        if not response:
            return None
        
        # Extract JSON
        tool_data = llm_client._extract_json(response)
        
        if tool_data:
            tool_data["last_updated"] = datetime.now().isoformat()
            tool_data["source_file"] = str(tool_file)
        
        return tool_data
    
    def get_registry(self) -> Dict:
        """Load current registry"""
        if not self.registry_path.exists():
            return {"tools": {}, "last_sync": None}
        
        with open(self.registry_path, 'r') as f:
            registry = json.load(f)

        if "tools" in registry:
            registry["tools"] = {
                name: meta
                for name, meta in registry["tools"].items()
                if name not in self.DISABLED_TOOLS
            }
        return registry
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict]:
        """Get info for specific tool"""
        registry = self.get_registry()
        return registry.get("tools", {}).get(tool_name)

    def resolve_source_file(self, tool_name: str) -> Optional[Path]:
        """Resolve a tool's source file using the registry (best-effort)."""
        def _norm(name: str) -> str:
            return "".join(ch for ch in (name or "").lower() if ch.isalnum())

        registry = self.get_registry() or {}
        tools = (registry.get("tools") or {}) if isinstance(registry, dict) else {}
        if not tools:
            return None

        entry = tools.get(tool_name)
        if not entry:
            wanted = _norm(tool_name)
            for existing_name, data in tools.items():
                if _norm(existing_name) == wanted:
                    entry = data
                    break

        source_file = str((entry or {}).get("source_file") or "").strip()
        if not source_file:
            return None

        path = Path(source_file)
        if path.exists():
            return path

        # Normalize separators for Windows/JSON mismatches.
        normalized = Path(source_file.replace("\\", "/"))
        if normalized.exists():
            return normalized

        # Try relative to repo root when registry stored a relative path.
        relative = Path.cwd() / source_file
        if relative.exists():
            return relative

        return None

    def update_tool(self, tool_data: Dict) -> bool:
        """Upsert a single tool entry and persist registry."""
        if not tool_data:
            return False

        tool_name = (tool_data.get("name") or "").strip()
        if not tool_name:
            return False
        if tool_name in self.DISABLED_TOOLS:
            return False

        registry = self.get_registry()
        if "tools" not in registry:
            registry["tools"] = {}

        existing = registry["tools"].get(tool_name, {})
        merged = dict(tool_data)
        merged["last_updated"] = datetime.now().isoformat()

        # Version: increment if capabilities changed, else keep existing
        old_hash = existing.get("capability_hash", "")
        new_hash = self._capability_hash(tool_data)
        merged["capability_hash"] = new_hash
        if old_hash and old_hash != new_hash:
            merged["version"] = (existing.get("version") or 1) + 1
        else:
            merged["version"] = existing.get("version") or 1

        # Status: preserve existing unless explicitly set
        merged["status"] = tool_data.get("status") or existing.get("status") or "active"

        # Reputation: preserve existing score, don't overwrite with None
        if "reputation_score" not in tool_data:
            merged["reputation_score"] = existing.get("reputation_score", 0.5)

        # Remove stale aliases that point to the same source file.
        source_norm = str(merged.get("source_file", "")).replace("\\", "/")
        if source_norm:
            for existing_name in list(registry["tools"].keys()):
                existing_source = str(registry["tools"][existing_name].get("source_file", "")).replace("\\", "/")
                if existing_name != tool_name and existing_source and existing_source == source_norm:
                    del registry["tools"][existing_name]

        registry["tools"][tool_name] = merged
        registry["last_sync"] = merged["last_updated"]

        with open(self.registry_path, 'w') as f:
            json.dump(registry, f, indent=2)

        return True

    @staticmethod
    def _capability_hash(tool_data: Dict) -> str:
        """SHA1 of sorted operation names — changes when capabilities are added/removed."""
        import hashlib
        ops = sorted((tool_data.get("operations") or {}).keys())
        return hashlib.sha1("|".join(ops).encode()).hexdigest()[:12]

    def prune_tools_not_in_sources(self, keep_sources: List[str]) -> int:
        """Remove registry entries whose source_file is not in keep_sources."""
        registry = self.get_registry()
        tools = registry.get("tools", {})
        keep = {str(p).replace("\\", "/") for p in keep_sources}

        removed = 0
        for tool_name in list(tools.keys()):
            source = str(tools[tool_name].get("source_file", "")).replace("\\", "/")
            if source and source not in keep:
                del tools[tool_name]
                removed += 1

        if removed:
            registry["tools"] = tools
            registry["last_sync"] = datetime.now().isoformat()
            with open(self.registry_path, 'w') as f:
                json.dump(registry, f, indent=2)
        return removed
    
    def get_all_capabilities_text(self) -> str:
        """Get formatted text of all capabilities for LLM prompts"""
        registry = self.get_registry()
        
        if not registry.get("tools"):
            return "No tools registered. Run sync first."
        
        lines = []
        for tool_name, tool_data in registry["tools"].items():
            lines.append(f"\n{tool_name}:")
            if "description" in tool_data:
                lines.append(f"  Description: {tool_data['description']}")
            
            operations = tool_data.get("operations", {})
            for op_name, op_data in operations.items():
                params = ", ".join(op_data.get("parameters", []))
                lines.append(f"  - {op_name}({params})")
                if "description" in op_data:
                    lines.append(f"    {op_data['description']}")
        
        return "\n".join(lines)
