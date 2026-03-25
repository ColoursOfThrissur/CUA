import sys, re, traceback
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

tool_name = 'MCPAdapterTool'

print('=== FILE LOOKUP ===')
try:
    from core.tool_registry_manager import ToolRegistryManager
    resolved = ToolRegistryManager().resolve_source_file(tool_name)
    print(f'Registry: {resolved}, exists={resolved.exists() if resolved else None}')
except Exception as e:
    print(f'Registry error: {e}')

snake_case = re.sub(r'(?<!^)(?=[A-Z])', '_', tool_name).lower()
candidates = [
    Path(f'tools/experimental/{tool_name}.py'),
    Path(f'tools/{tool_name}.py'),
    Path(f'tools/{tool_name.lower()}.py'),
    Path(f'tools/{snake_case}.py'),
    Path(f'tools/experimental/{tool_name.lower()}.py'),
    Path(f'tools/experimental/{snake_case}.py'),
]
for p in candidates:
    print(f'  {p}: {p.exists()}')

print()
print('=== LLMToolHealthAnalyzer._find_tool_file ===')
try:
    from core.llm_tool_health_analyzer import LLMToolHealthAnalyzer
    import inspect
    src = inspect.getsource(LLMToolHealthAnalyzer)
    idx = src.find('def _find_tool')
    print(src[idx:idx+600] if idx >= 0 else 'no _find_tool_file method')
except Exception as e:
    print(f'Error: {e}')

print()
print('=== FULL analyze_tool call ===')
try:
    from core.llm_tool_health_analyzer import LLMToolHealthAnalyzer
    a = LLMToolHealthAnalyzer()
    result = a.analyze_tool(tool_name, force_refresh=True)
    print(f'Result keys: {list(result.keys()) if result else None}')
    print(f'Error: {result.get("error") if result else "returned None"}')
except Exception as e:
    print(f'Exception: {e}')
    traceback.print_exc()

print()
print('=== ToolAnalyzer.analyze_tool call ===')
try:
    from core.tool_quality_analyzer import ToolQualityAnalyzer
    from core.tool_evolution.analyzer import ToolAnalyzer
    ta = ToolAnalyzer(ToolQualityAnalyzer())
    result = ta.analyze_tool(tool_name)
    print(f'Result: {result is not None}')
    if result:
        print(f'  tool_path: {result.get("tool_path")}')
        print(f'  health_score: {result.get("health_score")}')
    else:
        print('  returned None')
except Exception as e:
    print(f'Exception: {e}')
    traceback.print_exc()
