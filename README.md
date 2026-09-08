# Reel News Bot

Dos productos en el mismo repo:

1. **CLI de noticias → shorts** (`main.py`): a partir de una noticia, una URL, un
   vídeo largo de YouTube o un tema en tendencia, monta un reel/short vertical
   (1080×1920, ≤ 60 s) con guion, voz e imagen, listo para subir a
   Instagram / TikTok / YouTube Shorts.
2. **App web de Montaje** (`web/` + `api/`): subes una canción con su letra y
   genera un **videoclip por secciones** con fondos de **vídeo IA** (ComfyUI
   local) y la letra **sincronizada con lo que se canta**.

> La documentación de trabajo detallada (arquitectura del Montaje, gotchas de
> Docker/Next, integración con AI Studio) está en **`CLAUDE.md`**.
> Rama con todo el Montaje con vídeo IA: **`fix/local-reel-builder-and-encoding`**.

---

## Arranque

### Con Docker (recomendado)

```bash
docker compose up -d          # backend :8000 · frontend :3000 · whatsapp :3002
```

- Frontend Next.js → <http://localhost:3000> (el Montaje está en `/montaje`)
- Backend FastAPI (`api/server.py`) → <http://localhost:8000>
- Sidecar WhatsApp (QR para publicar) → <http://localhost:3002>

Producción sin GPU: `docker compose -f docker-compose.prod.yml up -d`.

### Sin Docker

Requiere Python 3.11+ y `ffmpeg` del sistema (no por pip).

```bash
pip install -r requirements.txt
bash start.sh                 # levanta backend + frontend + sidecar
```

Copia `.env.example` a `.env` y rellena solo las claves que quieras usar (todas
opcionales para el CLI de noticias; el Montaje con vídeo IA necesita el ComfyUI
del host — ver más abajo).

---

## CLI: noticias, URLs, YouTube y tendencias

```bash
# Temas variados o un tema/categoría concreto
python3 main.py --variado --cantidad 3
python3 main.py --tema tecnologia --cantidad 1
python3 main.py --tema "elecciones en argentina" --cantidad 2
python3 main.py --tema ciencia --duracion-maxima 45

# Artículos puntuales por URL o desde un .txt (si el sitio bloquea la descarga)
python3 main.py --url https://ejemplo.com/articulo-1
python3 main.py --archivo mi_articulo.txt

# Reels a partir de un vídeo largo de YouTube
python3 main.py --youtube https://youtu.be/VIDEO_ID          # recorte real (default)
python3 main.py --youtube URL --modo-youtube narrado         # narración sintética

# Tendencias
python3 main.py --trending-yt --pais AR --cantidad 3
python3 main.py --trending --pais AR --cantidad 3
```

Formato del `.txt` para `--archivo`:

```
TITULO: El titulo de la noticia
FUENTE: Nombre del sitio (opcional)
LINK: https://... (opcional)

Cuerpo completo del articulo, tantos parrafos como quieras.
```

### Modo `clip` de YouTube (default)

1. Descarga el vídeo con `yt-dlp` (sin API key).
2. Con la transcripción y sus marcas de tiempo reales, busca la ventana de
   ~20–60 s con mayor densidad de información (penaliza texto repetido de
   intros/outros/CTAs, premia números y palabras clave).
3. Recorta ese tramo y lo reencuadra a 9:16 (vídeo original centrado sobre un
   fondo desenfocado del mismo vídeo).
4. Quema subtítulos sincronizados con los tiempos reales.

Si el modo `clip` falla (vídeo privado/restringido, yt-dlp no puede
descargarlo…), cae automáticamente a `narrado`.

Los resultados (guion/info `.txt`, audio `.mp3` si aplica, vídeo `.mp4`) se
guardan en `output/`.

---

## App web de Montaje (`/montaje`)

Subes **audio + letra** y el backend genera un clip MP4 por sección de la letra
más un `<slug>_full_reel.mp4` ensamblado.

1. **Guion visual**: un LLM (LM Studio del host → Claude → Gemini) lee la letra y
   escribe un `style_prefix` de dirección de arte + una escena por sección
   (`image_prompt` + `motion_prompt`).
2. **Sincronía de la letra** (`lyric_aligner.py`):
   - Si pegas un `.lrc`, se usa tal cual (exacto).
   - Si no, se aísla la voz con demucs (GPU del host, vía el Centro de Control) y
     `faster-whisper` transcribe la voz limpia y la alinea contra la letra real
     con `difflib`. Idioma `auto` (selector en la UI).
   - Si casan menos del 25 % de las palabras → reparto uniforme y la UI avisa.
   - Render tipo **karaoke**: la línea que suena en grande, la anterior y la
     siguiente en gris.
3. **Fondo de cada sección** con el **ComfyUI local** (`host.docker.internal:8188`):
   - `wan22` (default): fotograma con Flux → animación Wan2.2 I2V (LoRA Lightning).
   - `ltx`: LTX-Video 2B, más rápido.
   - `fal`: API de pago (si `FAL_KEY`).
   - `imagen`: Pollinations + Ken Burns, sin ComfyUI.
   Tras escribir el guion se descarga LM Studio (vía Centro de Control) para
   dejarle la VRAM a ComfyUI.
4. Si una sección falla y hay Centro de Control, se le pide **reiniciar ComfyUI**
   y se reintenta esa sección una vez; si aun así falla, cae a imagen fija sin
   abortar y deja la marca `<clip>.imagen` (al **▶ Reanudar** se reintenta como
   vídeo).
5. **Control del job**: `POST /api/music-clip/jobs/{id}/cancel`,
   `GET /api/music-clip/reanudables`, `POST /api/music-clip/reanudar/{slug}`.
   El formulario se autoguarda en `localStorage`.

