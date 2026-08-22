@echo off
chcp 65001 >nul
title meetlive 子機 (相手側/ループバック)
cd /d "%~dp0"
echo   相手側(ループバック)専用。落ちたら自動で再試行します。止めるときはこの窓を閉じる。
:retry
"%~dp0venv\Scripts\python.exe" "%~dp0agent_loop.py"
echo   [再試行まで 3秒]
timeout /t 3 /nobreak >nul
goto retry
