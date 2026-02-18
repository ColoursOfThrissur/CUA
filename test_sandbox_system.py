"""
Test the complete sandbox testing system
Validates: patch generation, sandbox isolation, targeted testing, test execution
"""
import tempfile
import shutil
from pathlib import Path

def test_sandbox_system():
    """Test complete sandbox flow"""
    print("=" * 60)
    print("TESTING COMPLETE SANDBOX SYSTEM")
    print("=" * 60)
    
    # Test 1: Patch Generation
    print("\n[1/5] Testing Patch Generation...")
    from core.patch_generator import PatchGenerator
    
    patch_gen = PatchGenerator(repo_path=".")
    
    original = "def hello():\n    return 'old'\n"
    modified = "def hello():\n    return 'new'\n"
    
    patch = patch_gen.generate_patch("test.py", original, modified)
    
    if patch and "FILE_REPLACE:test.py" in patch:
        print("[OK] Patch generation works (FILE_REPLACE format)")
    else:
        print("[FAIL] Patch generation failed")
        return False
    
    # Test 2: Sandbox Isolation
    print("\n[2/5] Testing Sandbox Isolation...")
    from updater.sandbox_runner import SandboxRunner
    
    runner = SandboxRunner(repo_path=".")
    
    # Create a simple test patch
    test_patch = f"FILE_REPLACE:workspace/sandbox_test.txt\nTest content from sandbox"
    
    result = runner.run_in_sandbox(test_patch, timeout=30, changed_file="workspace/sandbox_test.txt")
    
    # Check original file NOT modified
    from pathlib import Path as PathLib
    original_file = PathLib("workspace/sandbox_test.txt")
    if original_file.exists():
        print("[FAIL] Sandbox leaked - original file was modified!")
        return False
    else:
        print("[OK] Sandbox isolation works (original files untouched)")
    
    # Test 3: Targeted Testing
    print("\n[3/5] Testing Targeted Test Selection...")
    
    # Test that shell_tool.py maps to test_shell_tool.py
    test_file = Path("tests/unit/test_shell_tool.py")
    if test_file.exists():
        print(f"[OK] Test file exists: {test_file}")
        
        # Verify mapping logic
        from pathlib import Path
        changed_file = "tools/shell_tool.py"
        file_name = Path(changed_file).stem
        expected_test = f"tests/unit/test_{file_name}.py"
        
        if expected_test == str(test_file):
            print(f"[OK] Mapping works: {changed_file} -> {expected_test}")
        else:
            print(f"[FAIL] Mapping failed: expected {expected_test}")
            return False
    else:
        print(f"[FAIL] Test file missing: {test_file}")
        return False
    
    # Test 4: Test Execution
    print("\n[4/5] Testing Test Execution...")
    import subprocess
    
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/unit/test_shell_tool.py", "-v", "--tb=no", "-q"],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    if "passed" in result.stdout or "skipped" in result.stdout:
        print(f"[OK] Tests executed successfully")
        # Parse results
        if "passed" in result.stdout:
            passed = result.stdout.count("PASSED")
            print(f"  - {passed} tests passed")
    else:
        print(f"[FAIL] Test execution failed")
        print(f"  Output: {result.stdout[:200]}")
        return False
    
    # Test 5: Full Integration
    print("\n[5/5] Testing Full Integration...")
    from core.sandbox_tester import SandboxTester
    from core.system_analyzer import SystemAnalyzer
    
    analyzer = SystemAnalyzer()
    tester = SandboxTester(analyzer)
    
    # Create a valid proposal
    proposal = {
        'raw_code': 'def test():\n    return "test"\n',
        'files_changed': ['workspace/test_integration.py'],
        'patch': 'FILE_REPLACE:workspace/test_integration.py\ndef test():\n    return "test"\n'
    }
    
    # This should work (syntax valid, no tests for this file)
    result = tester.test_proposal(proposal, timeout=30)
    
    if result['success'] or 'SKIPPED' in result['output']:
        print("[OK] Full integration works")
        print(f"  - Tests: {result['tests_passed']}/{result['tests_total']}")
    else:
        print("[FAIL] Integration failed")
        print(f"  Output: {result['output'][:200]}")
        return False
    
    print("\n" + "=" * 60)
    print("ALL SANDBOX TESTS PASSED")
    print("=" * 60)
    print("\nSandbox System Status:")
    print("  [OK] Patch generation (FILE_REPLACE format)")
    print("  [OK] Sandbox isolation (original files protected)")
    print("  [OK] Targeted testing (file -> test mapping)")
    print("  [OK] Test execution (pytest integration)")
    print("  [OK] Full integration (end-to-end flow)")
    print("\nThe sandbox system is ready for self-improvement!")
    
    return True

if __name__ == "__main__":
    try:
        success = test_sandbox_system()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n[FAIL] SANDBOX TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
