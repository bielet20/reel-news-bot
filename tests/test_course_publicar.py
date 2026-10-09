"""Petición 2026-10-07: subir un curso terminado a YouTube eligiendo qué
lecciones (o todas, o el curso completo) y si van públicas, ocultas o privadas.
No usa red: centro_redes.publicar está simulado."""
import pytest
from fastapi import HTTPException

import centro_redes as cr
import course_publicar as cp
import course_store as cs
import youtube_uploader as yt


@pytest.fixture
def curso(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "CURSOS_DIR", tmp_path)
    c = cs.crear_curso("Curso de prueba", "Aprende cosas.")
    render = cs.dir_curso(c["id"]) / "render"
    (render / "slides").mkdir(parents=True)
    for n in ("l1", "l2"):
        (render / f"leccion_{n}.mp4").write_bytes(b"x")
    (render / "curso_completo.mp4").write_bytes(b"x")
    (render / "capitulos.txt").write_text("00:00 M — Uno\n04:00 M — Dos\n", "utf-8")

    def fn(cur):
        cur["modulos"] = [{"id": "m1", "titulo": "Módulo 1", "lecciones": [
            {"id": "l1", "titulo": "Uno", "objetivos": ["Saber A"], "escenas": [],
             "render": {"archivo": "render/leccion_l1.mp4", "duracion": 60}},
            {"id": "l2", "titulo": "Dos", "objetivos": [], "escenas": [],
             "render": {"archivo": "render/leccion_l2.mp4", "duracion": 90}},
            {"id": "l3", "titulo": "Tres", "objetivos": [], "escenas": [], "render": None},
        ]}]
        cur["render"] = {"archivo": "render/curso_completo.mp4", "capitulos": "render/capitulos.txt", "duracion": 150}
    cs.modificar(c["id"], fn)
    monkeypatch.setattr(cp, "_pie", lambda canal: "RayverSec — cursos.")
    return c["id"]


@pytest.fixture
def llamadas(monkeypatch):
    hechas = []

    def falso(canal_id, video, titulo, descripcion="", redes=None, privacidad="public",
              miniatura=None, origen="", playlist=None):
        hechas.append(dict(canal=canal_id, video=str(video), titulo=titulo, descripcion=descripcion,
                           redes=redes, privacidad=privacidad, playlist=playlist, origen=origen))
        vid = f"v{len(hechas)}"
        return {"youtube": {"ok": True, "url": f"https://www.youtube.com/watch?v={vid}", "video_id": vid}}
    monkeypatch.setattr(cr, "publicar", falso)
    return hechas


def test_estado_dice_que_se_puede_subir(curso):
    e = cp.estado(curso)
    assert [(l["id"], l["renderizada"]) for l in e["lecciones"]] == [("l1", True), ("l2", True), ("l3", False)]
    assert e["completo"]["renderizado"] is True
    assert e["todas_renderizadas"] is False


def test_sube_solo_las_elegidas_con_la_privacidad_elegida(curso, llamadas):
    r = cp.publicar(curso, ["l2"], privacidad="unlisted", log=lambda m: None)
    assert len(llamadas) == 1 and len(r["subidas"]) == 1
    ll = llamadas[0]
    assert ll["privacidad"] == "unlisted"
    assert ll["canal"] == "rayversec" and ll["redes"] == ["youtube"]
    assert ll["titulo"] == "Curso de prueba | 2. Dos"
    assert ll["playlist"] == "Curso de prueba"
    assert ll["video"].endswith("leccion_l2.mp4")
    assert "Lección 2 de 3" in ll["descripcion"] and "RayverSec — cursos." in ll["descripcion"]
    pub = cp.publicaciones(curso)
    assert pub["l2"]["privacidad"] == "unlisted" and pub["l2"]["url"].endswith("v1")
    assert "l1" not in pub


