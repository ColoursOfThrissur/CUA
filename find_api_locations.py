"""Find all old API imports in bootstrap and locate their new paths"""
import re
from pathlib import Path

# Read bootstrap
bootstrap_path = Path("api/bootstrap.py")
content = bootstrap_path.read_text()

# Extract all api.*_api imports
pattern = r'from api\.(\w+_api) import'
old_imports = re.findall(pattern, content)

print("Old API imports found in bootstrap.py:")
print("=" * 60)

for old_import in set(old_imports):
    print(f"\n{old_import}.py")
    
    # Search for the file
    found = list(Path("api").rglob(f"{old_import}.py"))
    
    if found:
        for f in found:
            rel_path = f.relative_to(Path("api"))
            new_import = str(rel_path.parent / rel_path.stem).replace("\\", ".")
            print(f"  FOUND: api.{new_import}")
    else:
        print(f"  NOT FOUND - needs to be created or is missing")

print("\n" + "=" * 60)
print("\nSummary of required changes:")
print("=" * 60)

changes = {
    "tools_api": "api/rest/tools/tools_api.py",
    "libraries_api": "api/rest/system/libraries_router.py",
    "hybrid_api": "api/rest/chat/hybrid_router.py",
    "quality_api": "api/rest/monitoring/quality_router.py",
    "tool_evolution_api": "api/rest/evolution/tool_evolution_router.py",
    "observability_api": "api/rest/observability/observability_router.py",
    "observability_data_api": "api/rest/observability/observability_data_router.py",
    "cleanup_api": "api/rest/system/cleanup_router.py",
    "tool_info_api": "api/rest/tools/tool_info_router.py",
    "tool_list_api": "api/rest/tools/tool_list_router.py",
    "tools_management_api": "api/rest/tools/tools_management_router.py",
    "metrics_api": "api/rest/monitoring/metrics_router.py",
    "auto_evolution_api": "api/rest/evolution/auto_evolution_router.py",
    "agent_api": "api/rest/autonomy/agent_router.py",
    "skills_api": "api/rest/system/skills_router.py",
    "circuit_breaker_api": "api/rest/monitoring/circuit_breaker_router.py",
    "session_api": "api/rest/config/session_router.py",
    "services_api": "api/rest/system/services_router.py",
    "pending_skills_api": "api/rest/system/pending_skills_router.py",
    "mcp_api": "api/rest/config/mcp_router.py",
    "credentials_api": "api/rest/config/credentials_router.py",
}

for old, new in changes.items():
    exists = Path(new).exists()
    status = "✓" if exists else "✗"
    print(f"{status} {old:30} → {new}")
