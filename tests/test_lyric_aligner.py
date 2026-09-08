"""Tests de `lyric_aligner.py`: parseo de LRC, normalización y alineación
letra↔transcripción. La transcripción de Whisper se inyecta con un mock, así
que no hace falta `faster-whisper` ni audio real.
"""
import lyric_aligner


class TestParseLrc:
    def test_lrc_basico(self):
        lrc = "[00:01.50]Primera línea\n[00:04.00]Segunda línea\n[00:07.20]Tercera"
        out = lyric_aligner.parse_lrc(lrc)
        assert [round(l["start"], 2) for l in out] == [1.5, 4.0, 7.2]
        assert out[0]["texto"] == "Primera línea"
        # end de cada línea = start de la siguiente
        assert out[0]["end"] == out[1]["start"]
        assert out[-1]["end"] > out[-1]["start"]

    def test_multiples_marcas_en_una_linea(self):
        lrc = "[00:01.00][00:10.00]Estribillo repetido\n[00:05.00]Otra"
        out = lyric_aligner.parse_lrc(lrc)
        starts = sorted(l["start"] for l in out)
        assert starts == [1.0, 5.0, 10.0]

    def test_ordena_por_tiempo(self):
        lrc = "[00:09.00]Tarde\n[00:02.00]Pronto\n[00:05.00]Medio"
        out = lyric_aligner.parse_lrc(lrc)
        assert [l["texto"] for l in out] == ["Pronto", "Medio", "Tarde"]

    def test_texto_sin_marcas_devuelve_none(self):
        assert lyric_aligner.parse_lrc("solo\nletra\nsin tiempos") is None

    def test_una_sola_linea_devuelve_none(self):
        assert lyric_aligner.parse_lrc("[00:01.00]única línea") is None


class TestNorm:
    def test_quita_acentos_y_puntuacion_y_baja_caja(self):
        assert lyric_aligner._norm("¡Canción!") == "cancion"
        assert lyric_aligner._norm("CORAZÓN,") == "corazon"

    def test_solo_puntuacion_queda_vacio(self):
        assert lyric_aligner._norm("...") == ""


class TestLineasCantadas:
    def test_ignora_etiquetas_y_vacias(self):
        letra = "[Verse 1]\nLine one\n\nLine two\n[Chorus]\nHook line"
        assert lyric_aligner.lineas_cantadas(letra) == ["Line one", "Line two", "Hook line"]


class TestAlinearConWhisper:
    def _mock_palabras(self, monkeypatch, palabras):
        monkeypatch.setattr(
            lyric_aligner, "_palabras_whisper",
            lambda audio_path, idioma: [(lyric_aligner._norm(w), t) for w, t in palabras],
        )

    def test_alinea_lineas_a_su_primera_palabra(self, monkeypatch):
        letra = "hello world here\nsecond line now"
        palabras = [
            ("hello", 1.0), ("world", 1.4), ("here", 1.8),
            ("second", 5.0), ("line", 5.4), ("now", 5.8),
        ]
        self._mock_palabras(monkeypatch, palabras)
        out = lyric_aligner.alinear_con_whisper("x.wav", letra, "en")
        assert out is not None
        assert len(out) == 2
        assert abs(out[0]["start"] - 1.0) < 0.01
        assert abs(out[1]["start"] - 5.0) < 0.01
        assert out[0]["end"] == out[1]["start"]

    def test_transcripcion_muy_corta_devuelve_none(self, monkeypatch):
        self._mock_palabras(monkeypatch, [("hello", 1.0)])
        assert lyric_aligner.alinear_con_whisper("x.wav", "hello world", "en") is None

    def test_alineacion_pobre_devuelve_none(self, monkeypatch):
        # La transcripción no se parece en nada a la letra.
        self._mock_palabras(monkeypatch, [(f"zzz{i}", float(i)) for i in range(20)])
        letra = "\n".join(f"real lyric line {i}" for i in range(6))
        assert lyric_aligner.alinear_con_whisper("x.wav", letra, "en") is None

    def test_starts_monotonos(self, monkeypatch):
        # Aunque whisper devuelva tiempos desordenados, los starts salen crecientes.
        letra = "one two\nthree four\nfive six"
        palabras = [
            ("one", 2.0), ("two", 1.0),
            ("three", 0.5), ("four", 4.0),
            ("five", 3.0), ("six", 8.0),
        ]
        self._mock_palabras(monkeypatch, palabras)
        out = lyric_aligner.alinear_con_whisper("x.wav", letra, "en")
        starts = [l["start"] for l in out]
        assert starts == sorted(starts)


class TestAlinearLetra:
    def test_lrc_tiene_prioridad(self, monkeypatch):
        def _boom(*a, **k):
            raise AssertionError("no debería llamar a whisper si hay LRC válido")
        monkeypatch.setattr(lyric_aligner, "_palabras_whisper", _boom)
        lrc = "[00:01.00]A\n[00:02.00]B"
        out = lyric_aligner.alinear_letra("x.wav", "A\nB", "es", lrc=lrc)
        assert [l["texto"] for l in out] == ["A", "B"]

    def test_no_separa_voz_si_ya_es_acapella(self, monkeypatch):
        llamado = {"sep": False}
        monkeypatch.setattr(lyric_aligner, "_separar_voz",
                            lambda p: llamado.__setitem__("sep", True))
        monkeypatch.setattr(lyric_aligner, "alinear_con_whisper",
                            lambda *a, **k: [{"texto": "a", "start": 0.0, "end": 1.0}])
        lyric_aligner.alinear_letra("voz.wav", "a", "es", ya_es_voz=True)
        assert llamado["sep"] is False
