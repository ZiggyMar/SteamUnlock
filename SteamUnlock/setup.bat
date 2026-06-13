@echo off
:: setup.bat — First-time setup
:: Installs required Python packages and optionally builds the .exe

echo ============================================================
echo   SteamUnlock Setup
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.8+ from https://python.org
    pause
    exit /b 1
)
python --version

echo.
echo Installing required packages...
pip install aiohttp aiofiles
if errorlevel 1 (
    echo.
    echo pip install failed. Try running as administrator or check your Python install.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Setup complete!
echo.
echo   Quick start:
echo     Double-click steamunlock.bat     — interactive menu
echo     unlock.bat 730                   — unlock CS2
echo     search.bat "elden ring"          — search by name
echo     bulk_unlock.bat appids.txt       — unlock many at once
echo ============================================================
echo.

set /p BUILD="Build SteamUnlock.exe now? [y/N]: "
if /i "%BUILD%"=="y" (
    call "%~dp0build_exe.bat"
)

pause
