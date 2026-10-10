# Publicación de vídeos en YouTube: privado → botón «Publicar» → público

Desde octubre de 2026, los reels **se suben siempre en privado** y no se publican
hasta que lo decides tú con el botón **Publicar** de la web.

## Flujo

1. **Subida privada.** `youtube_uploader.subir_video()` sube con `privacyStatus: "private"`
   (sin `publishAt`) y registra el vídeo en `_config/youtube_publicacion.json`, con estado `pendiente`.
   Vale para todas las subidas: el job con «Subir a YouTube», `/api/publish`, el gestor y el autopublicador.
2. **Botón en la web.** Aparece en dos sitios, en cualquier reel cuyo enlace de YouTube esté
   registrado y siga privado:
   - **Gestor** (`/gestor`), en la tarjeta de cada reel de la cola, junto a la insignia «▶ YouTube».
   - **Inicio** (`/`), en el panel «YouTube» del job recién generado, debajo del enlace «Subido a YouTube».

   Qué se ve en cada caso:
   - **Privado:** insignia «🔒 Privado» y botón **Publicar**.
   - **Publicando:** el botón muestra «Publicando…».
   - **Público:** insignia verde **● Público**, con enlace al vídeo.
   - **No registrado** (vídeos subidos antes del cambio, que ya eran públicos, o URL añadida a mano):
     no aparece nada nuevo.
3. **Al pulsar Publicar** se pide confirmación y después se hace
   `POST /api/youtube/publicacion/{video_id}/publicar`. El backend consulta
   `videos.list(part=status,processingDetails)` y responde según el estado del vídeo:

| Situación en YouTube | Respuesta | Qué pasa |
|---|---|---|
| Procesado (`uploadStatus=processed` y `processingStatus=succeeded` o sin dato) | 200 | `videos.update(part=status)` a `public`, conservando `embeddable`, `license`, `publicStatsViewable`, `selfDeclaredMadeForKids` y `containsSyntheticMedia`. El estado pasa a `publicado` y el log dice `publicado manualmente`. |
| Ya era público | 200 | Idempotente: se marca `publicado` y no se llama a `update`. |
| Aún procesando | 409 | «YouTube todavía está procesando el vídeo, prueba en unos minutos.» No se publica. |
| Fallido, rechazado o borrado | 422 | Se marca `error` y sigue privado. |
| No existe | 404 | Sigue privado. |
| Permisos insuficientes (401/403) | 403 | Mensaje para reconectar YouTube en `/canales`. Sigue privado. |
| Otro error de API o cuota | 502 | Sigue privado. |
| Sin credenciales | 503 | Sigue privado. |

   Los mensajes de error aparecen junto al botón.

## Endpoints

- `GET /api/youtube/publicacion[?estado=pendiente|publicado|error|bloqueado]` devuelve
  `{autopublicar, items[]}`. Cada item lleva `estado` = `privado` | `publico` | `error`.
- `GET /api/youtube/publicacion/{video_id}` devuelve el estado según el registro local, sin consultar
  a YouTube. Si el vídeo no está registrado, responde 404.
- `POST /api/youtube/publicacion/{video_id}/publicar` corresponde al botón Publicar.
- `POST /api/youtube/publicacion/{video_id}/reintentar` solo tiene sentido con el publicador automático.

## Ficheros y logs

- Estado: `_config/youtube_publicacion.json` (`video_id`, `story_id` = nombre del mp4, `titulo`,
  `uploaded_at`, `next_check_at` en UTC, `state`, `alerta`, `history`).
- Log: `_config/youtube_publicacion.log` y `docker logs` del backend, con el prefijo `[YT-Publicacion]`.
  Cada paso deja una línea: subida privada, comprobación de estado, publicado manualmente, error.

## Publicador automático opcional (desactivado por defecto)

Si se arranca el backend con **`YT_AUTOPUBLICAR=1`**, vuelve el comportamiento automático.
A partir de 2h30m tras la subida, cada 5 minutos se comprueba el vídeo:
- Si está procesado, se publica.
- Si sigue procesando, se reintenta 30 minutos después.
- Con 3 errores seguidos, o 24 h sin terminar de procesar, queda `bloqueado` y privado, con una alerta en el log.

Con `YT_AUTOPUBLICAR=0`, o sin definir, el hilo no arranca y el ciclo no publica nada. Ojo: al
activarlo se publicarán los vídeos `pendiente` que ya tengan más de 2h30m.

## Permisos (scopes)

`videos.update` necesita `https://www.googleapis.com/auth/youtube` (o `youtube.force-ssl`).
El OAuth de `/canales` y `scripts/youtube_auth.py` ya piden `youtube.upload` y `youtube`.
Si el token se autorizó en su día solo con `youtube.upload`, el botón devolverá un error de permisos.
En ese caso hay que reconectar YouTube en `/canales`.

## Ojo: enlaces que se comparten nada más subir

`/api/publish` sigue devolviendo la URL en cuanto termina la subida. Varias cosas la comparten
enseguida, mientras el vídeo todavía es privado, así que el enlace no se podrá ver hasta que pulses
Publicar:
- el canal de WhatsApp;
- la confirmación de Telegram;
- la autodistribución a Telegram, X y WhatsApp;
- `distribuidor` (grupos de Telegram y Reddit).

Este cambio no los modifica.

## Pruebas

`python -m pytest tests/test_youtube_publicacion.py -q`. Usan un cliente de YouTube falso y no
hacen llamadas reales a la API.
