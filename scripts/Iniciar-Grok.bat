@echo off
cd /d "%~dp0\.."
echo Puente de Grok para reel-news-bot. Deja esta ventana abierta.
py -3 scripts\grok_puente.py
if errorlevel 1 python scripts\grok_puente.py
