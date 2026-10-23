@echo off
cd /d "%~dp0"
python -c "import duckdb" >nul 2>&1
if errorlevel 1 python -m pip install -r requirements.txt
python app.py
pause