def test_todas_en_orden_y_sin_renderizar_se_salta(curso, llamadas):
    r = cp.publicar(curso, ["l3", "l2", "l1"], privacidad="private", log=lambda m: None)
    assert [l["titulo"] for l in llamadas] == ["Curso de prueba | 1. Uno", "Curso de prueba | 2. Dos"]
    assert all(l["privacidad"] == "private" for l in llamadas)
    assert r["saltadas"] == [{"id": "l3", "titulo": "Tres", "motivo": "sin renderizar"}]


def test_no_duplica_las_ya_subidas_salvo_que_se_pida(curso, llamadas):
    cp.publicar(curso, ["l1"], log=lambda m: None)
    r = cp.publicar(curso, ["l1", "l2"], log=lambda m: None)
    assert len(llamadas) == 2  # l1 una vez + l2
    assert r["saltadas"][0]["motivo"] == "ya subida"
    cp.publicar(curso, ["l1"], resubir=True, log=lambda m: None)
    assert len(llamadas) == 3


def test_curso_completo_lleva_capitulos_y_no_va_a_la_lista(curso, llamadas):
    cp.publicar(curso, [], completo=True, privacidad="public", log=lambda m: None)
    ll = llamadas[0]
    assert ll["titulo"] == "Curso de prueba" and ll["playlist"] is None
    assert "Capítulos:\n00:00 M — Uno" in ll["descripcion"]
    assert cp.publicaciones(curso)[cp.COMPLETO]["privacidad"] == "public"


def test_un_fallo_no_para_las_demas_ni_se_apunta(curso, monkeypatch):
    def falso(canal_id, video, titulo, **kw):
        if "Uno" in titulo:
            return {"youtube": {"ok": False, "error": "invalid_grant"}}
        return {"youtube": {"ok": True, "url": "https://youtu.be/ok", "video_id": "ok"}}
    monkeypatch.setattr(cr, "publicar", falso)
    r = cp.publicar(curso, ["l1", "l2"], log=lambda m: None)
    assert [f["id"] for f in r["fallos"]] == ["l1"] and [s["id"] for s in r["subidas"]] == ["l2"]
    assert set(cp.publicaciones(curso)) == {"l2"}


def test_privacidad_no_valida(curso, llamadas):
    with pytest.raises(ValueError):
        cp.publicar(curso, ["l1"], privacidad="publico", log=lambda m: None)
    assert not llamadas


def test_titulo_largo_se_recorta_sin_perder_la_leccion():
    t = cp.titulo_leccion({"titulo": "Curso " * 30}, 12, {"titulo": "Manejo de archivos"})
    assert len(t) <= 100 and t.endswith("| 12. Manejo de archivos")


def test_api_valida_y_lanza_tarea(curso, llamadas):
    from api import cursos as api
    with pytest.raises(HTTPException) as e:
        api.publicar_curso(curso, api.PublicarCurso(lecciones=[], completo=False))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException):
        api.publicar_curso(curso, api.PublicarCurso(lecciones=["l1"], privacidad="oculto"))
    t = api.publicar_curso(curso, api.PublicarCurso(lecciones=["l1"], privacidad="unlisted"))
    assert t["tipo"] == "publicar" and "oculto" in t["etiqueta"]
    import time
    for _ in range(50):
        if api._tareas[t["id"]]["estado"] != "en_curso":
            break
        time.sleep(0.05)
    assert api._tareas[t["id"]]["estado"] == "completada"
    assert llamadas[0]["privacidad"] == "unlisted"


def test_lista_de_curso_nace_con_la_privacidad_del_video(monkeypatch):
    creadas = []

    class Lista:
        def list(self, **kw): return self
        def execute(self): return {"items": []} if not creadas else {"id": "PL1"}
        def list_next(self, *a): return None
        def insert(self, part, body):
            creadas.append(body["status"]["privacyStatus"]); return self

    class Servicio:
        def playlists(self): return Lista()

    yt._playlist_cache.clear()
    yt._playlist_id(Servicio(), "Curso X", privacidad="private")
    assert creadas == ["private"]
    yt._playlist_cache.clear()
