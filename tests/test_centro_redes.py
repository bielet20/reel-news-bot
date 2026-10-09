"""Centro de Redes (2026-10-05): un registro de cuentas y canales que usan
todas las aplicaciones para publicar. Lo que no debe volver a romperse:
  - cada canal sube con SU token y nunca cae al de otro canal;
  - un token de otro canal no sube nada;
  - las cachés de servicio/playlist no mezclan canales;
  - AI Studio publica por el Centro (antes por un script que desapareció).
"""
import json
from pathlib import Path
from unittest import mock

import pytest

import centro_redes as cr
import youtube_uploader as yt


@pytest.fixture
def centro(tmp_path, monkeypatch):
    tokens = tmp_path / "_tokens"
    tokens.mkdir()
    monkeypatch.setattr(cr, "TOKENS_DIR", tokens)
    monkeypatch.setattr(cr, "REGISTRO", tmp_path / "_config" / "redes.json")
    monkeypatch.setattr(cr, "PUBLICACIONES", tmp_path / "_config" / "redes_publicaciones.json")
    cr.olvidar_estado()
    return tmp_path


def test_semilla_tiene_los_tres_canales_con_sus_tokens(centro):
    data = cr.cargar()
    canales = {c["id"]: c for c in data["canales"]}
    assert set(canales) == {"bieninforma2", "rayver", "rayversec"}
    cuentas = {c["id"]: c for c in data["cuentas"]}
    assert cuentas[canales["bieninforma2"]["cuentas"]["youtube"]]["token"] == "youtube.json"
    assert cuentas[canales["rayver"]["cuentas"]["youtube"]]["token"] == "youtube_rayver.json"
    assert cuentas[canales["rayversec"]["cuentas"]["youtube"]]["token"] == "youtube-cursos.json"
    assert cr.REGISTRO.exists()


def test_crear_cuenta_y_asignarla_a_un_canal(centro):
    a = cr.crear_cuenta("youtube", "Mi Canal")
    b = cr.crear_cuenta("youtube", "Mi Canal")
    assert a["id"] == "youtube-mi-canal" and b["id"] == "youtube-mi-canal-2"
    assert a["token"] == "youtube-mi-canal.json"
    ch = cr.guardar_canal("", nombre="Viajes Épicos", cuentas={"youtube": a["id"]})
    assert ch["id"] == "viajes-epicos" and ch["cuentas"] == {"youtube": a["id"]}
    with pytest.raises(cr.RedesError):
        cr.guardar_canal("viajes-epicos", cuentas={"telegram": a["id"]})  # no es de telegram
    ch = cr.guardar_canal("viajes-epicos", cuentas={"youtube": ""})
    assert ch["cuentas"] == {}


def test_token_fuera_de_tokens_no_vale(centro):
    with pytest.raises(cr.RedesError):
        cr.token_path({"token": "../.env"})


def test_publicar_rayver_usa_su_token_y_exige_su_canal(centro):
    video = centro / "clip.mp4"
    video.write_bytes(b"\x00" * 10)
    with mock.patch.object(yt, "subir_video", return_value={"video_id": "v1", "url": "https://y/v1"}) as sub:
        res = cr.publicar("rayver", video, "Mi canción")
    assert res == {"youtube": {"ok": True, "cuenta": "youtube-rayver", "video_id": "v1", "url": "https://y/v1"}}
    kw = sub.call_args.kwargs
    assert Path(kw["token_file"]).name == "youtube_rayver.json"
    assert kw["exigir_channel_id"] == "UC1ayyOq-jLYWuT_apjAQ9MA"
    assert kw["categoria_id"] == "10"
    assert kw["playlist"] is None
    assert "rayvermusic.com" in kw["descripcion_override"]
    assert cr.publicaciones()[0]["canal"] == "rayver"


def test_canal_nuevo_no_hereda_tags_de_noticias(centro):
    a = cr.crear_cuenta("youtube", "Viajes")
    cr.guardar_canal("viajes", nombre="Viajes", cuentas={"youtube": a["id"]})
    video = centro / "v.mp4"
    video.write_bytes(b"\x00")
    with mock.patch.object(yt, "subir_video", return_value={"video_id": "x", "url": "u"}) as sub:
        cr.publicar("viajes", video, "Islandia")
    assert sub.call_args.kwargs["tags"] == []
    assert sub.call_args.kwargs["descripcion_override"] == "Islandia"


def test_error_de_una_red_no_tumba_la_publicacion(centro):
    video = centro / "v.mp4"
    video.write_bytes(b"\x00")
    with mock.patch.object(yt, "subir_video", side_effect=RuntimeError("invalid_grant: Token has been expired")):
        res = cr.publicar("rayversec", video, "Lección 1", redes=["youtube", "telegram"])
    assert res["youtube"]["ok"] is False and "Conectar" in res["youtube"]["error"]
    assert res["telegram"]["ok"] is False and "aún no" in res["telegram"]["error"]
    assert len(cr.publicaciones()) == 1


