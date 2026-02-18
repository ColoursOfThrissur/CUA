"""
Strict Plan Schema with JSON validation
Ensures LLM outputs only valid, typed ExecutionPlans
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Dict, Any, Optional, Union
from enum import Enum

# Dynamic tool/operation validation - no hardcoded enums
# Schema validates structure, registry validates tool availability

class PlanStepSchema(BaseModel):
    """Strict schema for execution step"""
    step_id: str = Field(..., description="Unique step identifier", pattern=r"^step_\d+$")
    tool: str = Field(..., description="Tool to use (validated against registry)")
    operation: str = Field(..., description="Operation to perform (validated against registry)")
    parameters: Dict[str, Any] = Field(..., description="Operation parameters")
    reasoning: str = Field(..., description="Why this step is needed", min_length=10, max_length=500)
    depends_on: Optional[List[str]] = Field(default=None, description="Step IDs this depends on")
    
    @field_validator('parameters')
    @classmethod
    def validate_parameters(cls, v, info):
        """Basic parameter validation - detailed validation by registry"""
        if not isinstance(v, dict):
            raise ValueError("parameters must be a dictionary")
        return v

class ExecutionPlanSchema(BaseModel):
    """Strict schema for execution plan"""
    plan_id: str = Field(..., description="Unique plan identifier")
    analysis: str = Field(..., description="Analysis of user request", min_length=20, max_length=1000)
    steps: List[PlanStepSchema] = Field(..., description="Execution steps", min_length=1, max_length=20)
    confidence: float = Field(..., description="Confidence score", ge=0.0, le=1.0)
    estimated_duration: Optional[int] = Field(default=None, description="Estimated seconds", ge=0)
    
    @field_validator('steps')
    @classmethod
    def validate_steps(cls, v):
        """Validate step dependencies"""
        step_ids = {step.step_id for step in v}
        
        for step in v:
            if step.depends_on:
                for dep_id in step.depends_on:
                    if dep_id not in step_ids:
                        raise ValueError(f"Step {step.step_id} depends on non-existent step {dep_id}")
        
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "plan_id": "plan_123",
                "analysis": "User wants to list files and create a summary",
                "steps": [
                    {
                        "step_id": "step_1",
                        "tool": "filesystem_tool",
                        "operation": "list_directory",
                        "parameters": {"path": "."},
                        "reasoning": "List files in current directory to see what exists"
                    },
                    {
                        "step_id": "step_2",
                        "tool": "filesystem_tool",
                        "operation": "write_file",
                        "parameters": {
                            "path": "./output/summary.txt",
                            "content": "File listing summary"
                        },
                        "reasoning": "Create summary file with the listing results",
                        "depends_on": ["step_1"]
                    }
                ],
                "confidence": 0.9,
                "estimated_duration": 5
            }
        }
    )

def validate_plan_json(plan_json: Dict) -> tuple[bool, Optional[ExecutionPlanSchema], Optional[str]]:
    """
    Validate plan JSON against strict schema
    Returns: (is_valid, plan_object, error_message)
    """
    try:
        plan = ExecutionPlanSchema(**plan_json)
        return True, plan, None
    except Exception as e:
        return False, None, str(e)

# JSON Schema for LLM prompt
import json
PLAN_JSON_SCHEMA = json.dumps(ExecutionPlanSchema.model_json_schema(), indent=2)

# Few-shot examples for LLM
FEW_SHOT_EXAMPLES = """
EXAMPLE 1 - Filesystem:
User: "list files in current directory"
Output:
{
  "plan_id": "plan_001",
  "analysis": "User wants to see all files in the current working directory",
  "steps": [
    {
      "step_id": "step_1",
      "tool": "filesystem_tool",
      "operation": "list_directory",
      "parameters": {"path": "."},
      "reasoning": "List all files and folders in current directory"
    }
  ],
  "confidence": 0.95,
  "estimated_duration": 2
}

EXAMPLE 2 - HTTP GET:
User: "fetch data from example.com"
Output:
{
  "plan_id": "plan_002",
  "analysis": "User wants to make HTTP GET request to example.com",
  "steps": [
    {
      "step_id": "step_1",
      "tool": "http_tool",
      "operation": "get",
      "parameters": {"url": "https://example.com"},
      "reasoning": "Fetch data from the specified URL using HTTP GET"
    }
  ],
  "confidence": 0.92,
  "estimated_duration": 3
}

EXAMPLE 3 - HTTP POST with JSON:
User: "POST to api.example.com/users with name: John, age: 30"
Output:
{
  "plan_id": "plan_003",
  "analysis": "User wants to send POST request with JSON data containing user information",
  "steps": [
    {
      "step_id": "step_1",
      "tool": "http_tool",
      "operation": "post",
      "parameters": {
        "url": "https://api.example.com/users",
        "data": {
          "name": "John",
          "age": 30
        }
      },
      "reasoning": "Send POST request with structured JSON body containing user data"
    }
  ],
  "confidence": 0.90,
  "estimated_duration": 4
}
"""

# Prompt template for LLM - will be populated with registry tools
LLM_PROMPT_TEMPLATE = """You are a task planning assistant. Generate a structured execution plan.

OUTPUT FORMAT (strict JSON):
{schema}

AVAILABLE TOOLS:
{tools}

RULES:
1. Use only tools listed above
2. step_id must be: step_1, step_2, etc.
3. reasoning must be 10-500 characters
4. Max 20 steps
5. Output ONLY valid JSON in this exact format

{examples}

USER REQUEST: {user_request}

Generate the execution plan as valid JSON:"""
