from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class WorkflowAutomationTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.description = "Process Automation"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        define_workflow_capability = ToolCapability(
            name="define_workflow",
            description="Operation: define_workflow",
            parameters=[
                Parameter(name="workflow_name", type=ParameterType.STRING, description="Name of the workflow to define", required=True),
                Parameter(name="steps", type=ParameterType.LIST, description="List of steps in the workflow. Each step is a dictionary with 'step_name', 'action', and 'parameters'", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.llm"],
        )
        self.add_capability(define_workflow_capability, self._handle_define_workflow)

        execute_workflow_capability = ToolCapability(
            name="execute_workflow",
            description="Operation: execute_workflow",
            parameters=[
                Parameter(name="workflow_name", type=ParameterType.STRING, description="Name of the workflow to execute", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.llm"],
        )
        self.add_capability(execute_workflow_capability, self._handle_execute_workflow)

        add_approval_gate_capability = ToolCapability(
            name="add_approval_gate",
            description="Operation: add_approval_gate",
            parameters=[
                Parameter(name="workflow_name", type=ParameterType.STRING, description="Name of the workflow to add an approval gate to", required=True),
                Parameter(name="gate_name", type=ParameterType.STRING, description="Name of the approval gate", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.llm"],
        )
        self.add_capability(add_approval_gate_capability, self._handle_add_approval_gate)

        approve_gate_capability = ToolCapability(
            name="approve_gate",
            description="Operation: approve_gate",
            parameters=[
                Parameter(name="workflow_name", type=ParameterType.STRING, description="Name of the workflow containing the gate to approve", required=True),
                Parameter(name="gate_name", type=ParameterType.STRING, description="Name of the approval gate to approve", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.llm"],
        )

        batch_capability = ToolCapability(
            name="batch",
            description="Execute multiple workflows in sequence and return all results.",
            parameters=[
                Parameter(name='workflows', type=ParameterType.LIST, description='List of workflow names to execute in sequence', required=True)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(batch_capability, self._handle_batch)
        self.add_capability(approve_gate_capability, self._handle_approve_gate)

    def _handle_batch(self, **kwargs) -> dict:
        workflows = kwargs.get('workflows')
        if not workflows:
            return {'success': False, 'error': 'Missing required parameter: workflows'}
        if not isinstance(workflows, list):
            workflows = [workflows]
        try:
            results = []
            for workflow_name in workflows:
                result = self._handle_execute_workflow(workflow_name=workflow_name)
                results.append({'workflow': workflow_name, 'result': result})
            return {'success': True, 'results': results}
        except Exception as e:
            self.services.logging.error(f"Batch operation failed: {e}")
            return {'success': False, 'error': str(e)}

    def execute(self, operation: str, **kwargs):
        if operation == "batch":
            return self._handle_batch(**kwargs)

        return self.execute_capability(operation, **kwargs)

    def _handle_define_workflow(self, **kwargs):
        workflow_name = kwargs.get("workflow_name")
        steps = kwargs.get("steps")

        if not workflow_name or not steps:
            return {'success': False, 'error': 'Missing required parameters', 'data': None}

        try:
            # Save the workflow definition to storage
            self.services.storage.save(workflow_name, {"steps": steps})
            return {'success': True, 'message': 'Workflow defined successfully', 'data': None}
        except Exception as e:
            return {'success': False, 'error': str(e), 'data': None}

    def _handle_execute_workflow(self, **kwargs):
            workflow_name = kwargs.get("workflow_name")

            if not workflow_name:
                return {'success': False, 'error': 'Missing required parameter: workflow_name', 'data': None}

            try:
                # Retrieve the workflow definition from storage
                workflow_definition = self.services.storage.get(workflow_name)
                if not workflow_definition or not isinstance(workflow_definition, dict):
                    return {'success': False, 'error': 'Invalid workflow definition', 'data': None}

                steps = workflow_definition.get("steps", [])
                for step in steps:
                    step_name = step.get("step_name")
                    action = step.get("action")
                    parameters = step.get("parameters", {})

                    if not step_name or not action:
                        return {'success': False, 'error': f'Missing required fields in step: {step}', 'data': None}

                    # Execute the step based on the action
                    if action == "http_request":
                        method = parameters.get("method", "GET").upper()
                        url = parameters.get("url")
                        data = parameters.get("data")

                        if not url:
                            return {'success': False, 'error': f'Missing URL in HTTP request for step: {step_name}', 'data': None}

                        if method == "POST":
                            response = self.services.http.post(url, data)
                        else:
                            response = self.services.http.get(url)
                        if not response or (isinstance(response, dict) and response.get('error')):
                            self.services.logging.error(f'HTTP request failed for step: {step_name}')
                            return {'success': False, 'error': f'HTTP request failed for step: {step_name}', 'data': None}
                    elif action == "shell_command":
                        command = parameters.get("command")
                        if not command:
                            return {'success': False, 'error': f'Missing command in shell execution for step: {step_name}', 'data': None}

                        result = self.services.shell.execute(command)
                        if result.returncode != 0:
                            self.services.logging.error(f'Shell command failed with return code {result.returncode} for step: {step_name}')
                            return {'success': False, 'error': f'Shell command failed with return code {result.returncode} for step: {step_name}', 'data': None}
                    else:
                        return {'success': False, 'error': f'Unsupported action: {action} for step: {step_name}', 'data': None}

                self.services.logging.info('Workflow executed successfully')
                return {'success': True, 'message': 'Workflow executed successfully', 'data': None}
            except Exception as e:
                self.services.logging.error(f'Exception occurred: {str(e)}')
                return {'success': False, 'error': str(e), 'data': None}

    def _handle_add_approval_gate(self, **kwargs):
        workflow_name = kwargs.get("workflow_name")
        gate_name = kwargs.get("gate_name")

        if not workflow_name or not gate_name:
            return {'success': False, 'error': 'Missing required parameters', 'data': None}

        try:
            # Retrieve the current workflow definition
            workflow_definition = self.services.storage.get(workflow_name)
            if not workflow_definition:
                return {'success': False, 'error': 'Workflow not found', 'data': None}

            steps = workflow_definition.get("steps", [])
            approval_gate_step = {
                "step_name": gate_name,
                "action": "approval",
                "parameters": {}
            }
            steps.append(approval_gate_step)

            # Save the updated workflow definition to storage
            self.services.storage.save(workflow_name, {"steps": steps})
            return {'success': True, 'message': 'Approval gate added successfully', 'data': None}
        except Exception as e:
            return {'success': False, 'error': str(e), 'data': None}

    def _handle_approve_gate(self, **kwargs):
        workflow_name = kwargs.get("workflow_name")
        gate_name = kwargs.get("gate_name")

        if not workflow_name or not gate_name:
            return {'success': False, 'error': 'Missing required parameters', 'data': None}

        try:
            # Retrieve the current workflow definition
            workflow_definition = self.services.storage.get(workflow_name)
            if not workflow_definition:
                return {'success': False, 'error': 'Workflow not found', 'data': None}

            steps = workflow_definition.get("steps", [])
            approval_gate_step = next((step for step in steps if step.get("step_name") == gate_name and step.get("action") == "approval"), None)
            if not approval_gate_step:
                return {'success': False, 'error': 'Approval gate not found', 'data': None}

            # Mark the approval gate as approved
            approval_gate_step["parameters"]["approved"] = True

            # Save the updated workflow definition to storage
            self.services.storage.save(workflow_name, {"steps": steps})
            return {'success': True, 'message': 'Approval gate approved successfully', 'data': None}
        except Exception as e:
            return {'success': False, 'error': str(e), 'data': None}
