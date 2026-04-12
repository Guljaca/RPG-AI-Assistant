@echo off
chcp 65001 >nul 2>&1
title RPG AI Assistant - Dependency Check

echo ===================================================
echo   RPG AI Assistant - Dependency Check
echo ===================================================
echo.

:: 1. Check Python
echo [1/3] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Please install Python and add it to your PATH.
    pause
    exit /b 1
)
python --version

:: 2. Check pip
echo.
echo [2/3] Checking pip...
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo pip not found. Attempting to install...
    python -m ensurepip
    if errorlevel 1 (
        echo Failed to install pip.
        pause
        exit /b 1
    )
)

:: 3. Check and install requests
echo.
echo [3/3] Checking requests library...
python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo requests not found. Installing...
    python -m pip install requests
    if errorlevel 1 (
        echo Failed to install requests.
        pause
        exit /b 1
    )
    echo requests successfully installed.
) else (
    echo requests already installed.
)

:: 4. Run the application (foreground, output visible)
echo.
echo Starting RPG AI Assistant...
echo (The window will close after the program finishes. Press any key to close manually.)
python "Project_Py3_RPG_AI_main_Tools_version_V4.4.py"

:: 5. Check return code and show error message
if errorlevel 1 (
    echo.
    echo ==========================================
    echo   PROGRAM EXITED WITH AN ERROR
    echo ==========================================
    echo Check the messages above.
    echo Possible causes:
    echo   - Corrupted JSON file in data/sessions/
    echo   - Missing data files
    echo   - Connection error to LM Studio
    echo.
)

:: 6. Wait for key press so the window doesn't close automatically
echo Press any key to exit...
pause >nul
exit