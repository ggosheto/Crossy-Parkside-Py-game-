@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe crossy_neon.py
) else (
  py -3 crossy_neon.py
)
if errorlevel 1 pause
