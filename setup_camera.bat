@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install --upgrade -r requirements-camera.txt
if errorlevel 1 goto failed
echo Camera setup complete. Start run_game.bat and open Camera settings.
pause
exit /b 0
:failed
echo Setup failed. Read the error above; Python 3.11 or 3.12 is a useful fallback.
pause
exit /b 1
