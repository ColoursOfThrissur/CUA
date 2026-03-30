"""Tool info API - get tool capabilities and description."""
from fastapi import APIRouter, HTTPException
from pathlib import Path
import ast

router = APIRouter()


@router.get("/tools/info/{tool_name}")
async def get_tool_info(tool_name: str):
    """Get tool capabilities and description."""
    
    # Find tool file
    candidates = [
        Path(f"tools/{tool_name}.py"),
        Path(f"tools/{tool_name.lower()}.py"),
        Path(f"tools/experimental/{tool_name}.py"),
    ]
    
    tool_path = None
    for path in candidates:
        if path.exists():
            tool_path = path
            break
    
    if not tool_path:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    # Parse tool file
    try:
        code = tool_path.read_text()
        tree = ast.parse(code)
        
        # Extract class docstring
        description = "No description available"
        capabilities = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if ast.get_docstring(node):
                    description = ast.get_docstring(node)
                
                # Find get_capabilities method
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "get_capabilities":
                        # Try to extract capability names and descriptions from return dict
                        for stmt in ast.walk(item):
                            if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Dict):
                                for i, key in enumerate(stmt.value.keys):
                                    if isinstance(key, ast.Constant):
                                        cap_name = key.value
                                        # Try to get description from Capability object
                                        if i < len(stmt.value.values):
                                            val = stmt.value.values[i]
                                            if isinstance(val, ast.Call):
                                                # Look for description in Capability constructor
                                                for kw in val.keywords:
                                                    if kw.arg == 'description' and isinstance(kw.value, ast.Constant):
                                                        capabilities.append(f"{cap_name}: {kw.value.value}")
                                                        break
                                                else:
                                                    capabilities.append(cap_name)
                                            else:
                                                capabilities.append(cap_name)
        
        # If generic docstring, generate better description from capabilities
        if description == "No description available" or description == "Thin tool using orchestrator services.":
            if capabilities:
                description = f"Tool that provides: {', '.join([c.split(':')[0] for c in capabilities])}"
            else:
                description = f"Tool: {tool_name}"
        
        return {
            "tool_name": tool_name,
            "description": description,
            "capabilities": capabilities,
            "file_path": str(tool_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse tool: {str(e)}")
