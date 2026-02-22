"""LLM Test Orchestrator - Intelligent tool testing with LLM-generated test cases."""
import json
import time
import logging
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass
from core.correlation_context import CorrelationContext

logger = logging.getLogger(__name__)

@dataclass
class TestCase:
    """Represents a single test case."""
    test_name: str
    description: str
    inputs: Dict[str, Any]
    expected_success: bool
    validation: Dict[str, Any]
    rationale: str

@dataclass
class TestResult:
    """Result of a test execution."""
    test_name: str
    passed: bool
    execution_time_ms: float
    output: Any
    error: Optional[str]
    quality_score: int
    validation_details: Dict[str, Any]
    skipped: bool = False
    skip_reason: Optional[str] = None

@dataclass
class TestSuiteResult:
    """Results of entire test suite."""
    tool_name: str
    capability_name: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    overall_quality_score: int
    test_results: List[TestResult]
    performance_metrics: Dict[str, Any]

class LLMTestOrchestrator:
    """Orchestrates LLM-based test generation and execution."""
    
    def __init__(self, llm_client, registry=None):
        self.llm_client = llm_client
        self.registry = registry
        self.test_library = {}
        
    def generate_test_cases(self, tool_name: str, capability: Dict[str, Any]) -> List[TestCase]:
        """Generate test cases for a tool capability using LLM."""
        
        prompt = self._build_test_generation_prompt(tool_name, capability)
        
        try:
            response = self.llm_client._call_llm(prompt, temperature=0.8, max_tokens=2000, expect_json=True)
            print(f"[TEST GEN] Raw response: {response[:200]}...")
            test_cases_json = self.llm_client._extract_json(response)
            print(f"[TEST GEN] Extracted JSON type: {type(test_cases_json)}")
            
            if not isinstance(test_cases_json, list):
                # LLM wrapped array in object like {"test_cases": [...]}
                if isinstance(test_cases_json, dict) and 'test_cases' in test_cases_json:
                    test_cases_json = test_cases_json['test_cases']
                    print(f"[TEST GEN] Unwrapped test_cases array")
                elif isinstance(test_cases_json, dict):
                    # Single test case returned as object - wrap in array
                    test_cases_json = [test_cases_json]
                    print(f"[TEST GEN] Wrapped single test in array")
                else:
                    print(f"[TEST GEN] Not a list! Type: {type(test_cases_json)}")
                    logger.error(f"LLM returned non-list response for test generation")
                    return self._generate_fallback_tests(capability)
            
            test_cases = []
            for tc in test_cases_json[:10]:  # Max 10 tests per capability
                try:
                    test_cases.append(TestCase(
                        test_name=tc.get('test_name', 'unnamed_test'),
                        description=tc.get('description', ''),
                        inputs=tc.get('inputs', {}),
                        expected_success=tc.get('expected_success', True),
                        validation=tc.get('validation', {}),
                        rationale=tc.get('rationale', '')
                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse test case: {e}")
                    continue
            
            if not test_cases:
                logger.warning("No valid test cases parsed, using fallback")
                return self._generate_fallback_tests(capability)
            
            return test_cases
            
        except Exception as e:
            logger.error(f"Test generation failed: {e}")
            return self._generate_fallback_tests(capability)
    
    def execute_test_suite(self, tool_name: str, capability_name: str, 
                          test_cases: List[TestCase]) -> TestSuiteResult:
        """Execute all test cases for a capability."""
        
        if not self.registry:
            logger.error("No registry available for test execution")
            return self._empty_test_result(tool_name, capability_name)
        
        test_results = []
        performance_data = []
        
        for test_case in test_cases:
            result = self._execute_single_test(tool_name, capability_name, test_case)
            test_results.append(result)
            if result.passed:
                performance_data.append(result.execution_time_ms)
        
        passed = sum(1 for r in test_results if r.passed)
        failed = sum(1 for r in test_results if not r.passed and not r.skipped)
        skipped = sum(1 for r in test_results if r.skipped)
        
        # Calculate overall quality score
        if test_results:
            avg_quality = sum(r.quality_score for r in test_results) / len(test_results)
            pass_rate = (passed / len(test_results)) * 100
            overall_quality = int((avg_quality * 0.7) + (pass_rate * 0.3))
        else:
            overall_quality = 0
        
        # Performance metrics
        perf_metrics = {}
        if performance_data:
            perf_metrics = {
                'avg_execution_time_ms': sum(performance_data) / len(performance_data),
                'min_execution_time_ms': min(performance_data),
                'max_execution_time_ms': max(performance_data)
            }
        
        return TestSuiteResult(
            tool_name=tool_name,
            capability_name=capability_name,
            total_tests=len(test_results),
            passed_tests=passed,
            failed_tests=failed,
            overall_quality_score=overall_quality,
            test_results=test_results,
            performance_metrics=perf_metrics
        )
    
    def _execute_single_test(self, tool_name: str, capability_name: str, 
                            test_case: TestCase) -> TestResult:
        """Execute a single test case."""
        
        start_time = time.time()
        
        # Check for skip conditions
        skip_keywords = ['file_path', 'filename', 'path', 'directory']
        requires_file = any(kw in test_case.inputs for kw in skip_keywords)
        
        if requires_file:
            # Check if file/path exists
            for key in skip_keywords:
                if key in test_case.inputs:
                    path_value = test_case.inputs[key]
                    if path_value and not self._resource_exists(path_value):
                        return TestResult(
                            test_name=test_case.test_name,
                            passed=False,
                            execution_time_ms=0,
                            output=None,
                            error=None,
                            quality_score=0,
                            validation_details={'valid': False},
                            skipped=True,
                            skip_reason=f"Required resource not found: {path_value}"
                        )
        
        try:
            # Execute capability
            result = self.registry.execute_capability(capability_name, **test_case.inputs)
            execution_time_ms = (time.time() - start_time) * 1000
            
            # Check if execution succeeded
            success = result and (
                (hasattr(result, 'status') and result.status.value == 'success') or
                (hasattr(result, 'is_success') and result.is_success()) or
                (isinstance(result, dict) and result.get('success', True))
            )
            
            # Extract output data
            output = None
            if hasattr(result, 'data'):
                output = result.data
            elif isinstance(result, dict):
                output = result
            else:
                output = result
            
            # Validate output
            validation_result = self._validate_output(test_case, output, success)
            
            # Calculate quality score
            quality_score = self._calculate_quality_score(
                test_case, success, validation_result, execution_time_ms
            )
            
            passed = (success == test_case.expected_success) and validation_result.get('valid', False)
            
            return TestResult(
                test_name=test_case.test_name,
                passed=passed,
                execution_time_ms=execution_time_ms,
                output=output,
                error=None,
                quality_score=quality_score,
                validation_details=validation_result,
                skipped=False,
                skip_reason=None
            )
            
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            
            return TestResult(
                test_name=test_case.test_name,
                passed=False,
                execution_time_ms=execution_time_ms,
                output=None,
                error=str(e),
                quality_score=0,
                validation_details={'valid': False, 'error': str(e)},
                skipped=False,
                skip_reason=None
            )
    
    def _validate_output(self, test_case: TestCase, output: Any, success: bool) -> Dict[str, Any]:
        """Validate test output against expected criteria."""
        
        validation = test_case.validation
        issues = []
        
        # Structure validation
        if validation.get('check_type') == 'structure':
            expected_fields = validation.get('expected_fields', [])
            if isinstance(output, dict):
                for field in expected_fields:
                    if field not in output:
                        issues.append(f"Missing field: {field}")
            else:
                issues.append("Output is not a dictionary")
        
        # Content validation
        elif validation.get('check_type') == 'content':
            pattern = validation.get('all_logs_contain')
            if pattern and isinstance(output, dict):
                logs = output.get('logs', [])
                if isinstance(logs, list):
                    for log in logs:
                        log_str = json.dumps(log).lower() if isinstance(log, dict) else str(log).lower()
                        if pattern.lower() not in log_str:
                            issues.append(f"Log doesn't contain pattern: {pattern}")
                            break
        
        # Use LLM for complex validation if needed
        if not issues and validation.get('use_llm', False):
            llm_validation = self._llm_validate_output(test_case, output)
            if not llm_validation.get('valid', True):
                issues.extend(llm_validation.get('issues', []))
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'checks_performed': list(validation.keys())
        }
    
    def _llm_validate_output(self, test_case: TestCase, output: Any) -> Dict[str, Any]:
        """Use LLM to validate complex outputs."""
        
        prompt = f"""Validate this tool output quality.

Test: {test_case.test_name}
Description: {test_case.description}
Expected: {test_case.validation.get('description', 'Valid output')}

Actual Output:
{json.dumps(output, indent=2)[:1000]}

Validate:
1. Does output match expected structure?
2. Is data format correct?
3. Any anomalies or issues?

Respond with JSON:
{{
  "valid": true/false,
  "issues": ["list of problems"],
  "quality_score": 0-100
}}"""
        
        try:
            response = self.llm_client._call_llm(prompt, temperature=0.3, max_tokens=500, expect_json=True)
            return self.llm_client._extract_json(response) or {'valid': True, 'issues': []}
        except:
            return {'valid': True, 'issues': []}
    
    def _calculate_quality_score(self, test_case: TestCase, success: bool, 
                                 validation: Dict, execution_time_ms: float) -> int:
        """Calculate quality score for test result."""
        
        score = 0
        
        # Success match (40 points)
        if success == test_case.expected_success:
            score += 40
        
        # Validation passed (40 points)
        if validation.get('valid', False):
            score += 40
        
        # Performance (20 points)
        if execution_time_ms < 1000:
            score += 20
        elif execution_time_ms < 3000:
            score += 10
        elif execution_time_ms < 5000:
            score += 5
        
        return min(score, 100)
    
    def _resource_exists(self, path: str) -> bool:
        """Check if a file or resource exists."""
        try:
            from pathlib import Path
            return Path(path).exists()
        except:
            return False
    
    def _build_test_generation_prompt(self, tool_name: str, capability: Dict) -> str:
        """Build prompt for LLM test generation."""
        
        params_desc = []
        for param in capability.get('parameters', []):
            req = "required" if param.get('required') else "optional"
            params_desc.append(f"- {param['name']} ({param.get('type', 'any')}, {req}): {param.get('description', '')}")
        
        return f"""Generate realistic test cases simulating real user requests.

Tool: {tool_name}
Capability: {capability['name']}
Description: {capability.get('description', '')}
Parameters:
{chr(10).join(params_desc) if params_desc else 'No parameters'}

Think like a real user who wants to:
- See latest entries ("show me last 5 logs")
- Analyze data ("find all failures this week")
- Get insights ("which tools are failing most?")
- Check status ("are there any errors?")

Create 3-5 diverse test cases with realistic user goals.
Use actual data values, varied queries, different time ranges.

Return ONLY a JSON array:
[
  {{
    "test_name": "descriptive_name",
    "description": "what user wants to achieve",
    "inputs": {{"param": "realistic_value"}},
    "expected_success": true,
    "validation": {{"check_type": "any"}},
    "rationale": "why user would do this"
  }}
]

JSON array:"""
    
    def _generate_fallback_tests(self, capability: Dict) -> List[TestCase]:
        """Generate basic fallback tests if LLM fails."""
        
        return [
            TestCase(
                test_name="basic_execution",
                description="Test basic capability execution",
                inputs={},
                expected_success=True,
                validation={'check_type': 'any'},
                rationale="Ensure capability can execute"
            )
        ]
    
    def _empty_test_result(self, tool_name: str, capability_name: str) -> TestSuiteResult:
        """Return empty test result."""
        return TestSuiteResult(
            tool_name=tool_name,
            capability_name=capability_name,
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            overall_quality_score=0,
            test_results=[],
            performance_metrics={}
        )
