@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

python -c "import requests, openpyxl" >nul 2>&1
if errorlevel 1 (
  echo Ставлю зависимости...
  python -m pip install --quiet -r requirements.txt
)

where pythonw >nul 2>&1 && (
  start "" pythonw "%~dp0pick_file.py"
) || (
  python "%~dp0pick_file.py"
)
