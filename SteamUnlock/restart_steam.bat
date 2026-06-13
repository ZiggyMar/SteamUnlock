@echo off
set PYTHONUTF8=1
:: restart_steam.bat — Kill Steam and restart it
:: Run this after unlocking games to apply changes

python "%~dp0steamunlock.py" restart
