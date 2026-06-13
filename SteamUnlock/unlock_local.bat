@echo off
set PYTHONUTF8=1
:: unlock_local.bat — Unlock a game but save files locally (no auto-install to Steam)
:: Usage: unlock_local.bat <AppID>
:: Creates a [AppID]GameName\ folder here with .manifest files + .lua script

if "%~1"=="" (
    echo Usage: unlock_local.bat ^<AppID^>
    pause
    exit /b 1
)

python "%~dp0steamunlock.py" unlock --local %*
pause
