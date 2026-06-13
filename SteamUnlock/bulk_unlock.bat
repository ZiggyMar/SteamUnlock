@echo off
set PYTHONUTF8=1
:: bulk_unlock.bat — Unlock many games at once from a text file
:: Usage: bulk_unlock.bat appids.txt
::
:: appids.txt format — one AppID per line:
::   730
::   570
::   440

if "%~1"=="" (
    echo Usage: bulk_unlock.bat ^<appids.txt^>
    echo.
    echo Create a text file with one Steam AppID per line, then pass it here.
    pause
    exit /b 1
)

if not exist "%~1" (
    echo File not found: %~1
    pause
    exit /b 1
)

python "%~dp0steamunlock.py" bulk "%~1"
pause
