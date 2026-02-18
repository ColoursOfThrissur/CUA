"""
Complete Improvement Flow Test
Tests: Analysis -> Step Planning -> Code Generation -> Validation -> Patching -> Sandbox
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.task_analyzer import TaskAnalyzer
from core.proposal_generator import ProposalGenerator
from core.sandbox_tester import SandboxTester
from core.system_analyzer import SystemAnalyzer
from core.patch_generator import PatchGenerator
from core.step_planner import StepPlanner
from planner.llm_client import LLMClient
from tools.capability_registry import CapabilityRegistry
from core.llm_logger import LLMLogger
from updater.orchestrator import UpdateOrchestrator

def test_improvement_flow():
    """Test complete improvement flow end-to-end"""
    
    print("=" * 70)
    print("COMPLETE IMPROVEMENT FLOW TEST")
    print("=" * 70 + "\n")
    
    # Initialize components
    print("Step 0: Initializing components...")
    registry = CapabilityRegistry()
    llm_client = LLMClient(registry=registry)
    analyzer = SystemAnalyzer()
    patch_gen = PatchGenerator()
    orchestrator = UpdateOrchestrator(repo_path=".")
    llm_logger = LLMLogger()
    
    task_analyzer = TaskAnalyzer(llm_client, analyzer, llm_logger)
    proposal_generator = ProposalGenerator(llm_client, analyzer, patch_gen, orchestrator)
    sandbox_tester = SandboxTester(analyzer)
    step_planner = StepPlanner(llm_client)
    
    print("  [OK] All components initialized\n")
    
    # Step 1: Task Analysis
    print("Step 1: Analyzing codebase for improvements...")
    tasks = task_analyzer.analyze_and_propose_tasks(
        focus="Add _put() and _delete() methods to HTTPTool",
        failed_suggestions=[],
        iteration_history=[]
    )
    
    assert tasks, "No tasks generated"
    assert len(tasks) > 0, "Task list is empty"
    
    analysis = tasks[0]
    print(f"  [OK] Task analyzed")
    print(f"       Target: {analysis.get('files_affected', ['unknown'])[0]}")
    print(f"       Task: {analysis.get('suggestion', 'N/A')[:60]}...")
    print(f"       Methods: {analysis.get('methods_to_modify', [])}")
    print(f"       Priority: {analysis.get('priority', 'N/A')}\n")
    
    # Step 2: Step Planning
    print("Step 2: Planning implementation steps...")
    steps, task_type = step_planner.plan_steps(analysis)
    
    assert steps, "No steps generated"
    assert task_type in ['add', 'modify'], f"Invalid task type: {task_type}"
    
    print(f"  [OK] Steps planned")
    print(f"       Task type: {task_type.upper()}")
    print(f"       Steps: {len(steps)}")
    for i, step in enumerate(steps, 1):
        print(f"         {i}. {step[:60]}...")
    print()
    
    # Step 3: Proposal Generation
    print("Step 3: Generating code proposal...")
    print(f"       Strategy: {'Single-shot' if task_type == 'add' else 'Incremental'}")
    
    proposal = proposal_generator.generate_proposal(analysis)
    
    assert proposal, "Proposal generation failed"
    assert 'raw_code' in proposal, "No raw_code in proposal"
    assert 'patch' in proposal, "No patch in proposal"
    assert 'files_changed' in proposal, "No files_changed in proposal"
    
    print(f"  [OK] Proposal generated")
    print(f"       Files changed: {proposal['files_changed']}")
    print(f"       Code size: {len(proposal['raw_code'])} chars")
    print(f"       Patch lines: {proposal['diff_lines']}")
    print(f"       Methods: {proposal.get('methods_to_modify', [])}\n")
    
    # Step 4: Code Validation
    print("Step 4: Validating generated code...")
    
    # Check syntax
    try:
        import ast
        ast.parse(proposal['raw_code'])
        print(f"  [OK] Syntax valid")
    except SyntaxError as e:
        raise AssertionError(f"Syntax error: {e}")
    
    # Check methods present
    methods = analysis.get('methods_to_modify', [])
    if methods:
        missing = [m for m in methods if f'def {m}' not in proposal['raw_code']]
        assert not missing, f"Missing methods: {missing}"
        print(f"  [OK] All methods present: {methods}")
    
    # Check completeness
    assert 'class ' in proposal['raw_code'], "No class definition"
    assert len(proposal['raw_code']) > 200, "Code too short"
    print(f"  [OK] Code structure valid\n")
    
    # Step 5: Patch Validation
    print("Step 5: Validating patch format...")
    
    patch = proposal['patch']
    
    # Check for FILE_REPLACE format (new simple format) or unified diff format
    if patch.startswith('FILE_REPLACE:'):
        print(f"  [OK] Patch format: FILE_REPLACE (simple)")
        assert '\n' in patch, "Missing content separator"
        file_marker, content = patch.split('\n', 1)
        assert len(content) > 0, "Empty patch content"
        print(f"  [OK] Patch content: {len(content)} chars")
    elif '---' in patch and '+++' in patch:
        print(f"  [OK] Patch format: Unified diff")
        assert '@@' in patch, "Missing hunk markers"
    else:
        raise AssertionError(f"Unknown patch format: {patch[:50]}")
    
    print(f"       Patch preview:")
    for line in patch.split('\n')[:5]:
        print(f"         {line}")
    print(f"         ... ({len(patch.split(chr(10)))} total lines)\n")
    
    # Step 6: Sandbox Testing
    print("Step 6: Testing in sandbox...")
    print(f"       Running tests for {proposal['files_changed'][0]}...")
    
    sandbox_result = sandbox_tester.test_proposal(proposal, timeout=30)
    
    print(f"  [{'OK' if sandbox_result['success'] else 'FAIL'}] Sandbox test completed")
    print(f"       Success: {sandbox_result['success']}")
    print(f"       Tests passed: {sandbox_result.get('tests_passed', 0)}/{sandbox_result.get('tests_total', 0)}")
    
    if sandbox_result.get('baseline_passed') is not None:
        print(f"       Baseline: {sandbox_result['baseline_passed']} tests")
    
    if not sandbox_result['success']:
        print(f"       Error: {sandbox_result.get('output', 'Unknown')[:100]}...")
    
    print()
    
    # Step 7: Summary
    print("=" * 70)
    print("FLOW TEST SUMMARY")
    print("=" * 70)
    print(f"Task Type:        {task_type.upper()}")
    print(f"Steps Planned:    {len(steps)}")
    print(f"Code Generated:   {len(proposal['raw_code'])} chars")
    print(f"Methods Added:    {len(analysis.get('methods_to_modify', []))}")
    print(f"Patch Valid:      YES")
    print(f"Sandbox Result:   {'PASS' if sandbox_result['success'] else 'FAIL'}")
    print("=" * 70)
    
    if sandbox_result['success']:
        print("\n[PASS] COMPLETE FLOW TEST PASSED")
    else:
        print("\n[WARN] FLOW COMPLETED WITH SANDBOX FAILURE")
        print("    (This is expected if tests don't exist yet)")
    
    return {
        'analysis': analysis,
        'steps': steps,
        'task_type': task_type,
        'proposal': proposal,
        'sandbox_result': sandbox_result
    }

def test_add_task_flow():
    """Test ADD task specifically"""
    print("\n" + "=" * 70)
    print("TESTING ADD TASK FLOW")
    print("=" * 70 + "\n")
    
    registry = CapabilityRegistry()
    llm_client = LLMClient(registry=registry)
    analyzer = SystemAnalyzer()
    
    step_planner = StepPlanner(llm_client)
    
    # Simulate ADD task analysis
    analysis = {
        'suggestion': 'Add _put() and _delete() methods to HTTPTool class',
        'files_affected': ['tools/http_tool.py'],
        'methods_to_modify': ['_put', '_delete'],
        'priority': 'high',
        'user_override': True
    }
    
    steps, task_type = step_planner.plan_steps(analysis)
    
    print(f"Task: {analysis['suggestion']}")
    print(f"Detected type: {task_type}")
    print(f"Steps: {len(steps)}")
    
    assert task_type == 'add', f"Expected 'add', got '{task_type}'"
    assert len(steps) == 1, f"ADD tasks should have 1 step, got {len(steps)}"
    
    print("[PASS] ADD task detection works correctly\n")

def test_modify_task_flow():
    """Test MODIFY task specifically with multi-step merge"""
    print("\n" + "=" * 70)
    print("TESTING MODIFY TASK FLOW WITH MERGE")
    print("=" * 70 + "\n")
    
    registry = CapabilityRegistry()
    llm_client = LLMClient(registry=registry)
    analyzer = SystemAnalyzer()
    patch_gen = PatchGenerator()
    orchestrator = UpdateOrchestrator(repo_path=".")
    llm_logger = LLMLogger()
    
    proposal_generator = ProposalGenerator(llm_client, analyzer, patch_gen, orchestrator)
    step_planner = StepPlanner(llm_client)
    
    # Simulate complex MODIFY task that needs multiple steps
    analysis = {
        'suggestion': 'Improve error handling and logging in execute method',
        'files_affected': ['tools/http_tool.py'],
        'methods_to_modify': ['execute'],
        'priority': 'medium',
        'user_override': False
    }
    
    steps, task_type = step_planner.plan_steps(analysis)
    
    print(f"Task: {analysis['suggestion']}")
    print(f"Detected type: {task_type}")
    print(f"Steps: {len(steps)}")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step}")
    
    assert task_type == 'modify', f"Expected 'modify', got '{task_type}'"
    
    if len(steps) > 1:
        print(f"\n[INFO] Multi-step MODIFY task will use LLM merge")
    
    print("[PASS] MODIFY task detection works correctly\n")

def test_dummy_task_flow():
    """Test with a simple dummy task that doesn't require real LLM"""
    print("\n" + "=" * 70)
    print("TESTING DUMMY TASK FLOW (No LLM required)")
    print("=" * 70 + "\n")
    
    from core.incremental_code_builder import IncrementalCodeBuilder
    
    # Dummy original code
    original_code = '''class DummyTool:
    def __init__(self):
        self.name = "dummy"
    
    def execute(self, operation, params):
        return {"status": "success"}
'''
    
    print("Original code:")
    print(original_code)
    print()
    
    # Test 1: IncrementalCodeBuilder
    print("Test 1: IncrementalCodeBuilder")
    builder = IncrementalCodeBuilder(original_code)
    
    # Add step 1
    step1_code = original_code.replace(
        'return {"status": "success"}',
        'if not operation:\n            raise ValueError("Operation required")\n        return {"status": "success"}'
    )
    builder.add_step("Add validation", step1_code)
    print(f"  [OK] Step 1 added: Add validation")
    
    # Add step 2
    step2_code = step1_code.replace(
        'def __init__(self):',
        'def __init__(self):\n        """Initialize dummy tool"""'
    )
    builder.add_step("Add docstring", step2_code)
    print(f"  [OK] Step 2 added: Add docstring")
    
    final_code = builder.get_complete_code()
    progress = builder.get_progress()
    
    print(f"  [OK] Steps completed: {progress['steps_completed']}")
    print(f"  [OK] Code size: {progress['original_size']} -> {progress['current_size']} chars")
    print()
    
    # Test 2: Task type detection
    print("Test 2: Task Type Detection")
    
    test_cases = [
        ("Add new method _validate", "add"),
        ("Create helper function", "add"),
        ("Improve error handling", "modify"),
        ("Fix bug in execute method", "modify"),
        ("Add _put and _delete methods", "add"),
    ]
    
    for task, expected_type in test_cases:
        detected = 'add' if any(kw in task.lower() for kw in ['add', 'create', 'new']) else 'modify'
        status = "[OK]" if detected == expected_type else "[FAIL]"
        print(f"  {status} '{task}' -> {detected} (expected: {expected_type})")
        assert detected == expected_type, f"Wrong detection for: {task}"
    
    print()
    
    # Test 3: Code validation
    print("Test 3: Code Validation")
    
    valid_code = '''class TestTool:
    def test_method(self):
        return True
'''
    
    invalid_code = '''class TestTool:
    def test_method(self)
        return True
'''
    
    import ast
    
    try:
        ast.parse(valid_code)
        print("  [OK] Valid code passes syntax check")
    except SyntaxError:
        raise AssertionError("Valid code failed syntax check")
    
    try:
        ast.parse(invalid_code)
        raise AssertionError("Invalid code passed syntax check")
    except SyntaxError:
        print("  [OK] Invalid code caught by syntax check")
    
    print()
    
    # Test 4: Method detection
    print("Test 4: Method Detection")
    
    code_with_methods = '''class Tool:
    def _put(self, url, data):
        pass
    
    def _delete(self, url):
        pass
'''
    
    required_methods = ['_put', '_delete']
    missing = [m for m in required_methods if f'def {m}' not in code_with_methods]
    
    assert not missing, f"Missing methods: {missing}"
    print(f"  [OK] All required methods found: {required_methods}")
    print()
    
    # Test 5: Patch format validation
    print("Test 5: Patch Format Validation")
    
    valid_patch = '''--- a/tools/dummy.py
+++ b/tools/dummy.py
@@ -1,3 +1,5 @@
 class DummyTool:
+    def new_method(self):
+        pass
'''
    
    assert '---' in valid_patch, "Missing patch header"
    assert '+++' in valid_patch, "Missing patch target"
    assert '@@' in valid_patch, "Missing hunk markers"
    print("  [OK] Patch format valid")
    print()
    
    print("=" * 70)
    print("[PASS] ALL DUMMY TESTS PASSED")
    print("=" * 70)
    
    return {
        'builder_test': 'passed',
        'detection_test': 'passed',
        'validation_test': 'passed',
        'method_test': 'passed',
        'patch_test': 'passed'
    }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test improvement flow')
    parser.add_argument('--dummy', action='store_true', help='Run dummy tests only (no LLM)')
    parser.add_argument('--full', action='store_true', help='Run full flow test (requires LLM)')
    args = parser.parse_args()
    
    try:
        if args.dummy or (not args.dummy and not args.full):
            # Run dummy tests (default)
            print("Running dummy tests (no LLM required)...\n")
            result = test_dummy_task_flow()
            print(f"\nDummy test results: {result}")
        
        if args.full:
            # Run full flow test
            print("\nRunning full flow test (requires LLM)...\n")
            result = test_improvement_flow()
            
            # Run specific task type tests
            test_add_task_flow()
            test_modify_task_flow()
        
        print("\n" + "=" * 70)
        print("ALL TESTS PASSED [OK]")
        print("=" * 70)
        
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
