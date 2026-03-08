@echo off
echo Restoring archived files...

if not exist _archived_files (
    echo Error: _archived_files folder not found!
    pause
    exit /b 1
)

echo Restoring test files...
move _archived_files\test_*.py . 2>nul
xcopy /E /I /Y _archived_files\tests tests 2>nul

echo Restoring backups...
move _archived_files\backups\*.bak backups\ 2>nul
move _archived_files\backups\test_v1.0.0.py backups\ 2>nul

echo Restoring checkpoints...
move _archived_files\checkpoints\*.json checkpoints\ 2>nul

echo Restoring output files...
xcopy /E /I /Y _archived_files\output output 2>nul

echo Restoring old docs...
move _archived_files\docs\*.md . 2>nul
move _archived_files\docs\*.txt . 2>nul

echo Restoring debug scripts...
move _archived_files\root_scripts\*.py . 2>nul

echo Restoring temp files...
move _archived_files\temp\*.json . 2>nul
move _archived_files\temp\*.txt . 2>nul

echo.
echo Restore complete!
echo To remove archive folder, run: rmdir /S /Q _archived_files
pause
