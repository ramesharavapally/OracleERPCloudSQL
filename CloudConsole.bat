@echo off
REM Starts Cloud SQL inside the uv environment (.venv) with the locked package versions
cd /d "%~dp0"

set "UV=uv"
uv --version >nul 2>&1
if not errorlevel 1 goto have_uv

set "UV=python -m uv"
python -m uv --version >nul 2>&1
if not errorlevel 1 goto have_uv

echo uv was not found. Run setup.bat once first.
pause
exit /b 1

:have_uv
cd /d "%~dp0cloudsql"
%UV% run --locked streamlit run app.py
if errorlevel 1 pause
