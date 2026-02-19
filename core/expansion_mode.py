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
    
    def create_experimental_tool(self, tool_name: str, template: str) -> tuple[bool, str]:
        """Create new tool in experimental namespace"""
        if not self.enabled:
            return False, "Expansion mode not enabled"
        
        exp_path = Path(self.experimental_dir) / f"{tool_name}.py"
        if exp_path.exists():
            return False, "Experimental tool already exists"
        
        # Write template
        with open(exp_path, 'w') as f:
            f.write(template)
        
        # Create test file
        test_path = Path("tests/experimental") / f"test_{tool_name}.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        with open(test_path, 'w') as f:
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
    
    def _generate_test_template(self, tool_name: str) -> str:
        """Generate minimal test template"""
        class_name = self._class_name_for_tool(tool_name)
        return f'''"""
Tests for experimental {tool_name}
"""
import pytest
from tools.experimental.{tool_name} import {class_name}

def test_{tool_name}_basic():
    """Basic functionality test"""
    tool = {class_name}()
    assert tool is not None

def test_{tool_name}_capabilities():
    """Test capability registration"""
    tool = {class_name}()
    caps = tool.get_capabilities()
    assert len(caps) > 0
'''

    def _class_name_for_tool(self, tool_name: str) -> str:
        return "".join(part[:1].upper() + part[1:] for part in tool_name.split("_") if part)
