@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python main.py run >> logs\daily_run.log 2>&1
