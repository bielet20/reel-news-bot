#!/bin/bash
# Descarga los modelos necesarios para el modo "Fondos con vídeo IA" del Montaje
# (texto->vídeo puro): Wan2.2-T2V-A14B (High/Low, GGUF Q3_K_S) + la LoRA de
# distilación Lightning T2V (4 pasos). El ComfyUI de E:\AI-Studio ya trae los
# equivalentes I2V; solo faltan los T2V.
#
# Uso:  bash scripts/descargar_wan_t2v.sh  [ruta_de_ComfyUI]
# Por defecto asume  E:\AI-Studio\tools\ComfyUI  (montado como /e/... en Git Bash).
set -euo pipefail

COMFY="${1:-/e/AI-Studio/tools/ComfyUI}"
UNET="$COMFY/models/unet"
LORA="$COMFY/models/loras/Wan2.2-Lightning-T2V"

if [ ! -d "$COMFY/models" ]; then
  echo "No encuentro ComfyUI en: $COMFY"
  echo "Pásalo como primer argumento: bash $0 /ruta/a/ComfyUI"
  exit 1
fi
mkdir -p "$UNET" "$LORA"

HF="https://huggingface.co"
dl() {  # url  destino
  # curl -C - reanuda una descarga a medias y no hace nada si ya está completa.
  echo "[dl] $2"
  curl -L -C - --retry 5 --retry-delay 5 --fail -o "$2" "$1"
  echo "[ok] $2 ($(du -h "$2" | cut -f1))"
}

dl "$HF/QuantStack/Wan2.2-T2V-A14B-GGUF/resolve/main/HighNoise/Wan2.2-T2V-A14B-HighNoise-Q3_K_S.gguf" \
   "$UNET/Wan2.2-T2V-A14B-HighNoise-Q3_K_S.gguf"
dl "$HF/QuantStack/Wan2.2-T2V-A14B-GGUF/resolve/main/LowNoise/Wan2.2-T2V-A14B-LowNoise-Q3_K_S.gguf" \
   "$UNET/Wan2.2-T2V-A14B-LowNoise-Q3_K_S.gguf"
dl "$HF/lightx2v/Wan2.2-Lightning/resolve/main/Wan2.2-T2V-A14B-4steps-lora-rank64-Seko-V1.1/high_noise_model.safetensors" \
   "$LORA/high_noise_model.safetensors"
dl "$HF/lightx2v/Wan2.2-Lightning/resolve/main/Wan2.2-T2V-A14B-4steps-lora-rank64-Seko-V1.1/low_noise_model.safetensors" \
   "$LORA/low_noise_model.safetensors"

echo
echo "Listo. Reinicia ComfyUI para que detecte los modelos nuevos."
