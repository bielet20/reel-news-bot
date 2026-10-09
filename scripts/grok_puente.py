"""
Puente local entre reel-news-bot y Grok.

El backend (Docker) habla el formato de chat de OpenAI. Este proceso corre en
el PC, fuera de Docker, y llama a grok.exe con la sesión ya iniciada en
~/.grok. No copia el token a ningún archivo.

Arranque: scripts\\Iniciar-Grok.bat
Escucha en 0.0.0.0:12434 y exige GROK_PUENTE_TOKEN (en el .env del proyecto).
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = os.environ.get("GROK_PUENTE_HOST", "0.0.0.0")
PORT = int(os.environ.get("GROK_PUENTE_PORT", "12434"))
GROK = os.environ.get("GROK_EXE", str(Path.home() / ".grok" / "bin" / "grok.exe"))
MODEL = os.environ.get("XAI_MODEL", "grok-4.7")
EFFORT = os.environ.get("XAI_EFFORT", "low")
CWD = Path(os.environ.get("GROK_PUENTE_CWD", Path(tempfile.gettempdir()) / "grok-puente"))
LOCK = threading.Lock()
TIMEOUT = int(os.environ.get("GROK_PUENTE_TIMEOUT", "300"))

SISTEMA_DEFECTO = (
    "Eres el redactor de un canal de noticias en español. "
    "Responde solo con el texto pedido, en español, sin usar herramientas."
)


def _leer_env(clave: str) -> str:
    valor = os.environ.get(clave, "").strip()
    if valor:
        return valor
    env = ROOT / ".env"
    if not env.exists():
        return ""
    for linea in env.read_text(encoding="utf-8").splitlines():
        if linea.startswith(f"{clave}="):
            return linea.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


TOKEN = _leer_env("GROK_PUENTE_TOKEN")


def _texto(content) -> str:
    if isinstance(content, list):
        content = "\n".join(
            p.get("text", "") for p in content if isinstance(p, dict)
        )
    return str(content or "").replace("/no_think", "").strip()


def _mensajes(messages: list) -> tuple[str, str]:
    sistema = []
    turnos = []
    for m in messages or []:
        rol = (m.get("role") or "user").strip()
        texto = _texto(m.get("content"))
        if not texto:
            continue
        if rol == "system":
            sistema.append(texto)
        else:
            turnos.append(texto if rol == "user" else f"{rol}:\n{texto}")
    orden = "\n\n".join(sistema).strip() or SISTEMA_DEFECTO
    prompt = "\n\n".join(turnos).strip()
    if len(orden) > 12000:
        prompt = orden[12000:] + "\n\n" + prompt
        orden = orden[:12000]
    return orden, prompt


def completar(messages: list) -> str:
    orden, prompt = _mensajes(messages)
    if not prompt:
        raise RuntimeError("el prompt llegó vacío")
    if not Path(GROK).exists():
        raise RuntimeError(f"no está grok.exe en {GROK}")
    CWD.mkdir(parents=True, exist_ok=True)
    fd, ruta = tempfile.mkstemp(suffix=".txt", dir=CWD)
    os.close(fd)
    Path(ruta).write_text(prompt, encoding="utf-8")
    cmd = [
        GROK, "--prompt-file", ruta,
        "--output-format", "json",
        "--model", MODEL,
        "--reasoning-effort", EFFORT,
        "--max-turns", "1",
        "--disable-web-search",
        "--no-subagents",
        "--verbatim",
        "--cwd", str(CWD),
        "--permission-mode", "dontAsk",
        "--system-prompt-override", orden,
        "--deny", "Bash",
        "--deny", "Edit",
        "--deny", "Write",
    ]
    env = os.environ.copy()
    env["GROK_DISABLE_AUTOUPDATER"] = "1"
    env["GROK_MEMORY"] = "0"
    try:
        with LOCK:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=TIMEOUT, env=env, cwd=str(CWD),
            )
    finally:
        Path(ruta).unlink(missing_ok=True)
    raw = (proc.stdout or "").strip()
    if proc.returncode != 0:
        detalle = ((proc.stderr or "") + "\n" + raw).strip()[-600:]
        raise RuntimeError(f"grok salió con código {proc.returncode}: {detalle}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        inicio, fin = raw.find("{"), raw.rfind("}")
        if inicio < 0 or fin <= inicio:
            raise RuntimeError("grok no devolvió JSON")
        data = json.loads(raw[inicio:fin + 1])
    texto = str(data.get("text") or "").strip()
    if not texto:
        raise RuntimeError("Grok devolvió una respuesta vacía")
    return texto


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"[grok-puente] {self.address_string()} {fmt % args}", flush=True)

    def _autorizado(self) -> bool:
        if not TOKEN:
            return False
        cab = self.headers.get("Authorization", "")
        return cab == f"Bearer {TOKEN}"

    def _json(self, code: int, payload: dict):
        cuerpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _leer(self) -> dict:
        n = int(self.headers.get("Content-Length", "0") or "0")
        if n > 2_000_000:
            raise RuntimeError("el cuerpo supera 2 MB")
        bruto = self.rfile.read(n) if n else b""
        return json.loads(bruto.decode("utf-8") or "{}")

    def do_GET(self):
        if not self._autorizado():
            self._json(401, {"error": {"message": "token del puente inválido"}})
            return
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": MODEL, "object": "model"}]})
            return
        self._json(404, {"error": {"message": "ruta no encontrada"}})

    def do_POST(self):
        if not self._autorizado():
            self._json(401, {"error": {"message": "token del puente inválido"}})
            return
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": {"message": "ruta no encontrada"}})
            return
        try:
            cuerpo = self._leer()
            texto = completar(cuerpo.get("messages") or [])
        except Exception as e:  # noqa: BLE001
            self._json(502, {"error": {"message": str(e)}})
            return
        self._json(200, {
            "id": "chatcmpl-grok-puente",
            "object": "chat.completion",
            "model": MODEL,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": texto},
                "finish_reason": "stop",
            }],
        })


def main():
    if not TOKEN:
        raise SystemExit("Falta GROK_PUENTE_TOKEN en el .env de reel-news-bot. No arranco un puente abierto.")
    if not Path(GROK).exists():
        raise SystemExit(f"No encuentro grok.exe en {GROK}")
    CWD.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[grok-puente] {MODEL} en http://{HOST}:{PORT}/v1  (grok: {GROK})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
