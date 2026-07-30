# Reel News Bot

Sistema en Python que genera automaticamente reels/shorts verticales
(1080x1920, Instagram Reels / TikTok / YouTube Shorts, maximo 60 segundos) a
partir de tres tipos de fuente:

- **Noticias/articulos**: busca noticias por tema (o recibe un link puntual) y
  arma un guion narrado con hook + puntos clave + cierre.
- **Videos largos de YouTube**: descarga el video real, detecta el tramo mas
  informativo segun su transcripcion, lo recorta y lo reencuadra a vertical
  (recorte real, no una narracion sintetica sobre fondo generico).
- **Tendencias**: busca temas/videos en tendencia (Google Trends / YouTube) y
  genera reels automaticamente sobre lo que esta siendo mas buscado ese dia.

Caracteristicas:

- Guion generado por IA si hay una API key configurada (Claude, Gemini o
  Groq, con fallback automatico entre ellas y a un resumen extractivo sin IA
  si no hay ninguna clave).
- Audio narrado con voces neuronales (edge-tts, gratis), con fallback a gTTS
  y a un motor offline si no hay internet.
- Subtitulos animados palabra por palabra (estilo karaoke/CapCut),
  sincronizados con el audio.
- Fondo dinamico con efecto de zoom lento (Ken Burns): foto real relacionada
  al tema si hay `PEXELS_API_KEY`, o un degradado procedural con viñeta y
  grano si no.
- Para videos de YouTube: recorte real del tramo mas denso en informacion,
  reencuadrado a vertical (video centrado sobre un fondo desenfocado del
  mismo video) con subtitulos quemados sincronizados con el video original.

Todo con herramientas gratuitas — ninguna API de pago es obligatoria; el bot
funciona igual de punta a punta sin configurar ninguna clave (ver
`.env.example` para las mejoras opcionales).

## Instalacion

Requiere Python 3.9+ y `ffmpeg` instalado en el sistema (`brew install ffmpeg`
en Mac, o `apt install ffmpeg` en Linux).

```bash
pip install -r requirements.txt
```

Opcional: copia `.env.example` a `.env` y completa las claves que quieras
usar (todas son opcionales, ver comentarios en el archivo).

## Uso: noticias y articulos

```bash
# Temas variados (tecnologia, mundo, negocios, ciencia, salud, deportes, entretenimiento)
python3 main.py --variado --cantidad 3

# Un tema/categoria especifico
python3 main.py --tema tecnologia --cantidad 1

# Un tema libre (busqueda por texto)
python3 main.py --tema "elecciones en argentina" --cantidad 2

# Limitar duracion del video (por defecto 60s)
python3 main.py --tema ciencia --duracion-maxima 45

# Pasar uno o varios links de articulos puntuales (en vez de buscar por tema)
python3 main.py --url https://ejemplo.com/articulo-1
python3 main.py --url https://ejemplo.com/articulo-1 --url https://ejemplo.com/articulo-2
```

Con `--url`, el sistema descarga esa pagina, detecta automaticamente el titulo
y la fuente (usando las etiquetas `og:title` / `og:site_name` o el `<h1>` de la
pagina), extrae el texto del articulo y corre el mismo pipeline de guion + TTS
+ video. Se puede repetir `--url` tantas veces como articulos se quieran
convertir, y se ignoran `--tema`/`--variado` si se usa `--url`.

### Cuando un sitio bloquea la descarga automatica

Algunos sitios (proteccion anti-bots, login, paywalls, o paginas que cargan el
contenido con JavaScript) van a rechazar la descarga automatica aunque la
pagina sea perfectamente publica para cualquier persona con navegador. En ese
caso, copia el articulo a un `.txt` con este formato:

```
TITULO: El titulo de la noticia
FUENTE: Nombre del sitio (opcional)
LINK: https://... (opcional)

Aca va el cuerpo completo del articulo, tantos parrafos como quieras.
Puede tener varias lineas.
```

Y corre:

```bash
python3 main.py --archivo mi_articulo.txt
```

Se puede repetir `--archivo` para procesar varios a la vez, y tambien se puede
combinar con `--url` en la misma corrida.

## Uso: reels a partir de videos largos de YouTube

```bash
# Recorta el tramo mas informativo del video real, reencuadrado a vertical
# con subtitulos sincronizados (no requiere API key)
python3 main.py --youtube https://youtu.be/VIDEO_ID

# Varios videos de YouTube en una sola corrida
python3 main.py --youtube URL1 --youtube URL2

# (Opcional) en vez de recortar el video real, genera una narracion sintetica
# nueva a partir de la transcripcion, sobre un fondo generico
python3 main.py --youtube URL --modo-youtube narrado
```

El modo por defecto (`clip`) hace lo siguiente:

1. Descarga el video con `yt-dlp` (sin API key de YouTube).
2. Usa la transcripcion con marcas de tiempo reales para encontrar la ventana
   de ~20-60 segundos con mayor densidad de datos/informacion (no el texto
   mas repetido: se penaliza el texto que se repite identico, tipico de
   intros/outros/CTAs, y se premian numeros y palabras clave informativas).
