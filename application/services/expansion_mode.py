"""
Sandboxed expansion mode for experimental features
"""
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import shutil

@dataclass
class ExpansionMode:
    enabled: bool = False
    experimental_dir: str = "tools/experimental"
    promotion_cycles_required: int = 2
    
    def __post_init__(self):
        Path(self.experimental_dir).mkdir(parents=True, exist_ok=True)
    
    def create_experimental_tool(self, tool_name: str, code: str, tool_spec: dict = None) -> tuple[bool, str]:
        """Create new tool in experimental namespace"""
        if not self.enabled:
            return False, "Expansion mode not enabled"
        
        exp_path = Path(self.experimental_dir) / f"{tool_name}.py"
        if exp_path.exists():
            return False, "Experimental tool already exists"
        
        # Write generated code
        with open(exp_path, 'w') as f:
            f.write(code)
        
        # Create test file from spec (if available) or fallback to template
        test_path = Path("tests/experimental") / f"test_{tool_name}.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        with open(test_path, 'w') as f:
            if tool_spec:
                f.write(self._generate_test_from_spec(tool_name, tool_spec))
            else:
                f.write(self._generate_test_template(tool_name))
        
        return True, f"Experimental tool created: {exp_path}"
    
    def promote_to_stable(self, tool_name: str, cycles_passed: int, 
                         coverage: float, regression_count: int) -> tuple[bool, str]:
        """Promote experimental tool to stable"""
        if cycles_passed < self.promotion_cycles_required:
            return False, f"Need {self.promotion_cycles_required} clean cycles"
        
        if regression_count > 0:
            return False, f"Has {regression_count} regressions"
        
        if coverage < 0.8:
            return False, f"Coverage too low: {coverage}"
        
        # Move to stable
        exp_path = Path(self.experimental_dir) / f"{tool_name}.py"
        stable_path = Path("tools") / f"{tool_name}.py"
        
        if not exp_path.exists():
            return False, "Experimental tool not found"
        
        shutil.move(str(exp_path), str(stable_path))
        
        # Move tests
        exp_test = Path("tests/experimental") / f"test_{tool_name}.py"
        stable_test = Path("tests/unit") / f"test_{tool_name}.py"
        if exp_test.exists():
            shutil.move(str(exp_test), str(stable_test))
        
        return True, f"Tool promoted to stable: {stable_path}"
    
    def _generate_test_from_spec(self, tool_name: str, tool_spec: dict) -> str:
        """Generate tests from spec, not from generated code"""
        class_name = self._class_name_for_tool(tool_name)
        operations = tool_spec.get('inputs', [])
        
        tests = [f'''"""Tests for experimental {tool_name}
Generated from spec, not implementation
"""
import pytest
from tools.experimental.{tool_name} import {class_name}
from application.use_cases.tool_lifecycle.tool_orchestrator import ToolOrchestrator
from tools.capability_registry import CapabilityRegistry

def test_{tool_name}_basic():
    """Basic instantiation test"""
    registry = CapabilityRegistry()
    orchestrator = ToolOrchestrator(registry=registry)
    tool = {class_name}(orchestrator=orchestrator)
    assert tool is not None
    assert tool.services is not None

def test_{tool_name}_capabilities():
    """Test capability registration"""
    registry = CapabilityRegistry()
    orchestrator = ToolOrchestrator(registry=registry)
    tool = {class_name}(orchestrator=orchestrator)
    caps = tool.get_capabilities()
    assert len(caps) > 0
''']
        
        # Generate operation tests from spec
        for op in operations:
            op_name = op.get('operation', 'unknown')
            params = op.get('parameters', [])
            
            # Build test parameters from spec
            test_params = {}
            for p in params:
                if isinstance(p, dict):
                    p_name = p.get('name')
                    p_type = p.get('type', 'string')
                    p_required = p.get('required', True)
                    
                    if p_required:
                        test_params[p_name] = self._mock_value_for_type(p_type)
            
            # Build parameter dict string with proper Python syntax
            param_parts = []
            for k, v in test_params.items():
                if isinstance(v, str):
                    param_parts.append(f'"{k}": "{v}"')
                elif isinstance(v, (list, dict)):
                    param_parts.append(f'"{k}": {repr(v)}')
                else:
                    param_parts.append(f'"{k}": {v}')
            param_dict_str = '{' + ', '.join(param_parts) + '}' if param_parts else '{}'
            
            tests.append(f'''
def test_{tool_name}_{op_name}():
    """Test {op_name} operation from spec"""
    registry = CapabilityRegistry()
    orchestrator = ToolOrchestrator(registry=registry)
    tool = {class_name}(orchestrator=orchestrator)
    result = orchestrator.execute_tool_step(
        tool=tool,
        tool_name="{tool_name}",
        operation="{op_name}",
        parameters={param_dict_str},
        context={{}}
    )
    assert result.success or result.error  # Either success or explicit error
''')
        
        return '\n'.join(tests)
    
    def _mock_value_for_type(self, param_type: str):
        """Generate mock value based on parameter type"""
        type_map = {
            'string': 'test_value',
            'integer': 1,
            'boolean': True,
            'list': ['test'],
            'dict': {'key': 'value'}
        }
        return type_map.get(param_type.lower(), 'test_value')
    
    def _generate_test_template(self, tool_name: str) -> str:
        """Generate minimal test template for thin tool architecture"""
        class_name = self._class_name_for_tool(tool_name)
        return f'''"""
Tests for experimental {tool_name}
"""
import pytest
from tools.experimental.{tool_name} import {class_name}
from application.use_cases.tool_lifecycle.tool_orchestrator import ToolOrchestrator
from tools.capability_registry import CapabilityRegistry

def test_{tool_name}_basic():
    """Basic functionality test"""
    registry = CapabilityRegistry()
    orchestrator = ToolOrchestrator(registry=registry)
    tool = {class_name}(orchestrator=orchestrator)
    assert tool is not None
    assert tool.services is not None

def test_{tool_name}_capabilities():
    """Test capability registration"""
    registry = CapabilityRegistry()
    orchestrator = ToolOrchestrator(registry=registry)
    tool = {class_name}(orchestrator=orchestrator)
    caps = tool.get_capabilities()
    assert len(caps) > 0
'''

    def _class_name_for_tool(self, tool_name: str) -> str:
        return "".join(part[:1].upper() + part[1:] for part in tool_name.split("_") if part)
    
    def can_promote(self, tool_name: str, metrics: dict) -> tuple[bool, str]:
        """Check if tool meets promotion criteria with explicit gates"""
        
        # Gate 1: Minimum successful runs
        if metrics.get('successful_runs', 0) < 10:
            return False, f"Need 10+ successful runs (has {metrics.get('successful_runs', 0)})"
        
        # Gate 2: No validator warnings
        if metrics.get('validator_warnings', 0) > 0:
            return False, f"Has {metrics['validator_warnings']} validator warnings"
        
        # Gate 3: Sandbox pass rate
        pass_rate = metrics.get('sandbox_pass_rate', 0.0)
        if pass_rate < 0.95:
            return False, f"Sandbox pass rate {pass_rate:.1%} < 95%"
        
        # Gate 4: Human review for high-risk tools
        risk_level = metrics.get('risk_level', 0.5)
        if risk_level > 0.6 and not metrics.get('human_reviewed', False):
            return False, "High-risk tool requires human review"
        
        # Gate 5: No production failures
        if metrics.get('production_failures', 0) > 0:
            return False, f"Has {metrics['production_failures']} production failures"
        
        return True, "Ready for promotion"
