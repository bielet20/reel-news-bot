#!/bin/bash
# Arranca el backend FastAPI (puerto 8000) y el frontend Next.js (puerto 3000)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Iniciando Reel News Bot..."

# Backend
echo "  → FastAPI en http://localhost:8000"
python3 -m uvicorn api.server:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# Pequeña pausa para que FastAPI arranque
sleep 1

# Frontend
echo "  → Next.js en http://localhost:3000"
cd "$SCRIPT_DIR/web" && node_modules/.bin/next dev --webpack --port 3000 &
WEB_PID=$!

echo ""
echo "✅ App corriendo en http://localhost:3000"
echo "   Presiona Ctrl+C para detener todo."
echo ""

# Al presionar Ctrl+C, mata ambos procesos
trap "kill $API_PID $WEB_PID 2>/dev/null; echo 'Detenido.'" INT TERM
wait
