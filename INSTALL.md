# Instalación — Reel News Bot

Guía para desplegar desde cero en un servidor Linux o un nuevo equipo a partir del backup.

---

## Requisitos del servidor

| Componente | Mínimo | Recomendado |
|---|---|---|
| OS | Ubuntu 22.04 / Debian 12 | Ubuntu 22.04 LTS |
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Disco | 20 GB libres | 50 GB+ |
| Docker | 24+ | última versión |
| Docker Compose | v2.20+ | última versión |
| GPU (opcional) | — | NVIDIA con CUDA 12.8 (para Montaje IA) |

---

## 1. Instalar Docker

```bash
# Ubuntu / Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker --version   # debe mostrar 24+
```

---

## 2. Transferir y descomprimir el backup

```bash
# Desde tu Mac/PC local:
scp reel-news-bot_backup_*.tar.gz usuario@servidor:~/

# En el servidor:
tar -xzf reel-news-bot_backup_*.tar.gz
cd reel-news-bot
```

---

## 3. Configurar variables de entorno

El backup incluye tu `.env` actual. Si estás en un equipo nuevo con **otras credenciales**, edítalo:

```bash
nano .env
```

Variables imprescindibles para el arranque básico (el resto son opcionales):

```env
# Al menos una de estas para generar el guion:
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
# O usa Ollama/LM Studio local (sin clave)

# Para publicar en YouTube:
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...

# Para notificaciones Telegram:
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

> Si el backup viene del mismo equipo (misma IP/mismo bot de Telegram), **no necesitas cambiar nada** en `.env`.

---

## 4. Revisar tokens OAuth

Los tokens de YouTube, Instagram y WhatsApp están en `_tokens/`. Son específicos del equipo donde se autenticaron.

- **Si es el mismo usuario/bot**: funcionan tal cual.
- **Si es un servidor nuevo**: tras el primer `docker compose up`, ve a `http://servidor:3000/canales` y reconecta las plataformas.

---

## 5. Configuración del servidor vs. local

Si el servidor **no** tiene AI Studio (ComfyUI/LM Studio del host), edita en `.env`:

```env
# Dejar vacío o apuntar a un ComfyUI externo si lo tienes
COMFY_URL=
CONTROL_CENTER_URL=
LLM_BASE_URL=

# El montaje de videoclips usará imágenes fijas (Pollinations) como fallback
```

El bot de noticias y la publicación en redes **funciona perfectamente sin GPU ni AI Studio**.

---

## 6. Arrancar con Docker Compose

```bash
# Modo desarrollo (hot-reload, logs en pantalla):
docker compose up

# Modo background:
docker compose up -d

# Ver logs:
docker compose logs -f backend
docker compose logs -f frontend
```

**Puertos:**
| Servicio | Puerto |
|---|---|
| Frontend (UI) | http://servidor:3000 |
| Backend API | http://servidor:8000 |
| WhatsApp QR | http://servidor:3002 |

---

## 7. Primera vez: conectar WhatsApp

1. Abre `http://servidor:3002` en el navegador.
2. Escanea el QR con WhatsApp del móvil.
3. La sesión se guarda en el volumen `wa_auth` y persiste entre reinicios.

---

## 8. Producción (opcional)

Para producción usa el compose de prod que construye las imágenes optimizadas:

```bash
docker compose -f docker-compose.prod.yml up -d
```

Diferencias principales respecto al dev:
- Frontend compilado (sin hot-reload)
- Sin bind-mount del código fuente
- Imágenes más ligeras

---

## 9. Actualizar desde backup nuevo

```bash
docker compose down
tar -xzf reel-news-bot_backup_NUEVO.tar.gz --strip-components=0
# Los volúmenes (wa_auth, hf_cache, frontend_modules) se preservan automáticamente
docker compose up -d --build
```

---

## 10. Comandos útiles

```bash
# Ver estado de los servicios
docker compose ps

# Reiniciar solo el backend
docker compose restart backend

# Reconstruir imágenes tras cambios en Dockerfile/requirements
docker compose up -d --build

# Ejecutar CLI de noticias manualmente
docker compose exec backend python3 main.py --tema tecnologia

# Ver logs del scanner automático
docker compose logs -f backend | grep -i scanner

# Detener todo
docker compose down

# Detener y borrar volúmenes (⚠ borra sesión WhatsApp y caché de modelos)
docker compose down -v
```

---

## Solución de problemas

**Backend no arranca:**
```bash
docker compose logs backend | tail -50
# Suele ser un paquete de Python que falta → docker compose up --build
```

**YouTube no autorizado tras mover al servidor:**
```bash
# Borrar el token viejo y reconectar desde la UI
rm _tokens/youtube.json
# Ir a http://servidor:3000/canales → Conectar YouTube
```

**WhatsApp da "Unauthorized":**
```bash
# El token guardado en _tokens/telegram.json puede tener prioridad sobre .env
# Revisar: cat _tokens/telegram.json
# Si el token está caducado, borrar el archivo y reiniciar
rm _tokens/telegram.json
docker compose restart backend
```

**Puerto 3001 ocupado (conflicto con open-webui):**
El WhatsApp sidecar escucha internamente en 3001 pero se mapea al 3002 del host.
Si el 3002 también está ocupado, edita `docker-compose.yml`:
```yaml
ports:
  - "3003:3001"   # cambia 3002 por el que esté libre
```

---

## Estructura de datos persistentes

```
_config/       → configuración de la app (scanner, gestor, colas)
_tokens/       → tokens OAuth de YouTube, Instagram, WhatsApp Canal, Telegram
_library/      → imágenes subidas a la biblioteca
_music/        → canciones para el Montaje
_templates/    → plantillas visuales personalizadas
output/        → vídeos generados (no incluido en el backup — se regenera)
```

Los volúmenes Docker (`wa_auth`, `hf_cache`) se crean solos al arrancar.
