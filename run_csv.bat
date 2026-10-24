@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

python -c "import requests, openpyxl" >nul 2>&1
if errorlevel 1 (
  echo Ставлю зависимости...
  python -m pip install --quiet -r requirements.txt
)

echo Формирую CSV из numbers.txt ...
python make_csv.py numbers.txt unitrade.csv

echo.
echo Готово. Файл: unitrade.csv
pause
