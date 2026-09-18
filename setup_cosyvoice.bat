@echo off
title CosyVoice 1-Click Setup
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_cosyvoice.ps1"
pause
