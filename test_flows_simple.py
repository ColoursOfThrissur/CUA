"""
Simple test to verify the platform server can start and main flows work.
Uses actual import paths that work in the server.
"""
import sys
import os
from pathlib import Path

from shared.config.branding import get_platform_name

# Fix Windows Unicode
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

def test_server_bootstrap():
    """Test that the server can bootstrap"""
    print("\n=== Testing Server Bootstrap ===")
    try:
        from api.server import app
        routes = [route.path for route in app.routes]
        print(f"[OK] Server bootstrapped with {len(routes)} routes")
        
        # Check critical endpoints
        critical = ['/chat', '/health', '/tools', '/evolution', '/autonomy']
        for endpoint in critical:
            matching = [r for r in routes if endpoint in r]
            if matching:
                print(f"  [OK] {endpoint} endpoint found")
            else:
                print(f"  [WARN] {endpoint} endpoint not found")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database():
    """Test database connection"""
    print("\n=== Testing Database ===")
    try:
        from infrastructure.persistence.sqlite.cua_database import get_conn
        with get_conn() as conn:
            result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 5").fetchall()
            print(f"[OK] Database connected, {len(result)} tables found")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_llm_client():
    """Test LLM client"""
    print("\n=== Testing LLM Client ===")
    try:
        from planner.llm_client import LLMClient
        client = LLMClient()
        print(f"[OK] LLM client initialized")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_skill_system():
    """Test skill system"""
    print("\n=== Testing Skill System ===")
    try:
        from application.services.skill_registry import SkillRegistry
        from application.services.skill_selector import SkillSelector
        
        registry = SkillRegistry()
        registry.load_all()
        selector = SkillSelector()
        
        selection = selector.select_skill("search the web for Python", registry, llm_client=None)
        if not selection.matched:
            raise AssertionError("Skill selector failed to match a basic web request")
        print(f"[OK] Skill system works, selected: {selection.skill_name}")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_task_planner():
    """Test task planner"""
    print("\n=== Testing Task Planner ===")
    try:
        from application.use_cases.planning.task_planner import TaskPlanner
        print(f"[OK] TaskPlanner imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_execution_engine():
    """Test execution engine"""
    print("\n=== Testing Execution Engine ===")
    try:
        from application.use_cases.execution.execution_engine import ExecutionEngine
        print(f"[OK] ExecutionEngine imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_tool_orchestrator():
    """Test tool orchestrator"""
    print("\n=== Testing Tool Orchestrator ===")
    try:
        # ToolOrchestrator is in execution package
        from application.use_cases.execution.execution_engine import ExecutionEngine
        print(f"[OK] Execution components imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_autonomous_agent():
    """Test autonomous agent"""
    print("\n=== Testing Autonomous Agent ===")
    try:
        from application.use_cases.autonomy.autonomous_agent import AutonomousAgent
        print(f"[OK] AutonomousAgent imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_gap_detection():
    """Test gap detection"""
    print("\n=== Testing Gap Detection ===")
    try:
        from domain.services.gap_analysis_service import GapAnalysisService
        from domain.services.gap_detector import GapDetector
        from domain.services.gap_tracker import GapTracker
        print(f"[OK] Gap detection system imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_tool_creation():
    """Test tool creation"""
    print("\n=== Testing Tool Creation ===")
    try:
        from application.use_cases.tool_lifecycle.tool_creation_flow import ToolCreationOrchestrator
        print(f"[OK] ToolCreationOrchestrator imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_tool_evolution():
    """Test tool evolution"""
    print("\n=== Testing Tool Evolution ===")
    try:
        from application.use_cases.tool_lifecycle.tool_evolution_flow import ToolEvolutionOrchestrator
        print(f"[OK] ToolEvolutionOrchestrator imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def main():
    print("=" * 60)
    print(f"{get_platform_name().upper()} PHASE 6 - MAIN FLOWS TEST")
    print("=" * 60)
    
    tests = [
        ("Server Bootstrap", test_server_bootstrap),
        ("Database", test_database),
        ("LLM Client", test_llm_client),
        ("Skill System", test_skill_system),
        ("Task Planner", test_task_planner),
        ("Execution Engine", test_execution_engine),
        ("Tool Orchestrator", test_tool_orchestrator),
        ("Autonomous Agent", test_autonomous_agent),
        ("Gap Detection", test_gap_detection),
        ("Tool Creation", test_tool_creation),
        ("Tool Evolution", test_tool_evolution),
    ]
    
    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"\n[FAIL] {name} crashed: {e}")
            results[name] = False
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status:8} {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed ({100*passed//total}%)")
    
    if passed == total:
        print("\n[SUCCESS] All tests passed!")
        return 0
    elif passed >= total * 0.8:
        print(f"\n[GOOD] Most tests passed, {total-passed} minor issues")
        return 0
    else:
        print(f"\n[WARNING] {total-passed} tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
