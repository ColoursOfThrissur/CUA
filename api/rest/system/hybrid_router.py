"""
Hybrid Engine API - Endpoints for memory, stats, and prioritization
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
from application.use_cases.improvement.hybrid_improvement_engine import HybridImprovementEngine
from infrastructure.persistence.file_storage.improvement_memory import ImprovementMemory
from infrastructure.failure_handling.error_prioritizer import ErrorPrioritizer

router = APIRouter(prefix="/hybrid", tags=["hybrid"])

# Initialize components - lazy loading for hybrid engine
hybrid_engine = None
memory = None
prioritizer = None

def get_hybrid_engine():
    global hybrid_engine, memory, prioritizer
    if hybrid_engine is None:
        hybrid_engine = HybridImprovementEngine()
        memory = hybrid_engine.memory
        prioritizer = hybrid_engine.prioritizer
    return hybrid_engine

@router.get("/stats")
async def get_stats():
    """Get overall improvement statistics"""
    try:
        engine = get_hybrid_engine()
        success_rate = engine.memory.get_success_rate()
        failed_attempts = engine.memory.get_failed_attempts(days=7)
        
        return {
            "success_rate": success_rate,
            "recent_failures": len(failed_attempts),
            "failed_files": list(set([f['file_path'] for f in failed_attempts]))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/priority-files")
async def get_priority_files(max_files: int = 5):
    """Get prioritized files based on errors"""
    try:
        engine = get_hybrid_engine()
        priority_files = engine.prioritizer.get_priority_files(max_files=max_files)
        
        result = []
        for file_path, error_count in priority_files:
            error_context = engine.prioritizer.get_error_context(file_path)
            past_attempts = engine.memory.get_similar_attempts(file_path, limit=3)
            
            result.append({
                "file": file_path,
                "error_count": error_count,
                "error_types": dict(error_context.get('error_types', {})),
                "past_attempts": len(past_attempts),
                "success_rate": engine.memory.get_success_rate(file_path)
            })
        
        return {"priority_files": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/memory/{file_path:path}")
async def get_file_memory(file_path: str, limit: int = 10):
    """Get improvement history for a specific file"""
    try:
        engine = get_hybrid_engine()
        attempts = engine.memory.get_similar_attempts(file_path, limit=limit)
        success_rate = engine.memory.get_success_rate(file_path)
        
        return {
            "file": file_path,
            "success_rate": success_rate,
            "attempts": attempts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/error-analysis")
async def get_error_analysis():
    """Get comprehensive error analysis"""
    try:
        engine = get_hybrid_engine()
        errors = engine.prioritizer.analyze_logs(days=7)
        
        # Summarize
        total_errors = sum(data['count'] for data in errors.values())
        files_with_errors = len(errors)
        
        # Top error types
        all_error_types = {}
        for data in errors.values():
            for error_type, count in data['error_types'].items():
                all_error_types[error_type] = all_error_types.get(error_type, 0) + count
        
        top_errors = sorted(all_error_types.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            "total_errors": total_errors,
            "files_affected": files_with_errors,
            "top_error_types": [{"type": t, "count": c} for t, c in top_errors],
            "errors_by_file": {k: v['count'] for k, v in list(errors.items())[:10]}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze")
async def trigger_analysis(custom_prompt: Optional[str] = None):
    """Trigger hybrid engine analysis"""
    try:
        engine = get_hybrid_engine()
        result = engine.analyze_and_improve(
            custom_prompt=custom_prompt,
            max_iterations=3
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
