"""Vinculo muchos-a-muchos curso-canal. No usa red ni secretos."""
import json

import course_store as cs
import course_canales as cc

RAY = "UCbEnilZIVXwp9lNAv91j69g"
OTRO = "UC1111111111111111111111"


def _curso(tmp, cid):
    d = tmp / cid
    d.mkdir()
    (d / "curso.json").write_text(
        json.dumps({"id": cid, "titulo": cid, "modulos": []}), encoding="utf-8")


def test_vinculo_muchos_a_muchos(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "CURSOS_DIR", tmp_path)
    monkeypatch.setattr(cc, "CANALES_PATH", tmp_path / "canales.json")
    monkeypatch.setattr(cc, "VINCULOS_PATH", tmp_path / "vinculos.json")
    monkeypatch.setattr(cc, "_credenciales_youtube", lambda: False)
    _curso(tmp_path, "c1")
    _curso(tmp_path, "c2")

    semilla = cc.listar_canales()
    assert [c["channel_id"] for c in semilla] == [RAY]
    assert semilla[0]["handle"] == "@RAYVERSEC"
    assert semilla[0]["nombre"] == "RayverSec"

    extra = cc.agregar_canal(OTRO, "otrocanal", "Otro canal")
    assert extra["handle"] == "@otrocanal"
    assert {c["channel_id"] for c in cc.listar_canales()} == {RAY, OTRO}

    cc.vincular("c1", RAY)
    cc.vincular("c1", OTRO)
    cc.vincular("c2", RAY)
    assert cc.vincular("c1", RAY)["estado"] == "pendiente"

    marcados = cc.registrar_subidas_al_terminar("c1")
    assert len(marcados) == 2
    assert {v["channel_id"] for v in marcados} == {RAY, OTRO}
    for v in marcados:
        assert v["estado"] == "omitido"
        assert v["debida"] is True
        assert v["url_publicada"] == ""
        assert v["estado"] != "subido"

    c2 = cc.listar_vinculos(curso_id="c2")
    assert len(c2) == 1 and c2[0]["estado"] == "pendiente" and c2[0]["debida"] is False
    assert len(cc.listar_vinculos(channel_id=RAY)) == 2

    monkeypatch.setattr(cc, "_credenciales_youtube", lambda: True)
    uno = cc.registrar_subidas_al_terminar("c2")
    assert uno[0]["estado"] == "pendiente"
    assert uno[0]["url_publicada"] == ""
    assert "no se ha publicado" in uno[0]["motivo"]

    publicado = cc.guardar_url_publicada("c2", RAY, "https://www.youtube.com/watch?v=abc123")
    assert publicado["estado"] == "subido"
    assert publicado["debida"] is False
    otra = cc.registrar_subidas_al_terminar("c2")
    assert otra[0]["estado"] == "subido"
    assert otra[0]["url_publicada"] == "https://www.youtube.com/watch?v=abc123"
