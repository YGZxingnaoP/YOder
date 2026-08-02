@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting YOder API Server...
start http://localhost:8000
env\python.exe -m uvicorn func.api.main:app --host 0.0.0.0 --port 8000 --reload
pause
