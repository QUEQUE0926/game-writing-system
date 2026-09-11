@echo off
rem Drop TXT files here: a dialog will pop up (prod environment)
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set GWS_ENV=prod
"C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe" scripts\drop_dialog.py %*
if errorlevel 1 pause
