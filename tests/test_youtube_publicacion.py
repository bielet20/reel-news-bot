"""Pruebas sin red de la publicación de YouTube (cliente falso, nunca llama a la API).
Ejecutar desde la raíz del repo:  python -m pytest tests/test_youtube_publicacion.py -q"""
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import youtube_publicacion as yp  # noqa: E402


# ── cliente de YouTube falso ──────────────────────────────────────────────────

class _Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class HttpErrorFalso(Exception):
    """Imita googleapiclient.errors.HttpError (resp.status + content)."""
    def __init__(self, status, reason):
        self.resp = type("R", (), {"status": status})()
        self.content = json.dumps({"error": {"errors": [{"reason": reason, "message": reason}]}}).encode()
        super().__init__(f"HttpError {status} {reason}")


class FakeVideos:
    def __init__(self, list_resp=None, list_exc=None, update_exc=None):
        self.list_resp, self.list_exc, self.update_exc = list_resp, list_exc, update_exc
        self.updates = []

    def list(self, part, id):
        def f():
            if self.list_exc:
                raise self.list_exc
            return self.list_resp
        return _Req(f)

    def update(self, part, body):
        def f():
            if self.update_exc:
                raise self.update_exc
            self.updates.append((part, body))
            return {"id": body["id"]}
        return _Req(f)


class FakeService:
    def __init__(self, videos):
        self._v = videos

    def videos(self):
        return self._v


def item(upload="processed", proc="succeeded", privacy="private"):
    return {"items": [{
        "status": {"uploadStatus": upload, "privacyStatus": privacy, "embeddable": True,
                   "license": "youtube", "publicStatsViewable": True,
                   "selfDeclaredMadeForKids": False, "madeForKids": False},
        "processingDetails": {"processingStatus": proc},
    }]}


@pytest.fixture(autouse=True)
def estado_temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(yp, "STATE_FILE", tmp_path / "youtube_publicacion.json")
    monkeypatch.setattr(yp, "LOG_FILE", tmp_path / "youtube_publicacion.log")
    monkeypatch.delenv("YT_AUTOPUBLICAR", raising=False)
    yield


def registrar(vid="VIDEO_AAAA1"):
    return yp.registrar_subida(vid, "Título", "historia_" + vid, "/app/output/x_reel.mp4")


def get(vid):
    return yp.obtener(vid)


# ── publicación manual (botón Publicar) ───────────────────────────────────────

def test_manual_procesado_pasa_a_publico_conservando_campos():
    registrar()
    v = FakeVideos(item())
    code, body = yp.publicar_manual("VIDEO_AAAA1", lambda: FakeService(v))
    assert code == 200 and body["estado"] == "publico"
    assert v.updates == [("status", {"id": "VIDEO_AAAA1", "status": {
        "embeddable": True, "license": "youtube", "publicStatsViewable": True,
        "selfDeclaredMadeForKids": False, "privacyStatus": "public"}})]
    assert get("VIDEO_AAAA1")["state"] == "publicado"
    assert "publicado manualmente" in yp.LOG_FILE.read_text(encoding="utf-8")


def test_manual_procesando_409_sin_publicar():
    registrar()
    v = FakeVideos(item("uploaded", "processing"))
    code, body = yp.publicar_manual("VIDEO_AAAA1", lambda: FakeService(v))
    assert code == 409 and "todavía está procesando" in body["detail"]
    assert not v.updates and get("VIDEO_AAAA1")["state"] == "pendiente"


def test_manual_fallido_error_y_privado():
    registrar()
    v = FakeVideos(item("rejected", "failed"))
    code, body = yp.publicar_manual("VIDEO_AAAA1", lambda: FakeService(v))
    assert code == 422 and not body["ok"] and not v.updates
    assert get("VIDEO_AAAA1")["state"] == "error"


def test_manual_no_encontrado():
    registrar()
    v = FakeVideos({"items": []})
    code, _ = yp.publicar_manual("VIDEO_AAAA1", lambda: FakeService(v))
    assert code == 404 and not v.updates


def test_manual_ya_publico_idempotente():
    registrar()
    v = FakeVideos(item(privacy="public"))
    code, body = yp.publicar_manual("VIDEO_AAAA1", lambda: FakeService(v))
    assert code == 200 and body["ok"] and body["estado"] == "publico"
    assert not v.updates and get("VIDEO_AAAA1")["state"] == "publicado"
    code2, _ = yp.publicar_manual("VIDEO_AAAA1", lambda: FakeService(v))
    assert code2 == 200 and not v.updates


