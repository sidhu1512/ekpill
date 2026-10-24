@echo off
REM Launch EkPill without a console window
cd /d "%~dp0\ekpill"
start "" pythonw main.py
