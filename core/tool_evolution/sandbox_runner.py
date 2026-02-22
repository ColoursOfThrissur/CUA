"""Sandbox runner for tool evolution - matches creation pattern."""
import tempfile
import subprocess
import re
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class EvolutionSandboxRunner:
    """Runs evolved tool in sandbox to test it."""
    
    def __init__(self, expansion_mode):
        self.expansion_mode = expansion_mode
    
    def test_improved_tool(
        self,
        tool_name: str,
        improved_code: str,
        original_path: str
    ) -> tuple[bool, str]:
        """Test improved tool in isolated environment. Returns (success, output)."""
        
        output_lines = []
        
        # Extract class name from code
        class_name = self._extract_class_name(improved_code)
        if not class_name:
            logger.error("Could not extract class name from improved code")
            return False, "Could not extract class name"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Write improved code to temp file
            temp_tool_file = tmpdir_path / f"{tool_name}.py"
            temp_tool_file.write_text(improved_code)
            
            # 1. Import test
            success, msg = self._test_import(temp_tool_file)
            output_lines.append(f"Import test: {msg}")
            if not success:
                logger.error("Import test failed")
                return False, "\n".join(output_lines)
            
            # 2. Instantiation test
            success, msg = self._test_instantiation(temp_tool_file, tool_name, class_name)
            output_lines.append(f"Instantiation test: {msg}")
            if not success:
                logger.error("Instantiation test failed")
                return False, "\n".join(output_lines)
            
            # 3. Basic execution test
            success, msg = self._test_basic_execution(temp_tool_file, tool_name, class_name)
            output_lines.append(f"Execution test: {msg}")
            if not success:
                logger.error("Basic execution test failed")
                return False, "\n".join(output_lines)
            
            logger.info(f"Sandbox tests passed for {tool_name}")
            return True, "\n".join(output_lines)
    
    def _extract_class_name(self, code: str) -> Optional[str]:
        """Extract class name from code."""
        match = re.search(r'class\s+(\w+)', code)
        return match.group(1) if match else None
    
    def _test_import(self, tool_file: Path) -> tuple[bool, str]:
        """Test if tool can be imported. Returns (success, message)."""
        test_code = f"""
import sys
sys.path.insert(0, r'{tool_file.parent}')
try:
    import {tool_file.stem}
    print('IMPORT_OK')
except Exception as e:
    print(f'IMPORT_FAIL: {{e}}')
"""
        
        result = subprocess.run(
            ["python", "-c", test_code],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        success = "IMPORT_OK" in result.stdout
        msg = result.stdout.strip() if success else f"{result.stdout} {result.stderr}"
        if not success:
            logger.error(f"Import failed: {msg}")
        return success, msg
    
    def _test_instantiation(self, tool_file: Path, tool_name: str, class_name: str) -> tuple[bool, str]:
        """Test if tool can be instantiated. Returns (success, message)."""
        test_code = f"""
import sys
sys.path.insert(0, r'{tool_file.parent}')
try:
    from {tool_file.stem} import {class_name}
    tool = {class_name}()
    print('INSTANTIATE_OK')
except Exception as e:
    print(f'INSTANTIATE_FAIL: {{e}}')
"""
        
        result = subprocess.run(
            ["python", "-c", test_code],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        success = "INSTANTIATE_OK" in result.stdout
        msg = result.stdout.strip() if success else f"{result.stdout} {result.stderr}"
        if not success:
            logger.error(f"Instantiation failed: {msg}")
        return success, msg
    
    def _test_basic_execution(self, tool_file: Path, tool_name: str, class_name: str) -> tuple[bool, str]:
        """Test basic tool execution. Returns (success, message)."""
        test_code = f"""
import sys
sys.path.insert(0, r'{tool_file.parent}')
try:
    from {tool_file.stem} import {class_name}
    tool = {class_name}()
    caps = tool.get_capabilities() if hasattr(tool, 'get_capabilities') else None
    if caps:
        print('EXECUTE_OK')
    else:
        print('EXECUTE_FAIL: No capabilities')
except Exception as e:
    print(f'EXECUTE_FAIL: {{e}}')
"""
        
        result = subprocess.run(
            ["python", "-c", test_code],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        success = "EXECUTE_OK" in result.stdout
        msg = result.stdout.strip() if success else f"{result.stdout} {result.stderr}"
        if not success:
            logger.error(f"Execution failed: {msg}")
        return success, msg
