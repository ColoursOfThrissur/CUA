"""
Sandbox Tester - Tests code proposals in isolated environment
"""
from typing import Dict, Optional
import ast
import tempfile
import sys
from pathlib import Path


class SandboxTester:
    def __init__(self, system_analyzer, libraries_manager=None):
        from core.config_manager import get_config
        self.config = get_config()
        self.analyzer = system_analyzer
        self.libraries_manager = libraries_manager
    
    def test_proposal(self, proposal: Dict, timeout: int = None) -> Dict:
        """
        Test proposal in sandbox with baseline comparison
        Args:
            proposal: Proposal dict with raw_code and patch
            timeout: Timeout in seconds (from config if not provided)
        Returns: {
            'success': bool,
            'tests_passed': int,
            'tests_total': int,
            'baseline_passed': int,
            'output': str
        }
        """
        from core.logging_system import get_logger
        logger = get_logger("sandbox_tester")
        
        timeout = timeout or self.config.improvement.sandbox_timeout
        raw_code = proposal.get('raw_code', '')
        target_file = proposal.get('files_changed', [''])[0]
        
        logger.info(f"Testing proposal for {target_file}")
        
        if not raw_code:
            logger.error("No code to test")
            return self._error_result("No code to test")
        
        # Syntax validation - MUST pass
        try:
            ast.parse(raw_code)
            logger.info("Syntax validation passed")
        except SyntaxError as e:
            logger.error(f"Syntax error: {e}")
            return self._error_result(f"Syntax error: {e}")
        
        # Check for new imports and create pending approvals
        if self.libraries_manager:
            new_imports = self.libraries_manager.detect_new_imports(raw_code)
            if new_imports:
                logger.info(f"Detected new imports: {new_imports}")
                for lib in new_imports:
                    lib_id = self.libraries_manager.add_pending(
                        lib,
                        f"Required by improvement to {target_file}",
                        "self_improvement"
                    )
                    logger.info(f"Created pending approval for library: {lib} (ID: {lib_id})")
                
                return {
                    "success": False,
                    "tests_passed": 0,
                    "tests_total": 1,
                    "baseline_passed": 0,
                    "output": f"PENDING: Requires library approval: {', '.join(new_imports)}",
                    "pending_libraries": new_imports
                }
        
        # Get baseline: run tests on ORIGINAL code
        baseline_result = self._get_baseline(target_file, timeout)
        if baseline_result is None:
            logger.error("Baseline test failed to run - cannot validate proposal")
            return self._error_result("Baseline test failed - cannot validate safely")
        
        baseline_passed, baseline_failed = baseline_result
        logger.info(f"Baseline: {baseline_passed} passed, {baseline_failed} failed")
        
        # Use patch from proposal (already validated)
        patch = proposal.get('patch', '')
        if not patch:
            logger.error("No patch in proposal")
            return self._error_result("Proposal missing patch")
        
        logger.info(f"Using patch from proposal: {len(patch)} chars")
        
        # Run tests on NEW code
        try:
            from updater.sandbox_runner import SandboxRunner
            logger.info("Testing new code in sandbox...")
            runner = SandboxRunner(repo_path=".")
            result = runner.run_in_sandbox(patch, timeout=timeout, changed_file=target_file)
            
            tests_passed = result.test_output.count('PASSED') if result.test_output else 0
            tests_failed = result.test_output.count('FAILED') if result.test_output else 0
            tests_total = tests_passed + tests_failed
            
            # STRICT VALIDATION RULES:
            # 1. At least as many tests must run (prevents test deletion)
            # 2. At least as many tests must pass (prevents regressions)
            # 3. No NEW failures allowed (prevents breaking working code)
            # 4. If baseline had 0 tests, new code must have tests
            # 5. Code must actually change (prevents no-op)
            
            baseline_total = baseline_passed + baseline_failed
            
            # Check if code actually changed
            code_changed = self._verify_code_changed(target_file, raw_code)
            if not code_changed:
                logger.error("Code did not change - LLM returned original code")
                return {
                    "success": False,
                    "tests_passed": tests_passed,
                    "tests_total": tests_total,
                    "baseline_passed": baseline_passed,
                    "output": "REJECT: Code unchanged - no improvement implemented"
                }
            
            if baseline_total == 0:
                # No baseline tests - require new code to have passing tests
                success = tests_passed > 0 and tests_failed == 0
                reason = "new tests added" if success else "no tests or failures"
            else:
                # Has baseline - strict comparison
                success = (
                    tests_total >= baseline_total and  # Same or more tests
                    tests_passed >= baseline_passed and  # Same or more passing
                    tests_failed <= baseline_failed  # Same or fewer failures
                )
                
                if tests_passed > baseline_passed:
                    reason = "improvement"
                elif tests_passed == baseline_passed and tests_failed < baseline_failed:
                    reason = "fixed failures"
                elif tests_passed == baseline_passed and tests_failed == baseline_failed:
                    reason = "maintained"
                else:
                    reason = "regression"
            
            logger.info(f"New code: {tests_passed}/{tests_total} passed (baseline: {baseline_passed}/{baseline_total})")
            logger.info(f"Result: {'ACCEPT' if success else 'REJECT'} - {reason}")
            
            return {
                "success": success,
                "tests_passed": tests_passed,
                "tests_total": tests_total if tests_total > 0 else 1,
                "baseline_passed": baseline_passed,
                "output": result.test_output[:2000] if result.test_output else (result.error or "Unknown error")  # Increased from 500 to 2000
            }
        except Exception as e:
            logger.error(f"Sandbox exception: {e}", exc_info=True)
            return self._error_result(f"Sandbox error: {str(e)}")

    def _get_baseline(self, target_file: str, timeout: int):
        """Get baseline test results on ORIGINAL code
        Returns: (passed, failed) tuple or None if baseline fails
        """
        from updater.sandbox_runner import SandboxRunner
        from core.logging_system import get_logger
        logger = get_logger("sandbox_tester")
        
        try:
            runner = SandboxRunner(repo_path=".")
            # Empty patch = test original code
            result = runner.run_in_sandbox("", timeout=timeout, changed_file=target_file)
            
            if not result.success and result.error:
                logger.error(f"Baseline test error: {result.error}")
                return None
            
            passed = result.test_output.count('PASSED') if result.test_output else 0
            failed = result.test_output.count('FAILED') if result.test_output else 0
            
            return (passed, failed)
        except Exception as e:
            logger.error(f"Baseline test exception: {e}")
            return None

    def _regenerate_patch(self, target_file: str, new_code: str) -> Optional[str]:
        """Regenerate patch from current file state (Option 2)"""
        from core.patch_generator import PatchGenerator
        from pathlib import Path
        
        patch_gen = PatchGenerator(repo_path=".")
        full_path = Path(target_file)
        
        if full_path.exists():
            with open(full_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
            return patch_gen.generate_patch(target_file, current_content, new_code)
        else:
            return patch_gen.generate_new_file_patch(target_file, new_code)
    
    def _error_result(self, message: str) -> Dict:
        """Return error result"""
        from core.logging_system import get_logger
        logger = get_logger("sandbox_tester")
        logger.error(f"Test failed: {message}")
        return {
            "success": False,
            "tests_passed": 0,
            "tests_total": 1,
            "output": message
        }
    
    def _verify_code_changed(self, target_file: str, new_code: str) -> bool:
        """Verify new code is different from original"""
        from pathlib import Path
        
        try:
            full_path = Path(target_file)
            if not full_path.exists():
                return True  # New file
            
            original_code = full_path.read_text(encoding='utf-8')
            
            # Normalize whitespace for comparison
            original_normalized = ''.join(original_code.split())
            new_normalized = ''.join(new_code.split())
            
            return original_normalized != new_normalized
        except Exception:
            return True  # Assume changed if can't verify
    
    def retry_with_libraries(self, proposal: Dict, timeout: int = None) -> Dict:
        """Retry test after libraries are installed"""
        # Just call test_proposal again - libraries should now be installed
        return self.test_proposal(proposal, timeout)