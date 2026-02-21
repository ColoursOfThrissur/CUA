"""Test DatabaseQueryTool directly"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from tools.experimental.DatabaseQueryTool import DatabaseQueryTool
from tools.capability_registry import CapabilityRegistry

# Create registry and tool
registry = CapabilityRegistry()
tool = DatabaseQueryTool()
registry.register_tool(tool)

print("=== Registered Capabilities ===")
for cap_name in registry.get_all_capabilities().keys():
    print(f"  - {cap_name}")

print("\n=== Testing find_failure_patterns ===")
result = registry.execute_capability("find_failure_patterns", hours_ago=24, limit=10)
print(f"Status: {result.status}")
print(f"Data: {result.data}")

print("\n=== Testing tool name parsing ===")
test_name = "DatabaseQueryTool_find_failure_patterns"
if "_" in test_name:
    parts = test_name.split("_", 1)
    tool_name = parts[0]
    operation = parts[1] if len(parts) > 1 else test_name
    print(f"Full name: {test_name}")
    print(f"Tool: {tool_name}")
    print(f"Operation: {operation}")
