@echo off

REM Check if virtualenv is installed
python -m pip show virtualenv >nul 2>&1
if errorlevel 1 (
    echo virtualenv is not installed. Installing...
    pip install virtualenv
)

REM Create virtual environment
if not exist "cloudsql_venv" (
    echo Creating virtual environment...
    virtualenv cloudsql_venv
)

REM Add a pause for 30 seconds (adjust as needed)
timeout /t 10 /nobreak >nul

REM Activate virtual environment
echo Activating virtual environment...
call cloudsql_venv\Scripts\activate

REM Add a pause for 3 seconds (adjust as needed)
timeout /t 3 /nobreak >nul

REM Install requirements
echo Installing requirements...
pip install -r requirements.txt

echo Setup complete!

REM Prompt user to press any key to exit
pause >nul
