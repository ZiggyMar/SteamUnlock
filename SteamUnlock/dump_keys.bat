@echo off
set PYTHONUTF8=1
:: dump_keys.bat — Extract depot decryption keys from your existing depotcache
:: Scans all .vdf files in Steam\depotcache and saves found keys to keys.txt
:: Useful for backing up or sharing keys you already have

python "%~dp0steamunlock.py" dumpkeys %*
pause
