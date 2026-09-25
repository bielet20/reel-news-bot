#!/bin/sh
# Limpia el lock de Chromium al arrancar para evitar el "profile in use" error
find /app/.wwebjs_auth -name "SingletonLock" -o -name "SingletonSocket" -o -name "SingletonCookie" 2>/dev/null | xargs rm -f 2>/dev/null || true
exec node server.js
