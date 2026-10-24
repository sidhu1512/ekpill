@echo off
REM Launch EkPill without a console window hanging around.
cd /d "%~dp0"
start "" pythonw main.py