def test_canal_inexistente_o_video_inexistente(centro):
    with pytest.raises(cr.RedesError):
        cr.publicar("no-existe", centro / "x.mp4", "t")
    with pytest.raises(cr.RedesError):
        cr.publicar("rayver", centro / "no.mp4", "t")


def test_guardar_token_de_otro_canal_se_rechaza(centro):
    cr.cargar()
    with mock.patch.object(yt, "invalidate_service_cache"):
        with pytest.raises(cr.RedesError):
            cr.guardar_token_youtube("youtube-rayver", {"refresh_token": "r"},
                                     {"channel_id": "UC_otro", "titulo": "Otro"})
        assert not (cr.TOKENS_DIR / "youtube_rayver.json").exists()
        c = cr.guardar_token_youtube("youtube-rayver", {"refresh_token": "r"},
                                     {"channel_id": "UC1ayyOq-jLYWuT_apjAQ9MA", "titulo": "RAYVERMUSIC"})
    guardado = json.loads((cr.TOKENS_DIR / "youtube_rayver.json").read_text(encoding="utf-8"))
    assert guardado["refresh_token"] == "r" and guardado["canal"] == "RAYVERMUSIC"
    assert c["channel_id"] == "UC1ayyOq-jLYWuT_apjAQ9MA"


# ── youtube_uploader multi-canal ──────────────────────────────────────────────

def test_token_de_canal_sin_conectar_no_cae_al_env(tmp_path, monkeypatch):
    """Si RAYVER no tiene token NO se usa el .env (que es Bieninforma2)."""
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "s")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "r-bieninforma2")
    with pytest.raises(RuntimeError, match="no está conectado"):
        yt._load_credentials(tmp_path / "youtube_rayver.json")


def test_token_de_canal_se_lee_de_su_fichero(tmp_path):
    f = tmp_path / "youtube-cursos.json"
    f.write_text(json.dumps({"client_id": "c", "client_secret": "s", "refresh_token": "r"}), encoding="utf-8")
    assert yt._load_credentials(f) == ("c", "s", "r", None)


def test_cache_de_servicio_y_playlists_por_canal(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    yt._service_cache.clear()
    yt._service_cache[yt._clave_token(a)] = {"service": "SA", "expires_at": 9e12}
    assert yt._get_service(a) == "SA"
    assert yt._clave_token(a) != yt._clave_token(b)
    yt.invalidate_service_cache(a)
    assert yt._clave_token(a) not in yt._service_cache
    yt._playlist_cache.clear()
    yt._playlist_cache[(yt._clave_token(a), "Música")] = "PL_A"
    assert yt._playlist_id(None, "Música", token_file=a) == "PL_A"
    yt._playlist_cache.clear()


def test_subir_no_sube_si_el_token_es_de_otro_canal(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\x00")
    service = mock.MagicMock()
    with mock.patch.object(yt, "_get_service", return_value=service), \
         mock.patch.object(yt, "canal_del_token", return_value={"channel_id": "UC_b2", "titulo": "Bieninforma2", "custom_url": ""}):
        with pytest.raises(RuntimeError, match="no del canal elegido"):
            yt.subir_video(str(video), "t", thumbnail_path="", exigir_channel_id="UC_rayver")
    service.videos.assert_not_called()


# ── OAuth: el callback de siempre reparte a las cuentas del Centro ───────────

def test_callback_youtube_reparte_al_centro():
    from api import accounts
    accounts._oauth_state["st1"] = {"cuenta": "youtube-rayver", "volver": "http://localhost:3000/redes"}
    with mock.patch("api.redes.completar_youtube", return_value="OK") as comp:
        assert accounts.youtube_callback(code="c", state="st1") == "OK"
    comp.assert_called_once()
    assert "st1" not in accounts._oauth_state


@pytest.mark.parametrize("ruta", [".env", "_tokens/youtube.json", "../.env", "output/../.env"])
def test_publicar_por_ruta_solo_videos_de_output(ruta):
    from fastapi import HTTPException

    from api.redes import redes_publicar
    with pytest.raises(HTTPException) as e:
        redes_publicar(canal="rayver", titulo="", descripcion="", redes="", privacidad="private",
                       origen="", ruta=ruta, archivo=None)
    assert e.value.status_code == 400


def test_volver_solo_a_esta_maquina():
    from api.redes import _volver_seguro, _con_query
    assert _volver_seguro("https://malo.com/x") == "http://localhost:3000/redes"
    assert _volver_seguro("http://127.0.0.1:8899/?perfil=rayver#ajustes").startswith("http://127.0.0.1:8899")
    assert _con_query("http://127.0.0.1:8899/?perfil=rayver#ajustes", youtube="ok") == \
        "http://127.0.0.1:8899/?perfil=rayver&youtube=ok#ajustes"
