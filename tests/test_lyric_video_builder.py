"""Tests de los helpers de estructura de `lyric_video_builder.py`
(`parsear_secciones`, `_formato`). Importa moviepy/PIL/numpy — si no están
instalados, la suite se salta en vez de fallar.
"""
import pytest

lvb = pytest.importorskip(
    "lyric_video_builder",
    reason="lyric_video_builder necesita moviepy/PIL/numpy",
)


class TestParsearSecciones:
    def test_formato_con_etiquetas(self):
        letra = "[Verso 1]\nlínea a\nlínea b\n\n[Estribillo]\nlínea c"
        secs = lvb.parsear_secciones(letra)
        assert [s["label"] for s in secs] == ["Verso 1", "Estribillo"]
        assert secs[0]["lineas"] == ["línea a", "línea b"]
        assert secs[1]["lineas"] == ["línea c"]

    def test_seccion_de_etiqueta_sin_lineas_se_descarta(self):
        letra = "[Intro]\n\n[Verso]\nhay contenido aquí"
        secs = lvb.parsear_secciones(letra)
        assert [s["label"] for s in secs] == ["Verso"]

    def test_formato_sin_etiquetas_divide_por_parrafos(self):
        letra = "primera estrofa\nsegunda línea\n\notra estrofa\ncon dos líneas"
        secs = lvb.parsear_secciones(letra)
        assert len(secs) == 2
        assert secs[0]["lineas"] == ["primera estrofa", "segunda línea"]

    def test_letra_vacia(self):
        assert lvb.parsear_secciones("") == []


class TestFormato:
    def test_conocidos(self):
        assert lvb._formato("16:9")["w"] == 1920
        assert lvb._formato("9:16")["w"] == 1080

    def test_desconocido_cae_a_16_9(self):
        assert lvb._formato("cuadrado") == lvb.FORMATOS["16:9"]
