"""
Fix remaining imports from core.* after Phase 6 migration
"""
import os
import re
from pathlib import Path

# Import mapping for remaining core.* imports
IMPORT_MAPPINGS = {
    # Skills system
    r'from core\.skills import (.+)': r'from application.services.skill_registry import \1',
    r'from core\.skills\.registry import': 'from application.services.skill_registry import',
    r'from core\.skills\.selector import': 'from application.services.skill_selector import',
    r'from core\.skills\.loader import': 'from application.services.skill_loader import',
    r'from core\.skills\.updater import': 'from application.services.skill_updater import',
    r'from core\.skills\.context_hydrator import': 'from application.services.skill_context_hydrator import',
    r'from core\.skills\.models import': 'from domain.entities.skill_models import',
    r'from core\.skills\.execution_context import': 'from domain.value_objects.execution_context import',
    r'from core\.skills import get_skill_registry': 'from application.services.skill_registry import get_skill_registry',
    r'from core\.skills import SkillRegistry': 'from application.services.skill_registry import SkillRegistry',
    r'from core\.skills import SkillSelector': 'from application.services.skill_selector import SkillSelector',
    r'from core\.skills import SkillUpdater': 'from application.services.skill_updater import SkillUpdater',
    r'from core\.skills import SkillContextHydrator': 'from application.services.skill_context_hydrator import SkillContextHydrator',
    r'from core\.skills import Skill': 'from domain.entities.skill_models import Skill',
    r'from core\.skills import build_skill_planning_context': 'from application.services.skill_context_hydrator import build_skill_planning_context',
    
    # Database
    r'from core\.cua_db import (.+)': r'from infrastructure.persistence.sqlite.cua_database import \1',
    
    # Event bus
    r'from core\.event_bus import (.+)': r'from infrastructure.messaging.event_bus import \1',
    
    # MCP
    r'from core\.mcp_process_manager import (.+)': r'from infrastructure.external.mcp_process_manager import \1',
    
    # Architecture contract
    r'from core\.architecture_contract import (.+)': r'from domain.services.architecture_contract import \1',
    
    # Validators
    r'from core\.enhanced_code_validator import (.+)': r'from infrastructure.validation.enhanced_code_validator import \1',
    r'from core\.behavior_validator import (.+)': r'from infrastructure.validation.behavior_validator import \1',
    r'from core\.ast_validator import (.+)': r'from infrastructure.validation.ast.ast_validator import \1',
    
    # Services
    r'from core\.services\.http_service import (.+)': r'from infrastructure.services.http_service import \1',
    r'from core\.services\.shell_service import (.+)': r'from infrastructure.services.shell_service import \1',
    
    # Tool creation
    r'from core\.tool_creation import SpecGenerator': 'from infrastructure.code_generation.spec_generator import SpecGenerator',
}

def fix_imports_in_file(file_path):
    """Fix imports in a single file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        changes = []
        
        for pattern, replacement in IMPORT_MAPPINGS.items():
            if re.search(pattern, content):
                new_content = re.sub(pattern, replacement, content)
                if new_content != content:
                    changes.append(f"  - {pattern} -> {replacement}")
                    content = new_content
        
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, changes
        
        return False, []
    
    except Exception as e:
        print(f"[ERROR] {file_path}: {e}")
        return False, []

def main():
    project_root = Path(__file__).parent
    print("=" * 80)
    print("Fixing Remaining Imports from core.*")
    print("=" * 80)
    print(f"\nProject root: {project_root}")
    
    # Find all Python files
    python_files = []
    for ext in ['*.py']:
        python_files.extend(project_root.rglob(ext))
    
    # Exclude venv and other non-project directories
    python_files = [
        f for f in python_files 
        if 'venv' not in str(f) and 
           'node_modules' not in str(f) and
           '.pytest' not in str(f) and
           '__pycache__' not in str(f)
    ]
    
    print(f"Found {len(python_files)} Python files to process\n")
    
    modified_count = 0
    total_changes = 0
    
    for file_path in python_files:
        modified, changes = fix_imports_in_file(file_path)
        if modified:
            modified_count += 1
            total_changes += len(changes)
            rel_path = file_path.relative_to(project_root)
            print(f"[OK] {rel_path}: {len(changes)} imports updated")
            for change in changes:
                print(change)
            print()
    
    print("=" * 80)
    print("SUMMARY:")
    print(f"  Files processed: {len(python_files)}")
    print(f"  Files modified: {modified_count}")
    print(f"  Total imports updated: {total_changes}")
    print("=" * 80)
    
    if modified_count > 0:
        print("\n[SUCCESS] Import fixes complete!")
    else:
        print("\n[INFO] No imports needed fixing")
    
    print("\nNext steps:")
    print("1. Check for any files that still need manual fixes")
    print("2. Run: python -m pytest -q")
    print("3. Fix any remaining import errors")

if __name__ == "__main__":
    main()
