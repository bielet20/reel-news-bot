@echo off
REM Arranca lo que hace falta para generar montajes con video IA:
REM   1) el guardian que impide que el PC se suspenda mientras se genera
REM   2) ComfyUI (Flux + Wan2.2)
REM Deja las dos ventanas abiertas mientras trabajes. Cierralas al terminar.

set COMFY=E:\AI-Studio\tools\ComfyUI

echo [1/2] Guardian de suspension...
start "Mantener despierto" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mantener_despierto.ps1"

echo [2/2] ComfyUI...
start "ComfyUI" cmd /c "cd /d %COMFY% && env\python.exe main.py --disable-smart-memory --reserve-vram 1.0"

echo.
echo Listo. Espera a que ComfyUI diga "To see the GUI go to: http://127.0.0.1:8188"
echo y luego lanza el Montaje desde la web.
