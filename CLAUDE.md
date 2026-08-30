# Reel News Bot — generador de reels/shorts

Dos productos en el mismo repo:

1. **CLI de noticias→shorts** (`main.py`): noticia / URL / vídeo de YouTube / tendencia
   → guion → TTS o clip real → vídeo vertical → sube a IG/YT/TikTok.
2. **App web de Montaje** (`web/` + `api/`): subes una canción + su letra y genera
   un videoclip por secciones con **fondos de vídeo IA** (ComfyUI local) y la letra
   **sincronizada con lo que se canta**.

Rama de trabajo actual: **`fix/local-reel-builder-and-encoding`** (todo el Montaje
con vídeo IA, la sincronía de letra, y la integración con AI Studio viven aquí).

## Arranque

```bash
docker compose up -d          # backend :8000, frontend :3000, whatsapp :3002
# o sin Docker:
bash start.sh
```

- **Frontend** Next.js → http://localhost:3000  (Montaje en `/montaje`)
- **Backend** FastAPI (`api/server.py`) → http://localhost:8000
- **WhatsApp sidecar** (QR para publicar) → http://localhost:3002  (mapea a :3001 interno;
  el :3001 del host lo ocupa `open-webui` del proyecto AI Studio)

CLI:
```bash
python3 main.py --tema tecnologia
python3 main.py --youtube https://youtu.be/ID      # reel musical: usa el vídeo real
python3 main.py --trending-yt --pais AR --cantidad 3
```

## El Montaje con vídeo IA (`/montaje`)

Flujo (código en `lyric_video_builder.py` + `comfy_video_builder.py`, endpoints en
`api/music_clip.py`):

1. Un **LLM** (LM Studio del host → Claude → Gemini) lee la letra y escribe un
   guion visual: `style_prefix` + una escena por sección (`image_prompt` +
   `motion_prompt`). `plan_escenas()` tolera JSON malformado del modelo
   (`_json_lenient` + reintento de auto-corrección).
2. **Sincronía de la letra** (`lyric_aligner.py`): si pegas un `.lrc` se usa tal
   cual (exacto); si no, se **aísla la voz con demucs** (GPU del host, vía el
   Centro de Control `POST /api/separate`, ~20 s; `MONTAJE_NO_SEPARAR_VOZ=1` para
   saltarlo) y `faster-whisper` (`WHISPER_MODEL`, def. `small`) transcribe la voz
   limpia y alinea contra la letra real con `difflib`. Idioma `"auto"` (selector
   en la UI). Si <25% de palabras casan → reparto uniforme y la UI avisa en
   amarillo. Una pista a cappella subida se usa directa (sin separar).
   Render **tipo karaoke** (`_frame_karaoke`): 3 líneas: la que suena en color
   grande, la anterior y la siguiente en gris.
3. **Fondo de cada sección** con el **ComfyUI local** (`host.docker.internal:8188`):
   - `wan22` (def.): frame con Flux → animación Wan2.2 I2V (LoRA Lightning, 4 pasos).
   - `ltx`: LTX-Video 2B, más rápido.
   - `fal`: API de pago (si `FAL_KEY`).
   - `imagen`: Pollinations + Ken Burns, sin ComfyUI.
   Tras escribir el guion se **descarga LM Studio** (vía Centro de Control) para
   dejarle la VRAM a ComfyUI — era la causa nº1 de que ComfyUI crasheara a mitad.
4. Si una sección falla, cae a imagen fija **sin abortar** y deja marca
   `<clip>.imagen`; al **▶ Reanudar** se reintenta como vídeo.
5. Se ensambla `<slug>_full_reel.mp4` (crossfade 0,4 s sin descuadrar el audio).

**Job control**: `POST /api/music-clip/jobs/{id}/cancel`, `GET /api/music-clip/reanudables`,
`POST /api/music-clip/reanudar/{slug}` (reusa el plan, salta lo ya hecho). El
formulario se autoguarda en `localStorage` (`montaje_draft_v1`).

## Integración con AI Studio (Centro de Control)

