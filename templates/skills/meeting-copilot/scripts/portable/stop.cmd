@echo off
chcp 65001 >nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*meetlive*agent.py*' -or $_.CommandLine -like '*\agent.py*' } | ForEach-Object { Write-Host ('止めました PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force }"
