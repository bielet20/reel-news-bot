"""Petición 2026-10-07: cada noticia dice de cuándo es, en el vídeo (rótulo bajo
el título) y en los textos publicados ("📅 Noticia del 7 de octubre de 2026").

Antes la fecha del feed se perdía por el camino (el gestor no la pasaba a
main.py) y en _fuente.json casi siempre quedaba fecha_publicacion vacía.
También: Telegram rechazaba vídeos con "message caption is too long".
"""
import json

import numpy as np

import fecha_noticia as fn
import telegram_uploader
import video_builder
from api import gestor, publish, server


# ── Formatos de fecha ────────────────────────────────────────────────────────

def test_normaliza_los_formatos_que_llegan():
    assert fn.normalizar("2026-10-07T09:54:13Z") == "2026-10-07"
    assert fn.normalizar("2026-10-07T14:12:37+00:00") == "2026-10-07"
    assert fn.normalizar("Tue, 06 Oct 2026 14:00:00 GMT") == "2026-10-06"
    assert fn.normalizar("20261005") == "2026-10-05"
    assert fn.normalizar("2026-10-04") == "2026-10-04"


def test_noche_utc_cuenta_como_dia_siguiente_en_espana():
    # 22:30 UTC del 6 = 00:30 del 7 en Madrid (CEST)
    assert fn.normalizar("2026-10-06T22:30:00Z") == "2026-10-07"


def test_fechas_basura_o_imposibles_se_descartan():
    for malo in ("", None, "ayer", "hace 3 horas", "1970-01-01", "2999-01-01"):
        assert fn.normalizar(malo) == ""


def test_texto_en_espanol():
    assert fn.larga("2026-10-07") == "7 de octubre de 2026"
    assert fn.linea("2026-10-07") == "📅 Noticia del 7 de octubre de 2026"
    assert fn.larga("") == ""


def test_con_fecha_va_bajo_el_titulo_y_no_se_repite():
    texto = "🔥 TITULAR\n\nCuerpo de la noticia"
    con = fn.con_fecha(texto, "2026-10-07")
    assert con == "🔥 TITULAR\n📅 Noticia del 7 de octubre de 2026\n\nCuerpo de la noticia"
    assert fn.con_fecha(con, "2026-10-07") == con
    assert fn.con_fecha(texto, "") == texto
    assert fn.con_fecha("Solo título", "2026-10-07").endswith("octubre de 2026")


# ── Fecha guardada junto al reel ─────────────────────────────────────────────

def test_lee_fecha_de_fuente_json_y_de_info_txt(tmp_path):
    (tmp_path / "a_fuente.json").write_text(
        json.dumps({"fecha_noticia": "", "fecha_publicacion": "2026-10-07T14:00:08+00:00"}), "utf-8")
    assert fn.de_reel(tmp_path, "a_reel.mp4") == "2026-10-07"
    (tmp_path / "b_short2_info.txt").write_text("Titulo: x\nFecha: 2026-10-05\n", "utf-8")
    assert fn.de_reel(tmp_path, "b_short2.mp4") == "2026-10-05"
    assert fn.de_reel(tmp_path, "nada_reel.mp4") == ""


def test_main_usa_fecha_del_feed_si_el_articulo_no_trae(monkeypatch):
    import main
    monkeypatch.setenv("FECHA_NOTICIA", "Tue, 06 Oct 2026 10:00:00 GMT")
    assert main._dia_de_noticia({}, {"fecha_publicacion": ""}) == "2026-10-06"
    # la del propio artículo manda
    assert main._dia_de_noticia({}, {"fecha_publicacion": "2026-10-05"}) == "2026-10-05"
    monkeypatch.delenv("FECHA_NOTICIA")
    assert main._dia_de_noticia({"fecha": "20261004"}, None) == "2026-10-04"


