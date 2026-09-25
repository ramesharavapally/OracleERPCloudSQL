@echo off
REM One-time setup (and after every update): installs uv if needed, then creates .venv
REM with the exact package versions from uv.lock.
cd /d "%~dp0"

set "UV=uv"
uv --version >nul 2>&1
if not errorlevel 1 goto have_uv

set "UV=python -m uv"
python -m uv --version >nul 2>&1
if not errorlevel 1 goto have_uv

echo uv was not found. Installing it with pip...
python -m pip install --user --upgrade uv
if errorlevel 1 (
    echo Could not install uv. Install it from https://docs.astral.sh/uv/ and run setup.bat again.
    pause
    exit /b 1
)

:have_uv
echo Using %UV%
echo Creating .venv and installing the locked packages...
%UV% sync --locked
if errorlevel 1 (
    echo Setup failed. See the messages above.
    pause
    exit /b 1
)

echo Setup complete! Start the app with CloudConsole.bat
pause
