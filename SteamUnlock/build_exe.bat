@echo off
:: build_exe.bat - Build SteamUnlock.exe (standalone, no Python needed)

echo ============================================================
echo   Building SteamUnlock.exe
echo ============================================================
echo.

pip install pyinstaller >nul 2>&1

pyinstaller ^
    --onefile ^
    --noconsole ^
    --name SteamUnlock ^
    --icon "%~dp0assets\app.ico" ^
    --add-data "%~dp0assets;assets" ^
    "%~dp0SteamUnlock_GUI.pyw"

if errorlevel 1 (
    echo.
    echo Build failed. Check errors above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Done! Executable: %~dp0dist\SteamUnlock.exe
echo   Copy SteamUnlock.exe anywhere and double-click to run.
echo ============================================================
echo.
pause
