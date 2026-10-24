@echo off
chcp 65001 >nul
cd /d "%~dp0server"
start "" http://127.0.0.1:8770/
"C:\Users\74187\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" app.py
pause
