"""Regresión 2026-10-05: reels de 11 s con solo el titular, publicados solos.

Causa: las noticias de Google News llegaban al guionista sin artículo (solo un
<a href> con el titular), la IA respondía CONTENIDO_INSUFICIENTE y salía la
plantilla "¿Sabías esto sobre <titular>? <titular> Sígueme...".
"""
import json
from pathlib import Path
from unittest import mock

import pytest

import main
import summarizer
from api import autopublisher, gestor

GN_LINK = "https://news.google.com/rss/articles/CBMiqAFBVV9?oc=5"


# ── El guionista no fabrica reels vacíos ─────────────────────────────────────

def test_solo_titular_y_sin_ia_no_genera_reel(monkeypatch):
    monkeypatch.setattr(summarizer, "usar_grok", lambda: False)
    monkeypatch.setattr(summarizer, "nube_permitida", lambda: False)
    monkeypatch.setattr(summarizer, "_llamar_ollama", mock.Mock(side_effect=OSError("no")))
    monkeypatch.setattr(summarizer, "_llamar_lmstudio",
                        mock.Mock(return_value="CONTENIDO_INSUFICIENTE"))
    monkeypatch.setattr("llm_local.asegurar_llm", lambda: None)
    with pytest.raises(summarizer.SinContenidoError):
        summarizer.generar_guion_reel_claude(
            "Altman acaba de aceptar riesgos y nadie lo esperaba",
            "Altman acaba de aceptar riesgos y nadie lo esperaba", "Reuters",
            duracion_seg=40)


def test_guion_corto_pide_ampliar_tambien_en_reels_de_40s(monkeypatch):
    monkeypatch.setattr(summarizer, "usar_grok", lambda: False)
    monkeypatch.setattr(summarizer, "_llamar_ollama", mock.Mock(side_effect=OSError("no")))
    monkeypatch.setattr("llm_local.asegurar_llm", lambda: None)
    corto = "Dato uno. " * 20          # 40 palabras < mínimo de 40 s (59)
    largo = "Dato con cifra. " * 25    # 75 palabras
    llm = mock.Mock(side_effect=[corto, largo])
    monkeypatch.setattr(summarizer, "_es_texto_en_espanol", lambda t: True)
    monkeypatch.setattr(summarizer, "_llamar_lmstudio", llm)
    g = summarizer.generar_guion_reel_claude("Titular", "palabra " * 400, "Reuters",
                                             duracion_seg=40)
    assert llm.call_count == 2
    assert g["palabras"] == 75


def test_prompt_articulo_usa_la_duracion_y_el_minimo():
    p = summarizer._prompt_articulo("T", "F", "texto", 134, min_palabras=89, duracion_seg=60)
    assert "60 segundos" in p and "entre 89 y 134 palabras" in p
    p = summarizer._prompt_articulo("T", "F", "texto", 88, min_palabras=59, duracion_seg=40)
    assert "40 segundos" in p and "entre 59 y 88" in p


# ── Duración: base de Ajustes, hasta 60 s si la noticia da para más ──────────

@pytest.mark.parametrize("palabras,esperado", [(80, 40), (300, 50), (600, 60)])
def test_duracion_segun_noticia(palabras, esperado):
    assert main.duracion_segun_noticia(40, palabras, techo=60) == esperado


def test_duracion_no_baja_si_la_base_ya_es_el_techo():
    assert main.duracion_segun_noticia(60, 50, techo=60) == 60


# ── El Gestor busca el artículo real de Google News ──────────────────────────

def _item_gn():
    noticia = {"titulo": "Altman acaba de aceptar riesgos",
               "titulo_original": "OpenAI's Altman says AI benefits warrant accepting some risks - Reuters",
               "fuente": "Reuters", "link": GN_LINK,
               "resumen": f'<a href="{GN_LINK}" target="_blank">', "gancho": "Dato"}
    return {"id": "x", "tipo": "noticia", "titulo": noticia["titulo"],
            "contenido": json.dumps(noticia)}


def test_gestor_sin_articulo_no_genera():
    with mock.patch("cobertura.texto_de_noticia", return_value=None):
        with pytest.raises(gestor.SinTextoDeNoticia):
            gestor._build_generate_payload(_item_gn())


def test_gestor_manda_el_articulo_real():
    cob = {"texto": "palabra " * 300, "url": "https://medio.test/a", "medio": "Medio"}
    with mock.patch("cobertura.texto_de_noticia", return_value=cob):
        p = gestor._build_generate_payload(_item_gn())
    assert p["mode"] == "texto"
    assert p["url_fuente"] == "https://medio.test/a"
    assert len(p["texto"].split()) > 300
    assert "Titular original: OpenAI's Altman" in p["texto"]


def test_start_job_marca_fallido_sin_articulo():
    item = _item_gn()
    with mock.patch("cobertura.texto_de_noticia", return_value=None):
        assert gestor._start_job(item, [item]) is False
    assert item["estado"] == "failed" and "No se encontró el texto" in item["error"]


# ── El piloto automático no publica reels vacíos ─────────────────────────────

def _reel(tmp_path, guion: str) -> str:
    out = tmp_path / "output"
    out.mkdir()
    (out / "n_reel.mp4").write_bytes(b"x")
    (out / "n_guion_reel.txt").write_text(guion, "utf-8")
    return "n_reel.mp4"


def test_autopub_rechaza_plantilla(tmp_path, monkeypatch):
    f = _reel(tmp_path, "Titulo: x\n\n¿Sabías esto sobre Altman? Altman Sígueme para más")
    monkeypatch.setattr(autopublisher, "__file__", str(tmp_path / "api" / "autopublisher.py"))
    monkeypatch.setattr(autopublisher, "_duracion_video", lambda r: 40.0)
    ok, motivo = autopublisher.reel_publicable(f)
    assert not ok and "plantilla" in motivo


def test_autopub_rechaza_reel_corto(tmp_path, monkeypatch):
    f = _reel(tmp_path, "Titulo: x\n\nGuion real con datos.")
    monkeypatch.setattr(autopublisher, "__file__", str(tmp_path / "api" / "autopublisher.py"))
    monkeypatch.setattr(autopublisher, "_duracion_video", lambda r: 11.3)
    ok, motivo = autopublisher.reel_publicable(f)
    assert not ok and "11 s" in motivo


def test_autopub_acepta_reel_bueno(tmp_path, monkeypatch):
    f = _reel(tmp_path, "Titulo: x\n\nGuion real con datos.")
    monkeypatch.setattr(autopublisher, "__file__", str(tmp_path / "api" / "autopublisher.py"))
    monkeypatch.setattr(autopublisher, "_duracion_video", lambda r: 39.1)
    assert autopublisher.reel_publicable(f) == (True, "")


def test_publish_item_rechazado_libera_el_piloto(monkeypatch):
    monkeypatch.setattr(autopublisher, "reel_publicable", lambda f: (False, "corto"))
    monkeypatch.setattr(autopublisher, "_rechazar", lambda t, m: None)
    autopublisher._publishing = True
    autopublisher._publish_item({"item_id": "x", "output_file": "n_reel.mp4", "titulo": "t",
                                 "platforms": ["youtube"], "tipo_contenido": "noticia",
                                 "tiktok_privacy": "SELF_ONLY", "score": 9})
    assert autopublisher._publishing is False


# ── cobertura ────────────────────────────────────────────────────────────────

def test_titular_limpio_quita_el_medio():
    from cobertura import _titular_limpio
    assert _titular_limpio("OpenAI's Altman says AI benefits warrant accepting some risks - Reuters") \
        == "OpenAI's Altman says AI benefits warrant accepting some risks"
