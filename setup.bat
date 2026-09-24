@echo off
REM Creates cloudsql_venv next to this file and installs or upgrades the requirements.
REM Safe to run again after every update.
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Python was not found. Install Python 3.10 or newer and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist "cloudsql_venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv cloudsql_venv
    if errorlevel 1 (
        echo Could not create the virtual environment.
        pause
        exit /b 1
    )
)

echo Installing requirements...
"cloudsql_venv\Scripts\python.exe" -m pip install --upgrade pip
"cloudsql_venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
    echo Installing the requirements failed. See the messages above.
    pause
    exit /b 1
)

echo Setup complete! Start the app with CloudConsole.bat
pause
