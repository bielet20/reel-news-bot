# Reel News Bot — Manual completo

Aplicación local para crear y publicar vídeo de forma automática:

- **Shorts y reels de noticias** (Generar / Gestor): noticia → guion con IA → voz → vídeo vertical → publicación.
- **Videoclips** de canciones con fondos de vídeo IA (Montaje).
- **Cursos y formaciones** en vídeo a partir de tu documentación (Cursos).

Todo corre en tu PC dentro de Docker. La IA de texto está en el Mac y la GPU del PC se usa para las imágenes y los vídeos.

---

## Índice

1. [Arranque rápido](#1-arranque-rápido)
2. [Qué piezas usa la app y cómo saber si funcionan](#2-qué-piezas-usa-la-app-y-cómo-saber-si-funcionan)
3. [Generar](#3-generar)
4. [Gestor](#4-gestor)
5. [Montaje (videoclips)](#5-montaje-videoclips)
6. [Fuentes y verificación](#6-fuentes-y-verificación)
7. [Canales](#7-canales)
8. [TikTok](#8-tiktok)
9. [Biblioteca de imágenes y de música](#9-biblioteca-de-imágenes-y-de-música)
10. [Cursos y formaciones](#10-cursos-y-formaciones)
11. [Settings](#11-settings)
12. [Solución de problemas](#12-solución-de-problemas)
13. [Referencia técnica](#13-referencia-técnica)

---

## 1. Arranque rápido

```bash
cd C:\Dev\reel-news-bot
docker compose up -d
```

| Servicio | Dirección |
|---|---|
| Web (lo que usas) | http://localhost:3000 |
| API (backend) | http://localhost:8000 |
| QR de WhatsApp | http://localhost:3002 |

> ⚠️ La copia que corre de verdad es **`C:\Dev\reel-news-bot`**, no `C:\Users\biel\reel-news-bot`.
> Levanta siempre el stack con `docker compose up -d` desde esa carpeta, nunca con un «Run» suelto
> de Docker Desktop: la imagen del frontend no lleva el código dentro.

**Qué pasa al arrancar el backend** (automático, ver `api/sistema.py`):

1. Crea las carpetas de datos que falten (`output`, `_library`, `_music`, `_templates`, `_uploads`,
   `_tokens`, `_config`, `_cursos`).
2. Comprueba las librerías de Python. Si falta alguna (por ejemplo, porque se recreó el contenedor
   sin reconstruir la imagen), **la instala sola en segundo plano**. Se desactiva con `AUTO_INSTALAR_LIBS=0`.
3. Comprueba todos los servicios y deja el informe en el log (`docker logs reel-news-bot-backend-1 | grep arranque`)
   y en **Settings → Estado del sistema**.

Después de cambiar `requirements.txt` o el `Dockerfile`:

```bash
docker compose build backend && docker compose up -d
```

---

## 2. Qué piezas usa la app y cómo saber si funcionan

La app depende de varias piezas. Algunas son internas (van dentro de Docker) y otras son externas,
en otros equipos o programas.

| Pieza | Dónde está | Para qué sirve | Cómo se arranca |
|---|---|---|---|
| **IA del Mac (LM Studio)** | Mac mini `100.64.207.9:1234`, por Tailscale | Escribe y traduce guiones, temarios de cursos y lecciones | Encender el Mac con LM Studio y su servidor activo, o botón **Despertar** |
| **ComfyUI** | GPU del PC, `host.docker.internal:8188` | Vídeo IA (Flux + LTX/Wan), Portada IA, fondos del Montaje | Botón **Arrancar ComfyUI** (necesita el Centro de Control) o `E:\AI-Studio` |
| **Centro de Control** | PC, `host.docker.internal:8090` | Arrancar ComfyUI / LM Studio desde la web | `E:\AI-Studio\Centro-Control.bat` |
| **Internet** | — | Voz (edge-tts), noticias, imágenes, publicación | — |
| ffmpeg, Chromium, librerías | Dentro del backend | Montar vídeo, capturar diapositivas, leer PDF/Word/PowerPoint | Vienen en la imagen; se reinstalan solas si faltan |
| Web vista desde el backend | `http://frontend:3000` | Fotografiar las diapositivas de los cursos | `docker compose up -d` |
| Disco | `C:\Dev\reel-news-bot` | Vídeos, audios y cursos | Gestor → Almacenamiento → Limpiar |

**Regla del reparto de equipos:** LM Studio va siempre en el Mac. La GPU del PC queda solo para
imagen y vídeo (ComfyUI); no hay que cargar modelos de texto en ella.

### Cómo lo ves en la web

- **Barra superior** (arriba a la derecha):
  - 🟢 *Sistema listo* — todo funciona.
  - 🟠 *IA lista · N servicios apagados* — la IA va, pero hay algo apagado. Al pasar el ratón se ve qué;
    el enlace lleva a Settings.
  - 🔴 *IA del Mac sin respuesta* + botón **Despertar**.
  - 🔴 *Backend sin respuesta* — la API no está levantada: `docker compose up -d`.
- **Arriba de cada sección** aparece un aviso con lo que esa sección necesita:
  - **Rojo**: falta algo obligatorio y la sección no funcionará. Explica cómo arreglarlo y, si se puede,
    muestra un botón (*Despertar el Mac*, *Arrancar ComfyUI*).
  - **Ámbar**: falta algo opcional; solo algunas opciones no estarán disponibles (por ejemplo,
    Vídeo IA en Generar si ComfyUI está apagado).
  - **Gris**: *Todo listo para …* y la hora de la última comprobación.
- **Settings → Estado del sistema**: la lista completa, a qué sección afecta cada fallo y el informe del
  último arranque (librerías reinstaladas, carpetas creadas, errores).

El estado se comprueba cada 20 s, o cada 4 s mientras algo está arrancando. **Volver a comprobar**
lo fuerza al momento.

### Qué necesita cada sección

| Sección | Obligatorio | Opcional |
|---|---|---|
| Generar | IA del Mac, ffmpeg, internet | ComfyUI (Vídeo IA y Portada IA) |
| Gestor | IA del Mac, ffmpeg, internet | ComfyUI (Vídeo IA y Portada IA) |
| Montaje | ComfyUI, IA del Mac, ffmpeg, faster-whisper | Centro de Control (botón de arranque) |
| Fuentes · Canales · TikTok | internet | — |
| Biblioteca | disco | — |
| Música | ffmpeg, disco | — |
| Cursos | IA del Mac, ffmpeg, Chromium, web vista desde el backend, lectores de documentos, internet | — |

La tabla sale de `SECCIONES` en `api/sistema.py`. Si una sección pasa a usar algo nuevo, se añade ahí.

---

## 3. Generar

Crea un vídeo a partir de:

- una noticia descubierta;
- una URL;
- un texto pegado;
- un vídeo de YouTube;
- una canción;
- un tema.

**Modos**

- **Descubrir**: al abrirlo ya aparecen las *alertas virales del scanner*, las mismas que en el Gestor,
  con fuente, score, fecha y quién la contrasta.
  - **Usar →** lee el artículo completo y lo carga en el formulario.
  - Marcando varias, **Añadir a la cola del Gestor**.
  - **Buscar** lanza una búsqueda nueva por idioma y tema.
- **Artículo URL · Texto · Tema**: noticia narrada con voz, imágenes y subtítulos.
- **YouTube**: *Clip* (recorte del vídeo real, es la opción por defecto) o *Narrado*.
- **Música**: reel con la canción real.

**Formato del vídeo**

| Formato | Duración | Estructura del guion |
|---|---|---|
| ⚡ Corto (por defecto) | 10-30 s (30 por defecto) | Gancho en la primera frase, contexto, giro y cierre en pregunta o en bucle. Sin «sígueme» |
| 🎬 Medio | 31-60 s | Gancho y tres revelaciones |
| 📺 Largo (solo noticias) | 2-30 min | Vídeo entero en 4 actos: gancho, contexto, impacto y debate |

Cómo encaja el guion en el tiempo:

- La voz habla a unas 2,3 palabras por segundo (medido), y el guion se dimensiona para la duración elegida.
- Si la voz se pasa del máximo, se acelera como mucho un 15 % en vez de cortar la frase.
- En el Largo, a partir de unos 13 minutos el guion se pide acto a acto. Si la noticia no da para tanto,
  sale más corto en vez de rellenar.

**Reglas fijas**

- Los reels van **siempre en español**, aunque la fuente sea inglesa.
- Si no hay IA para traducir, no se hace el reel y avisa: «enciende el Mac».

**Opciones**

- Imágenes de fondo, voz, música de fondo con volúmenes, avatar hablando, subtítulos karaoke, título,
  texto propio y marca de agua.
- **Vídeo IA en movimiento** (~15 min, necesita ComfyUI).
- **Portada IA** (+3-6 min, necesita ComfyUI).
- **Publicar en YouTube** al terminar.

A la derecha, en pantallas anchas, se ven el trabajo en curso con su log y los **vídeos generados**. Desde
cada vídeo se puede:

- 🎬 aplicar Vídeo IA después;
- ✨ crear la Portada IA;
- ↑ publicar;
- ✏ añadir hotspots;
- descargar o eliminar.

---

## 4. Gestor

Producción en lote y automatización.

- **Tendencias YouTube por nicho** y **Scanner de noticias virales**: buscan solos y dejan *alertas*. En
  cada una se marca y se pulsa *Generar*.
- **Autopublicador**: publica solo lo que cumple las reglas de Fuentes, con un límite diario.
- **Añadir contenido**: por URL, texto manual, Descubrir o subiendo un vídeo.
- **Cola de generación**: estado de cada elemento (pendiente → generando → listo), con estas acciones:
  - generar o regenerar con opciones;
  - publicar en todas las plataformas conectadas;
  - asignar a un hilo temático;
  - borrar archivos.
- **Preferencias de generación**: voz, tipo de contenido y duración (30 s por defecto, deslizador de 10 a 60 s).
- **Almacenamiento**: uso de disco por tipo de archivo, *Simular limpieza* y *Limpiar ahora*.
- **Archivo de noticias**: la auto-limpieza archiva y borra del disco lo que se subió hace más de 7 días.
- **Distribución automática**: captions para Instagram, TikTok y X.

---

## 5. Montaje (videoclips)

Subes una canción y su letra, y genera un videoclip por secciones con fondos de vídeo IA y la
letra sincronizada con lo que se canta (faster-whisper).

- Necesita **ComfyUI** (GPU del PC) y la **IA del Mac**. Si faltan, lo avisa arriba con el botón para
  arrancarlos (a través del Centro de Control).
- Opciones: canción, estilo visual, fondos, formato y opciones.
- Si se corta, **▶ Reanudar** salta lo que ya está hecho. Lo escrito en el formulario se guarda solo.
- Detalles técnicos en `CLAUDE.md` → «El Montaje con vídeo IA».

---

## 6. Fuentes y verificación

- Lista de medios con **nivel de fiabilidad (1-4)** y temática. Se pueden activar, desactivar y añadir.
- **Evaluar una fuente nueva**: mira si otros medios fiables repiten sus titulares, su sensacionalismo,
  si tiene RSS/HTTPS y su volumen. Sugiere un nivel.
- **Qué debe cumplir una noticia para generarse y publicarse sola**: fiabilidad mínima, número de medios
  que la confirman, etc. Lo usa el Autopublicador.

---

## 7. Canales

Credenciales y conexión de cada plataforma de publicación:

- YouTube (perfiles bieninforma2 y rayver);
- Instagram;
- Facebook;
- TikTok;
- X;
- Telegram;
- canal de WhatsApp.

Cada tarjeta muestra si está conectada. Las claves se guardan en `_config/credentials.json`.

---

## 8. TikTok

Publicación manual con la interfaz que exige TikTok para aprobar la app:

1. Conectar la cuenta.
2. Elegir un vídeo.
3. Escribir el texto.
4. Elegir privacidad e interacciones.
5. Publicar.

Necesita `TIKTOK_API_KEY` (Canales → TikTok).

---

## 9. Biblioteca de imágenes y de música

- **Biblioteca**: imágenes y QR reutilizables para los reels (hotspots, fondos).
- **Música**: pistas para la música de fondo de reels y cursos. Se suben aquí y luego se eligen en
  Generar, en el Gestor o en los ajustes de un curso.

---

## 10. Cursos y formaciones

Convierte tu documentación en un curso en vídeo (16:9, 1080p), editable como en un editor de vídeo.

### Flujo

1. **Cursos → Nuevo curso**: título, descripción, público y duración de cada lección.
2. **Documentación**: arrastra o sube PDF, Word (.docx), PowerPoint (.pptx), Markdown o texto,
   o añade URLs de documentación online.
   - Un **PowerPoint** se puede **importar tal cual**: cada diapositiva pasa a ser una escena y sus
     notas del orador, la narración. Si una diapositiva no tiene notas, la IA las escribe.
3. **Proponer temario**: la IA lee la documentación y propone módulos, lecciones y objetivos. En el árbol
   de la izquierda se pueden renombrar, reordenar (↑ ↓), añadir y borrar.
4. **Generar lección** (una a una o *Generar N pendientes*). La IA escribe escenas con diseños variados y
   la narración de cada una, usando **solo tu documentación** e indicando de qué sección sale.
5. **Editar**:
   - **Sobre la diapositiva**: clic en cualquier texto para cambiarlo.
   - **Panel derecho**:
     - diseño (portada, viñetas, imagen + texto, imagen completa, pasos, comparación, código, cita,
       resumen, cuestionario);
     - imagen (subir, generar con IA o quitar);
     - narración con **▶ Escuchar**;
     - duración fija, transición (fundido o corte) y notas.
   - **Línea de tiempo** (abajo):
     - bloques proporcionales a su duración, que se reordenan arrastrando;
     - zoom;
     - *+ Diapositiva*, *+ Vídeo* (grabaciones de pantalla, con inicio y fin), *Duplicar*, *Borrar*;
     - pista de voz: verde = generada, rayado = pendiente.
   - **▶ Vista previa**: reproduce la lección en el navegador, generando antes las voces que falten.
   - Todo se **guarda solo** (arriba: ✓ Guardado).
6. **⚙ Ajustes del curso**:
   - tema de color (5 predefinidos o colores propios);
   - voz;
   - música de fondo, que baja sola cuando habla la voz;
   - subtítulos grabados en el vídeo o no;
   - duración objetivo por lección.
7. **🎬 Renderizar lección** o **Renderizar curso**.
   - Cada lección da un MP4 1920×1080 más su `.srt`.
   - El curso completo va en un solo MP4 con `capitulos.txt` listo para YouTube.

### Cómo se monta el vídeo

- Voz por escena, con caché: solo se regenera si cambia el texto o la voz.
- Cada diapositiva se fotografía en la propia web (página `/cursos/render/...`) con Chromium, así que
  **lo que ves en el editor es lo que sale en el vídeo**.
- ffmpeg une las escenas con fundidos, mezcla la música y añade los subtítulos.
- Una escena dura lo que la voz más 0,7 s, o lo fijado a mano.
- En un clip de vídeo, si la voz en off dura más que el clip, la imagen se congela en el último fotograma.
  Un clip sin voz conserva su sonido original.

### Límites actuales

Está hecha la fase 1. Queda para la fase 2:

- avatar en una esquina;
- dividir clips;
- más transiciones;
- intro y outro;
- 4K;
- importación de PowerPoint idéntica al original (LibreOffice).

---

## 11. Settings

- **Estado del sistema** (arriba): ver el [apartado 2](#2-qué-piezas-usa-la-app-y-cómo-saber-si-funcionan).
- **Destinos de almacenamiento**: copia automática de cada vídeo generado en una carpeta local, Google Drive
  (rclone) o SMB.

---

## 12. Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Barra: *IA del Mac sin respuesta* | Mac apagado, fuera de Tailscale o LM Studio cerrado | Botón **Despertar**; si falla, encender el Mac y abrir LM Studio con el servidor activo |
| Reels leídos en inglés / «Error al generar video» | Sin IA no hay traducción | Ver la fila anterior. Los errores de cada trabajo se ven en `GET localhost:8000/api/jobs` |
| Montaje: aviso rojo de ComfyUI | ComfyUI apagado | Abrir `E:\AI-Studio\Centro-Control.bat` y pulsar **Arrancar ComfyUI** |
| *Backend sin respuesta* | Contenedor caído | `docker compose up -d` desde `C:\Dev\reel-news-bot`; log en `docker logs reel-news-bot-backend-1` |
| «Faltan librerías» en el estado | Contenedor recreado con una imagen vieja | Se instalan solas al arrancar; para dejarlo fijo: `docker compose build backend && docker compose up -d` |
| Un render o una generación de un curso desaparece a medias | Se editó código del backend (uvicorn `--reload` reinicia y las tareas viven en memoria) | Volver a lanzarla |
| Algo de la web «no responde» tras un cambio | Caché del navegador | Recarga forzada (Ctrl+F5) |
| Página a medias al abrirla por `127.0.0.1` o por la IP | Next bloquea orígenes no permitidos en desarrollo | Usar `localhost:3000` o añadir el origen en `web/next.config.ts` → `allowedDevOrigins` |
| Disco lleno | Muchos vídeos | Gestor → Almacenamiento → *Simular limpieza* / *Limpiar ahora* |

---

## 13. Referencia técnica

### Estructura

```
api/            FastAPI (server.py + un router por zona: gestor, scanner, cursos, sistema…)
web/app/        Next.js 16 (una carpeta por sección; components/ compartidos)
main.py         CLI y pipeline de reels (noticia → guion → voz → vídeo)
summarizer.py   Guiones (corto/medio/largo) con LM Studio + respaldo en la nube
course_*.py     Cursos: store (datos), ingest (documentos), builder (IA), render (vídeo)
_config/        Configuración y estado persistente (JSON)
_cursos/        Un directorio por curso
output/         Vídeos generados
```

### Endpoints más usados

| Endpoint | Qué hace |
|---|---|
| `GET /api/sistema/estado` | Estado de todas las piezas y de cada sección |
| `POST /api/sistema/arrancar/{llm\|comfyui}` | Despertar el Mac / arrancar ComfyUI |
| `POST /api/generate` · `GET /api/jobs` | Generar un reel · ver trabajos |
| `GET /api/scanner/notifications` | Alertas virales |
| `POST /api/gestor/items` | Añadir a la cola del Gestor |
| `/api/cursos/...` | Cursos: CRUD, documentos, temario, lecciones, estructura, narración, render, archivos |

### Variables de entorno relevantes (`.env`)

| Variable | Para qué |
|---|---|
| `LLM_BASE_URL`, `LMSTUDIO_MODEL` | IA del Mac (por defecto `qwen/qwen3-8b`) |
| `IA_NUBE=1` | Permite Claude / Gemini / Groq de respaldo si no hay LM Studio |
| `COMFY_URL`, `CONTROL_CENTER_URL` | ComfyUI y Centro de Control del PC |
| `CURSOS_FRONTEND_URL` | Web que fotografía el render de cursos (por defecto `http://frontend:3000`) |
| `AUTO_INSTALAR_LIBS=0` | Desactiva la autoinstalación de librerías al arrancar |
| `MINIATURAS_MODO` | `rapida` (por defecto) o `completa` (Portada IA) |

Más detalle de desarrollo en [`CLAUDE.md`](../CLAUDE.md) y de instalación en [`INSTALL.md`](../INSTALL.md).
