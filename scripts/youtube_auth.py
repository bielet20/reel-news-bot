"""
scripts/youtube_auth.py
Autenticación OAuth 2.0 para YouTube (se ejecuta UNA SOLA VEZ).

Pasos previos:
  1. Ve a https://console.cloud.google.com/
  2. Crea un proyecto nuevo o usa uno existente.
  3. Activa la API: "APIs y servicios" → "Habilitar APIs" → busca "YouTube Data API v3"
  4. Crea credenciales: "APIs y servicios" → "Credenciales" → "Crear credenciales"
     → "ID de cliente de OAuth" → Tipo: "Aplicación de escritorio"
  5. Descarga el JSON o anota el Client ID y Client Secret.
  6. Añade al .env:
       YOUTUBE_CLIENT_ID=tu-client-id
       YOUTUBE_CLIENT_SECRET=tu-client-secret
  7. Ejecuta este script: python scripts/youtube_auth.py
  8. Se abrirá el navegador. Inicia sesión con la cuenta de YouTube del canal.
  9. Copia el YOUTUBE_REFRESH_TOKEN que aparece en la consola y añádelo al .env.

Uso:
    cd /ruta/al/proyecto
    python scripts/youtube_auth.py
"""

import os
import sys
from pathlib import Path

# Añadir el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

CLIENT_ID     = os.environ.get("YOUTUBE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: Configura YOUTUBE_CLIENT_ID y YOUTUBE_CLIENT_SECRET en el .env primero.")
        print("       Lee los pasos al inicio de este archivo para obtenerlos.")
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("ERROR: Falta la librería. Ejecuta:")
        print("       pip install google-auth-oauthlib google-api-python-client")
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id":      CLIENT_ID,
            "client_secret":  CLIENT_SECRET,
            "auth_uri":       "https://accounts.google.com/o/oauth2/auth",
            "token_uri":      "https://oauth2.googleapis.com/token",
            "redirect_uris":  ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    print("Abriendo el navegador para autenticación con Google…")
    flow  = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n" + "=" * 60)
    print("✅  AUTENTICACIÓN COMPLETADA")
    print("=" * 60)
    print("\nAñade esta línea a tu archivo .env:\n")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
    print("\nEl refresh token no caduca. No necesitas repetir este proceso.")
    print("=" * 60)


if __name__ == "__main__":
    main()