3. Recorta ese tramo del video original y lo reencuadra a 9:16: el video
   original centrado, sobre un fondo desenfocado del mismo video (sin
   deformar ni recortar el contenido real).
4. Quema subtitulos sincronizados con los tiempos reales de la transcripcion.

Si el modo `clip` falla por algun motivo (video privado/restringido, yt-dlp
no puede descargarlo, etc.), el sistema cae automaticamente al modo
`narrado` para igual generar un reel.

## Uso: tendencias

```bash
# Videos en tendencia de YouTube (busca temas trending y ordena por vistas)
python3 main.py --trending-yt --pais AR --cantidad 3

# Noticias sobre los temas mas buscados del dia (Google Trends + Google News)
python3 main.py --trending --pais AR --cantidad 3
```

`--pais` acepta cualquier codigo ISO 3166-1 alpha-2 (AR, US, ES, MX, CO, ...).

---

Los resultados (guion/info .txt, audio .mp3 si aplica, video .mp4) se guardan
en la carpeta `output/`.

## Como funciona el pipeline

1. **news_fetcher.py** — busca noticias recientes usando el feed RSS de Google
   News (gratis, sin API key), para el tema o categoria elegida.
2. **article_extractor.py** — descarga el articulo completo y extrae el texto
   principal (parrafos), para tener mas contexto que solo el titular.
3. **youtube_extractor.py** — extrae titulo, canal y transcripcion (con
   marcas de tiempo reales) de un video de YouTube, sin API key.
4. **trending_finder.py** — encuentra temas/videos en tendencia via Google
   Trends y busqueda de YouTube, sin API key.
5. **summarizer.py** — genera el guion del reel (hook + puntos clave + cierre,
   ~120-140 palabras). Usa IA si hay alguna API key configurada (orden:
   Ollama local -> Claude -> Gemini -> Groq), y cae a un resumen extractivo
   por frecuencia de palabras si no hay ninguna disponible.
6. **tts.py** — convierte el guion en audio narrado (edge-tts -> gTTS ->
   pyttsx3, en ese orden de preferencia).
7. **video_builder.py** — genera el video de un articulo/transcripcion
   narrada: fondo dinamico (foto real o degradado procedural) con zoom Ken
   Burns, titulo arriba, subtitulos karaoke sincronizados con el audio.
8. **video_clipper.py** — genera el video de un recorte real de YouTube:
   descarga el video, detecta el mejor tramo, reencuadra a vertical y quema
   subtitulos sincronizados con el video original.
9. **main.py** — orquesta todo el proceso de punta a punta (CLI).

## Notas y limitaciones a tener en cuenta

- El resumen sin IA es **extractivo** (selecciona las oraciones mas
  relevantes del articulo original), no genera texto nuevo. Es gratis y
  funciona offline, pero la calidad de redaccion es mas simple que la de un
  guion hecho por una IA generativa; por eso conviene configurar al menos una
  de las API keys opcionales (ver `.env.example`).
- El recorte real de YouTube (`--modo-youtube clip`) depende de que el video
  tenga transcripcion/subtitulos disponibles y de que `yt-dlp` pueda
  descargarlo (puede fallar en videos privados, con restriccion de edad/region,
  o si YouTube cambia algo del lado de ellos). Cuando falla, se usa
  automaticamente el modo `narrado` como respaldo.
- Los tiempos de los subtitulos karaoke (modo articulo/narrado) son una
  **estimacion proporcional** por palabra a partir de la duracion total del
  audio, no una alineacion forzada exacta con el TTS. En la mayoria de los
  casos se ve bien sincronizado, pero puede haber un pequeño desfasaje en
  guiones muy largos.
- Google News RSS y Google Trends a veces limitan la cantidad de resultados o
  cambian de formato; si una busqueda devuelve una lista vacia, probar con
  otro tema/pais o revisar la conexion a internet.
- Para publicar directamente en Instagram/TikTok/YouTube hace falta ademas
  usar sus APIs oficiales (o subir el mp4 manualmente); este sistema genera el
  video listo para subir, no lo publica automaticamente.

## Estructura de archivos

```
reel_news_bot/
├── main.py                # orquestador principal (CLI)
├── news_fetcher.py         # busqueda de noticias (RSS)
├── article_extractor.py    # descarga y extraccion de texto del articulo
├── youtube_extractor.py    # transcripcion + metadatos de YouTube (con tiempos)
├── trending_finder.py      # temas/videos en tendencia (Google Trends + YouTube)
├── summarizer.py            # resumen + guion del reel (con o sin IA)
├── tts.py                    # texto a voz (edge-tts / gTTS / pyttsx3)
├── video_builder.py          # video vertical narrado (articulos/transcripciones)
├── video_clipper.py          # recorte real + reencuadre vertical (YouTube)
├── requirements.txt
├── .env.example              # variables opcionales (API keys, voz, modelo)
└── output/                  # aqui se guardan los reels generados
```
