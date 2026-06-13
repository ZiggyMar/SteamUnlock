@echo off
set PYTHONUTF8=1
:: unlock.bat - Unlock a game by AppID
:: Usage: unlock.bat <AppID> [AppID2 ...]
:: Example: unlock.bat 730
::          unlock.bat 730 570 440

if "%~1"=="" (
    echo Usage: unlock.bat ^<AppID^> [AppID2 AppID3 ...]
    echo Example: unlock.bat 730
    pause
    exit /b 1
)

python "%~dp0steamunlock.py" unlock %*
pause
