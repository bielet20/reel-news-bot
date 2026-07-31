#!/bin/bash
# Instala SadTalker y descarga los modelos (~1.5 GB).
# Requiere Python 3.10, git y ffmpeg.

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ST_DIR="$SCRIPT_DIR/vendor/sadtalker"
PYTHON="/opt/homebrew/bin/python3.10"

echo "=== Setup SadTalker ==="

# 1. Verificar python3.10
if [ ! -f "$PYTHON" ]; then
    echo "Python 3.10 no encontrado en $PYTHON."
    echo "Instálalo con: brew install python@3.10"
    exit 1
fi
echo "  Python: $($PYTHON --version)"

# 2. Descargar repo (zip, más fiable que git clone en redes lentas)
if [ ! -d "$ST_DIR" ]; then
    echo "  Descargando SadTalker..."
    ZIP_TMP=$(mktemp /tmp/sadtalker_XXXX.zip)
    curl -L --retry 3 --retry-delay 2 \
        "https://github.com/OpenTalker/SadTalker/archive/refs/heads/main.zip" \
        -o "$ZIP_TMP"
    mkdir -p "$ST_DIR"
    unzip -q "$ZIP_TMP" -d /tmp/st_extracted
    mv /tmp/st_extracted/SadTalker-main/* "$ST_DIR/"
    rm -rf "$ZIP_TMP" /tmp/st_extracted
else
    echo "  SadTalker ya instalado."
fi

# 3. Crear venv
if [ ! -d "$ST_DIR/venv" ]; then
    echo "  Creando venv con Python 3.10..."
    "$PYTHON" -m venv "$ST_DIR/venv"
fi

PIP="$ST_DIR/venv/bin/pip"
PYTHON_VENV="$ST_DIR/venv/bin/python"

# 4. Instalar dependencias
echo "  Instalando PyTorch y dependencias..."
"$PIP" install --upgrade pip -q
"$PIP" install torch torchvision torchaudio -q
"$PIP" install -r "$ST_DIR/requirements.txt" -q
"$PIP" install huggingface_hub -q

# 5. Descargar modelos desde HuggingFace
echo "  Descargando modelos SadTalker (~1.5 GB)..."
"$PYTHON_VENV" -c "
from huggingface_hub import snapshot_download
import os
dest = os.path.join('$ST_DIR', 'checkpoints')
snapshot_download(repo_id='vinthony/SadTalker', local_dir=dest, repo_type='model')
print('Modelos OK.')
"

echo ""
echo "=== SadTalker listo ==="
echo "  Directorio: $ST_DIR"
echo "  Para probar: bash setup_sadtalker.sh test"
