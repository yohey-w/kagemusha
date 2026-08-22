@echo off
chcp 65001 >nul
title meetlive 子機 セットアップ
cd /d "%~dp0"
echo.
echo   meetlive 子機のセットアップを始めます (初回だけ・2〜3分)
echo.

rem --- 1. Python を探す。無ければ入れる ---
set PY=
for %%C in ("py -3" "python") do (
  if not defined PY ( %%~C -c "import sys;assert sys.version_info>=(3,9)" >nul 2>&1 && set PY=%%~C )
)
if not defined PY (
  echo   [1/4] Python が見つからないので入れます...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo.
    echo   !! Python を自動で入れられませんでした。
    echo   !! https://www.python.org/downloads/ から入れて、もう一度 setup.cmd を叩いてください。
    pause & exit /b 1
  )
  set PY=py -3
) else (
  echo   [1/4] Python は入っています
)

rem --- 2. 専用の置き場を作る ---
echo   [2/4] 部品の置き場を作ります...
%PY% -m venv "%~dp0venv"
if errorlevel 1 ( echo   !! 失敗しました & pause & exit /b 1 )

rem --- 3. 音を録る部品を入れる ---
echo   [3/4] 音を録る部品を入れます...
"%~dp0venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check --upgrade pip
"%~dp0venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check soundcard numpy
if errorlevel 1 ( echo   !! 失敗しました & pause & exit /b 1 )

rem --- 4. 設定ファイルを用意する ---
if exist "%~dp0config.txt" (
  echo   [4/4] config.txt は既にあります
) else (
  copy /y "%~dp0config.txt.example" "%~dp0config.txt" >nul
  echo   [4/4] config.txt を作りました。**中身を書き換えてください**
  echo        host  = 親機のアドレス
  echo        token = 親機と合わせる合言葉
  notepad "%~dp0config.txt"
)

echo.
echo   完了。会議のときは START.bat を叩いてください。
echo   ※イヤホン/イヤモニは START.bat の前に挿すこと
echo.
pause
