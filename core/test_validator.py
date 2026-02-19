"""
Test-Driven Validator - Automatically validates code changes with tests
"""
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional

class TestValidator:
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
    
    def run_tests(self, test_path: Optional[str] = None, timeout: int = 60) -> Dict:
        """Run tests and return results"""
        cmd = ["pytest", "-v", "--tb=short", "--json-report", "--json-report-file=test_results.json"]
        
        if test_path:
            cmd.append(test_path)
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            # Parse JSON report if available
            report_file = self.project_root / "test_results.json"
            if report_file.exists():
                with open(report_file, 'r') as f:
                    test_data = json.load(f)
                
                return {
                    'passed': test_data.get('summary', {}).get('passed', 0),
                    'failed': test_data.get('summary', {}).get('failed', 0),
                    'errors': test_data.get('summary', {}).get('error', 0),
                    'total': test_data.get('summary', {}).get('total', 0),
                    'duration': test_data.get('duration', 0),
                    'success': result.returncode == 0,
                    'output': result.stdout,
                    'failures': self._extract_failures(test_data)
                }
            else:
                # Fallback to parsing stdout
                return self._parse_pytest_output(result.stdout, result.returncode)
        
        except subprocess.TimeoutExpired:
            return {
                'passed': 0,
                'failed': 0,
                'errors': 1,
                'total': 0,
                'success': False,
                'output': 'Test execution timed out',
                'failures': []
            }
        except Exception as e:
            return {
                'passed': 0,
                'failed': 0,
                'errors': 1,
                'total': 0,
                'success': False,
                'output': str(e),
                'failures': []
            }
    
    def _extract_failures(self, test_data: dict) -> List[Dict]:
        """Extract failure details from test report"""
        failures = []
        for test in test_data.get('tests', []):
            if test.get('outcome') in ['failed', 'error']:
                failures.append({
                    'test': test.get('nodeid', ''),
                    'message': test.get('call', {}).get('longrepr', ''),
                    'duration': test.get('call', {}).get('duration', 0)
                })
        return failures
    
    def _parse_pytest_output(self, output: str, return_code: int) -> Dict:
        """Parse pytest output when JSON report is not available"""
        lines = output.split('\n')
        
        passed = failed = errors = 0
        for line in lines:
            if 'passed' in line.lower():
                import re
                match = re.search(r'(\d+)\s+passed', line)
                if match:
                    passed = int(match.group(1))
            if 'failed' in line.lower():
                import re
                match = re.search(r'(\d+)\s+failed', line)
                if match:
                    failed = int(match.group(1))
            if 'error' in line.lower():
                import re
                match = re.search(r'(\d+)\s+error', line)
                if match:
                    errors = int(match.group(1))
        
        return {
            'passed': passed,
            'failed': failed,
            'errors': errors,
            'total': passed + failed + errors,
            'success': return_code == 0,
            'output': output,
            'failures': []
        }
    
    def check_syntax(self, file_path: str) -> Dict:
        """Check Python syntax without running"""
        try:
            with open(file_path, 'r') as f:
                code = f.read()
            
            compile(code, file_path, 'exec')
            return {
                'valid': True,
                'error': None
            }
        except SyntaxError as e:
            return {
                'valid': False,
                'error': f"Line {e.lineno}: {e.msg}"
            }
        except Exception as e:
            return {
                'valid': False,
                'error': str(e)
            }
    
    def validate_change(self, file_path: str, run_tests: bool = True) -> Dict:
        """Validate a code change"""
        # First check syntax
        syntax_result = self.check_syntax(file_path)
        if not syntax_result['valid']:
            return {
                'valid': False,
                'reason': 'syntax_error',
                'details': syntax_result['error'],
                'tests': None
            }
        
        # Run tests if requested
        if run_tests:
            test_results = self.run_tests()
            return {
                'valid': test_results['success'],
                'reason': 'tests_failed' if not test_results['success'] else 'success',
                'details': test_results,
                'tests': test_results
            }
        
        return {
            'valid': True,
            'reason': 'syntax_valid',
            'details': None,
            'tests': None
        }
