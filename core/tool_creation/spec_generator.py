"""
Tool specification generation with LLM
"""
import logging
import re
from typing import Optional, Any, List

logger = logging.getLogger(__name__)


class SpecGenerator:
    """Generates tool specifications from capability gap descriptions"""
    
    def __init__(self, capability_graph):
        self.capability_graph = capability_graph
    
    def propose_tool_spec(
        self,
        gap_description: str,
        llm_client,
        preferred_tool_name: Optional[str] = None,
    ) -> Optional[dict]:
        """LLM proposes tool specification with fixed fallback logic"""
        prompt = """Propose a tool specification for: {gap_description}

Return JSON with:
- name: tool_name
- domain: capability_domain
- inputs: [{{"operation": "op_name", "parameters": [{{"name": "param", "type": "string", "description": "...", "required": true}}]}}]
- outputs: [list of output types]
- dependencies: [list of tool dependencies]
- risk_level: 0.0-1.0

Example inputs format:
[
  {{"operation": "create_project", "parameters": [{{"name": "project_name", "type": "string", "description": "Project name", "required": true}}]}},
  {{"operation": "list_projects", "parameters": [{{"name": "limit", "type": "integer", "description": "Max results", "required": false, "default": 10}}]}}
]
""".format(gap_description=gap_description)
        
        try:
            response = llm_client._call_llm(prompt, temperature=0.3, expect_json=True)
            if not response:
                logger.warning("LLM returned empty response for tool spec")
                return None
            
            response = llm_client._extract_json(response)
            if not response:
                logger.warning("Failed to extract JSON from LLM response")
                return None
            
            spec = response
            
            # Normalize tool name
            if preferred_tool_name:
                locked_name = self._normalize_tool_name(preferred_tool_name)
                if not locked_name:
                    logger.error(f"Invalid preferred tool name: {preferred_tool_name}")
                    return None
                spec['name'] = locked_name
            else:
                spec['name'] = self._normalize_tool_name(spec.get('name', ''))
                if not spec['name']:
                    logger.error("Failed to normalize tool name from spec")
                    return None
            
            # Normalize inputs with fixed fallback logic
            raw_inputs = spec.get('inputs', [])
            if not isinstance(raw_inputs, list):
                raw_inputs = []
            
            # Calculate confidence BEFORE applying fallback
            confidence = self._calculate_confidence(spec, raw_inputs, gap_description)
            if confidence < 0.5:
                logger.warning(f"Low confidence spec ({confidence:.2f}) - rejecting")
                return None
            
            # Check if inputs are structured (new format with operations)
            if raw_inputs and isinstance(raw_inputs[0], dict) and 'operation' in raw_inputs[0]:
                # Normalize parameters in structured inputs
                inputs = []
                for item in raw_inputs:
                    if not isinstance(item, dict):
                        continue
                    op_name = item.get('operation')
                    if not op_name:
                        continue
                    params = item.get('parameters', [])
                    normalized_params = self._normalize_parameters(params)
                    inputs.append({"operation": op_name, "parameters": normalized_params})
            else:
                # FIXED: Fallback to common CRUD operations instead of empty list
                logger.info("No structured operations in spec, using CRUD fallback")
                inputs = [
                    {"operation": "create", "parameters": []},
                    {"operation": "get", "parameters": [{"name": "id", "type": "string", "description": "Item ID", "required": True}]},
                    {"operation": "list", "parameters": [{"name": "limit", "type": "integer", "description": "Max results", "required": False, "default": 10}]},
                ]
            
            # Normalize other fields
            outputs = self._normalize_to_string_list(spec.get('outputs', []))
            dependencies = self._normalize_to_string_list(spec.get('dependencies', []))
            domain = str(spec.get('domain', 'general'))
            
            # Calculate dynamic risk based on domain and operations
            risk_level = self._calculate_risk(domain, dependencies, inputs)
            
            spec['confidence'] = confidence
            spec['risk_level'] = risk_level
            spec['requires_human_review'] = confidence < 0.7 or risk_level > 0.6
            
            # Create capability node
            from core.capability_graph import CapabilityNode
            input_names = [inp['operation'] for inp in inputs if isinstance(inp, dict) and 'operation' in inp]
            
            # FIXED: Always have at least one input for capability graph
            if not input_names:
                input_names = ['generic_input']
            
            spec['node'] = CapabilityNode(
                tool_name=spec['name'],
                inputs=input_names,
                outputs=outputs,
                domain=domain,
                dependencies=dependencies,
                risk_level=risk_level,
                maturity='experimental'
            )
            spec['inputs'] = inputs
            return spec
            
        except Exception as e:
            logger.error(f"Failed to propose tool spec: {e}", exc_info=True)
            return None
    
    def _normalize_parameters(self, params: List) -> List[dict]:
        """Normalize parameters from various formats to standard dict format"""
        normalized_params = []
        for p in params:
            if isinstance(p, str):
                # Convert string to parameter dict
                normalized_params.append({
                    "name": p,
                    "type": "string",
                    "description": f"Parameter {p}",
                    "required": True
                })
            elif isinstance(p, dict):
                # Ensure dict has required fields
                if 'name' not in p:
                    continue
                normalized_params.append(p)
        return normalized_params
    
    def _normalize_to_string_list(self, value: Any) -> List[str]:
        """Normalize LLM-provided fields into list[str]"""
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        
        result: List[str] = []
        for item in value:
            if isinstance(item, str):
                s = item.strip()
                if s:
                    result.append(s)
                continue
            if isinstance(item, dict):
                for key in ("name", "id", "type", "value"):
                    v = item.get(key)
                    if isinstance(v, str) and v.strip():
                        result.append(v.strip())
                        break
                else:
                    result.append(str(item))
                continue
            result.append(str(item))
        return result
    
    def _normalize_risk_level(self, risk_level: Any) -> float:
        """Normalize risk level to float between 0.0 and 1.0"""
        try:
            risk_level = float(risk_level)
        except Exception:
            risk_level = 0.5
        return max(0.0, min(1.0, risk_level))
    
    def _normalize_tool_name(self, raw_name: str) -> str:
        """Normalize tool name to valid Python identifier"""
        if not raw_name:
            return ""
        cleaned = re.sub(r'[^A-Za-z0-9_]+', '_', str(raw_name)).strip('_')
        if not cleaned:
            return ""
        if cleaned[0].isdigit():
            cleaned = f"tool_{cleaned}"
        return cleaned
    
    def _calculate_confidence(self, spec: dict, raw_inputs: List, gap_description: str) -> float:
        """Calculate confidence score for spec quality"""
        confidence = 1.0
        
        # No operations specified
        if not raw_inputs or len(raw_inputs) == 0:
            confidence -= 0.4
        
        # Missing operation names
        if raw_inputs:
            for inp in raw_inputs:
                if isinstance(inp, dict) and not inp.get('operation'):
                    confidence -= 0.2
                    break
        
        # Vague gap description
        if len(gap_description.split()) < 5:
            confidence -= 0.2
        
        # Missing domain
        if not spec.get('domain') or spec.get('domain') == 'general':
            confidence -= 0.1
        
        return max(0.0, confidence)
    
    def _calculate_risk(self, domain: str, dependencies: List[str], inputs: List[dict]) -> float:
        """Calculate dynamic risk based on domain and operations"""
        risk = 0.2  # Base risk
        
        domain_lower = domain.lower()
        deps_str = ' '.join(dependencies).lower()
        
        # External I/O
        if 'http' in deps_str or 'api' in domain_lower or 'web' in domain_lower:
            risk += 0.3
        
        # AI/LLM calls
        if 'llm' in deps_str or 'ai' in domain_lower:
            risk += 0.2
        
        # Filesystem operations
        if 'filesystem' in domain_lower or 'file' in domain_lower:
            risk += 0.15
        
        # Storage operations
        if 'storage' in domain_lower:
            risk += 0.05
        
        # Dangerous operations
        operations = [inp.get('operation', '') for inp in inputs]
        if any(op in ['delete', 'remove', 'drop'] for op in operations):
            risk += 0.1
        if any(op in ['execute', 'run', 'eval'] for op in operations):
            risk += 0.3
        
        return min(risk, 1.0)
