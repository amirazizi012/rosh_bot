@echo off
chcp 65001 >nul
cd /d "%~dp0"
set DEST=%USERPROFILE%\rosh_backup
robocopy data "%DEST%" /MIR /NFL /NDL /NJH /NJS >nul
echo Backup done: %DEST%
pause
