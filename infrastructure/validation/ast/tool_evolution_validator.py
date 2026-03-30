"""Validator for tool evolution - ensures no breaking changes."""
import ast
from typing import Tuple, Dict, Any, List
from domain.services.architecture_contract import validate_architecture_contract
from infrastructure.validation.enhanced_code_validator import EnhancedCodeValidator
from infrastructure.analysis.cua_code_analyzer import CUACodeAnalyzer, CodeIssue
from infrastructure.external.service_validation import ServicePatternValidator


class EvolutionValidator:
    """Validates evolved tool code."""
    
    def __init__(self):
        self.enhanced_validator = EnhancedCodeValidator()
        self.cua_analyzer = CUACodeAnalyzer()
        self.service_validator = ServicePatternValidator()
    
    def validate(
        self,
        original_code: str,
        improved_code: str,
        proposal: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Validate improved code doesn't break interface."""
        
        # 0. Enhanced validation (truncation, undefined methods, uninitialized attrs)
        # Extract class name for proper validation
        self._last_syntax_error = None
        class_name = self._extract_class_name(improved_code)
        if not class_name:
            syntax_detail = getattr(self, '_last_syntax_error', None)
            if syntax_detail:
                return False, f"Syntax error in generated code: {syntax_detail}"
            return False, "Could not extract class name from improved code (no class definition found)"
        
        is_valid, error = self.enhanced_validator.validate(improved_code, class_name)
        if not is_valid:
            return False, f"Enhanced validation failed: {error}"
        
        # 0.5. CUA architecture validation (NEW)
        tool_spec = proposal.get('tool_spec')  # May be None for some evolutions
        if tool_spec:
            contract_ok, contract_error = validate_architecture_contract(tool_spec)
            if not contract_ok:
                return False, f"Architecture contract failed: {contract_error}"
        cua_issues = self.cua_analyzer.analyze(improved_code, tool_spec)
        
        # Block on CRITICAL and HIGH issues
        critical_issues = [i for i in cua_issues if i.severity in ['CRITICAL', 'HIGH']]
        if critical_issues:
            error_msg = self._format_issues(critical_issues)
            return False, f"CUA validation failed:\n{error_msg}"
        
        # 0.6. Service pattern validation (previously 0% — now wired for evolution)
        skill_definition = proposal.get('skill_definition')
        if skill_definition:
            svc_result = self.service_validator.validate_tool_against_skill(improved_code, skill_definition)
            if not svc_result.valid:
                return False, f"Service validation failed: {'; '.join(svc_result.errors)}"

        # 0.7. Validate skill alignment if execution_context provided
        execution_context = proposal.get('analysis', {}).get('execution_context_data')
        if execution_context:
            skill_error = self._validate_skill_alignment(improved_code, execution_context)
            if skill_error:
                return False, f"Skill alignment failed: {skill_error}"
        
        # 1. Syntax check
        try:
            ast.parse(improved_code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        
        # 2. Extract class names from both
        original_classes = self._extract_class_names(original_code)
        improved_classes = self._extract_class_names(improved_code)
        
        # Class names must match (no renaming)
        if original_classes != improved_classes:
            return False, f"Class names changed: {original_classes} -> {improved_classes}"
        
        # 3. Extract public methods from both
        original_methods = self._extract_public_methods(original_code)
        improved_methods = self._extract_public_methods(improved_code)
        
        # All original public methods must exist (can add new ones)
        missing = original_methods - improved_methods
        if missing:
            return False, f"Public methods removed: {missing}"
        
        # 4. Required tool methods check
        if not self._has_required_methods(improved_code):
            return False, "Missing required methods (get_capabilities or execute)"

        # 5. Duplicate capability name check
        dup_error = self._check_duplicate_capabilities(improved_code)
        if dup_error:
            return False, dup_error
        
        return True, ""
    
    def _check_duplicate_capabilities(self, code: str) -> str:
        """Detect duplicate add_capability calls with the same name.
        Python silently uses the last definition, so duplicates indicate
        the LLM added a new capability without removing the old one.
        """
        try:
            tree = ast.parse(code)
            seen: dict = {}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Attribute) and func.attr == 'add_capability'):
                    continue
                for kw in node.keywords:
                    if kw.arg == 'name' and isinstance(kw.value, ast.Constant):
                        cap_name = kw.value.value
                        if cap_name in seen:
                            return (f"Duplicate capability '{cap_name}' registered twice in "
                                    f"register_capabilities (lines {seen[cap_name]} and "
                                    f"{getattr(node, 'lineno', '?')}). Remove the old registration.")
                        seen[cap_name] = getattr(node, 'lineno', '?')
        except Exception:
            pass
        return ""
    
    def _format_issues(self, issues: List[CodeIssue]) -> str:
        """Format issues for error message"""
        lines = []
        for issue in issues[:5]:  # Show first 5
            line_info = f" (line {issue.line})" if issue.line else ""
            lines.append(f"  [{issue.severity}] {issue.description}{line_info}")
        if len(issues) > 5:
            lines.append(f"  ... and {len(issues) - 5} more issues")
        return "\n".join(lines)
    
    def _extract_class_name(self, code: str) -> str:
        """Extract primary class name from code."""
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    return node.name
            return ""
        except SyntaxError as e:
            self._last_syntax_error = str(e)
            return ""
        except Exception:
            return ""
    
    def _extract_class_names(self, code: str) -> set:
        """Extract class names from code."""
        try:
            tree = ast.parse(code)
            return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        except:
            return set()
    
    def _extract_public_methods(self, code: str) -> set:
        """Extract public method names from code."""
        try:
            tree = ast.parse(code)
            methods = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not node.name.startswith('_'):
                        methods.add(node.name)
            return methods
        except:
            return set()
    
    def _has_required_methods(self, code: str) -> bool:
        """Check for required tool methods."""
        try:
            tree = ast.parse(code)
            methods = set()
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    methods.add(node.name)
            
            # Must have get_capabilities or register_capabilities, and execute
            has_capabilities = "get_capabilities" in methods or "register_capabilities" in methods
            has_execute = "execute" in methods
            
            return has_capabilities and has_execute
        except:
            return False
    
    def _validate_skill_alignment(self, code: str, execution_context: Any) -> str:
        """Validate evolved tool still matches skill requirements."""
        if isinstance(execution_context, dict):
            verification_mode = execution_context.get('verification_mode')
        else:
            verification_mode = getattr(execution_context, 'verification_mode', None)
        
        if not verification_mode:
            return ""
        
        # Only enforce source_backed if the tool's own registered capabilities
        # indicate it is a web/research tool. Avoid blocking summarizers, processors,
        # or other tools that happen to be queued under web_research skill.
        if verification_mode == "source_backed":
            import ast as _ast
            try:
                tree = _ast.parse(code)
                cap_names = []
                for node in _ast.walk(tree):
                    if isinstance(node, _ast.Call):
                        func = node.func
                        if isinstance(func, _ast.Attribute) and func.attr == 'add_capability':
                            for kw in node.keywords:
                                if kw.arg == 'name' and isinstance(kw.value, _ast.Constant):
                                    cap_names.append(kw.value.value.lower())
                web_caps = {'search', 'fetch', 'crawl', 'scrape', 'browse', 'lookup', 'research'}
                is_web_tool = any(any(w in c for w in web_caps) for c in cap_names)
                if not is_web_tool:
                    return ""  # Not a web tool — skip source_backed enforcement
            except Exception:
                return ""  # Parse failure — don't block
            if "sources" not in code.lower() and "source" not in code.lower():
                return "Tool must return 'sources' field for source_backed verification"
        
        elif verification_mode == "side_effect_observed":
            # Only enforce side_effect_observed if the tool's capabilities indicate
            # it actually performs file/shell operations. Storage-only tools
            # (benchmark runners, note tools, snippet libraries) are not file tools
            # and should never be required to return a file path.
            import ast as _ast
            try:
                tree = _ast.parse(code)
                cap_names = []
                for node in _ast.walk(tree):
                    if isinstance(node, _ast.Call):
                        func = node.func
                        if isinstance(func, _ast.Attribute) and func.attr == 'add_capability':
                            for kw in node.keywords:
                                if kw.arg == 'name' and isinstance(kw.value, _ast.Constant):
                                    cap_names.append(kw.value.value.lower())
                file_caps = {'write', 'execute', 'run', 'create_file', 'save_file',
                             'download', 'export', 'generate_file', 'render'}
                is_file_tool = any(any(w in c for w in file_caps) for c in cap_names)
                if not is_file_tool:
                    return ""  # Not a file/shell tool — skip side_effect_observed enforcement
            except Exception:
                return ""  # Parse failure — don't block
            if "file_path" not in code.lower() and "path" not in code.lower():
                return "Tool must return 'file_path' or 'path' for side_effect_observed verification"
        
        return ""
