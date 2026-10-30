@echo off
title Telegram to MT5 Signal Copier
cd /d "D:\Double X\Trade Copier"
echo ====================================================
echo Starting Telegram to MT5 Signal Copier...
echo ====================================================
call .venv\Scripts\activate.bat
python cli.py run
pause
