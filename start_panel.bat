@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Rosh panel: open http://localhost:8080 in your browser (close this window to stop)
venv\Scripts\python.exe -m app.panel
pause