def test_manual_error_permisos_en_update_sigue_privado():
    registrar()
    v = FakeVideos(item(), update_exc=HttpErrorFalso(403, "insufficientPermissions"))
    code, body = yp.publicar_manual("VIDEO_AAAA1", lambda: FakeService(v))
    assert code == 403 and "/canales" in body["detail"] and body["estado"] == "privado"
    assert get("VIDEO_AAAA1")["state"] == "pendiente"


def test_manual_error_permisos_en_list():
    registrar()
    v = FakeVideos(list_exc=HttpErrorFalso(403, "forbidden"))
    code, _ = yp.publicar_manual("VIDEO_AAAA1", lambda: FakeService(v))
    assert code == 403 and not v.updates


def test_manual_cuota_no_es_error_de_permisos():
    registrar()
    v = FakeVideos(item(), update_exc=HttpErrorFalso(403, "quotaExceeded"))
    code, _ = yp.publicar_manual("VIDEO_AAAA1", lambda: FakeService(v))
    assert code == 502


def test_manual_sin_credenciales_503():
    registrar()
    def boom():
        raise RuntimeError("Faltan credenciales")
    code, _ = yp.publicar_manual("VIDEO_AAAA1", boom)
    assert code == 503


# ── publicador automático desactivado por defecto ─────────────────────────────

def test_autopublicador_desactivado_por_defecto():
    assert yp.autopublicar_activo() is False
    e = registrar()
    v = FakeVideos(item())
    hecho = yp.ciclo(lambda: FakeService(v), yp._parse(e["uploaded_at"]) + timedelta(hours=5))
    assert hecho == 0 and not v.updates and get("VIDEO_AAAA1")["state"] == "pendiente"


def test_iniciar_publicador_no_arranca_hilo_si_desactivado(monkeypatch):
    monkeypatch.setattr(yp, "_hilo", None)
    yp.iniciar_publicador()
    assert yp._hilo is None


def test_autopublicador_activado_publica_tras_2h30(monkeypatch):
    monkeypatch.setenv("YT_AUTOPUBLICAR", "1")
    e = registrar()
    up = yp._parse(e["uploaded_at"])
    v = FakeVideos(item())
    assert yp.ciclo(lambda: FakeService(v), up + timedelta(hours=2)) == 0
    yp.ciclo(lambda: FakeService(v), up + timedelta(hours=2, minutes=31))
    assert get("VIDEO_AAAA1")["state"] == "publicado" and len(v.updates) == 1


def test_autopublicador_activado_procesando_y_3_errores(monkeypatch):
    monkeypatch.setenv("YT_AUTOPUBLICAR", "1")
    e = registrar()
    up = yp._parse(e["uploaded_at"])
    v = FakeVideos(item("uploaded", "processing"))
    yp.ciclo(lambda: FakeService(v), up + timedelta(hours=3))
    assert get("VIDEO_AAAA1")["state"] == "pendiente" and not v.updates
    v2 = FakeVideos(item(), update_exc=HttpErrorFalso(403, "insufficientPermissions"))
    t = up + timedelta(hours=4)
    for _ in range(3):
        yp.ciclo(lambda: FakeService(v2), t)
        t += timedelta(hours=2)
    assert get("VIDEO_AAAA1")["state"] == "bloqueado" and not v2.updates


# ── endpoints HTTP ────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import youtube_publicacion_api as mod
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app)


def test_endpoint_get_estado(client):
    assert client.get("/api/youtube/publicacion/VIDEO_AAAA1").status_code == 404
    registrar()
    r = client.get("/api/youtube/publicacion/VIDEO_AAAA1")
    assert r.status_code == 200 and r.json()["estado"] == "privado"
    lista = client.get("/api/youtube/publicacion").json()
    assert lista["autopublicar"] is False and len(lista["items"]) == 1


def test_endpoint_publicar(client, monkeypatch):
    registrar()
    v = FakeVideos(item("uploaded", "processing"))
    monkeypatch.setattr("youtube_uploader._get_service", lambda: FakeService(v))
    r = client.post("/api/youtube/publicacion/VIDEO_AAAA1/publicar")
    assert r.status_code == 409 and "procesando" in r.json()["detail"]
    v.list_resp = item()
    r = client.post("/api/youtube/publicacion/VIDEO_AAAA1/publicar")
    assert r.status_code == 200 and r.json()["estado"] == "publico"
    assert client.get("/api/youtube/publicacion/VIDEO_AAAA1").json()["estado"] == "publico"


def test_endpoint_id_invalido(client):
    assert client.post("/api/youtube/publicacion/..%2Fx/publicar").status_code in (400, 404)
    assert client.post("/api/youtube/publicacion/a b/publicar").status_code == 400
