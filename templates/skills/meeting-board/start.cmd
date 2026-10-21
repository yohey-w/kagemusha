@echo off
setlocal
rem Starts the meeting-board helper. Closing this window stops it (Ctrl+C also works).
rem This file is pure ASCII on purpose: the Japanese messages live in helper\messages\*.txt
rem and are shown with "type" after "chcp 65001", so no code page can garble this script.
rem Node.js is looked for in this order: .\node\node.exe, .\node.exe, then node on PATH.

set "HERE=%~dp0"
set "NODE_EXE="
if exist "%HERE%node\node.exe" set "NODE_EXE=%HERE%node\node.exe"
if not defined NODE_EXE if exist "%HERE%node.exe" set "NODE_EXE=%HERE%node.exe"
if not defined NODE_EXE where node >nul 2>nul && set "NODE_EXE=node"
if not defined NODE_EXE goto :nonode

"%NODE_EXE%" -e "process.exit(Number(process.versions.node.split('.')[0])>=18?0:1)" >nul 2>nul
if errorlevel 1 goto :oldnode

"%NODE_EXE%" "%HERE%helper\server.js" --open %*
if errorlevel 1 goto :failed
exit /b 0

:nonode
chcp 65001 >nul
echo.
type "%HERE%helper\messages\no-node.txt"
echo.
pause
exit /b 1

:oldnode
chcp 65001 >nul
echo.
type "%HERE%helper\messages\old-node.txt"
echo.
pause
exit /b 1

:failed
chcp 65001 >nul
echo.
type "%HERE%helper\messages\failed.txt"
echo.
pause
exit /b 1
