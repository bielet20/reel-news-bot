"""Tests de `voice_detector.py`. `detectar_voces` con audio real necesita
librosa; aquí solo se cubre el camino de error (sin fichero) y el atajo
`es_femenina`, que son pura lógica.
"""
import voice_detector


class TestEsFemenina:
    def test_mujer_y_mixta_cuentan_como_femenina(self):
        assert voice_detector.es_femenina({"tipo": "mujer"}) is True
        assert voice_detector.es_femenina({"tipo": "mixta"}) is True

    def test_hombre_no(self):
        assert voice_detector.es_femenina({"tipo": "hombre"}) is False

    def test_sin_deteccion_usa_por_defecto(self):
        assert voice_detector.es_femenina(None, por_defecto=True) is True
        assert voice_detector.es_femenina(None) is False

    def test_desconocida_no_es_femenina(self):
        assert voice_detector.es_femenina({"tipo": "desconocida"}) is False


class TestDetectarVoces:
    def test_fichero_inexistente_devuelve_desconocida(self):
        out = voice_detector.detectar_voces("no_existe_este_audio.wav")
        assert out["tipo"] == "desconocida"

    def test_no_revienta_nunca(self):
        # Contrato: pase lo que pase, devuelve un dict con 'tipo'.
        out = voice_detector.detectar_voces("", pista_voz="tampoco_existe.wav")
        assert isinstance(out, dict) and "tipo" in out
