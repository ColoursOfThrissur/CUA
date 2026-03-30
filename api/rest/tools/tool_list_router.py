"""List all available tools API."""
from fastapi import APIRouter
from pathlib import Path

router = APIRouter()


@router.get("/tools/list")
async def list_all_tools():
    """List all available tool files."""
    tools = []
    
    # Scan tools directory
    tools_dir = Path("tools")
    if tools_dir.exists():
        for file in tools_dir.glob("*.py"):
            if file.stem not in ["__init__", "tool_interface", "tool_result", "tool_capability", 
                                  "capability_registry", "capability_extractor", "static_analyzer",
                                  "analyze_llm_logs", "test_web_content_extractor"]:
                tools.append({
                    "tool_name": file.stem,
                    "file_path": str(file)
                })
    
    # Scan experimental directory
    exp_dir = Path("tools/experimental")
    if exp_dir.exists():
        for file in exp_dir.glob("*.py"):
            if file.stem != "__init__":
                tools.append({
                    "tool_name": file.stem,
                    "file_path": str(file)
                })
    
    return {"tools": tools}
