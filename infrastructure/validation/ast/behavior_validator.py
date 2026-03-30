"""
Behavior Validator - Detect undeclared behavioral changes
"""
import ast
from typing import Dict, Optional, Set
from dataclasses import dataclass

@dataclass
class BehaviorContract:
    """Expected behavior contract for a method"""
    method_name: str
    parameters: list
    return_type: Optional[str]
    exceptions: Set[str]
    is_async: bool

@dataclass
class BehaviorDrift:
    """Detected behavioral drift"""
    has_drift: bool
    changes: list
    severity: str  # 'minor', 'major', 'breaking'

class BehaviorValidator:
    """Validate behavioral changes against declared contracts"""
    
    def extract_contract(self, code: str, method_name: str) -> Optional[BehaviorContract]:
        """Extract behavioral contract from method"""
        try:
            tree = ast.parse(code)
            method = self._find_method(tree, method_name)
            
            if not method:
                return None
            
            return BehaviorContract(
                method_name=method_name,
                parameters=self._get_parameters(method),
                return_type=self._get_return_annotation(method),
                exceptions=self._get_raised_exceptions(method),
                is_async=isinstance(method, ast.AsyncFunctionDef)
            )
        except:
            return None
    
    def validate_change(self, old_code: str, new_code: str, method_name: str, 
                       declared_changes: Optional[Dict] = None) -> BehaviorDrift:
        """Validate behavioral changes"""
        old_contract = self.extract_contract(old_code, method_name)
        new_contract = self.extract_contract(new_code, method_name)
        
        if not old_contract or not new_contract:
            return BehaviorDrift(False, [], 'minor')
        
        changes = []
        severity = 'minor'
        
        # Check parameter changes
        if old_contract.parameters != new_contract.parameters:
            param_change = self._analyze_parameter_change(
                old_contract.parameters, 
                new_contract.parameters
            )
            changes.append(param_change['description'])
            if param_change['breaking']:
                severity = 'breaking'
        
        # Check default value changes
        old_defaults = self._get_default_values(old_code, method_name)
        new_defaults = self._get_default_values(new_code, method_name)
        if old_defaults != new_defaults:
            changes.append(f"Default values changed: {old_defaults} → {new_defaults}")
            severity = 'major' if severity != 'breaking' else severity
        
        # Check return type changes
        if old_contract.return_type != new_contract.return_type:
            changes.append(f"Return type: {old_contract.return_type} → {new_contract.return_type}")
            severity = 'major' if severity != 'breaking' else severity
        
        # Check exception changes
        new_exceptions = new_contract.exceptions - old_contract.exceptions
        removed_exceptions = old_contract.exceptions - new_contract.exceptions
        
        if new_exceptions:
            changes.append(f"New exceptions: {', '.join(new_exceptions)}")
            severity = 'major' if severity != 'breaking' else severity
        
        if removed_exceptions:
            changes.append(f"Removed exceptions: {', '.join(removed_exceptions)}")
            severity = 'breaking'
        
        # Check async/sync change
        if old_contract.is_async != new_contract.is_async:
            changes.append(f"Changed to {'async' if new_contract.is_async else 'sync'}")
            severity = 'breaking'
        
        # Check if changes were declared
        has_undeclared_drift = False
        if changes and declared_changes:
            # Verify all changes were declared
            for change in changes:
                if not self._is_declared(change, declared_changes):
                    has_undeclared_drift = True
                    break
        elif changes:
            has_undeclared_drift = True
        
        return BehaviorDrift(
            has_drift=has_undeclared_drift,
            changes=changes,
            severity=severity
        )
    
    def _find_method(self, tree: ast.Module, method_name: str) -> Optional[ast.FunctionDef]:
        """Find method in AST"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == method_name:
                    return node
        return None
    
    def _get_parameters(self, method: ast.FunctionDef) -> list:
        """Extract parameter names"""
        params = []
        for arg in method.args.args:
            if arg.arg != 'self':
                params.append(arg.arg)
        return params
    
    def _get_return_annotation(self, method: ast.FunctionDef) -> Optional[str]:
        """Extract return type annotation"""
        if method.returns:
            return ast.unparse(method.returns)
        return None
    
    def _get_raised_exceptions(self, method: ast.FunctionDef) -> Set[str]:
        """Extract raised exception types"""
        exceptions = set()
        for node in ast.walk(method):
            if isinstance(node, ast.Raise) and node.exc:
                if isinstance(node.exc, ast.Call):
                    if isinstance(node.exc.func, ast.Name):
                        exceptions.add(node.exc.func.id)
                elif isinstance(node.exc, ast.Name):
                    exceptions.add(node.exc.id)
        return exceptions
    
    def _analyze_parameter_change(self, old_params: list, new_params: list) -> Dict:
        """Analyze parameter changes"""
        added = set(new_params) - set(old_params)
        removed = set(old_params) - set(new_params)
        
        # Removed parameters = breaking change
        if removed:
            return {
                'description': f"Removed parameters: {', '.join(removed)}",
                'breaking': True
            }
        
        # Added parameters = potentially breaking (unless optional)
        if added:
            return {
                'description': f"Added parameters: {', '.join(added)}",
                'breaking': False  # Assume optional unless proven otherwise
            }
        
        # Reordered parameters = breaking
        if old_params != new_params:
            return {
                'description': "Parameter order changed",
                'breaking': True
            }
        
        return {'description': '', 'breaking': False}
    
    def _is_declared(self, change: str, declared_changes: Dict) -> bool:
        """Check if change was declared in plan"""
        declared_text = str(declared_changes).lower()
        change_lower = change.lower()
        
        # Simple keyword matching
        keywords = ['parameter', 'return', 'exception', 'async', 'default']
        for keyword in keywords:
            if keyword in change_lower and keyword in declared_text:
                return True
        
        return False
    
    def _get_default_values(self, code: str, method_name: str) -> Dict:
        """Extract default parameter values"""
        try:
            tree = ast.parse(code)
            method = self._find_method(tree, method_name)
            
            if not method:
                return {}
            
            defaults = {}
            args = method.args
            
            # Match defaults to parameters (defaults align from right)
            if args.defaults:
                num_defaults = len(args.defaults)
                num_args = len(args.args)
                
                for i, default in enumerate(args.defaults):
                    arg_index = num_args - num_defaults + i
                    if arg_index < len(args.args):
                        param_name = args.args[arg_index].arg
                        if param_name != 'self':
                            defaults[param_name] = ast.unparse(default)
            
            return defaults
        except:
            return {}
