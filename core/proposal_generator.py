"""
Proposal Generator - Generates code proposals with validation
"""
from typing import Optional, Dict, Tuple
from pathlib import Path
import ast
import hashlib
import json

class ProposalGenerator:
    def __init__(self, llm_client, system_analyzer, patch_generator, update_orchestrator):
        from core.config_manager import get_config
        self.config = get_config()
        self.llm_client = llm_client
        self.analyzer = system_analyzer
        self.patch_gen = patch_generator
        self.update_orchestrator = update_orchestrator
        self.previous_errors = []  # Track errors for learning
        
        # Create code generator
        from core.orchestrated_code_generator import OrchestratedCodeGenerator
        self.code_generator = OrchestratedCodeGenerator(llm_client, system_analyzer)
        
        # Create step planner
        from core.step_planner import StepPlanner
        self.step_planner = StepPlanner(llm_client)
        
        # Output validator
        from core.output_validator import OutputValidator
        self.output_validator = OutputValidator()
        self._blocked_history_path = Path("data/proposal_block_history.json")
        self._blocked_history = self._load_blocked_history()
    
    def add_error(self, error: str):
        """Add error with size limit"""
        self.previous_errors.append(error)
        max_errors = self.config.improvement.max_error_history
        if len(self.previous_errors) > max_errors:
            self.previous_errors = self.previous_errors[-max_errors:]
    
    def clear_errors(self):
        """Clear error history"""
        self.previous_errors = []
    
    def generate_proposal(self, analysis: Dict) -> Optional[Dict]:
        """Generate proposal with syntax, security, and semantic validation"""
        # CRITICAL: Check if modifying protected interface
        from core.interface_protector import InterfaceProtector
        protector = InterfaceProtector()
        
        target_file = analysis.get('files_affected', [''])[0]
        if protector.is_protected(target_file):
            from core.logging_system import get_logger
            logger = get_logger("proposal_generator")
            logger.error(f"BLOCKED: {target_file} is a protected interface")
            return None
        
        proposal = self._generate_incremental_proposal(analysis)
        if not proposal:
            return None
        
        raw_code = proposal.get('raw_code', '')
        target_file = proposal.get('files_changed', [''])[0]
        
        # Get original code for comparison
        original_code = self.analyzer.get_file_content(target_file)
        
        # CRITICAL: Validate code actually changed
        if original_code and raw_code.strip() == original_code.strip():
            from core.logging_system import get_logger
            logger = get_logger("proposal_generator")
            logger.error("Code did not change - LLM returned original code")
            return None
        
        # Validate Python syntax
        try:
            import ast
            ast.parse(raw_code)
        except SyntaxError as e:
            from core.logging_system import get_logger
            logger = get_logger("proposal_generator")
            logger.error(f"Syntax validation failed: Line {e.lineno}: {e.msg}")
            return None
        
        # PHASE 1B: Critic stage - semantic validation
        from core.code_critic import CodeCritic
        critic = CodeCritic()
        methods = analysis.get('methods_to_modify', [])
        method_name = methods[0] if methods else 'execute'
        
        critic_result = critic.critique(raw_code, original_code, method_name)
        if not critic_result.valid:
            from core.logging_system import get_logger
            logger = get_logger("proposal_generator")
            logger.error(f"Critic rejected: {', '.join(critic_result.issues)}")
            if critic_result.warnings:
                logger.warning(f"Warnings: {', '.join(critic_result.warnings)}")
            return None
        
        # Security validation
        security_error = self._validate_code(raw_code, target_file)
        if security_error:
            from core.logging_system import get_logger
            logger = get_logger("proposal_generator")
            logger.error(f"Security validation failed: {security_error}")
            return None
        
        # PHASE 2C: Behavioral drift detection
        from core.behavior_validator import BehaviorValidator
        behavior_validator = BehaviorValidator()
        drift = behavior_validator.validate_change(original_code, raw_code, method_name)
        
        if drift.has_drift and drift.severity in ['major', 'breaking']:
            from core.logging_system import get_logger
            logger = get_logger("proposal_generator")
            logger.warning(f"Behavioral drift detected ({drift.severity}): {', '.join(drift.changes)}")
            # Don't reject, but flag for approval
            proposal['requires_approval'] = True
            proposal['drift_detected'] = drift.changes
        
        # Add validation metadata
        proposal['validation'] = {
            'syntax_valid': True,
            'security_valid': True,
            'code_changed': True,
            'critic_confidence': critic_result.confidence,
            'behavioral_drift': drift.severity if drift.has_drift else 'none'
        }
        
        return proposal
    
    def _generate_incremental_proposal(self, analysis: Dict) -> Optional[Dict]:
        """
        Generate code proposal using multi-step approach for ALL tasks.
        Steps are broken down and merged using LLM.
        """
        from core.logging_system import get_logger
        from core.incremental_code_builder import IncrementalCodeBuilder
        logger = get_logger("proposal_generator")
        
        files_affected = analysis.get('files_affected', [])
        if not files_affected or not files_affected[0]:
            logger.error("No files_affected in analysis")
            return None
        
        target_file = files_affected[0]
        target_tool = analysis.get('target_tool')
        blocked_signature_prefix = self._blocked_task_key(target_file, analysis.get('suggestion', ''))
        # If this task repeatedly hits blocked validation recently, skip early.
        if self._blocked_history.get(blocked_signature_prefix, 0) >= 3:
            logger.warning(f"Skipping repeatedly blocked task for {target_file}")
            return None
        
        logger.info(f"Generating proposal for {target_file}")
        
        # Step 1: Plan steps (no task type distinction)
        steps, task_type = self.step_planner.plan_steps(analysis)
        logger.info(f"Task type: {task_type}, {len(steps)} steps")
        
        # Get original code
        original_code = self.analyzer.get_file_content(target_file)
        if not original_code:
            logger.error(f"Cannot read {target_file}")
            return None
        
        user_override = analysis['suggestion'] if analysis.get('user_override') else None
        
        # Step 2: Generate code incrementally for ALL tasks
        raw_code = self._generate_modify_incremental(steps, target_file, target_tool, user_override, original_code, logger)
        
        if not raw_code:
            return None
        
        logger.info(f"Code generated ({len(raw_code)} chars)")

        # Fast structural gate before expensive validation/retry loops.
        if not self._is_structurally_valid_python(raw_code):
            logger.error("Generated code failed structural validation before retry stage")
            return None
        
        # Step 3: Validate with retry
        raw_code = self._validate_with_retry(raw_code, target_file, analysis, target_tool, user_override, logger)
        if not raw_code:
            return None
        
        # Step 4: Generate patch with retry
        patch = self._patch_with_retry(raw_code, target_file, analysis, target_tool, user_override, logger)
        if not patch:
            return None
        
        logger.info(f"Proposal generated successfully")
        return {
            "description": analysis['suggestion'],
            "files_changed": [target_file],
            "diff_lines": len(patch.split('\n')),
            "patch": patch,
            "raw_code": raw_code,
            "methods_to_modify": analysis.get('methods_to_modify', [])
        }

    def _is_structurally_valid_python(self, code: str) -> bool:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not node.body:
                    return False
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    return False
        return True

    
    def _validate_code(self, code: str, file_path: str) -> Optional[str]:
        """Validate generated code with security pattern checks"""
        import ast
        
        if not file_path.endswith('.py'):
            return None
        
        # Check for external library imports and add to pending
        import re
        external_imports = re.findall(r'^(?:from|import)\s+(\w+)', code, re.MULTILINE)
        stdlib = {'os', 'sys', 'time', 'json', 'logging', 're', 'subprocess', 'pathlib', 'typing', 'datetime', 'collections', 'itertools', 'functools', 'ast', 'inspect'}
        
        for lib in external_imports:
            if lib not in stdlib and not lib.startswith(('tools', 'core', 'updater', 'planner', 'api')):
                # Add to pending libraries instead of blocking
                try:
                    from core.pending_libraries_manager import PendingLibrariesManager
                    manager = PendingLibrariesManager()
                    manager.add_pending(lib, f"Required by {file_path}", "code_generator")
                except Exception:
                    pass
        
        # CRITICAL: Check for duplicate class definitions
        import re
        class_defs = re.findall(r'^class (\w+)', code, re.MULTILINE)
        if len(class_defs) != len(set(class_defs)):
            duplicates = [c for c in class_defs if class_defs.count(c) > 1]
            return f"BLOCKED: Duplicate class definitions: {', '.join(set(duplicates))}"
        
        # CRITICAL: Check for JSON-wrapped code (Qwen issue)
        if code.strip().startswith('{') and '"modified_method"' in code:
            return "BLOCKED: LLM returned JSON instead of Python code"
        
        # Check for JSON with escaped newlines
        if code.strip().startswith('{') and '\\n' in code:
            return "BLOCKED: LLM returned JSON-escaped code instead of plain Python"
        
        # Protected files from config
        protected_files = self.config.improvement.protected_files
        
        for protected in protected_files:
            if protected in file_path.replace('\\', '/'):
                return f"BLOCKED: {file_path} is protected"
        
        # Syntax validation
        try:
            ast.parse(code)
        except SyntaxError as e:
            return f"Syntax error line {e.lineno}: {e.msg}"
        except Exception as e:
            return f"Parse error: {str(e)}"
        
        # CRITICAL: Check for security anti-patterns
        security_issues = self._check_security_patterns(code, file_path)
        if security_issues:
            return f"BLOCKED: {security_issues}"
        
        # Dangerous patterns
        dangerous = ['eval(', 'exec(', '__import__', 'compile(']
        for pattern in dangerous:
            if pattern in code:
                return f"Dangerous pattern: {pattern}"
        
        # Check for incomplete code
        lines = code.split('\n')
        for i, line in enumerate(lines, 1):
            if 'raise NotImplementedError' in line:
                return f"Line {i}: Incomplete implementation"
            if '# ... existing code ...' in line.lower() or '# ... rest of' in line.lower():
                return f"Line {i}: Placeholder comment"
        
        # Test code in production files (path-based check)
        is_test_file = ('tests/' in file_path.replace('\\', '/') or 
                       file_path.replace('\\', '/').split('/')[-1].startswith('test_'))
        
        if not is_test_file:
            test_indicators = ['import unittest', 'import pytest', 'class Test', 'def test_']
            for indicator in test_indicators:
                if indicator in code:
                    return f"BLOCKED: Test code in production file: {indicator}"
        
        # Pytest style for tests
        if 'tests/' in file_path and 'test_' in file_path:
            if 'import unittest' in code or 'unittest.TestCase' in code:
                return "Use pytest instead of unittest"
        
        return None
    
    def _check_security_patterns(self, code: str, file_path: str) -> Optional[str]:
        """Check for security anti-patterns that should never be allowed"""
        
        # SSRF vulnerability patterns - substring matching in URL validation
        if any(func in code for func in ['_is_allowed_url', 'validate_url', 'check_url']):
            # Check for weak validation patterns
            weak_patterns = [
                ('domain in parsed.netloc', 'Use exact domain matching: parsed.netloc == domain or parsed.netloc.endswith("." + domain)'),
                ('domain in url', 'Use exact domain matching with urlparse'),
                (' in parsed.netloc', 'Substring matching in URL validation is vulnerable to SSRF'),
            ]
            
            for pattern, fix in weak_patterns:
                if pattern in code:
                    return f"SSRF vulnerability: {pattern}. Fix: {fix}"
        
        # SQL injection patterns - AST/context based to avoid false positives.
        if self._has_dynamic_sql_execute(code):
            # Exclude static analyzers and pattern detection tools
            if 'static_analyzer' not in file_path and 'analyzer' not in file_path and '_detect_patterns' not in code and 'detect_issues' not in code:
                return "Potential SQL injection - use parameterized queries"
        
        # Path traversal - exclude analyzers and validators
        if 'open(' in code or 'Path(' in code:
            # Skip validation for analyzer tools and validators
            if 'analyzer' in file_path or 'validator' in file_path or 'static_' in file_path:
                return None
            if '_validate_path' not in code and 'validate' not in file_path:
                # Only warn for tools that handle user input
                if 'tool' in file_path.lower() and 'test_tool' not in file_path:
                    return "File operations without path validation in tool"
        
        return None
    
    def _try_self_correction(self, broken_code: str, error: str, task: str, target_file: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Let LLM fix its own indentation errors"""
        from core.logging_system import get_logger
        logger = get_logger("proposal_generator")
        logger.info("Attempting to fix indentation error...")
        
        # Show LLM its broken code with line numbers
        lines = broken_code.split('\n')
        numbered_code = '\n'.join([f"{i+1:3d}: {line}" for i, line in enumerate(lines)])
        
        prompt = self.llm_client._format_prompt(f"""Fix the indentation error in this code.

TASK: {task}
FILE: {target_file}
ERROR: {error}

Your code with line numbers:
```python
{numbered_code}
```

Rules:
1. Fix ONLY the indentation (use 4 spaces consistently)
2. Do NOT change the logic
3. Do NOT use tabs
4. Output complete corrected code
5. Remove line numbers from output

Fixed code:""", expect_json=False)
        
        response = self.llm_client._call_llm(prompt, temperature=0.1, expect_json=False)
        if not response:
            return False, broken_code, "Self-correction failed: no response"
        
        # Extract fixed code
        fixed_code = None
        if '```python' in response:
            start = response.find('```python') + 9
            end = response.find('```', start)
            if end != -1:
                fixed_code = response[start:end].strip()
        elif '```' in response:
            start = response.find('```') + 3
            end = response.find('```', start)
            if end != -1:
                fixed_code = response[start:end].strip()
        
        if not fixed_code:
            return False, broken_code, "Self-correction failed: no code extracted"
        
        # Remove line numbers if LLM included them
        import re
        lines = fixed_code.split('\n')
        cleaned = []
        for line in lines:
            # Remove leading line numbers like "  1: " or "123: "
            cleaned_line = re.sub(r'^\s*\d+:\s*', '', line)
            cleaned.append(cleaned_line)
        fixed_code = '\n'.join(cleaned)
        
        # Validate fixed code
        try:
            import ast
            ast.parse(fixed_code)
            logger.info("Success - indentation fixed")
            return True, fixed_code, None
        except Exception as e:
            return False, broken_code, f"Self-correction failed: {str(e)}"

    def _generate_add_methods(self, analysis, target_file, target_tool, user_override, logger):
        """Generate code for ADD tasks - single shot with all methods"""
        logger.info("ADD task: Single-shot generation")
        
        methods = analysis.get('methods_to_modify', [])
        task = analysis['suggestion']
        
        # Build comprehensive prompt for adding methods
        original_code = self.analyzer.get_file_content(target_file)
        
        prompt = self.llm_client._format_prompt(f"""Add new methods to this class.

Task: {task}
Methods to add: {', '.join(methods)}

Current complete file:
```python
{original_code}
```

Rules:
1. Output COMPLETE file with ALL existing code + new methods
2. Add methods at end of class before final closing
3. Match existing code style and indentation
4. Include docstrings and error handling
5. No placeholders or TODO

Complete file with new methods:""", expect_json=False)
        
        for attempt in range(3):
            response = self.llm_client._call_llm(prompt, temperature=0.2, max_tokens=4096, expect_json=False)
            if not response:
                logger.warning(f"Attempt {attempt+1}: No response")
                continue
            
            code = self._extract_code_from_response(response)
            if not code:
                logger.warning(f"Attempt {attempt+1}: Could not extract code")
                prompt += "\n\nERROR: Use ```python blocks."
                continue
            
            # Validate all new methods are present
            missing = [m for m in methods if f'def {m}' not in code]
            if missing:
                logger.warning(f"Attempt {attempt+1}: Missing methods: {missing}")
                prompt += f"\n\nERROR: Missing methods: {', '.join(missing)}. Include ALL methods."
                continue
            
            return code
        
        logger.error("ADD task failed after 3 attempts")
        return None
    
    def _generate_modify_incremental(self, steps, target_file, target_tool, user_override, original_code, logger):
        """Generate code with output validation"""
        
        if len(steps) == 1:
            logger.info("Single-shot generation")
            step = steps[0]
            
            success, step_code, error, _ = self.code_generator.generate_code_with_plan(
                step,
                target_file,
                target_tool=target_tool,
                previous_errors=self.previous_errors,
                user_override=None
            )
            
            if success and step_code:
                # Validate output
                valid, msg = self.output_validator.validate_method_code(step_code)
                if not valid:
                    logger.error(f"Output validation failed: {msg}")
                    return None
                logger.info("Code generation completed")
                return step_code
            else:
                logger.error(f"Code generation failed: {error}")
                return None
        
        # Complex task - multi-step with sequential apply-and-verify
        logger.info(f"Multi-step generation: {len(steps)} steps")

        from core.code_integrator import CodeIntegrator
        integrator = CodeIntegrator()
        current_code = original_code

        for i, step in enumerate(steps, 1):
            logger.info(f"Step {i}/{len(steps)}: {step[:60]}")
            
            for attempt in range(2):
                success, step_code, error, _ = self.code_generator.generate_code_with_plan(
                    step,
                    target_file,
                    target_tool=target_tool,
                    previous_errors=self.previous_errors,
                    user_override=None,  # Don't override detailed step descriptions
                    base_code=current_code
                )
                
                if success and step_code:
                    if step_code.strip() == current_code.strip():
                        logger.info(f"Step {i} already applied; no file changes detected")
                        break

                    if not integrator.verify_expected_methods(step_code, []):
                        logger.warning(f"Step {i} attempt {attempt+1} produced unparsable code")
                        if attempt == 1:
                            logger.error(f"Step {i} failed after 2 attempts")
                            return None
                        continue

                    current_code = step_code
                    logger.info(f"Step {i} completed")
                    break
                else:
                    logger.warning(f"Step {i} attempt {attempt+1} failed: {error}")
                    if attempt == 1:
                        logger.error(f"Step {i} failed after 2 attempts")
                        return None

        logger.info(f"Sequential apply completed ({len(current_code)} chars)")
        return current_code
    
    def _validate_with_retry(self, raw_code, target_file, analysis, target_tool, user_override, logger):
        """Validate code with retry and regeneration"""
        for attempt in range(3):
            validation_error = self._validate_code(raw_code, target_file)
            if not validation_error:
                return raw_code
            
            logger.warning(f"Validation attempt {attempt+1}: {validation_error}")
            
            if "BLOCKED:" in validation_error:
                signature = self._blocked_signature(target_file, analysis.get('suggestion', ''), validation_error)
                blocked_count = self._increment_blocked_signature(signature)
                task_key = self._blocked_task_key(target_file, analysis.get('suggestion', ''))
                self._increment_blocked_signature(task_key)
                logger.error(f"Validation blocked (repeat #{blocked_count})")
                logger.error("Validation blocked")
                return None
            
            if "Syntax error" in validation_error and attempt < 2:
                logger.info("Regenerating to fix syntax error")
                success, raw_code, error, _ = self.code_generator.generate_code_with_plan(
                    analysis['suggestion'] + f" (Fix: {validation_error})",
                    target_file,
                    target_tool=target_tool,
                    previous_errors=self.previous_errors + [validation_error],
                    user_override=None  # Use detailed description, not vague user prompt
                )
                if not success:
                    return None
            elif attempt == 2:
                logger.error("Validation failed after 3 attempts")
                return None
        
        return raw_code

    def _blocked_signature(self, file_path: str, suggestion: str, validation_error: str) -> str:
        raw = f"{file_path}|{suggestion.strip().lower()}|{validation_error.strip().lower()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _blocked_task_key(self, file_path: str, suggestion: str) -> str:
        raw = f"{file_path}|{suggestion.strip().lower()}|blocked_any"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _load_blocked_history(self) -> Dict[str, int]:
        if not self._blocked_history_path.exists():
            return {}
        try:
            with open(self._blocked_history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {str(k): int(v) for k, v in data.items()}
        except Exception:
            pass
        return {}

    def _save_blocked_history(self):
        self._blocked_history_path.parent.mkdir(parents=True, exist_ok=True)
        # Keep only most recent signatures to bound file size.
        if len(self._blocked_history) > 1000:
            items = list(self._blocked_history.items())[-1000:]
            self._blocked_history = dict(items)
        with open(self._blocked_history_path, "w", encoding="utf-8") as f:
            json.dump(self._blocked_history, f, indent=2)

    def _increment_blocked_signature(self, signature: str) -> int:
        new_count = int(self._blocked_history.get(signature, 0)) + 1
        self._blocked_history[signature] = new_count
        self._save_blocked_history()
        return new_count

    def _has_dynamic_sql_execute(self, code: str) -> bool:
        """
        Detect dynamic SQL execution patterns with AST analysis.
        This avoids false positives from method names like `_query`.
        """
        try:
            tree = ast.parse(code)
        except Exception:
            return False

        sql_tokens = ("select ", "insert ", "update ", "delete ", "drop ", "create ", "alter ", "where ", " from ")

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr.lower() != "execute":
                continue
            if not node.args:
                continue

            first_arg = node.args[0]
            # f-strings or string concatenation in execute() are suspicious.
            if isinstance(first_arg, ast.JoinedStr):
                return True
            if isinstance(first_arg, ast.BinOp) and isinstance(first_arg.op, ast.Add):
                return True

            # Literal SQL is okay; dynamic format placeholders are not.
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                literal = first_arg.value.lower()
                if any(tok in literal for tok in sql_tokens):
                    continue
            if isinstance(first_arg, ast.Call):
                # e.g. "...{}".format(user_input)
                if isinstance(first_arg.func, ast.Attribute) and first_arg.func.attr == "format":
                    return True
        return False
    
    def _patch_with_retry(self, raw_code, target_file, analysis, target_tool, user_override, logger):
        """Generate patch with retry - distinguish code vs process errors"""
        for attempt in range(3):
            patch = self.patch_gen.parse_llm_changes(f"```python\n{raw_code}\n```", target_file)
            
            if patch:
                logger.info("Patch generated")
                return patch
            
            logger.warning(f"Patch attempt {attempt+1} failed")
            
            # Check if code is incomplete (code error)
            if len(raw_code) < 100 or 'class ' not in raw_code:
                logger.info("Code incomplete, regenerating")
                success, raw_code, error, _ = self.code_generator.generate_code_with_plan(
                    analysis['suggestion'] + " (Generate complete file with class)",
                    target_file,
                    target_tool=target_tool,
                    previous_errors=self.previous_errors + ["Incomplete code"],
                    user_override=None  # Use detailed description, not vague user prompt
                )
                if not success:
                    return None
            else:
                # Patching process error - just retry
                if attempt == 2:
                    logger.error("Patch failed after 3 attempts")
                    return None
        
        return None
    
    def _extract_code_from_response(self, response: str) -> Optional[str]:
        """Extract code from LLM response"""
        if '```python' in response:
            start = response.find('```python') + 9
            end = response.find('```', start)
            if end != -1:
                return response[start:end].strip()
        
        if '```' in response:
            start = response.find('```') + 3
            end = response.find('```', start)
            if end != -1:
                return response[start:end].strip()
        
        return None
