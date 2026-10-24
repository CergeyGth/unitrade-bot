@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if not exist "token.txt" (
  echo Нет файла token.txt
  echo Скопируйте token.txt.example в token.txt и вставьте токен от @BotFather.
  pause
  exit /b 1
)

python -c "import requests, openpyxl" >nul 2>&1
if errorlevel 1 (
  echo Ставлю зависимости...
  python -m pip install --quiet -r requirements.txt
)

echo Бот запущен. Остановить: Ctrl+C или закрыть окно.
python bot.py
pause
