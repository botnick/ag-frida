@echo off
title ag-frida Installer
echo [INFO] Checking Python...
python --version
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b
)

echo.
echo [INFO] Installing/Updating Dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b
)

echo.
echo [SUCCESS] Environment is ready!
echo [INFO] You can now run 'start_web_dashboard.bat'
pause
