# meetlive child launcher. ASCII only. Opens MIC window and LOOP window.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
$py = Join-Path $here "venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "venv not found. Run setup.cmd first."; Read-Host "Press Enter"; exit 1 }
if (-not (Test-Path (Join-Path $here "config.txt"))) { Write-Host "config.txt not found. Copy config.txt.example to config.txt and edit host/port/token."; Read-Host "Press Enter"; exit 1 }
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'agent_(mic|loop)\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 500
Start-Process powershell -ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-Command',"`$host.UI.RawUI.WindowTitle='MIC (agent_mic) - my voice'; Set-Location '$here'; & '$py' agent_mic.py")
Start-Sleep -Milliseconds 800
Start-Process powershell -ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-Command',"`$host.UI.RawUI.WindowTitle='LOOP (agent_loop) - other side'; Set-Location '$here'; while(`$true){ & '$py' agent_loop.py; Start-Sleep 3 }")
Write-Host "Opened MIC and LOOP windows. Ready when both show: [..] OK -> sending"
Start-Sleep 3
