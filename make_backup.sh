#!/usr/bin/env bash
# make_backup.sh — Genera un tar.gz completo de reel-news-bot para llevar a otro equipo.
# Incluye: código, config, tokens OAuth, música, biblioteca de imágenes, .env
# Excluye: output/ (1.2 GB de vídeos generados), caches, logs, node_modules

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="reel-news-bot_backup_${DATE}.tar.gz"
DEST="${1:-$HOME}"   # Primer argumento = carpeta destino; por defecto $HOME

echo ""
echo "=== Backup reel-news-bot ==="
echo "Origen : $SCRIPT_DIR"
echo "Destino: $DEST/$BACKUP_NAME"
echo ""

# Calcular tamaño estimado (excluyendo lo que se va a omitir)
echo "Calculando tamaño..."

tar -czf "$DEST/$BACKUP_NAME" \
  --exclude='.git' \
  --exclude='.DS_Store' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='.env.save' \
  --exclude='output' \
  --exclude='_img_cache' \
  --exclude='_uploads' \
  --exclude='_job_*.log' \
  --exclude='web/node_modules' \
  --exclude='web/.next' \
  --exclude='vendor/sadtalker/checkpoints' \
  --exclude='vendor/sadtalker/venv' \
  --exclude='*.egg-info' \
  --exclude='.venv' \
  --exclude='venv' \
  -C "$(dirname "$SCRIPT_DIR")" \
  "$(basename "$SCRIPT_DIR")"

SIZE=$(du -sh "$DEST/$BACKUP_NAME" | cut -f1)
echo ""
echo "✓ Backup creado: $DEST/$BACKUP_NAME ($SIZE)"
echo ""
echo "Para restaurar en el servidor:"
echo "  scp $DEST/$BACKUP_NAME usuario@servidor:~/"
echo "  ssh usuario@servidor"
echo "  tar -xzf $BACKUP_NAME"
echo "  cd $(basename "$SCRIPT_DIR")"
echo "  # Editar .env con las credenciales del nuevo entorno"
echo "  docker compose up -d"
echo ""