def test_caption_txt_lleva_la_fecha_bajo_el_titulo(tmp_path, monkeypatch):
    import main
    monkeypatch.delenv("FECHA_NOTICIA", raising=False)
    noticia = {"titulo": "Titular", "link": "https://x.com/a", "fuente": "Medio",
               "fecha": "2026-10-07T08:00:00Z"}
    at = main._guardar_atribucion("s", str(tmp_path), noticia, {}, titulo_es="Titular ES")
    assert at["fecha_noticia"] == "2026-10-07"
    lineas = (tmp_path / "s_caption.txt").read_text("utf-8").splitlines()
    assert lineas[:2] == ["Titular ES", "📅 Noticia del 7 de octubre de 2026"]


# ── El gestor pasa la fecha del feed hasta main.py ───────────────────────────

def test_gestor_manda_la_fecha_del_feed(monkeypatch):
    item = {"tipo": "noticia", "titulo": "T", "contenido": json.dumps(
        {"titulo": "T", "link": "https://medio.es/n", "fuente": "M",
         "fecha": "Tue, 06 Oct 2026 10:00:00 GMT"})}
    payload = gestor._build_generate_payload(item)
    assert payload["fecha_noticia"] == "Tue, 06 Oct 2026 10:00:00 GMT"
    args = server._build_cli_args(server.GenerateRequest(**payload))
    i = args.index("--fecha-noticia")
    assert args[i + 1] == "Tue, 06 Oct 2026 10:00:00 GMT"


# ── Textos publicados ────────────────────────────────────────────────────────

def test_publicar_mete_la_fecha_en_todos_los_textos(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "OUTPUT_DIR", tmp_path)
    (tmp_path / "n_fuente.json").write_text(json.dumps({"fecha_noticia": "2026-10-07"}), "utf-8")
    req = publish.PublishRequest(filename="n_reel.mp4", titulo="T", platforms=["telegram"],
                                 descripcion="Titular\n\nCuerpo", tiktok_caption="Gancho\n\n#tags",
                                 instagram_caption="🔥 T\n\nX", x_caption="x" * 270)
    r = publish._con_fecha_noticia(req)
    lin = "📅 Noticia del 7 de octubre de 2026"
    assert r.descripcion.splitlines()[1] == lin
    assert r.tiktok_caption.splitlines()[1] == lin
    assert r.instagram_caption.splitlines()[1] == lin
    assert r.x_caption == "x" * 270            # en X no cabe: se deja igual
    # sin fecha conocida, nada cambia
    req2 = req.model_copy(update={"filename": "otro_reel.mp4"})
    assert publish._con_fecha_noticia(req2) == req2


def test_telegram_recorta_textos_largos():
    largo = "Titular\n" + ("línea de texto con emoji 📰\n" * 80)
    corto = telegram_uploader.recortar_caption(largo)
    assert telegram_uploader._largo_tg(corto) <= telegram_uploader.CAPTION_MAX
    assert corto.startswith("Titular\n") and corto.endswith("…")
    assert telegram_uploader.recortar_caption("corto") == "corto"


# ── Rótulo en el vídeo ───────────────────────────────────────────────────────

def test_rotulo_de_fecha_se_dibuja_y_no_pisa_el_titulo():
    clip = video_builder.clip_fecha("2026-10-07", 400, 2.0)
    frame = clip.get_frame(0)
    filas = np.where(frame[:, :, 0] > 200)[0]   # el ámbar tiene rojo alto
    assert len(filas) and 350 < filas.min() and filas.max() < 450
    assert video_builder.clip_fecha("", 400, 2.0) is None
    # el alto calculado crece con el título (fecha siempre debajo)
    corto = video_builder.alto_texto("Corto", video_builder.FONT_EXTRABOLD, 62, max_ancho=960)
    largo = video_builder.alto_texto("Un titular muy largo " * 6, video_builder.FONT_EXTRABOLD, 62,
                                     max_ancho=960)
    assert largo > corto > 0
