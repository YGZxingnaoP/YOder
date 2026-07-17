@echo off
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
start "" "%SCRIPT_DIR%env\python.exe" "%SCRIPT_DIR%run.py"