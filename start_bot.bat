@echo off
chcp 65001 >nul
cd /d "%~dp0"
:loop
echo [%date% %time%] bot starting...
venv\Scripts\python.exe -m app.main
echo Bot stopped. Restarting in 10 seconds (close this window to stop).
timeout /t 10 /nobreak >nul
goto loop