### Requisitos del vídeo IA

El Montaje con vídeo IA necesita el ComfyUI de **AI Studio** (`E:\AI-Studio`,
RTX 5070 Ti) encendido, con los modelos I2V + Flux. El backend lo arranca por el
**Centro de Control** del host (`:8090`) desde un botón de la UI.

```
COMFY_URL=http://host.docker.internal:8188
LLM_BASE_URL=http://host.docker.internal:1234/v1
CONTROL_CENTER_URL=http://host.docker.internal:8090
WHISPER_MODEL=small                 # base | small | medium
MONTAJE_XFADE=0.4                    # crossfade entre secciones
MONTAJE_NO_SEPARAR_VOZ=1             # saltar la separación de voz con demucs
MONTAJE_NO_LIBERAR_LM=1              # no descargar LM Studio durante el montaje
FAL_KEY= / FAL_MODEL=                # generador de vídeo de pago (opcional)
ANTHROPIC_API_KEY / GEMINI_API_KEY   # LLM de reserva para el guion
WA_SERVICE_URL=http://whatsapp:3001  # sidecar de WhatsApp (lo fija docker-compose)
```

---

## Desarrollo y mantenimiento

```bash
pip install -r requirements-dev.txt

pytest -q                       # tests
ruff check .                    # lint (pyflakes: nombres sin definir, etc.)
python scripts/doctor.py        # diagnóstico del entorno (ver abajo)
bash   scripts/limpiar.sh       # borra artefactos de prueba (dry-run; --si para aplicar)
```

- **Tests** (`tests/`): lógica pura — parseo de LRC, alineación letra↔audio con
  la transcripción mockeada, reparación de JSON del LLM, resumen extractivo,
  detección de voz, estructura de secciones. Los que necesitan `moviepy`/
  `librosa` se saltan solos si no están instalados.
- **`scripts/doctor.py`**: comprueba ffmpeg/ffprobe, dependencias, frescura de
  `yt-dlp`, `.env`, permisos de `output/`, y si ComfyUI / LM Studio / Centro de
  Control responden. Para los chequeos del Montaje córrelo dentro del contenedor:
  `docker compose exec backend python scripts/doctor.py`.
- **CI** (`.github/workflows/ci.yml`): `py_compile` + `ruff` + `pytest` en Python
  3.11 y 3.12, más una pasada con la suite completa. `dependabot.yml` agrupa las
  actualizaciones de pip/npm/actions en PRs semanales.

---

## Cómo funciona el pipeline del CLI

| Módulo | Rol |
| --- | --- |
| `news_fetcher.py` | Busca noticias por RSS de Google News (sin API key). |
| `article_extractor.py` | Descarga el artículo y extrae el texto principal. |
| `youtube_extractor.py` | Título, canal y transcripción con tiempos de un vídeo. |
| `trending_finder.py` | Temas/vídeos en tendencia (Google Trends + YouTube). |
| `summarizer.py` | Guion del reel (hook + puntos + cierre). IA si hay API key (Ollama → LM Studio → Claude → Gemini → Groq); si no, resumen extractivo. |
| `tts.py` | Texto a voz (edge-tts → gTTS → pyttsx3). |
| `video_builder.py` | Vídeo vertical narrado (fondo Ken Burns + subtítulos karaoke). |
| `video_clipper.py` | Recorte real + reencuadre vertical de un vídeo de YouTube. |
| `main.py` | Orquestador CLI. |

### Módulos del Montaje

| Módulo | Rol |
| --- | --- |
| `lyric_video_builder.py` | Monta el vídeo por secciones + letra. Reanudable. |
| `comfy_video_builder.py` | Guion LLM + workflows de ComfyUI + Centro de Control. |
| `lyric_aligner.py` | Sincronía letra↔audio (LRC / faster-whisper). |
| `voice_detector.py` | Detecta voz de hombre / mujer / mixta (`librosa.pyin`). |
| `api/music_clip.py` | Endpoints del Montaje (subida, generar, cancelar, reanudar, estado). |
| `web/app/montaje/page.tsx` | UI del Montaje. |

---

## Notas y limitaciones

- El resumen sin IA es **extractivo** (elige las oraciones más relevantes del
  original), no genera texto nuevo. Conviene configurar al menos una API key.
- El recorte real de YouTube depende de que el vídeo tenga transcripción y de
  que `yt-dlp` pueda descargarlo. `yt-dlp` va pineado `>=2026.08.19`; YouTube
  rompe compatibilidad a menudo (`pip install --upgrade yt-dlp` dentro del venv).
- La sincronía de la letra por Whisper sobre la mezcla nunca es perfecta: para
  precisión, pega un `.lrc` o sube una pista de voz a cappella.
- **MoviePy 1.0.3** va fijo (la API cambió en la v2). `ffmpeg` del sistema.
- El sistema deja el `.mp4` listo para subir; publicar en IG/TikTok/YouTube
  requiere sus APIs (o subida manual).

## Estructura

```
main.py                  # CLI noticias→shorts (orquestador)
api/                     # FastAPI (server.py monta los routers)
lyric_video_builder.py   # Montaje: vídeo por secciones + letra
comfy_video_builder.py   # Montaje: guion LLM + ComfyUI + Centro de Control
lyric_aligner.py         # Montaje: sincronía letra↔audio
voice_detector.py        # Montaje: hombre/mujer/mixta
video_builder.py video_clipper.py   # CLI: narrado / recorte de YouTube
web/                     # Frontend Next.js (Montaje en app/montaje/)
wa_service/              # Sidecar Node.js de WhatsApp
scripts/                 # doctor.py, limpiar.sh, descargas de modelos, mantener_despierto.ps1
tests/                   # suite de pytest
output/ _uploads/        # reels generados / audios subidos (no se versionan)
```
