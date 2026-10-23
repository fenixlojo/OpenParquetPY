@echo off
cd /d "%~dp0"
python -c "import duckdb, openpyxl, xlrd" >nul 2>&1
if errorlevel 1 python -m pip install -r requirements.txt
python app.py
pause
