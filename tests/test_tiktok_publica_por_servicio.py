"""Regresión 2026-10-04: el piloto automático publicaba TikTok con el
tiktok_uploader.py viejo ("TikTok no conectado") aunque la cuenta estaba
autorizada en el servicio api.bieninforma2.site."""
from pathlib import Path
from unittest import mock

from api.publish import PublishRequest, _upload_tiktok


def test_upload_tiktok_va_por_el_servicio(tmp_path, monkeypatch):
    video = tmp_path / "reel.mp4"
    video.write_bytes(b"\x00" * 10)
    monkeypatch.setenv("TIKTOK_API_KEY", "k")
    monkeypatch.setenv("TIKTOK_API_URL", "https://svc.test")
    resp = mock.Mock(ok=True)
    resp.json.return_value = {"publishId": "p123"}
    with mock.patch("api.tiktok_post.requests.post", return_value=resp) as post:
        r = _upload_tiktok(PublishRequest(filename="reel.mp4", platforms=["tiktok"],
                                          tiktok_caption="hola"), video)
    assert r == {"status": "ok", "publish_id": "p123"}
    url = post.call_args.args[0]
    assert url == "https://svc.test/publish"
    assert post.call_args.kwargs["headers"] == {"X-API-Key": "k"}
    assert post.call_args.kwargs["data"]["privacyLevel"] == "SELF_ONLY"


def test_sin_api_key_da_error_claro(tmp_path, monkeypatch):
    monkeypatch.delenv("TIKTOK_API_KEY", raising=False)
    try:
        _upload_tiktok(PublishRequest(filename="r.mp4", platforms=["tiktok"]), Path("r.mp4"))
    except RuntimeError as e:
        assert "TIKTOK_API_KEY" in str(e)
    else:
        raise AssertionError("debía fallar sin API key")
