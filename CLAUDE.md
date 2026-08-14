# Reel News Bot — Generador de Shorts Automáticos

Bot Python que genera YouTube Shorts/Reels automáticamente desde noticias, URLs, videos de YouTube o tendencias. Descarga, genera audio con gTTS, monta el vídeo vertical con MoviePy y lo sube a Instagram/YouTube.

## Stack

- **Lenguaje:** Python 3
- **Video:** MoviePy 1.0.3, ffmpeg (requerido en sistema)
- **Audio:** gTTS (text-to-speech)
- **Web scraping:** feedparser, requests, BeautifulSoup4
- **YouTube:** `youtube-transcript-api`
- **Deploy:** Docker (`docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.cpu.yml`)

## Uso

```bash
python3 main.py --tema tecnologia
python3 main.py --tema "elecciones en argentina" --cantidad 3
python3 main.py --variado                          # mezcla temas
python3 main.py --url https://ejemplo.com/noticia  # URL directa
python3 main.py --youtube https://youtu.be/ID      # desde YouTube
python3 main.py --trending-yt --pais AR --cantidad 3
python3 main.py --trending --pais ES               # Google Trends
```

## Estructura

```
main.py                    # Orquestador principal — entry point
news_fetcher.py            # Descarga feeds RSS
article_extractor.py       # Extrae texto de artículos
news_curator.py            # Selecciona las mejores noticias
image_pipeline.py          # Genera imágenes para el vídeo
music_video_builder.py     # Monta vídeos musicales
lyric_video_builder.py     # Vídeos con letras
avatar_generator.py        # Avatares para narración
accounts_manager.py        # Gestión de cuentas redes sociales
instagram_uploader.py      # Sube a Instagram
music_analyzer.py          # Análisis de música
hotspot_manager.py         # Gestión de hotspots de red
api/                       # API REST del bot
_library/                  # Biblioteca de clips/música
_templates/                # Plantillas de vídeo
_music/                    # Música de fondo
_uploads/                  # Vídeos generados listos para subir
```

## Variables de entorno

```
# Instagram
INSTAGRAM_USERNAME=
INSTAGRAM_PASSWORD=
# YouTube Data API (opcional, para trending)
YOUTUBE_API_KEY=
# Otros según módulos activos
```

## Reglas clave

- `main.py` es el orquestador — no contiene lógica, delega a los módulos
- MoviePy **versión 1.0.3** fija — no actualizar, la API cambió en v2
- ffmpeg debe estar instalado en el sistema (no via pip)
- Los vídeos generados van a `_uploads/` antes de subirse
- Para producción usar `docker-compose.prod.yml`
