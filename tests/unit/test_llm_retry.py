"""
Test LLM retry loop with malformed outputs
"""
import pytest
from unittest.mock import Mock, patch
from planner.llm_client import LLMClient

class TestLLMRetryLoop:
    
    def test_valid_json_first_attempt(self):
        """Test successful parse on first attempt"""
        client = LLMClient(max_retries=3)
        
        valid_response = """{
            "plan_id": "plan_001",
            "analysis": "User wants to list files in current directory",
            "steps": [{
                "step_id": "step_1",
                "tool": "filesystem_tool",
                "operation": "list_directory",
                "parameters": {"path": "."},
                "reasoning": "List all files in current directory"
            }],
            "confidence": 0.95,
            "estimated_duration": 2
        }"""
        
        with patch.object(client, '_call_llm', return_value=valid_response):
            success, plan, error = client.generate_plan("list files")
            
            assert success is True
            assert plan is not None
            assert plan.plan_id == "plan_001"
            assert error is None
    
    def test_json_in_code_fence(self):
        """Test extraction from markdown code fence"""
        client = LLMClient(max_retries=3)
        
        fenced_response = """Here's the plan:
```json
{
    "plan_id": "plan_002",
    "analysis": "User wants to create a test file",
    "steps": [{
        "step_id": "step_1",
        "tool": "filesystem_tool",
        "operation": "write_file",
        "parameters": {"path": "./test.txt", "content": "hello"},
        "reasoning": "Create test file with hello content"
    }],
    "confidence": 0.9,
    "estimated_duration": 1
}
```
Done!"""
        
        with patch.object(client, '_call_llm', return_value=fenced_response):
            success, plan, error = client.generate_plan("create test file")
            
            assert success is True
            assert plan is not None
            assert plan.plan_id == "plan_002"
    
    def test_invalid_json_retries(self):
        """Test retry loop with invalid JSON"""
        client = LLMClient(max_retries=3)
        
        # First two attempts return invalid JSON
        invalid_responses = [
            "This is not JSON at all",
            "{invalid json syntax}",
            # Third attempt succeeds
            """{
                "plan_id": "plan_003",
                "analysis": "User wants to list files after retries",
                "steps": [{
                    "step_id": "step_1",
                    "tool": "filesystem_tool",
                    "operation": "list_directory",
                    "parameters": {"path": "."},
                    "reasoning": "List files in current directory"
                }],
                "confidence": 0.85,
                "estimated_duration": 2
            }"""
        ]
        
        call_count = 0
        def mock_call(prompt, temperature=0.1):
            nonlocal call_count
            response = invalid_responses[call_count]
            call_count += 1
            return response
        
        with patch.object(client, '_call_llm', side_effect=mock_call):
            success, plan, error = client.generate_plan("list files")
            
            assert success is True
            assert plan is not None
            assert len(client.validation_errors) == 2  # Two failed attempts logged
    
    def test_schema_validation_failure(self):
        """Test Pydantic validation failure and retry"""
        client = LLMClient(max_retries=3)
        
        # Missing required field
        invalid_schema = """{
            "plan_id": "plan_004",
            "steps": [{
                "step_id": "step_1",
                "tool": "filesystem_tool",
                "operation": "list_directory",
                "parameters": {"path": "."},
                "reasoning": "List files"
            }],
            "confidence": 0.9
        }"""
        
        # Valid response after retry
        valid_response = """{
            "plan_id": "plan_004",
            "analysis": "User wants to list files with proper schema",
            "steps": [{
                "step_id": "step_1",
                "tool": "filesystem_tool",
                "operation": "list_directory",
                "parameters": {"path": "."},
                "reasoning": "List all files in current directory"
            }],
            "confidence": 0.9,
            "estimated_duration": 2
        }"""
        
        responses = [invalid_schema, valid_response]
        call_count = 0
        
        def mock_call(prompt, temperature=0.1):
            nonlocal call_count
            response = responses[call_count]
            call_count += 1
            return response
        
        with patch.object(client, '_call_llm', side_effect=mock_call):
            success, plan, error = client.generate_plan("list files")
            
            assert success is True
            assert plan is not None
            assert "analysis" in client.validation_errors[0]  # Error mentions missing field
    
    def test_max_retries_exhausted(self):
        """Test failure after max retries"""
        client = LLMClient(max_retries=3)
        
        with patch.object(client, '_call_llm', return_value="invalid json always"):
            success, plan, error = client.generate_plan("list files")
            
            assert success is False
            assert plan is None
            assert error is not None
            assert "3 attempts" in error
            assert len(client.validation_errors) == 3
    
    def test_error_feedback_in_prompt(self):
        """Test that errors are fed back into prompt"""
        client = LLMClient(max_retries=3)
        
        prompts_received = []
        
        def mock_call(prompt, temperature=0.1):
            prompts_received.append(prompt)
            if len(prompts_received) == 1:
                return "invalid"
            else:
                return """{
                    "plan_id": "plan_005",
                    "analysis": "User wants to list files after error feedback",
                    "steps": [{
                        "step_id": "step_1",
                        "tool": "filesystem_tool",
                        "operation": "list_directory",
                        "parameters": {"path": "."},
                        "reasoning": "List files in current directory"
                    }],
                    "confidence": 0.9,
                    "estimated_duration": 2
                }"""
        
        with patch.object(client, '_call_llm', side_effect=mock_call):
            success, plan, error = client.generate_plan("list files")
            
            assert success is True
            assert len(prompts_received) == 2
            # Second prompt should contain error feedback
            assert "ERROR" in prompts_received[1] or "VALIDATION" in prompts_received[1]
