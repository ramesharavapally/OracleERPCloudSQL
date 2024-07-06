@echo off
REM Step 1: Activate py_automate venv
call %~dp0cloudsql_venv\Scripts\activate

REM Step 2: Navigate to ERPE2E\tests folder
cd /d "%~dp0cloudsql"

REM Step 3: Run pyteest -m jobs command
streamlit run app.py

REM Step 4: Deactivate py_automate venv (optional)
deactivate