El backend (Docker) llama al Centro de Control del host (`E:\AI-Studio`, `:8090`)
por `host.docker.internal`:
- `POST /api/service/{comfyui,lmstudio}/start` → botón "Arrancar ComfyUI/LM Studio".
- `POST /api/service/lmstudio/unload` → libera la VRAM del modelo tras el guion.
Config: `CONTROL_CENTER_URL`, `COMFY_URL`, `LLM_BASE_URL` en `.env`.
`docker-compose.yml` tiene `extra_hosts: host.docker.internal:host-gateway`.

## Estructura

```
main.py                 # CLI noticias→shorts (orquestador, delega en módulos)
api/                     # FastAPI. server.py monta los routers:
  music_clip.py          #   Montaje (subida, generar, cancelar, reanudar, estado)
  article_index.py music.py library.py publish.py templates.py ...
lyric_video_builder.py   # Montaje: monta el vídeo por secciones + letra
comfy_video_builder.py   # Montaje: guion LLM + workflows ComfyUI + Centro de Control
lyric_aligner.py         # Montaje: sincronía letra↔audio (LRC / faster-whisper)
voice_detector.py        # Montaje: detecta hombre/mujer/mixta (librosa.pyin)
video_clipper.py         # CLI: recorta trozos reales de un vídeo de YouTube
local_reel_builder.py    # CLI: montaje del reel en local
web/app/montaje/page.tsx # UI del Montaje
scripts/                 # descargar_wan_t2v.sh, descargar_ltx.sh, mantener_despierto.ps1
output/                  # reels generados + sidecars *_montaje_plan.json / *_montaje_req.json
_uploads/                # audios subidos al Montaje (persisten)
```

## Reglas / gotchas

- **MoviePy 1.0.3** fijo — no actualizar (la API cambió en v2).
- **ffmpeg** del sistema, no por pip.
- Frontend: `next dev --webpack` en `web/package.json` (Turbopack panica con este
  stack en Docker). No cambiar a turbopack.
- Routers FastAPI que devuelven listas: `@router.get("")`, **nunca** `@router.get("/")`
  (el 307 a URL absoluta `http://backend:8000` rompe el proxy del navegador).
- `docker-compose.yml`: `WATCHPACK_POLLING`/`CHOKIDAR_USEPOLLING` en frontend
  (Windows+bind-mount no propaga inotify); `WHISPER_MODEL`, `hf_cache` volume.
- `web/next.config.ts`: `allowedDevOrigins: ["127.0.0.1"]` (sin esto, abrir la app
  en 127.0.0.1 en vez de localhost la deja sin hidratar → los clics no hacen nada).
- `web/app/layout.tsx`: `suppressHydrationWarning` en html/body (extensiones del
  navegador inyectan atributos).
- `yt-dlp` pineado `>=2026.08.19`, cliente `android_vr` excluido, `deno` como JS
  runtime — ver la memoria del proyecto si vuelven los 403 de YouTube.
- ComfyUI retiene VRAM: no generar canciones con ACE-Step del AI Studio mientras
  ComfyUI esté abierto.

## Variables de entorno (ver `.env.example`)

```
COMFY_URL=http://host.docker.internal:8188
LLM_BASE_URL=http://host.docker.internal:1234/v1
CONTROL_CENTER_URL=http://host.docker.internal:8090
WHISPER_MODEL=small              # base | small | medium
MONTAJE_XFADE=0.4                # crossfade entre secciones
MONTAJE_NO_LIBERAR_LM=1          # no descargar LM Studio durante el montaje
FAL_KEY= / FAL_MODEL=            # generador de vídeo de pago (opcional)
ANTHROPIC_API_KEY / GEMINI_API_KEY   # LLM de reserva para el guion
INSTAGRAM_USERNAME / INSTAGRAM_PASSWORD / YOUTUBE_API_KEY
```

## Producción

`docker-compose.prod.yml`. El Montaje con vídeo IA necesita siempre el ComfyUI
del host (AI Studio), esté donde esté el backend.
