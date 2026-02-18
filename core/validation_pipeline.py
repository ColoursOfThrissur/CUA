"""Validation pipeline for LLM outputs"""
import json
import re
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class ValidationResult:
    valid: bool
    data: Optional[Dict]
    schema_valid: bool
    semantic_valid: bool
    auto_repaired: bool
    retry_count: int
    errors: list

class ValidationPipeline:
    def __init__(self):
        self.retry_count = 0
    
    def validate(self, llm_response: str, expected_schema: Dict = None) -> ValidationResult:
        """Full validation pipeline: Parse → Schema → Semantic"""
        self.retry_count += 1
        errors = []
        
        # Step 1: JSON Parse
        parsed = self._parse_json(llm_response)
        if not parsed:
            return ValidationResult(False, None, False, False, False, self.retry_count, ["JSON parse failed"])
        
        # Step 2: Schema Validate
        schema_valid = self._validate_schema(parsed, expected_schema) if expected_schema else True
        if not schema_valid:
            errors.append("Schema validation failed")
        
        # Step 3: Semantic Validate
        semantic_valid, semantic_errors = self._validate_semantic(parsed)
        if not semantic_valid:
            errors.extend(semantic_errors)
        
        # Step 4: Auto-repair if possible
        auto_repaired = False
        if errors and self._can_repair(parsed, errors):
            parsed = self._auto_repair(parsed, errors)
            auto_repaired = True
            errors = []
        
        valid = len(errors) == 0
        return ValidationResult(valid, parsed, schema_valid, semantic_valid, auto_repaired, self.retry_count, errors)
    
    def _parse_json(self, response: str) -> Optional[Dict]:
        """Parse JSON with markdown stripping"""
        # Strip markdown fences
        response = re.sub(r'^```(?:json)?\s*\n', '', response, flags=re.MULTILINE)
        response = re.sub(r'\n```\s*$', '', response, flags=re.MULTILINE)
        
        # Hard fail if backticks still present
        if '```' in response:
            return None
        
        try:
            return json.loads(response.strip())
        except:
            # Try extracting JSON object
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except:
                    pass
        return None
    
    def _validate_schema(self, data: Dict, schema: Dict) -> bool:
        """Basic schema validation"""
        if not schema:
            return True
        required = schema.get('required', [])
        return all(field in data for field in required)
    
    def _validate_semantic(self, data: Dict) -> Tuple[bool, list]:
        """Semantic validation - check logical consistency"""
        errors = []
        
        # Check for empty critical fields
        if 'description' in data and not data['description'].strip():
            errors.append("Empty description")
        
        if 'files_changed' in data and not data['files_changed']:
            errors.append("No files specified")
        
        # Check for suspicious patterns
        if 'patch' in data:
            patch = data['patch']
            if patch.count('+++') != patch.count('---'):
                errors.append("Malformed patch: unbalanced diff markers")
        
        return len(errors) == 0, errors
    
    def _can_repair(self, data: Dict, errors: list) -> bool:
        """Check if errors are auto-repairable"""
        repairable = ["Empty description", "No files specified"]
        return any(err in repairable for err in errors)
    
    def _auto_repair(self, data: Dict, errors: list) -> Dict:
        """Auto-repair common issues"""
        if "Empty description" in errors:
            data['description'] = "Auto-generated improvement"
        if "No files specified" in errors and 'files_affected' in data:
            data['files_changed'] = data['files_affected']
        return data
