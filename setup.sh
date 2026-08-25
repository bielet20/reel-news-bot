#!/bin/bash
# setup.sh — Instalación completa de Reel News Bot en un equipo nuevo
# Uso: bash setup.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
info() { echo -e "${BLUE}→${NC} $1"; }

echo ""
echo "╔══════════════════════════════════════╗"
echo "║        Reel News Bot — Setup         ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ─── 1. Requisitos del sistema ─────────────────────────────────────────────

info "Verificando requisitos del sistema..."

check_cmd() {
    if command -v "$1" &>/dev/null; then
        ok "$1 encontrado ($(command -v $1))"
        return 0
    else
        fail "$1 NO encontrado"
        return 1
    fi
}

MISSING=0
check_cmd python3    || MISSING=1
check_cmd node       || MISSING=1
check_cmd npm        || MISSING=1
check_cmd ffmpeg     || MISSING=1
check_cmd yt-dlp     || MISSING=1

if [ "$MISSING" = "1" ]; then
    echo ""
    echo "Instala los requisitos faltantes:"
    echo "  macOS:  brew install python node ffmpeg yt-dlp"
    echo "  Ubuntu: sudo apt install python3 nodejs npm ffmpeg && pip install yt-dlp"
    echo ""
    read -p "¿Continuar de todos modos? [s/N] " resp
    [[ "$resp" =~ ^[sS]$ ]] || exit 1
fi

# rclone (opcional, para Drive/SMB)
if command -v rclone &>/dev/null; then
    ok "rclone encontrado — Drive/SMB disponibles"
else
    warn "rclone no encontrado — Drive/SMB no disponibles hasta instalarlo"
    echo "       Para instalarlo: brew install rclone  |  curl https://rclone.org/install.sh | bash"
fi

echo ""

# ─── 2. Variables de entorno ───────────────────────────────────────────────

info "Configurando .env..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    ok ".env creado desde .env.example"
    warn "Edita .env con tus claves antes de arrancar la app"
else
    ok ".env ya existe"
fi

# ─── 3. Dependencias Python ────────────────────────────────────────────────

echo ""
info "Instalando dependencias Python..."
if python3 -m pip install -r requirements.txt --quiet; then
    ok "Dependencias Python instaladas"
else
    fail "Error instalando dependencias Python"
    exit 1
fi

# ─── 4. Dependencias web (Next.js) ────────────────────────────────────────

echo ""
info "Instalando dependencias del frontend (Next.js)..."
cd web
if npm install --silent 2>/dev/null; then
    ok "Dependencias frontend instaladas"
else
    fail "Error instalando dependencias frontend"
    exit 1
fi
cd "$SCRIPT_DIR"

# ─── 5. WhatsApp sidecar (Node.js) ────────────────────────────────────────

echo ""
info "Instalando dependencias de WhatsApp sidecar..."
cd wa_service
if npm install --silent 2>/dev/null; then
    ok "WhatsApp sidecar instalado"
else
    warn "Error instalando WhatsApp sidecar (opcional)"
fi
cd "$SCRIPT_DIR"

# ─── 6. yt-dlp — configurar JS runtime ────────────────────────────────────

echo ""
info "Configurando yt-dlp..."

YT_DLP_CONFIG_DIR="$HOME/.config/yt-dlp"
YT_DLP_CONFIG="$YT_DLP_CONFIG_DIR/config"
mkdir -p "$YT_DLP_CONFIG_DIR"

NODE_PATH=$(command -v node 2>/dev/null || echo "")

if [ -f "$YT_DLP_CONFIG" ]; then
    ok "Config de yt-dlp ya existe ($YT_DLP_CONFIG)"
else
    cat > "$YT_DLP_CONFIG" <<EOF
--js-runtimes node:${NODE_PATH}
--remote-components ejs:github
EOF
    ok "Config de yt-dlp creado con Node.js como runtime JS"
fi

# ─── 7. Carpetas de datos ──────────────────────────────────────────────────

echo ""
info "Creando carpetas de datos..."
for dir in output _library _music _templates _uploads _tokens _config; do
    mkdir -p "$dir"
done
ok "Carpetas creadas: output/ _library/ _music/ _templates/ _uploads/ _tokens/ _config/"

# ─── 8. rclone — configuración guiada (opcional) ──────────────────────────

if command -v rclone &>/dev/null; then
    echo ""
    read -p "¿Configurar rclone ahora para Google Drive o SMB? [s/N] " resp
    if [[ "$resp" =~ ^[sS]$ ]]; then
        echo "  Abriendo configuración interactiva de rclone..."
        echo "  Crea un remote llamado 'gdrive' para Drive o 'nas' para red local."
        rclone config
    else
        warn "Puedes configurar rclone más tarde con: rclone config"
    fi
fi

# ─── 9. Resumen ────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                    Setup completado                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Próximos pasos:"
echo ""
echo "  1. Edita .env con tus claves API (mínimo ninguna es obligatoria)"
echo "     nano .env"
echo ""
echo "  2. Arranca la app:"
echo "     bash start.sh"
echo ""
echo "  3. Abre http://localhost:3000 en el navegador"
echo ""
echo "  4. Para Telegram: ve a /canales → conecta tu bot"
echo "     (Crea un bot en https://t.me/BotFather)"
echo ""
echo "  5. Para WhatsApp: start.sh ya arranca el sidecar."
echo "     Ve a /canales → Ver QR → escanea con WhatsApp"
echo ""
echo "  6. Para almacenamiento Drive/SMB:"
echo "     rclone config  (luego configura en /settings de la app)"
echo ""
