"""Test computer use tools capability extraction"""
from tools.capability_extractor import CapabilityExtractor

extractor = CapabilityExtractor()

files = [
    'tools/computer_use/screen_perception_tool.py',
    'tools/computer_use/input_automation_tool.py', 
    'tools/computer_use/system_control_tool.py'
]

print("Testing Computer Use Tools Capability Extraction")
print("=" * 60)

for f in files:
    print(f'\nFile: {f}')
    try:
        result = extractor.extract_from_file(f)
        print(f'  [OK] Tool: {result["name"]}')
        print(f'  [OK] Operations: {len(result["operations"])}')
        print(f'  [OK] Sample ops: {list(result["operations"].keys())[:3]}')
    except Exception as e:
        print(f'  [FAIL] {e}')

# Test excluded files should fail
print("\n" + "=" * 60)
print("Testing Excluded Files (should fail)")
print("=" * 60)

excluded = [
    'tools/computer_use/ocr_clicker.py',
    'tools/computer_use/task_state.py',
    'tools/computer_use/visual_policy.py'
]

for f in excluded:
    print(f'\nFile: {f}')
    try:
        result = extractor.extract_from_file(f)
        print(f'  [UNEXPECTED] Extracted: {result["name"]}')
    except Exception as e:
        print(f'  [EXPECTED] Failed: {str(e)[:80]}...')
