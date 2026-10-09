# Reel News Bot — generador de reels/shorts

Tres productos en el mismo repo (manual de usuario: **`docs/MANUAL.md`**):

1. **Noticias → shorts** (`main.py` + web Generar/Gestor): noticia / URL / vídeo de YouTube /
   tendencia → guion (formato Corto 10-30 s, Medio ≤60 s o Largo 2-30 min) → TTS o clip real
   → vídeo → sube a IG/YT/TikTok.
2. **Montaje** (`/montaje`): subes una canción + su letra y genera un videoclip por secciones
   con **fondos de vídeo IA** (ComfyUI local) y la letra **sincronizada con lo que se canta**.
3. **Cursos y formaciones** (`/cursos`): documentación → temario → lecciones con diapositivas
   y narración → editor con línea de tiempo → vídeo 16:9.

El stack que corre de verdad monta **`C:\Dev\reel-news-bot`** (rama `main`), no
`C:\Users\biel\reel-news-bot`.

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

## Estado del sistema y arranque (`api/sistema.py`)

Manual de usuario completo: **`docs/MANUAL.md`**.

- **Al arrancar** el backend (`@app.on_event("startup")` → `preparar_arranque`): crea las
  carpetas de datos, y si falta alguna librería de `LIBRERIAS` la **instala en segundo plano**
  con pip (`AUTO_INSTALAR_LIBS=0` lo desactiva). Deja un informe `[arranque] …` en el log.
- `GET /api/sistema/estado` (caché 8 s): componentes (`llm`, `comfyui`, `control_center`,
  `internet`, `frontend`, `ffmpeg`, `chromium`, `libs_documentos`, `whisper`, `librerias`,
  `disco`, `carpetas`) y, por sección, qué falta (`SECCIONES`: obligatorio / opcional).
  `POST /api/sistema/arrancar/{llm|comfyui}` despierta el Mac o arranca ComfyUI vía Centro de Control.
- **Web**: `components/estadoSistema.ts` (un único sondeo compartido, 20 s / 4 s si algo arranca),
  `AvisoServicios` arriba de cada página (`seccion="..."`), `EstadoMac` en la barra (resumen) y
  `PanelEstadoSistema` en Settings. **Página nueva → añadir `<AvisoServicios seccion=…/>` y su
  entrada en `SECCIONES`.**

## Cursos y formaciones (`/cursos`)

Documentación → temario → lecciones (escenas = diapositiva + narración) → editor → vídeo 16:9.

- **Datos**: `_cursos/<id>/curso.json` + `docs/` (texto extraído, `originales/`) + `assets/`
  (imágenes, `videos/` = grabaciones de pantalla) + `audio/` + `render/`. Rutas en el JSON
  siempre **relativas al curso**; se sirven por `GET /api/cursos/{id}/archivo/{ruta}`.
  Modelo y utilidades en `course_store.py`.
- **Ingesta** (`course_ingest.py`): PDF (pymupdf, secciones por el índice del PDF), .docx,
  .pptx (además devuelve cada diapositiva con viñetas, imágenes y **notas → narración**),
  Markdown/texto y URLs (`article_extractor`).
- **IA** (`course_builder.py`): `proponer_temario`, `generar_leccion` (JSON de escenas con
  layout; usa solo la documentación, sección relevante por solapamiento de palabras),
  `importar_pptx`. LM Studio con la cadena de `summarizer._completar_largo`.
- **Render** (`course_render.py`): voz por escena con caché por hash (texto+voz) → PNG de
  cada diapositiva fotografiando **la página del frontend** `/cursos/render/<curso>/<escena>`
  con el Chromium de Playwright del backend (`CURSOS_FRONTEND_URL`, por defecto
  `http://frontend:3000`) → ffmpeg libx264 (NVENC no funciona dentro del contenedor) →
  música con sidechain + subtítulos .srt (quemados si `subtitulos`). Clips de vídeo:
  recorte inicio/fin; si la voz en off es más larga, se congela el último fotograma.
- **Un solo renderizador**: `web/app/cursos/components/SlideRender.tsx` (sin hooks, sirve
  como componente de servidor). Lo usan el editor (con edición en línea) y la página de
  render. Cambiar un layout = cambia el editor y el vídeo a la vez.
- **Tareas**: cola de un solo hilo en `api/cursos.py` (IA y render, una a la vez). Viven en
  memoria: **un `--reload` de uvicorn (editar cualquier .py) mata la tarea en curso**.
- **Autoguardado del editor**: `PUT /api/cursos/{id}/estructura` con los módulos completos;
  el servidor conserva `audio`/`render`/`estado` y no deja que una copia vieja vacíe una
  lección recién generada. Cambiar la narración invalida el audio.
- Fase 2 pendiente: avatar en una esquina (`avatar_generator`), más transiciones,
  intro/outro, 4K, render fiel de .pptx con LibreOffice.

## Integración con AI Studio (Centro de Control)

El backend (Docker) llama al Centro de Control del host (`E:\AI-Studio`, `:8090`)
por `host.docker.internal`:
- `POST /api/service/{comfyui,lmstudio}/start` → botón "Arrancar ComfyUI/LM Studio".
- `POST /api/service/lmstudio/unload` → libera la VRAM del modelo tras el guion.
Config: `CONTROL_CENTER_URL`, `COMFY_URL`, `LLM_BASE_URL` en `.env`.
`docker-compose.yml` tiene `extra_hosts: host.docker.internal:host-gateway`.

## Centro de Redes (`/redes`, `centro_redes.py`, `api/redes.py`)

Un solo sitio para las cuentas de redes y los canales (marcas) que las usan;
todas las aplicaciones publican por aquí.
- **Cuenta** = una conexión a una red (p. ej. YouTube RAYVERMUSIC). Sus secretos
  siguen en `_tokens/<fichero>.json`; el registro solo apunta al fichero.
- **Canal** = marca (Bieninforma2, RAYVER, RayverSec…): qué cuenta usa en cada red
  y cómo publica (categoría, pie, tags, playlist).
- Registro `_config/redes.json` (se siembra la primera vez con los tokens que ya
  existían); historial `_config/redes_publicaciones.json`.
- `POST /api/redes/publicar` (form: `canal`, `titulo`, `descripcion`, `redes`,
  `privacidad`, `origen` + `archivo` o `ruta` dentro de `output/`/`_uploads/`) →
  `{trabajo}`; resultado en `GET /api/redes/trabajos/{id}`. Las subidas grandes van
  directas a `:8000` (el proxy de Next corta cuerpos de >10 MB).
- Conectar YouTube: `GET /api/redes/cuentas/{id}/conectar` usa la misma app y el
  mismo redirect que Canales (`/api/accounts/youtube/callback`, que reparte por
  `state`). Si el token es de otro canal, no se guarda; al subir se exige el
  `channel_id` del canal (nunca se sube al canal equivocado).
- `youtube_uploader.subir_video(token_file=…)`: un canal sin token NO cae al `.env`
  (que es Bieninforma2). Cachés de servicio y playlists por token.
- AI Studio (`E:\AI-Studio\tools\EstudioIA\publicar.py`) publica por esta API.
- Fase 1: solo YouTube se publica desde el Centro; FB/IG/TikTok/X/WhatsApp siguen
  por el sistema de reels (`/canales`) y aquí solo se ve su estado.
- Tests: `tests/test_centro_redes.py`.

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
