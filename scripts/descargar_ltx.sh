#!/bin/bash
# Descarga lo que falta para usar el generador "LTX-Video 2B" en el Montaje.
# El modelo GGUF (ltx-video-2b-v0.9-Q6_K.gguf) ya viene con el ComfyUI de
# E:\AI-Studio; faltan el text encoder T5-XXL y la VAE de LTX.
#
# Uso:  bash scripts/descargar_ltx.sh  [ruta_de_ComfyUI]
set -euo pipefail
COMFY="${1:-/e/AI-Studio/tools/ComfyUI}"
[ -d "$COMFY/models" ] || { echo "No encuentro ComfyUI en: $COMFY"; exit 1; }
mkdir -p "$COMFY/models/text_encoders" "$COMFY/models/vae"

dl(){ echo "[dl] $2"; curl -L -C - --retry 5 --retry-delay 5 --fail -o "$2" "$1"; echo "[ok] $2 ($(du -h "$2"|cut -f1))"; }

dl "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors" \
   "$COMFY/models/text_encoders/t5xxl_fp8_e4m3fn.safetensors"
dl "https://huggingface.co/city96/LTX-Video-gguf/resolve/main/LTX-Video-VAE-BF16.safetensors" \
   "$COMFY/models/vae/LTX-Video-VAE-BF16.safetensors"

echo
echo "Listo (~5.7 GB). Reinicia ComfyUI para que los detecte."
