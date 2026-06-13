@echo off
set PYTHONUTF8=1
:: search.bat — Search for a game by name to find its AppID
:: Usage: search.bat elden ring
::        search.bat "counter-strike"

if "%~1"=="" (
    echo Usage: search.bat ^<game name^>
    pause
    exit /b 1
)

python "%~dp0steamunlock.py" search %*
pause
