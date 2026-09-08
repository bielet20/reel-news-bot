"""Tests de los helpers puros de `comfy_video_builder.py` (parseo de la
respuesta del LLM, conteo de secciones, utilidades de nombres de modelo y
cálculo de frames). No tocan ComfyUI ni la red.
"""
import pytest

import comfy_video_builder as cvb


class TestStripThink:
    def test_quita_bloque_think(self):
        assert cvb.strip_think("<think>razonando...</think>respuesta") == "respuesta"

    def test_sin_think_no_cambia(self):
        assert cvb.strip_think("  hola  ") == "hola"


class TestExtractJson:
    def test_quita_fences(self):
        assert cvb.extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_recorta_texto_alrededor(self):
        assert cvb.extract_json('blah blah {"a": 1} trailing') == '{"a": 1}'


class TestJsonLenient:
    def test_json_valido(self):
        assert cvb._json_lenient('{"a": 1, "b": [2, 3]}') == {"a": 1, "b": [2, 3]}

    def test_comas_colgando(self):
        assert cvb._json_lenient('{"a": 1, "b": [2, 3,],}') == {"a": 1, "b": [2, 3]}

    def test_claves_sin_comillas(self):
        assert cvb._json_lenient('{a: 1, b: 2}') == {"a": 1, "b": 2}

    def test_salida_cortada_se_reequilibra(self):
        out = cvb._json_lenient('{"escenas": [{"x": 1}, {"y": 2}')
        assert out == {"escenas": [{"x": 1}, {"y": 2}]}

    def test_con_fence_y_texto(self):
        raw = 'Aquí tienes el plan:\n```json\n{"style": "noir",}\n```\nEspero que sirva'
        assert cvb._json_lenient(raw) == {"style": "noir"}

    def test_ilegible_lanza(self):
        with pytest.raises((ValueError, Exception)):
            cvb._json_lenient("esto no es json ni de lejos")


class TestCountLinesPerSection:
    def test_cuenta_por_etiqueta(self):
        letra = "[Verse]\na\nb\n\n[Chorus]\nc\nd\ne"
        assert cvb.count_lines_per_section(letra) == [2, 3]

    def test_texto_antes_de_primera_etiqueta_se_ignora(self):
        letra = "titulo suelto\n[Verse]\na\nb"
        assert cvb.count_lines_per_section(letra) == [2]

    def test_sin_etiquetas_devuelve_vacio(self):
        assert cvb.count_lines_per_section("a\nb\nc") == []


class TestNombresDeModelo:
    def test_base_normaliza_separadores(self):
        assert cvb._base("Wan2.2-Lightning\\high_noise_model.safetensors") == "high_noise_model.safetensors"
        assert cvb._base("foo/bar/baz.gguf") == "baz.gguf"

    def test_tiene_compara_por_basename(self):
        lista = ["subdir/high_noise_model.safetensors", "other.gguf"]
        assert cvb._tiene("Wan2.2-Lightning\\high_noise_model.safetensors", lista) is True
        assert cvb._tiene("no_esta.safetensors", lista) is False


class TestSnapLtxFrames:
    def test_forma_8k_mas_1(self):
        for n in (9, 20, 33, 100, 184.6):
            assert (cvb._snap_ltx_frames(n) - 1) % 8 == 0

    def test_respeta_limites(self):
        assert cvb._snap_ltx_frames(1) >= 9
        assert cvb._snap_ltx_frames(99999) <= cvb.LTX_MAX_FRAMES
