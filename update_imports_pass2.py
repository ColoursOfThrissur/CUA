#!/usr/bin/env python3
"""
Import Update Script - Phase 8 (Second Pass)
Updates remaining imports for modules already moved by Gemini
"""

import os
import re
from pathlib import Path
from typing import Dict

# Additional mappings for modules already moved by Gemini
ADDITIONAL_MAPPINGS = {
    # Database (already moved by Gemini)
    r'from core\.cua_db import': 'from infrastructure.persistence.sqlite.cua_database import',
    
    # Event Bus (already exists in infrastructure)
    r'from core\.event_bus import': 'from infrastructure.messaging.event_bus import',
    
    # MCP Process Manager (already exists in infrastructure)
    r'from core\.mcp_process_manager import': 'from infrastructure.external.mcp_process_manager import',
    
    # Skills module imports (need to be more specific)
    r'from core\.skills import SkillRegistry': 'from application.services.skill_registry import SkillRegistry',
    r'from core\.skills import SkillSelector': 'from application.services.skill_selector import SkillSelector',
    r'from core\.skills import SkillContextHydrator': 'from application.services.skill_context_hydrator import SkillContextHydrator',
    r'from core\.skills import SkillUpdater': 'from application.services.skill_updater import SkillUpdater',
    r'from core\.skills import Skill': 'from domain.entities.skill_models import Skill',
    r'from core\.skills import get_skill_registry': 'from application.services.skill_registry import get_skill_registry',
    r'from core\.skills import build_skill_planning_context': 'from application.services.skill_context_hydrator import build_skill_planning_context',
    
    # Architecture contract (likely in domain or infrastructure)
    r'from core\.architecture_contract import': 'from domain.services.architecture_contract import',
    
    # Enhanced code validator (likely in infrastructure/validation)
    r'from core\.enhanced_code_validator import': 'from infrastructure.validation.enhanced_code_validator import',
    
    # Behavior validator (likely in infrastructure/validation)
    r'from core\.behavior_validator import': 'from infrastructure.validation.behavior_validator import',
    
    # AST Validator (already moved by Gemini)
    r'from core\.ast_validator import': 'from infrastructure.validation.ast.ast_validator import',
    
    # Tool creation spec generator
    r'from core\.tool_creation import SpecGenerator': 'from infrastructure.code_generation.spec_generator import SpecGenerator',
    
    # HTTP and Shell services
    r'from core\.services\.http_service import': 'from infrastructure.services.http_service import',
    r'from core\.services\.shell_service import': 'from infrastructure.services.shell_service import',
}


def find_python_files(root_dir: str, exclude_dirs=None) -> list:
    """Find all Python files, excluding venv and other directories."""
    if exclude_dirs is None:
        exclude_dirs = ['__pycache__', '.pytest_cache', 'venv', 'env', '.git', 'node_modules', 'ui']
    
    python_files = []
    root_path = Path(root_dir)
    
    for py_file in root_path.rglob('*.py'):
        if any(excluded in py_file.parts for excluded in exclude_dirs):
            continue
        python_files.append(py_file)
    
    return python_files


def update_imports_in_file(file_path: Path, mappings: Dict[str, str]) -> tuple:
    """Update imports in a single file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return 0, []
    
    original_content = content
    changes = []
    
    for old_pattern, new_import in mappings.items():
        if re.search(old_pattern, content):
            content = re.sub(old_pattern, new_import, content)
            changes.append(f"{old_pattern} -> {new_import}")
    
    if content != original_content:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return len(changes), changes
        except Exception as e:
            print(f"Error writing {file_path}: {e}")
            return 0, []
    
    return 0, []


def main():
    """Main function."""
    print("=" * 80)
    print("PHASE 8: Import Update Script (Second Pass)")
    print("=" * 80)
    print()
    
    project_root = Path(__file__).parent
    print(f"Project root: {project_root}")
    print(f"Finding Python files...")
    
    python_files = find_python_files(str(project_root))
    print(f"Found {len(python_files)} Python files to process")
    print()
    
    total_changes = 0
    files_modified = 0
    
    for file_path in python_files:
        num_changes, changes = update_imports_in_file(file_path, ADDITIONAL_MAPPINGS)
        
        if num_changes > 0:
            files_modified += 1
            total_changes += num_changes
            print(f"[OK] {file_path.relative_to(project_root)}: {num_changes} imports updated")
            for change in changes:
                print(f"  - {change}")
            print()
    
    print("=" * 80)
    print(f"SUMMARY:")
    print(f"  Files processed: {len(python_files)}")
    print(f"  Files modified: {files_modified}")
    print(f"  Total imports updated: {total_changes}")
    print("=" * 80)
    print()
    print("[SUCCESS] Second pass import update complete!")


if __name__ == "__main__":
    main()
