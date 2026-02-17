import json
import re
from typing import Dict, List, Optional
from dataclasses import dataclass
from uuid import uuid4

@dataclass
class PlanStep:
    step_id: str
    tool: str
    operation: str
    parameters: Dict
    reasoning: str

@dataclass
class ExecutionPlan:
    plan_id: str
    analysis: str
    steps: List[PlanStep]
    confidence: float
    raw_response: str

class PlanParser:
    def __init__(self):
        self.json_pattern = re.compile(r'\{.*\}', re.DOTALL)
    
    def parse_llm_response(self, llm_response: str) -> Optional[ExecutionPlan]:
        """Parse LLM response into structured execution plan"""
        
        # Extract JSON from response
        json_match = self.json_pattern.search(llm_response)
        if not json_match:
            return None
        
        try:
            plan_data = json.loads(json_match.group())
            
            # Validate required fields
            if not all(key in plan_data for key in ["analysis", "steps"]):
                return None
            
            # Parse steps
            steps = []
            for i, step_data in enumerate(plan_data["steps"]):
                if not all(key in step_data for key in ["tool", "operation", "parameters"]):
                    continue
                
                step = PlanStep(
                    step_id=f"step_{i+1}",
                    tool=step_data["tool"],
                    operation=step_data["operation"],
                    parameters=step_data["parameters"],
                    reasoning=step_data.get("reasoning", "")
                )
                steps.append(step)
            
            return ExecutionPlan(
                plan_id=str(uuid4()),
                analysis=plan_data["analysis"],
                steps=steps,
                confidence=plan_data.get("confidence", 0.7),
                raw_response=llm_response
            )
            
        except json.JSONDecodeError:
            return None
    
    def validate_plan(self, plan: ExecutionPlan, available_tools: List[str]) -> bool:
        """Validate plan against available tools"""
        
        # Check if all tools exist
        for step in plan.steps:
            if step.tool not in available_tools:
                return False
        
        # Basic parameter validation
        for step in plan.steps:
            if not isinstance(step.parameters, dict):
                return False
        
        return True