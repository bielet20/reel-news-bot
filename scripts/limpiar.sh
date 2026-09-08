#!/bin/bash
# Borra artefactos generados y temporales que se acumulan al probar el bot:
# reels de output/, audios subidos al Montaje, cachés de Python y restos de
# ComfyUI/moviepy/yt-dlp. NO toca código, ni _tokens/, ni _library/, ni .env.
#
# Uso:
#   bash scripts/limpiar.sh            # muestra lo que borraría (dry-run)
#   bash scripts/limpiar.sh --si       # borra de verdad
#   bash scripts/limpiar.sh --si --todo-uploads   # además vacía _uploads/
set -euo pipefail
cd "$(dirname "$0")/.."

APLICAR=0
UPLOADS=0
for arg in "$@"; do
  case "$arg" in
    --si|-y|--yes)      APLICAR=1 ;;
    --todo-uploads)     UPLOADS=1 ;;
    *) echo "arg desconocido: $arg"; exit 1 ;;
  esac
done

rm_glob() {  # rm_glob "descripción" patrón...
  local desc="$1"; shift
  local encontrados=()
  for p in "$@"; do
    for f in $p; do [ -e "$f" ] && encontrados+=("$f"); done
  done
  [ ${#encontrados[@]} -eq 0 ] && return 0
  echo "  $desc: ${#encontrados[@]} elemento(s)"
  if [ "$APLICAR" = "1" ]; then
    rm -rf "${encontrados[@]}"
  else
    printf '    %s\n' "${encontrados[@]}" | head -n 10
    [ ${#encontrados[@]} -gt 10 ] && echo "    …"
  fi
}

echo "[limpiar] $([ "$APLICAR" = 1 ] && echo 'BORRANDO' || echo 'dry-run (usa --si para borrar)')"

rm_glob "reels y sidecars de output/" \
  "output/*.mp4" "output/*.mp3" "output/*_info.txt" "output/*_guion.txt" \
  "output/*_caption.txt" "output/*_fuente.json" "output/*_montaje_plan.json" \
  "output/*_montaje_req.json" "output/*.imagen" "output/*_karaoke_test.png" \
  "output/*_concat_list.txt"

rm_glob "logs de jobs" "_job_*.log"
rm_glob "cachés de Python" "__pycache__" "*/__pycache__" ".pytest_cache" ".ruff_cache"
rm_glob "temporales de yt-dlp/moviepy" "_ytsrc_*" "_tmp_*" "_mus_audio_*" "_imgs_*" "_img_cache/*"
rm_glob "temporales de ComfyUI (TEMP)" "${TMPDIR:-/tmp}/comfy_*" "${TMPDIR:-/tmp}/_lyric_*"

if [ "$UPLOADS" = "1" ]; then
  rm_glob "audios subidos al Montaje (_uploads/)" "_uploads/*"
else
  echo "  (_uploads/ se conserva; usa --todo-uploads para vaciarlo)"
fi

echo "[limpiar] hecho."
