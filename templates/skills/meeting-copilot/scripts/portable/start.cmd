@echo off
chcp 65001 >nul
title meetlive 子機 (1プロセス版)
cd /d "%~dp0"
if not exist "%~dp0venv\Scripts\python.exe" (
  echo   まだセットアップされていません。先に setup.cmd を叩いてください。
  pause & exit /b 1
)
if not exist "%~dp0config.txt" (
  echo   config.txt がありません。config.txt.example をコピーして書き換えてください。
  pause & exit /b 1
)
call "%~dp0stop.cmd" >nul 2>&1
echo.
echo   ※これは agent.py の1プロセス版です。実運用は START.bat を推奨。
echo   イヤホン/イヤモニは挿さっていますか？(挿してから始めてください)
echo   止めるときは この窓を閉じるか stop.cmd
echo.
"%~dp0venv\Scripts\python.exe" "%~dp0agent.py" %*
pause
