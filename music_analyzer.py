"""
music_analyzer.py
Detecta el tramo mas energetico de una cancion (tipicamente el coro/hook)
usando analisis espectral con librosa. No necesita transcripcion ni subtitulos.

Soporta archivos de audio (.mp3, .wav, .flac, .aac, .m4a, ...) y
de video (.mp4, .mov, ...), en cuyo caso extrae el audio primero con moviepy.
"""

import os
import tempfile

import numpy as np

EXTS_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v", ".ts"}
EXTS_AUDIO = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".opus", ".wma"}


def _extraer_audio_tmp(ruta_video: str) -> str:
    """Extrae el audio de un video a un WAV temporal. Devuelve la ruta del WAV."""
    from moviepy.editor import VideoFileClip
    tmp = os.path.join(tempfile.gettempdir(), f"_mus_audio_{os.getpid()}.wav")
    clip = VideoFileClip(ruta_video)
    try:
        clip.audio.write_audiofile(tmp, verbose=False, logger=None)
    finally:
        clip.close()
    return tmp


def detectar_coro(ruta: str, duracion_objetivo: int = 45,
                   duracion_min: int = 20, duracion_max: int = 59) -> dict:
    """
    Detecta el tramo con mayor energia sonora del audio (el coro o hook
    de una cancion, donde la musica suele ser mas densa e intensa).

    Args:
        ruta:              Ruta al archivo (.mp3, .wav, .mp4, .mov, ...).
        duracion_objetivo: Duracion ideal del tramo en segundos.
        duracion_min:      Minimo de segundos aceptable.
        duracion_max:      Maximo de segundos permitido.

    Returns:
        Dict con {inicio, fin, duracion} en segundos.
    """
    try:
        import librosa
    except ImportError:
        raise ImportError(
            "librosa no esta instalado. Ejecuta: pip install librosa"
        )

    ext = os.path.splitext(ruta)[1].lower()
    tmp_wav = None
    ruta_audio = ruta

    if ext in EXTS_VIDEO:
        print("   -> Extrayendo audio del video para analizar...")
        tmp_wav = _extraer_audio_tmp(ruta)
        ruta_audio = tmp_wav

    print("   -> Analizando energia del audio (detectando coro/hook)...")
    try:
        y, sr = librosa.load(ruta_audio, sr=22050, mono=True)
    finally:
        if tmp_wav and os.path.isfile(tmp_wav):
            try:
                os.remove(tmp_wav)
            except Exception:
                pass

    duracion_total = len(y) / sr

    if duracion_total <= duracion_max:
        return {"inicio": 0.0, "fin": duracion_total, "duracion": duracion_total}

    hop_length = 512
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]

    # Suavizar para evitar picos aislados (transitorios, palmas, etc.)
    from scipy.ndimage import uniform_filter1d
    ventana_suav = max(1, int(sr / hop_length))
    rms_suave = uniform_filter1d(rms.astype(float), size=ventana_suav)

    n_frames = len(rms_suave)
    frames_obj = int(duracion_objetivo * sr / hop_length)
    frames_min = int(duracion_min * sr / hop_length)

    # Sliding window: buscar la ventana con mayor energia promedio
    mejor_score = -1.0
    mejor_i = 0
    for i in range(max(1, n_frames - frames_min + 1)):
        fin_i = min(i + frames_obj, n_frames)
        if fin_i - i < frames_min:
            break
        score = np.mean(rms_suave[i:fin_i])
        if score > mejor_score:
            mejor_score = score
            mejor_i = i

    inicio = mejor_i * hop_length / sr
    fin = min(inicio + duracion_objetivo, duracion_total)

    # Snap al beat mas cercano: que el corte de inicio caiga en un tiempo
    # musical natural (no en la mitad de un compas)
    try:
        _, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
        beat_times = librosa.frames_to_time(beats, sr=sr, hop_length=hop_length)
        if len(beat_times) > 0:
            idx = int(np.argmin(np.abs(beat_times - inicio)))
            candidato = float(beat_times[idx])
            if abs(candidato - inicio) < 2.0:
                inicio = candidato
                fin = min(inicio + duracion_objetivo, duracion_total)
    except Exception:
        pass

    return {"inicio": inicio, "fin": fin, "duracion": fin - inicio}
