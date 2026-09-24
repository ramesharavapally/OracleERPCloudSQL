@echo off
REM Starts Cloud SQL with the Python of cloudsql_venv (never the global Python)
set "VENV_PY=%~dp0cloudsql_venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo cloudsql_venv was not found next to this file.
    echo Run setup.bat once, then start CloudConsole.bat again.
    pause
    exit /b 1
)

cd /d "%~dp0cloudsql"
"%VENV_PY%" -m streamlit run app.py
