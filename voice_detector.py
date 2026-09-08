"""
voice_detector.py
Detecta si la voz principal de una canción es de hombre, de mujer o mixta
(dúo / coro con ambos registros), a partir del tono fundamental (F0).

Se usa para:
  - decidir a quién pone en pantalla el guion visual (protagonista que canta),
  - decidir si tiene sentido el lip-sync,
sin que el usuario tenga que marcarlo a mano.

Método: `librosa.pyin` sobre la pista (a cappella si la hay, si no la mezcla)
da el F0 por frame; se mira la mediana de los tramos con voz y cuánta masa cae
en la banda masculina (~85-165 Hz) frente a la femenina (~165-320 Hz). Si hay
masa relevante en las dos bandas -> "mixta".

Si librosa falla o no hay tramos con voz claros -> {"tipo": "desconocida"}.
"""
from __future__ import annotations

import os

# Bandas de F0 típicas del canto (Hz). El solape real ~165 Hz es la frontera.
_BANDA_H = (85.0, 165.0)     # voz masculina cantada
_BANDA_M = (165.0, 320.0)    # voz femenina cantada


def detectar_voces(audio_path: str, pista_voz: str | None = None) -> dict:
    """Devuelve {tipo, f0_mediana, frac_hombre, frac_mujer, confianza, fuente}.

    tipo ∈ {"hombre", "mujer", "mixta", "desconocida"}.
    """
    fuente = pista_voz if (pista_voz and os.path.exists(pista_voz)) else audio_path
    a_cappella = fuente == pista_voz
    try:
        import librosa
        import numpy as np

        # 30-150 s son de sobra para el estadístico y evita cargar canciones
        # enteras de 5+ min en RAM.
        y, sr = librosa.load(fuente, sr=16000, mono=True, duration=150.0)
        if y.size < sr * 3:
            return {"tipo": "desconocida", "motivo": "audio demasiado corto"}

        if not a_cappella:
            # En una mezcla, quedarse con la componente armónica ayuda a que pyin
            # siga la voz y no la percusión/bajo.
            y = librosa.effects.harmonic(y, margin=3.0)

        f0, voiced_flag, voiced_prob = librosa.pyin(
            y, fmin=70, fmax=400, sr=sr, frame_length=2048,
        )
        m = np.isfinite(f0) & (voiced_prob > 0.5)
        f0v = f0[m]
        if f0v.size < 40:
            return {"tipo": "desconocida", "motivo": "pocos tramos con voz"}

        mediana = float(np.median(f0v))
        frac_h = float(np.mean((f0v >= _BANDA_H[0]) & (f0v < _BANDA_H[1])))
        frac_m = float(np.mean((f0v >= _BANDA_M[0]) & (f0v <= _BANDA_M[1])))

        # "mixta" si las dos bandas tienen presencia real y ninguna domina del todo
        if frac_h >= 0.25 and frac_m >= 0.25:
            tipo = "mixta"
            conf = min(frac_h, frac_m) * 2
        elif mediana < 165 or frac_h > frac_m:
            tipo = "hombre"
            conf = frac_h
        else:
            tipo = "mujer"
            conf = frac_m

        return {
            "tipo": tipo,
            "f0_mediana": round(mediana, 1),
            "frac_hombre": round(frac_h, 2),
            "frac_mujer": round(frac_m, 2),
            "confianza": round(float(conf), 2),
            "fuente": "a cappella" if a_cappella else "mezcla",
        }
    except Exception as e:  # noqa: BLE001
        return {"tipo": "desconocida", "motivo": f"{type(e).__name__}: {e}"}


def es_femenina(deteccion: dict | None, por_defecto: bool = False) -> bool:
    """Atajo para el pipeline actual (protagonista en pantalla / lip-sync):
    una voz de mujer o mixta cuenta como 'femenina' a efectos de mostrar a la
    cantante y aplicar LatentSync."""
    if not deteccion:
        return por_defecto
    return deteccion.get("tipo") in ("mujer", "mixta")
