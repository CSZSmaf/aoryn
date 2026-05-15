@echo off
setlocal
cd /d "%~dp0"
python scripts\dev_start.py %*
