"""
Capture and display actual sandbox file after patch is applied
This will show you the EXACT file that the 191 tests ran against
"""
import tempfile
import shutil
from pathlib import Path

# Simulate the exact flow from test_self_improvement.py
print("=" * 80)
print("CAPTURING ACTUAL SANDBOX FILE AFTER PATCH")
print("=" * 80)

# Initialize components
from core.config_manager import get_config
from planner.llm_client import LLMClient
from core.system_analyzer import SystemAnalyzer
from core.task_analyzer import TaskAnalyzer
from core.proposal_generator import ProposalGenerator
from core.patch_generator import PatchGenerator
from updater.orchestrator import UpdateOrchestrator
from core.sandbox_tester import SandboxTester

config = get_config()
llm_client = LLMClient()
system_analyzer = SystemAnalyzer(".")
task_analyzer = TaskAnalyzer(llm_client, system_analyzer)
patch_generator = PatchGenerator(repo_path=".")
update_orchestrator = UpdateOrchestrator(repo_path=".")
proposal_generator = ProposalGenerator(llm_client, system_analyzer, patch_generator, update_orchestrator)
sandbox_tester = SandboxTester(system_analyzer)

print("\n[1/4] Analyzing system...")
analysis_result = task_analyzer.analyze_for_improvements()

if analysis_result and analysis_result.get('tasks'):
    task = analysis_result['tasks'][0]
    print(f"[2/4] Generating proposal for: {task['description'][:60]}...")
    
    proposal = proposal_generator.generate_proposal(task)
    
    if proposal:
        target_file = proposal['files_changed'][0]
        raw_code = proposal['raw_code']
        
        print(f"[3/4] Target file: {target_file}")
        print(f"[3/4] Generated code size: {len(raw_code)} chars")
        
        # Regenerate patch from current state (Option 2)
        print("[4/4] Creating sandbox and applying patch...")
        
        # Manually create sandbox to capture file
        with tempfile.TemporaryDirectory() as temp_dir:
            sandbox_path = Path(temp_dir) / "sandbox"
            
            # Copy repo
            shutil.copytree(".", sandbox_path, 
                           ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git', 
                                                        'checkpoints', 'logs', 'sandbox', 'backups'))
            
            print(f"\n{'='*80}")
            print("BEFORE PATCH - Original File in Sandbox:")
            print(f"{'='*80}")
            original_file = sandbox_path / target_file
            if original_file.exists():
                original_content = original_file.read_text(encoding='utf-8')
                print(original_content[:500])
                print(f"\n... (showing first 500 chars of {len(original_content)} total)")
            
            # Apply patch (FILE_REPLACE format)
            from core.patch_generator import PatchGenerator
            patch_gen = PatchGenerator(repo_path=".")
            
            if original_file.exists():
                current_content = original_file.read_text(encoding='utf-8')
                patch = patch_gen.generate_patch(target_file, current_content, raw_code)
            else:
                patch = patch_gen.generate_new_file_patch(target_file, raw_code)
            
            # Apply patch
            if patch.startswith("FILE_REPLACE:"):
                lines = patch.split('\n', 1)
                if len(lines) == 2:
                    file_path = lines[0].replace("FILE_REPLACE:", "").strip()
                    new_content = lines[1]
                    target = sandbox_path / file_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(new_content, encoding='utf-8')
                    
                    print(f"\n{'='*80}")
                    print("AFTER PATCH - Modified File in Sandbox (THIS IS WHAT 191 TESTS RAN AGAINST):")
                    print(f"{'='*80}")
                    print(new_content[:1000])
                    print(f"\n... (showing first 1000 chars of {len(new_content)} total)")
                    
                    print(f"\n{'='*80}")
                    print("COMPARISON:")
                    print(f"{'='*80}")
                    print(f"Original size: {len(original_content)} chars")
                    print(f"Modified size: {len(new_content)} chars")
                    print(f"Difference: {len(new_content) - len(original_content):+d} chars")
                    
                    # Check for test code
                    if 'import pytest' in new_content:
                        print("\n[WARNING] File contains 'import pytest' - this is why tests failed!")
                    
                    # Count test discovery
                    import subprocess
                    try:
                        result = subprocess.run(
                            ["python", "-m", "pytest", "tests/unit/", "--collect-only"],
                            cwd=sandbox_path,
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if "collected" in result.stdout:
                            import re
                            match = re.search(r'collected (\d+)', result.stdout)
                            if match:
                                test_count = match.group(1)
                                print(f"\n[INFO] Pytest collected {test_count} tests in sandbox")
                    except:
                        pass
                    
    else:
        print("[ERROR] No proposal generated")
else:
    print("[ERROR] No tasks found")

print(f"\n{'='*80}")
print("CAPTURE COMPLETE")
print(f"{'='*80}")
