@echo off
REM Check if local venv exists
if exist "%~dp0..\venv\Scripts\python.exe" (
    "%~dp0..\venv\Scripts\python.exe" "%~dp0main.py" %*
) else (
    REM Fallback to system python
    python "%~dp0main.py" %*
)
