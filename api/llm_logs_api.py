"""
LLM Logs API - Stream real-time LLM communication logs
"""
from fastapi import APIRouter
from pathlib import Path
import json

router = APIRouter(prefix="/llm-logs", tags=["llm-logs"])

@router.get("/latest")
async def get_latest_llm_logs(limit: int = 50):
    """Get latest LLM communication logs"""
    try:
        logs_dir = Path("logs/llm")
        if not logs_dir.exists():
            return {"logs": []}
        
        # Get most recent session file
        session_files = sorted(logs_dir.glob("session_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        
        if not session_files:
            return {"logs": []}
        
        latest_file = session_files[0]
        
        # Read last N lines
        logs = []
        with open(latest_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    log_entry = json.loads(line.strip())
                    # Extract readable summary
                    prompt_preview = log_entry.get('prompt', '')[:200]
                    response_preview = log_entry.get('response', '')[:200]
                    
                    logs.append({
                        'timestamp': log_entry.get('timestamp', ''),
                        'interaction': log_entry.get('interaction', 0),
                        'prompt_preview': prompt_preview,
                        'response_preview': response_preview,
                        'session_id': log_entry.get('session_id', '')
                    })
                except json.JSONDecodeError:
                    continue
        
        return {"logs": logs[-limit:]}
    
    except Exception as e:
        return {"logs": [], "error": str(e)}
