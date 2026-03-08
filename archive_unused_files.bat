@echo off
echo Creating archive folder...
mkdir _archived_files 2>nul
mkdir _archived_files\tests 2>nul
mkdir _archived_files\backups 2>nul
mkdir _archived_files\checkpoints 2>nul
mkdir _archived_files\output 2>nul
mkdir _archived_files\docs 2>nul
mkdir _archived_files\root_scripts 2>nul
mkdir _archived_files\temp 2>nul

echo Moving test files...
move test_*.py _archived_files\ 2>nul
xcopy /E /I /Y tests _archived_files\tests 2>nul
rmdir /S /Q tests 2>nul

echo Moving backups...
move backups\*.bak _archived_files\backups\ 2>nul
move backups\test_v1.0.0.py _archived_files\backups\ 2>nul

echo Moving checkpoints...
move checkpoints\*.json _archived_files\checkpoints\ 2>nul

echo Moving output files...
xcopy /E /I /Y output _archived_files\output 2>nul
rmdir /S /Q output 2>nul

echo Moving old docs...
move ACTIONABLE_RECOMMENDATIONS.md _archived_files\docs\ 2>nul
move AGENTIC_RESPONSE_FIX.md _archived_files\docs\ 2>nul
move ARCHITECTURE_ANALYSIS.md _archived_files\docs\ 2>nul
move AUTONOMOUS_AGENT_STATUS.md _archived_files\docs\ 2>nul
move BROWSER_TOOL_SPEC.txt _archived_files\docs\ 2>nul
move CHANGELOG_VISUAL.md _archived_files\docs\ 2>nul
move COMPLETE_TOOL_CREATION_FLOW_MAP.md _archived_files\docs\ 2>nul
move CURRENT_ARCHITECTURE.md _archived_files\docs\ 2>nul
move CURRENT_STATE.md _archived_files\docs\ 2>nul
move DIFF_BASED_ARCHITECTURE.md _archived_files\docs\ 2>nul
move FAILURE_ANALYSIS.md _archived_files\docs\ 2>nul
move FINAL_FIX_SUMMARY.md _archived_files\docs\ 2>nul
move FLOW_DIAGRAMS.md _archived_files\docs\ 2>nul
move FLOW_EXPLANATION.md _archived_files\docs\ 2>nul
move improvement_prompt.txt _archived_files\docs\ 2>nul
move PHASE1_VERIFICATION_REPORT.md _archived_files\docs\ 2>nul
move PRIORITY1_COMPLETE.md _archived_files\docs\ 2>nul
move q-dev-chat-2026-02-20.md _archived_files\docs\ 2>nul
move q-dev-chat-2026-02-22.md _archived_files\docs\ 2>nul
move QUICK_REFERENCE.md _archived_files\docs\ 2>nul
move SOLUTION_ANALYSIS.md _archived_files\docs\ 2>nul
move structure.txt _archived_files\docs\ 2>nul
move TOOL_CREATION_FLOW_COMPLETE.md _archived_files\docs\ 2>nul
move TOOL_CREATION_IMPROVEMENTS.md _archived_files\docs\ 2>nul

echo Moving debug scripts...
move analysis.py _archived_files\root_scripts\ 2>nul
move architecture_plan.py _archived_files\root_scripts\ 2>nul
move audit_improvements_v2.py _archived_files\root_scripts\ 2>nul
move capture_sandbox_file.py _archived_files\root_scripts\ 2>nul
move check_creation_log.py _archived_files\root_scripts\ 2>nul
move control_loop.py _archived_files\root_scripts\ 2>nul
move FINAL_AUDIT_REPORT.py _archived_files\root_scripts\ 2>nul
move migrate_risk_scores.py _archived_files\root_scripts\ 2>nul
move run_continuous.py _archived_files\root_scripts\ 2>nul
move SYSTEM_ANALYSIS.py _archived_files\root_scripts\ 2>nul
move verify_inter_tool_communication.py _archived_files\root_scripts\ 2>nul
move verify_phase1.py _archived_files\root_scripts\ 2>nul

echo Moving temp files...
move temp_analysis.json _archived_files\temp\ 2>nul
move temp_llm_response.txt _archived_files\temp\ 2>nul
move all_py_files.txt _archived_files\temp\ 2>nul
move project_py_files.txt _archived_files\temp\ 2>nul
del "strftime('%s'" 2>nul
del unknown 2>nul
del 1771694880 2>nul

echo Removing empty directories...
rmdir audit 2>nul
rmdir sandbox 2>nul
rmdir workspace 2>nul

echo.
echo Archive complete! Files moved to _archived_files\
echo To revert, run: restore_archived_files.bat
pause
