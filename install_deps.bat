@echo off
echo Installing requests...
python -m pip install requests
if errorlevel 1 (
    echo Failed to install requests.
    pause
    exit /b 1
)
echo All dependencies installed.
pause