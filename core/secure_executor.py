import time
from typing import List, Dict, Optional
from dataclasses import dataclass
from core.plan_validator import PlanValidator, PlanValidationResult
from core.session_permissions import PermissionGate
from tools.capability_registry import CapabilityRegistry

@dataclass
class SecureExecutionResult:
    success: bool
    completed_steps: int
    total_steps: int
    validation_result: PlanValidationResult
    step_results: List[Dict]
    execution_time: float
    security_violations: List[str]

class SecureExecutor:
    """Secure execution engine with multi-layer safety validation."""
    
    def __init__(self, capability_registry: CapabilityRegistry):
        self.registry = capability_registry
        self.validator = PlanValidator()
        self.permission_gate = PermissionGate()
        self.security_violations = []
    
    def execute_plan_secure(self, plan) -> SecureExecutionResult:
        """Execute plan with full security validation."""
        
        start_time = time.time()
        self.security_violations = []
        
        # Phase 1: Plan validation
        validation_result = self.validator.validate_plan(plan)
        if not validation_result.is_approved:
            return SecureExecutionResult(
                success=False,
                completed_steps=0,
                total_steps=len(plan.steps),
                validation_result=validation_result,
                step_results=[],
                execution_time=time.time() - start_time,
                security_violations=validation_result.reasons
            )
        
        # Phase 2: Execute validated steps
        step_results = []
        completed_steps = 0
        
        for i, step in enumerate(plan.steps):
            # Real-time permission check
            perm_result = self.permission_gate.check_permission(
                step.tool, step.operation, step.parameters
            )
            
            if not perm_result.is_valid:
                self.security_violations.append(f"Step {i+1}: {perm_result.reason}")
                break
            
            # Execute step
            step_result = self._execute_step_secure(step)
            step_results.append(step_result)
            
            if step_result["success"]:
                completed_steps += 1
                # Record successful operation
                self.permission_gate.record_operation(
                    step.tool, step.operation, True
                )
            else:
                break
        
        execution_time = time.time() - start_time
        success = completed_steps == len(plan.steps)
        
        return SecureExecutionResult(
            success=success,
            completed_steps=completed_steps,
            total_steps=len(plan.steps),
            validation_result=validation_result,
            step_results=step_results,
            execution_time=execution_time,
            security_violations=self.security_violations
        )
    
    def _execute_step_secure(self, step) -> Dict:
        """Execute single step with security monitoring."""
        
        step_start = time.time()
        
        try:
            # Get tool with robust lookup
            tool = self.registry.get_tool_by_name(step.tool)
            if not tool:
                # Try matching by class name
                for t in self.registry.tools:
                    class_name = t.__class__.__name__
                    # Match: FilesystemTool -> filesystem, filesystem_tool
                    if (class_name.lower().replace('tool', '') == step.tool.lower().replace('_tool', '').replace('_', '') or
                        class_name.lower() == step.tool.lower() or
                        step.tool.lower() in class_name.lower()):
                        tool = t
                        break
                
            if not tool:
                return {
                    "success": False,
                    "error": f"Tool '{step.tool}' not found",
                    "execution_time": time.time() - step_start
                }
            
            # Execute with monitoring
            result = tool.execute(step.operation, step.parameters)
            
            return {
                "success": result.status.value == "success" if hasattr(result, 'status') else result.success,
                "data": result.data if hasattr(result, 'data') else None,
                "error": result.error_message if hasattr(result, 'error_message') and not (result.status.value == "success" if hasattr(result, 'status') else result.success) else None,
                "execution_time": time.time() - step_start
            }
            
        except Exception as e:
            self.security_violations.append(f"Execution error: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "execution_time": time.time() - step_start
            }