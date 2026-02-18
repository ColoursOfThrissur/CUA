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
    
    def __init__(self, registry_path: str = "data/tool_registry.json", tools_dir: str = "tools"):
        self.registry_path = Path(registry_path)
        self.tools_dir = Path(tools_dir)
        self.registry_path.parent.mkdir(exist_ok=True)
    
    def sync_all_tools(self, llm_client) -> Dict:
        """Sync all tools using LLM to analyze code"""
        results = {"synced": [], "failed": [], "timestamp": datetime.now().isoformat()}
        
        # Find all tool files
        tool_files = list(self.tools_dir.glob("*_tool.py"))
        
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
            return json.load(f)
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict]:
        """Get info for specific tool"""
        registry = self.get_registry()
        return registry.get("tools", {}).get(tool_name)
    
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
