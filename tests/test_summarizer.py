"""Tests de los helpers de resumen sin IA (`summarizer.py`).

Son funciones puras (solo `os` + `re`), así que corren sin red ni modelos.
"""
import summarizer


class TestDividirOraciones:
    def test_descarta_fragmentos_cortos(self):
        texto = "Hola. Esta oración es lo bastante larga para contar de verdad."
        out = summarizer._dividir_oraciones(texto)
        assert out == ["Esta oración es lo bastante larga para contar de verdad."]

    def test_colapsa_saltos_de_linea(self):
        texto = "Primera oración con longitud suficiente aquí.\nSegunda oración también larga."
        out = summarizer._dividir_oraciones(texto)
        assert len(out) == 2
        assert all("\n" not in o for o in out)

    def test_texto_vacio(self):
        assert summarizer._dividir_oraciones("") == []


class TestResumenExtractivo:
    def test_devuelve_todo_si_hay_pocas_oraciones(self):
        texto = ("La primera oración habla del tema principal con detalle. "
                 "La segunda oración amplía el mismo asunto.")
        out = summarizer.resumen_extractivo(texto, n_oraciones=3)
        assert len(out) == 2

    def test_selecciona_n_oraciones_y_conserva_orden(self):
        texto = " ".join(
            f"Oración número {i} sobre economía y mercados financieros globales." for i in range(8)
        )
        out = summarizer.resumen_extractivo(texto, n_oraciones=3)
        assert len(out) == 3
        # el orden de aparición se mantiene
        indices = [int(o.split()[2]) for o in out]
        assert indices == sorted(indices)

    def test_texto_vacio(self):
        assert summarizer.resumen_extractivo("", n_oraciones=3) == []


class TestLimpiarTranscripcion:
    def test_quita_muletillas_y_espacios(self):
        out = summarizer._limpiar_transcripcion("eh  bueno   o sea   esto es importante")
        assert "  " not in out
        assert out == out.strip()


class TestChunksTranscripcion:
    def test_agrupa_por_tamano_y_descarta_restos_muy_cortos(self):
        texto = " ".join(f"palabra{i}" for i in range(76))
        chunks = summarizer._chunks_transcripcion(texto, n_palabras=35)
        assert [pos for pos, _ in chunks] == [0, 35]  # el resto de 6 palabras se descarta
        assert all(len(c.split()) >= 8 for _, c in chunks)

    def test_transcripcion_corta_no_produce_chunks(self):
        assert summarizer._chunks_transcripcion("una dos tres", n_palabras=35) == []


class TestScoreChunkVideo:
    def test_premia_numeros(self):
        con_datos = summarizer._score_chunk_video("el pib creció un 25 por ciento en 2024", {})
        sin_datos = summarizer._score_chunk_video("el ambiente estaba muy tranquilo aquella tarde", {})
        assert con_datos > sin_datos

    def test_chunk_vacio(self):
        assert summarizer._score_chunk_video("", {}) == 0.0


class TestRecortarAPalabras:
    def test_no_toca_si_cabe(self):
        assert summarizer._recortar_a_palabras("una dos tres", 5) == "una dos tres"

    def test_recorta_y_marca_con_puntos(self):
        out = summarizer._recortar_a_palabras("una dos tres cuatro cinco seis", 3)
        assert out == "una dos tres..."


class TestConstruirResultado:
    def test_estructura_y_duracion_estimada(self):
        r = summarizer._construir_resultado(
            titulo="T", fuente="F", hook="Un hook.",
            puntos=["Punto uno.", "Punto dos."], cierre="Un cierre.",
            max_palabras=135,
        )
        assert r["titulo"] == "T"
        assert r["palabras"] == len(r["guion"].split())
        assert r["duracion_estimada_seg"] == round(r["palabras"] / 2.5, 1)
