"""
Tool specification generation with LLM
"""
import logging
import re
from typing import Optional, Any, List

from infrastructure.validation.ast.architecture_validator import (
    enrich_tool_spec_with_skill_context,
    validate_skill_aware_architecture_contract,
)

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
        skill_context: Optional[dict] = None,
    ) -> Optional[dict]:
        """LLM proposes tool specification with fixed fallback logic"""
        # VALIDATION: Filter out invalid capability gaps
        if gap_description.startswith("skill:"):
            logger.warning(f"Rejecting skill routing gap as tool creation target: {gap_description}")
            return None
        
        if skill_context:
            gap_type = skill_context.get("gap_type", "")
            suggested_action = skill_context.get("suggested_action", "")
            
            # Allow skill routing issues — treat as a normal tool creation request
            if gap_type == "no_matching_skill" and skill_context:
                logger.info(f"Resolving skill routing issue with self.services.X patterns: {gap_description}")
                skill_context['required_tools'] = skill_context.get('required_tools', []) + ['routing_service']

            # Reject other invalid gaps
            if gap_type in ["actionable_request_no_tool_call"]:
                logger.warning(f"Rejecting skill routing issue (gap_type={gap_type}) as tool creation target")
                return None
            
            # Reject if suggested action is not tool creation
            if suggested_action and suggested_action != "create_tool":
                logger.warning(f"Rejecting gap with suggested_action={suggested_action} (not create_tool)")
                return None
        
        # Dynamically get valid parameter types from ParameterType enum
        from tools.tool_capability import ParameterType
        valid_types = [pt.value for pt in ParameterType]
        types_list = "\n".join([f"- {t}: {self._get_type_description(t)}" for t in valid_types])
        
        # Dynamically get available services from dependency checker with method signatures
        from infrastructure.analysis.dependency_checker import DependencyChecker
        service_specs = {
            'storage': 'save(id, data), get(id), list(limit=10), update(id, updates), delete(id), exists(id) - Key-value store: each item needs unique ID',
            'llm': 'generate(prompt, temperature=0.3, max_tokens=500)',
            'http': 'get(url), post(url, data), put(url, data), delete(url)',
            'fs': 'read(path), write(path, content), list(path)',
            'json': 'parse(text), stringify(data), query(data, path)',
            'shell': 'execute(command, args=[])',
            'logging': 'info(msg), warning(msg), error(msg), debug(msg)',
            'time': 'now_utc(), now_local(), now_utc_iso(), now_local_iso()',
            'ids': 'generate(prefix=""), uuid() - Use for generating unique IDs',
            'browser': 'open_browser(), navigate(url), get_page_text(), find_element(by, value), take_screenshot(filename), close()'
        }
        
        services_list = "\n".join([
            f"- self.services.{name}: {methods}" 
            for name, methods in service_specs.items() 
            if name in DependencyChecker.AVAILABLE_SERVICES
        ])
        
        skill_guidance = self._build_skill_guidance(skill_context)
        existing_tools_section = self._build_existing_tools_section()
        
        # Build base prompt first
        prompt = f"""Propose a tool specification for: {gap_description}

SKILL CONTEXT:
{skill_guidance}

{existing_tools_section}
Return JSON with:
- name: tool_name
- domain: capability_domain
- inputs: [{{"operation": "op_name", "parameters": [{{"name": "param", "type": "string", "description": "...", "required": true}}]}}]
- outputs: [list of output types]
- artifact_types: [list of typed artifacts this tool returns for planner/UI state]
- dependencies: [list of tool dependencies]
- verification_mode: how the result should be verified
- ui_renderer: preferred renderer key for this tool's output family
- risk_level: 0.0-1.0

VALID PARAMETER TYPES (use ONLY these):
{types_list}

AVAILABLE SERVICES (access via self.services.X):
{services_list}

For dependencies field, list ONLY the services you need from above (e.g., ["self.services.browser", "self.services.storage"])

IMPORTANT - Parameter Requirements:
- If an operation works on CURRENT STATE (e.g., get current page content, close browser), use EMPTY parameters list: "parameters": []
- If an operation needs INPUT (e.g., navigate to URL, find element), specify required parameters
- Be explicit: operations that maintain state should not require repeated inputs

Example inputs format:
[
  {{"operation": "open_and_navigate", "parameters": [{{"name": "url", "type": "string", "description": "URL to navigate", "required": true}}]}},
  {{"operation": "get_page_content", "parameters": []}},
  {{"operation": "close", "parameters": []}}
]
"""
        
        # Enhance prompt with skill constraints if available
        enhanced_prompt = prompt
        if skill_context and skill_context.get("target_skill"):
            try:
                from application.use_cases.tool_lifecycle.skill_aware_creation import enhance_tool_creation_with_skill
                from application.services.skill_registry import SkillRegistry
                
                # Get skill definition for enhancement
                skill_registry = SkillRegistry()
                skill_registry.load_all()
                skill_def = skill_registry.get(skill_context["target_skill"])
                
                if skill_def:
                    enhanced_prompt = enhance_tool_creation_with_skill(
                        prompt, skill_def, gap_description, "spec"
                    )
                    logger.info(f"Enhanced prompt with {skill_def.name} skill constraints")
            except Exception as e:
                logger.warning(f"Failed to enhance prompt with skill constraints: {e}")
                # Continue with original prompt
        
        try:
            response = llm_client._call_llm(enhanced_prompt, temperature=0.3, expect_json=True)
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
            
            # Calculate confidence BEFORE applying fallback (threshold applied in flow.py)
            confidence = self._calculate_confidence(spec, raw_inputs, gap_description)
            if confidence < 0.3:
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
                    {"operation": "create", "parameters": [{"name": "data", "type": "dict", "description": "Data to create", "required": True}]},
                    {"operation": "get", "parameters": [{"name": "id", "type": "string", "description": "Item ID", "required": True}]},
                    {"operation": "list", "parameters": [{"name": "limit", "type": "integer", "description": "Max results", "required": False, "default": 10}]},
                ]
            
            # Normalize other fields
            outputs = self._normalize_to_string_list(spec.get('outputs', []))
            dependencies = self._normalize_to_string_list(spec.get('dependencies', []))
            domain = str(spec.get('domain', 'general'))
            if skill_context:
                target_skill = str(skill_context.get("target_skill") or "").strip()
                target_category = str(skill_context.get("target_category") or "").strip()
                if domain == "general" and target_category:
                    domain = target_category
                if target_skill:
                    spec["target_skill"] = target_skill
                if target_category:
                    spec["target_category"] = target_category
                if skill_context.get("gap_type"):
                    spec["gap_type"] = str(skill_context.get("gap_type"))
                if skill_context.get("suggested_action"):
                    spec["suggested_action"] = str(skill_context.get("suggested_action"))
                if skill_context.get("reasons"):
                    spec["reasons"] = [str(item) for item in skill_context.get("reasons", [])]
                if skill_context.get("example_tasks"):
                    spec["example_tasks"] = [str(item) for item in skill_context.get("example_tasks", [])]
                if skill_context.get("example_errors"):
                    spec["example_errors"] = [str(item) for item in skill_context.get("example_errors", [])]
            spec["outputs"] = outputs
            spec["dependencies"] = dependencies
            spec["domain"] = domain
            
            # Resolve services from dependencies BEFORE architecture contract validation
            service_resolution = self._resolve_services(dependencies)
            spec['available_services'] = service_resolution['available']
            spec['missing_services'] = service_resolution['missing']
            spec['service_methods'] = service_resolution['methods']
            
            spec = enrich_tool_spec_with_skill_context(spec, skill_context)
            contract_ok, contract_error = validate_skill_aware_architecture_contract(spec)
            if not contract_ok:
                logger.warning(f"Architecture contract rejected tool spec: {contract_error}")
                return None
            
            # Calculate dynamic risk based on domain and operations
            risk_level = self._calculate_risk(domain, dependencies, inputs)
            
            spec['confidence'] = confidence
            spec['risk_level'] = risk_level
            spec['requires_human_review'] = confidence < 0.7 or risk_level > 0.6
            
            # Generate implementation sketches for each handler
            # Second focused LLM call — spec prompt is already complex enough
            try:
                handler_sketches = self._generate_handler_sketches(inputs, dependencies, llm_client)
                if handler_sketches:
                    spec['handler_sketches'] = handler_sketches
                    logger.info(f"Generated sketches for {len(handler_sketches)} handlers")
            except Exception as e:
                logger.warning(f"Handler sketch generation skipped: {e}")
                spec['handler_sketches'] = {}
            
            # Create capability node
            from domain.services.capability_graph import CapabilityNode
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
            
            # Remove node before returning (not JSON serializable)
            node = spec.pop('node', None)
            
            return spec
            
        except Exception as e:
            logger.error(f"Failed to propose tool spec: {e}", exc_info=True)
            return None
    
    def _normalize_parameters(self, params: List) -> List[dict]:
        """Normalize parameters from various formats to standard dict format"""
        # Map common LLM-generated types to valid ParameterType values
        type_mapping = {
            'array': 'list',
            'date': 'string',
            'datetime': 'string',
            'timestamp': 'string',
            'number': 'integer',
            'float': 'integer',
            'object': 'dict',
            'json': 'dict',
            'bool': 'boolean',
            'path': 'file_path',
            'filepath': 'file_path',
        }
        
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
                # Normalize type to valid ParameterType
                param_type = p.get('type', 'string').lower()
                p['type'] = type_mapping.get(param_type, param_type)
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

    def _build_existing_tools_section(self) -> str:
        """Build a compact list of already-registered tools so LLM avoids speccing duplicates."""
        try:
            from application.use_cases.tool_lifecycle.tool_registry_manager import ToolRegistryManager
            registry = ToolRegistryManager()
            tools = registry.list_tools() if hasattr(registry, 'list_tools') else []
            if not tools:
                # Fallback: scan tools/ directories
                from pathlib import Path
                names = []
                for d in (Path('tools'), Path('tools/experimental')):
                    if d.exists():
                        names += [p.stem for p in d.glob('*.py') if not p.stem.startswith('_')]
                tools = names
            if not tools:
                return ""
            tool_list = ', '.join(sorted(set(str(t) for t in tools)))
            return f"EXISTING TOOLS (do NOT duplicate these — propose something new):\n{tool_list}\n\n"
        except Exception:
            return ""

    def _build_skill_guidance(self, skill_context: Optional[dict]) -> str:
        """Build enriched skill guidance for tool generation.
        
        PHASE 1.1 ENHANCEMENT: Now includes skill description, trigger examples,
        and workflow instructions to guide LLM toward better tool design.
        """
        if not skill_context:
            return "No skill context provided. Infer the tool purely from the gap description."

        target_skill = skill_context.get("target_skill") or "unspecified"
        target_category = skill_context.get("target_category") or "unspecified"
        
        # Build comprehensive skill guidance
        guidance = []
        guidance.append(f"=== SKILL CONTEXT ===")
        guidance.append(f"Target skill: {target_skill}")
        guidance.append(f"Target category: {target_category}")
        
        # PHASE 1.1 STEP 2: Add skill description
        skill_description = skill_context.get("skill_description")
        if skill_description:
            guidance.append(f"\nSkill Purpose:")
            guidance.append(f"{skill_description}")
        
        # PHASE 1.1 STEP 3: Add trigger examples
        trigger_examples = skill_context.get("trigger_examples", [])
        if trigger_examples:
            guidance.append(f"\nThis skill handles requests like:")
            for example in trigger_examples[:5]:  # Show top 5 examples
                guidance.append(f"  - {example}")
        
        # Preferred tools
        preferred_tools = skill_context.get("preferred_tools", [])
        if preferred_tools:
            guidance.append(f"\nPreferred tools in this skill: {', '.join(preferred_tools)}")
            guidance.append("Consider if this tool should work WITH these tools (inter-tool calls via self.services.call_tool)")
        
        # Required tools
        required_tools = skill_context.get("required_tools", [])
        if required_tools:
            guidance.append(f"\nRequired tools in this skill: {', '.join(required_tools)}")
            guidance.append("This tool may need to call these required tools")
        
        # PHASE 1.1 STEP 5: Add preferred connectors (services)
        preferred_connectors = skill_context.get("preferred_connectors", [])
        if preferred_connectors:
            guidance.append(f"\nPreferred services/connectors: {', '.join(preferred_connectors)}")
            guidance.append("Use these services in your tool implementation when possible")
        
        # Input/Output types
        input_types = skill_context.get("expected_input_types", [])
        output_types = skill_context.get("expected_output_types", [])
        if input_types:
            guidance.append(f"\nExpected input types: {', '.join(input_types)}")
        if output_types:
            guidance.append(f"Expected output types: {', '.join(output_types)}")
            guidance.append("Tool outputs field MUST include these types")
        
        # Verification mode
        verification_mode = skill_context.get("verification_mode")
        if verification_mode:
            guidance.append(f"\nVerification mode: {verification_mode}")
            if verification_mode == "source_backed":
                guidance.append("Tool MUST return sources/citations in output")
            elif verification_mode == "strict":
                guidance.append("Tool MUST validate all outputs strictly")
            elif verification_mode == "side_effect_observed":
                guidance.append("Tool MUST demonstrate observable side effects (files created, data changed, etc.)")
        
        # Risk level
        risk_level = skill_context.get("risk_level")
        if risk_level:
            guidance.append(f"\nSkill risk level: {risk_level}")
            if risk_level == "low":
                guidance.append("Tool should be safe-by-default with minimal external I/O")
            elif risk_level == "medium":
                guidance.append("Tool may access external resources; include appropriate error handling")
            elif risk_level == "high":
                guidance.append("Tool may perform risky operations but needs validation and safety checks")
        
        # UI renderer
        ui_renderer = skill_context.get("ui_renderer")
        if ui_renderer:
            guidance.append(f"\nUI renderer: {ui_renderer}")
        
        # Fallback strategy
        fallback_strategy = skill_context.get("fallback_strategy")
        if fallback_strategy:
            guidance.append(f"Fallback strategy: {fallback_strategy}")
        
        # Skill constraints
        skill_constraints = skill_context.get("skill_constraints", [])
        if skill_constraints:
            guidance.append(f"\nSkill constraints:")
            for constraint in skill_constraints:
                guidance.append(f"- {constraint}")
        
        # PHASE 1.1 STEP 4: Add skill workflow instructions (from SKILL.md)
        workflow_guidance = skill_context.get("workflow_guidance")
        if workflow_guidance:
            guidance.append(f"\n=== WORKFLOW GUIDANCE ===")
            guidance.append(workflow_guidance)
        
        guidance.append("\n=== IMPORTANT REQUIREMENTS ===")
        guidance.append("Tool design must align with ALL skill expectations above.")
        guidance.append("Follow the workflow guidance closely - it encodes proven patterns for this skill domain.")
        
        return "\n".join(guidance)
    
    def _generate_handler_sketches(self, inputs: List[dict], dependencies: List[str], llm_client) -> dict:
        """Generate pseudocode implementation sketches for each handler.

        Separate focused LLM call so the spec prompt stays clean.
        Returns dict of {handler_name: [step1, step2, ...]} or empty dict on failure.
        """
        if not inputs:
            return {}

        # Build service list from dependencies
        from infrastructure.analysis.dependency_checker import DependencyChecker
        service_specs = {
            'storage': 'save(id, data), get(id), list(limit=10), update(id, updates), delete(id), exists(id)',
            'llm': 'generate(prompt, temperature=0.3, max_tokens=500)',
            'http': 'get(url), post(url, data), put(url, data), delete(url)',
            'fs': 'read(path), write(path, content), list(path)',
            'json': 'parse(text), stringify(data), query(data, path)',
            'shell': 'execute(command)',
            'logging': 'info(msg), warning(msg), error(msg)',
            'time': 'now_utc_iso()',
            'ids': 'generate(prefix), uuid()',
        }
        dep_names = [d.replace('self.services.', '').strip() for d in dependencies]
        relevant_services = {
            k: v for k, v in service_specs.items()
            if k in dep_names or k in ('logging', 'ids')
        }
        services_text = '\n'.join(f'- self.services.{k}: {v}' for k, v in relevant_services.items())

        # Build operations summary
        ops_text = ''
        for op in inputs:
            if not isinstance(op, dict):
                continue
            op_name = op.get('operation', '')
            params = op.get('parameters', [])
            param_desc = ', '.join(
                f"{p.get('name')} ({p.get('type','string')}, {'required' if p.get('required') else 'optional'})"
                for p in params if isinstance(p, dict)
            )
            ops_text += f"- _handle_{op_name}({param_desc or 'no params'})\n"

        prompt = f"""For each handler method below, write numbered pseudocode steps (plain English, not Python).
Describe exactly: which services to call, what to validate, what to return.
Keep each step to one sentence. Max 5 steps per handler.

CRITICAL API RULES:
- storage.save(id, data) — ALWAYS two arguments: unique string ID first, then data dict
- storage.get(id) — ONE argument only, no default kwarg
- storage.list(limit=N) — returns a list of all items
- Every return MUST have 'success' key: {{'success': True, 'data': ...}} or {{'success': False, 'error': '...'}}
- For filtering: specify exact field and comparison (e.g. 'keep items where query in item["description"]')

SERVICE RETURN TYPES (critical — do NOT assume wrong types):
- llm.generate() — returns a plain STRING, never a dict. Store it directly: result_str = self.services.llm.generate(prompt)
- storage.get(id) — returns a dict or None
- storage.list(limit) — returns a list of dicts
- http.get/post() — returns a dict with 'status' and 'body' keys
- json.parse() — returns a Python object (dict/list)
- json.stringify() — returns a string

Available services:
{services_text}

Handlers to sketch:
{ops_text}

Return JSON only:
{{
  "_handle_operation_name": [
    "1. Get param_x from kwargs. Return {{'success': False, 'error': 'missing param_x'}} if missing.",
    "2. Call self.services.storage.save(param_x, data_dict).",
    "3. Return {{'success': True, 'data': result}}."
  ]
}}"""

        try:
            raw = llm_client._call_llm(prompt, temperature=0.1, max_tokens=1500, expect_json=True)
            if not raw:
                return {}
            data = llm_client._extract_json(raw)
            if not isinstance(data, dict):
                return {}
            # Normalize: ensure all values are lists of strings
            result = {}
            for handler_name, steps in data.items():
                if isinstance(steps, list):
                    result[handler_name] = [str(s) for s in steps if s]
                elif isinstance(steps, str) and steps:
                    result[handler_name] = [s.strip() for s in steps.splitlines() if s.strip()]
            return result
        except Exception as e:
            logger.warning(f"Handler sketch LLM call failed: {e}")
            return {}

    def _get_type_description(self, type_name: str) -> str:
        """Get human-readable description for parameter type."""
        descriptions = {
            'string': 'Text values',
            'integer': 'Numbers (int or float)',
            'boolean': 'True/False',
            'list': 'Arrays/lists',
            'dict': 'Objects/JSON',
            'file_path': 'File paths'
        }
        return descriptions.get(type_name.lower(), type_name)
    
    def _resolve_services(self, dependencies: List[str]) -> dict:
        """Resolve which services are available vs missing"""
        from infrastructure.analysis.dependency_checker import DependencyChecker
        
        # Service method signatures
        service_specs = {
            'storage': 'save(id, data), get(id), list(limit=10), update(id, updates), delete(id)',
            'llm': 'generate(prompt, temperature=0.3, max_tokens=500)',
            'http': 'get(url), post(url, data), put(url, data), delete(url)',
            'fs': 'read(path), write(path, content), list(path)',
            'json': 'parse(text), stringify(data), query(data, path)',
            'shell': 'execute(command, args=[])',
            'logging': 'info(msg), warning(msg), error(msg), debug(msg)',
            'time': 'now_utc(), now_local(), now_utc_iso(), now_local_iso()',
            'ids': 'generate(prefix=""), uuid()',
            'browser': 'open_browser(), navigate(url), get_page_text(), find_element(by, value), take_screenshot(filename), close()'
        }
        
        available = []
        missing = []
        methods = {}
        
        for dep in dependencies:
            # Extract service name from "self.services.X" format
            service_name = dep.replace('self.services.', '').strip()
            
            if service_name in DependencyChecker.AVAILABLE_SERVICES:
                available.append(service_name)
                methods[service_name] = service_specs.get(service_name, '')
            elif service_name in ['email', 'sms', 'database', 'cache', 'queue', 'auth', 'crypto']:
                # Known patterns that need to be created
                missing.append(service_name)
            else:
                # Unknown service - treat as missing
                missing.append(service_name)
        
        return {
            'available': available,
            'missing': missing,
            'methods': methods
        }
    
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
