"""
lyric_aligner.py
Sincroniza la letra con el audio: devuelve, por cada línea cantada, el instante
en que empieza a sonar en la canción.

Dos vías:
  1. Si el usuario pega una letra en formato .lrc ([mm:ss.xx] texto), se usa tal cual.
  2. Si no, se transcribe el audio con faster-whisper (word timestamps) y se
     alinean las palabras transcritas con las de la letra real (difflib), para
     colgar cada línea del momento en que se canta su primera palabra.

Si faster-whisper no está o algo falla, devuelve None y el builder cae al
reparto uniforme de siempre.
"""
import difflib
import os
import re
import unicodedata

# ── LRC ──────────────────────────────────────────────────────────────────────

_LRC_TS = re.compile(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]")


def parse_lrc(texto: str) -> list[dict] | None:
    """[{texto, start}] a partir de una letra en formato LRC. None si no lo parece."""
    lineas = []
    for raw in texto.splitlines():
        marcas = list(_LRC_TS.finditer(raw))
        if not marcas:
            continue
        cuerpo = _LRC_TS.sub("", raw).strip()
        if not cuerpo:
            continue
        for m in marcas:
            mm, ss, frac = m.group(1), m.group(2), m.group(3) or "0"
            t = int(mm) * 60 + int(ss) + float(f"0.{frac}")
            lineas.append({"texto": cuerpo, "start": t})
    if len(lineas) < 2:
        return None
    lineas.sort(key=lambda x: x["start"])
    for i, ln in enumerate(lineas):
        ln["end"] = lineas[i + 1]["start"] if i + 1 < len(lineas) else ln["start"] + 6.0
    return lineas


# ── Utilidades de texto ──────────────────────────────────────────────────────

def _norm(w: str) -> str:
    w = unicodedata.normalize("NFKD", w.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^\w]", "", w)


def lineas_cantadas(letra: str) -> list[str]:
    """Líneas de la letra que se cantan (sin etiquetas [Verso], sin vacías)."""
    out = []
    for ln in letra.splitlines():
        ln = ln.strip()
        if not ln or re.fullmatch(r"\[[^\]]*\]", ln):
            continue
        out.append(ln)
    return out


# ── Whisper + alineación ─────────────────────────────────────────────────────

_MODEL = None


def _get_model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        tam = os.getenv("WHISPER_MODEL", "base")
        _MODEL = WhisperModel(tam, device="cpu", compute_type="int8")
    return _MODEL


def _palabras_whisper(audio_path: str, idioma: str) -> list[tuple[str, float]]:
    """[(palabra_normalizada, start), ...] de la transcripción del audio."""
    model = _get_model()
    kw = {"word_timestamps": True, "vad_filter": True}
    if idioma and idioma != "auto":
        kw["language"] = idioma
    segments, _info = model.transcribe(audio_path, **kw)
    palabras = []
    for seg in segments:
        for w in (seg.words or []):
            n = _norm(w.word)
            if n:
                palabras.append((n, float(w.start)))
    return palabras


def alinear_con_whisper(audio_path: str, letra: str, idioma: str = "es") -> list[dict] | None:
    """Alinea la letra real con la transcripción del audio. Devuelve
    [{texto, start, end}] por línea cantada, o None si no se puede."""
    try:
        wh = _palabras_whisper(audio_path, idioma)
    except Exception as e:  # noqa: BLE001
        print(f"[LyricAligner] faster-whisper no disponible / falló: {e}")
        return None
    if len(wh) < 4:
        print("[LyricAligner] transcripción demasiado corta para alinear.")
        return None

    lineas = lineas_cantadas(letra)
    if not lineas:
        return None

    # palabras de la letra con su índice de línea
    letra_tokens: list[tuple[int, str]] = []
    for li, ln in enumerate(lineas):
        for w in ln.split():
            n = _norm(w)
            if n:
                letra_tokens.append((li, n))
    if not letra_tokens:
        return None

    wh_words = [w for w, _ in wh]
    wh_times = [t for _, t in wh]
    lt_words = [w for _, w in letra_tokens]

    sm = difflib.SequenceMatcher(a=lt_words, b=wh_words, autojunk=False)
    # tiempo asignado a cada token de la letra (None si no casó)
    t_tok: list[float | None] = [None] * len(letra_tokens)
    for i, j, n in sm.get_matching_blocks():
        for k in range(n):
            t_tok[i + k] = wh_times[j + k]

    matches = sum(1 for x in t_tok if x is not None)
    if matches < max(4, len(letra_tokens) * 0.25):
        print(f"[LyricAligner] alineación pobre ({matches}/{len(letra_tokens)} palabras).")
        return None

    # interpolar los huecos y forzar monotonía
    dur_audio = wh_times[-1] + 2.0
    idxs = [i for i, x in enumerate(t_tok) if x is not None]
    for a, b in zip(idxs, idxs[1:]):
        if b - a > 1:
            t0, t1 = t_tok[a], t_tok[b]
            for k in range(a + 1, b):
                t_tok[k] = t0 + (t1 - t0) * (k - a) / (b - a)
    # extremos
    for i in range(idxs[0] - 1, -1, -1):
        t_tok[i] = max(0.0, t_tok[i + 1] - 0.4)
    for i in range(idxs[-1] + 1, len(t_tok)):
        t_tok[i] = min(dur_audio, t_tok[i - 1] + 0.4)

    # inicio de cada línea = primer token de esa línea
    starts: dict[int, float] = {}
    for (li, _), t in zip(letra_tokens, t_tok):
        if li not in starts:
            starts[li] = t

    prev = 0.0
    res = []
    for li, ln in enumerate(lineas):
        s = starts.get(li, prev)
        s = max(s, prev)  # monótono
        res.append({"texto": ln, "start": s, "end": 0.0})
        prev = s
    for i in range(len(res)):
        res[i]["end"] = res[i + 1]["start"] if i + 1 < len(res) else dur_audio
    return res


def alinear_letra(audio_path: str, letra: str, idioma: str = "es",
                  lrc: str | None = None) -> list[dict] | None:
    """Punto de entrada. Prioriza LRC; si no, Whisper. None => reparto uniforme."""
    if lrc and lrc.strip():
        got = parse_lrc(lrc)
        if got:
            print(f"[LyricAligner] usando LRC ({len(got)} líneas).")
            return got
    return alinear_con_whisper(audio_path, letra, idioma)
