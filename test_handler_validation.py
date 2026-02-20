#!/usr/bin/env python3
"""Test handler validation logic"""

# Simulate the update_status operation parameters
params_list = [
    {'name': 'project_name', 'type': 'string', 'required': True},
    {'name': 'task_name', 'type': 'string', 'required': False},
    {'name': 'status', 'type': 'string', 'required': True}
]

# Build required_params list (NEW LOGIC)
required_params = [
    p.get("name") if isinstance(p, dict) else str(p)
    for p in params_list
    if isinstance(p, dict) and p.get("name") and p.get("required", True) == True
]

print(f"Required params: {required_params}")
print(f"Expected: ['project_name', 'status']")

# Test with sandbox params
kwargs = {'project_name': 'Demo name', 'status': 'active'}

# Validation logic (NEW)
missing = [p for p in required_params if p not in kwargs or kwargs[p] in (None, "")]
print(f"\nMissing params: {missing}")
print(f"Expected: []")

if not missing:
    print("\n✓ VALIDATION PASSES")
else:
    print(f"\n✗ VALIDATION FAILS: {missing}")
