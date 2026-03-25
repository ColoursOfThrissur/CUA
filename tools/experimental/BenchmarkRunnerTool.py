from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class BenchmarkRunnerTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.description = "computer_automation"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        run_benchmark_suite_capability = ToolCapability(
            name="run_benchmark_suite",
            description="Run all benchmark cases and return results",
            parameters=[
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.shell"],
        )
        self.add_capability(run_benchmark_suite_capability, self._handle_run_benchmark_suite)

        add_benchmark_case_capability = ToolCapability(
            name="add_benchmark_case",
            description="Add a new benchmark case with task description and expected result",
            parameters=[
                Parameter(name="task_description", type=ParameterType.STRING, description="Description of the benchmark task/prompt", required=True),
                Parameter(name="expected_result", type=ParameterType.STRING, description="Expected result for the benchmark case", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.shell"],
        )
        self.add_capability(add_benchmark_case_capability, self._handle_add_benchmark_case)

        remove_benchmark_case_capability = ToolCapability(
            name="remove_benchmark_case",
            description="Remove a benchmark case by ID",
            parameters=[
                Parameter(name="case_id", type=ParameterType.STRING, description="Unique ID of the benchmark case to remove", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.shell"],
        )
        self.add_capability(remove_benchmark_case_capability, self._handle_remove_benchmark_case)
        
        # Add execute capability for compatibility
        execute_capability = ToolCapability(
            name="execute",
            description="Execute a benchmark task (alias for run_benchmark_suite)",
            parameters=[
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.shell"],
        )
        self.add_capability(execute_capability, self._handle_run_benchmark_suite)
        
        # Add aliases for BenchmarkSuiteTool compatibility
        run_suite_capability = ToolCapability(
            name="run_suite",
            description="Run benchmark suite (alias for run_benchmark_suite)",
            parameters=[],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.shell"],
        )
        self.add_capability(run_suite_capability, self._handle_run_benchmark_suite)
        
        run_capability = ToolCapability(
            name="run",
            description="Run benchmark suite (alias for run_benchmark_suite)",
            parameters=[],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.shell"],
        )
        self.add_capability(run_capability, self._handle_run_benchmark_suite)
        
        add_case_capability = ToolCapability(
            name="add_case",
            description="Add benchmark case (alias for add_benchmark_case)",
            parameters=[
                Parameter(name="task_description", type=ParameterType.STRING, description="Description of the benchmark task/prompt", required=True),
                Parameter(name="expected_result", type=ParameterType.STRING, description="Expected result for the benchmark case", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.shell"],
        )

        batch_capability = ToolCapability(
            name="batch",
            description="Add batch processing support to BenchmarkRunnerTool",
            parameters=[
                Parameter(name='suite_ids', type=ParameterType.STRING, description='suite_ids parameter', required=True)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(batch_capability, self._handle_batch)
        self.add_capability(add_case_capability, self._handle_add_benchmark_case)

    def _handle_batch(self, **kwargs) -> dict:
            # Extract parameters
            suite_ids = kwargs.get('suite_ids')

            # Validate required parameters
            if not suite_ids or not isinstance(suite_ids, list):
                return {'error': 'Missing or invalid parameter: suite_ids'}

            results = []
            for suite_id in suite_ids:
                result = self.services.call_tool('BenchmarkRunnerTool', '_handle_run_benchmark_suite', suite_id=suite_id)
                if 'side_effect_observed' not in result or result['side_effect_observed'] != 'expected':
                    return {'success': False, 'error': f"Unexpected side effect for suite {suite_id}"}
                results.append(result)

            return {'success': True, 'results': results}

    def execute(self, operation: str, **kwargs):
        if operation == "batch":
            return self._handle_batch(**kwargs)

        return self.execute_capability(operation, **kwargs)

    def _handle_run_benchmark_suite(self, **kwargs):
        try:
            # Retrieve all benchmark cases from storage
            benchmark_cases = self.services.storage.list()
            
            if not benchmark_cases:
                return {"success": False, "error": "No benchmark cases found", "data": None}

            results = []
            for case in benchmark_cases:
                task_description = case.get("task_description")
                expected_result = case.get("expected_result")

                # Execute the benchmark task using shell
                shell_result = self.services.shell.execute(task_description)
                
                # Extract result string from ToolResult or dict
                if hasattr(shell_result, 'data'):
                    result = str(shell_result.data)
                elif isinstance(shell_result, dict):
                    result = str(shell_result.get('output', shell_result.get('data', '')))
                else:
                    result = str(shell_result)
                
                # Compare the actual result with the expected result
                if result.strip() == expected_result.strip():
                    results.append({"case_id": case["id"], "status": "passed"})
                else:
                    results.append({"case_id": case["id"], "status": "failed", "actual_result": result})

            return {"success": True, "data": results}

        except Exception as e:
            self.services.logging.error(f"Error running benchmark suite: {e}")
            return {"success": False, "error": str(e), "data": None}

    def _handle_add_benchmark_case(self, **kwargs):
        try:
            task_description = kwargs.get("task_description")
            expected_result = kwargs.get("expected_result")

            # Validate required inputs
            if not task_description or not expected_result:
                return {"success": False, "error": "Missing required parameters", "data": None}

            # Generate a unique ID for the benchmark case
            case_id = self.services.ids.uuid()

            # Prepare the benchmark case data
            benchmark_case_data = {
                "id": case_id,
                "task_description": task_description,
                "expected_result": expected_result
            }

            # Save the benchmark case to storage
            self.services.storage.save(case_id, benchmark_case_data)

            return {"success": True, "data": {"case_id": case_id}}

        except Exception as e:
            self.services.logging.error(f"Error adding benchmark case: {e}")
            return {"success": False, "error": str(e), "data": None}

    def _handle_remove_benchmark_case(self, **kwargs):
        try:
            case_id = kwargs.get("case_id")

            # Validate required inputs
            if not case_id:
                return {"success": False, "error": "Missing required parameters", "data": None}

            # Check if the benchmark case exists
            if not self.services.storage.exists(case_id):
                return {"success": False, "error": f"Benchmark case with ID {case_id} does not exist", "data": None}

            # Delete the benchmark case from storage
            self.services.storage.delete(case_id)

            return {"success": True, "data": {"case_id": case_id}}

        except Exception as e:
            self.services.logging.error(f"Error removing benchmark case: {e}")
            return {"success": False, "error": str(e), "data": None}
