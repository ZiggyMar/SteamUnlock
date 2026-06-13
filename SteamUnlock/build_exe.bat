@echo off
:: build_exe.bat — Build a standalone SteamUnlock.exe (no Python needed to run it)
:: Requires PyInstaller: pip install pyinstaller

echo Building SteamUnlock.exe...
echo.

pip install pyinstaller >nul 2>&1

pyinstaller ^
    --onefile ^
    --console ^
    --name SteamUnlock ^
    --add-data "..\SteamToolbox\assets\data\depotkeys.json;assets" ^
    "%~dp0steamunlock.py"

if errorlevel 1 (
    echo.
    echo Build failed. Check errors above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Build complete!
echo   Executable: %~dp0dist\SteamUnlock.exe
echo.
echo   You can copy SteamUnlock.exe anywhere and run it standalone.
echo   The .bat files will also work if you put SteamUnlock.exe
echo   next to them and change 'python steamunlock.py' to 'SteamUnlock.exe'
echo ============================================================
echo.
pause
