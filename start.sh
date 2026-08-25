#!/bin/bash
# Arranca el backend FastAPI (8000), el frontend Next.js (3000)
# y el sidecar de WhatsApp (3001) si está disponible.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Iniciando Reel News Bot..."

# Backend FastAPI
echo "  → FastAPI en http://localhost:8000"
python3 -m uvicorn api.server:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# WhatsApp sidecar (opcional — solo si está instalado)
WA_PID=""
if [ -f "$SCRIPT_DIR/wa_service/node_modules/.bin/qrcode" ] || [ -d "$SCRIPT_DIR/wa_service/node_modules" ]; then
    echo "  → WhatsApp sidecar en http://localhost:3001"
    cd "$SCRIPT_DIR/wa_service" && node server.js &
    WA_PID=$!
    cd "$SCRIPT_DIR"
else
    echo "  ! WhatsApp sidecar no instalado — ejecuta: cd wa_service && npm install"
fi

sleep 1

# Frontend Next.js
echo "  → Next.js en http://localhost:3000"
cd "$SCRIPT_DIR/web" && node_modules/.bin/next dev --port 3000 &
WEB_PID=$!

echo ""
echo "App corriendo en http://localhost:3000"
echo "Presiona Ctrl+C para detener todo."
echo ""

trap "kill $API_PID $WA_PID $WEB_PID 2>/dev/null; echo 'Detenido.'" INT TERM
wait
