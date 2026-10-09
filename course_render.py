"""
course_render.py
Convierte las lecciones de un curso en vídeo 16:9.

  narrar_escena()    → mp3 por escena con tts.generar_audio (caché por hash
                       de texto + voz: solo se regenera si cambia algo)
  capturar_escena()  → PNG 1920×1080 de la diapositiva. La pinta el MISMO
                       componente React que el editor (ruta del frontend
                       /cursos/render/<curso>/<escena>), fotografiada con el
                       Chromium de Playwright: lo que ves es lo que sale.
  render_leccion()   → un MP4 por lección (+ .srt), con fundidos entre
                       escenas y música de fondo que baja con la voz
  render_curso()     → todas las lecciones seguidas + capítulos de YouTube

Dentro del contenedor NVENC no está disponible (no hay GPU): libx264.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import course_store as cs

FRONTEND_URL = os.environ.get("CURSOS_FRONTEND_URL", "http://frontend:3000").rstrip("/")
ANCHO, ALTO, FPS = 1920, 1080, 30
PAUSA_ESCENA = 0.7        # aire tras la narración antes de cambiar de diapositiva
DURACION_SIN_VOZ = 5.0    # diapositiva sin narración ni duración fijada
FUNDIDO = 0.35


def _ffmpeg(args: list, log=print) -> None:
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {r.stderr.strip()[-600:]}")


def _duracion(ruta: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", ruta], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _tiene_audio(ruta: str) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=index", "-of", "csv=p=0", ruta], capture_output=True, text=True)
    return bool(r.stdout.strip())


def _rel(curso_id: str, ruta: Path) -> str:
    return str(ruta.relative_to(cs.dir_curso(curso_id))).replace("\\", "/")


# ─── Narración ───────────────────────────────────────────────────────────────

def _hash_narracion(curso: dict, escena: dict) -> str:
    voz = curso.get("voz") or cs.VOZ_DEFECTO
    base = json.dumps([escena.get("narracion", "").strip(), voz.get("servicio"), voz.get("voz")],
                      ensure_ascii=False)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def narrar_escena(curso_id: str, escena_id: str, forzar: bool = False, log=print) -> dict | None:
    """Genera (o reutiliza) el audio de una escena. Devuelve escena["audio"]."""
    from tts import generar_audio
    curso = cs.cargar(curso_id)
    _, escena = cs.buscar_escena(curso, escena_id)
    texto = escena.get("narracion", "").strip()
    if not texto:
        cs.modificar(curso_id, lambda c: cs.buscar_escena(c, escena_id)[1].update(audio=None))
        return None
    h = _hash_narracion(curso, escena)
    previo = escena.get("audio") or {}
    if (not forzar and previo.get("hash") == h
            and (cs.dir_curso(curso_id) / previo.get("archivo", "_")).exists()):
        return previo
    voz = curso.get("voz") or cs.VOZ_DEFECTO
    ruta = cs.subdir(curso_id, "audio") / f"{escena_id}_{h}.mp3"
    log(f"   -> Voz: {texto[:60]}...")
    ruta_final = generar_audio(texto, str(ruta), servicio=voz.get("servicio", "edge-tts"), voz=voz.get("voz"))
    ruta_final = Path(ruta_final)
    audio = {"archivo": _rel(curso_id, ruta_final), "hash": h, "duracion": round(_duracion(str(ruta_final)), 2)}
    # borrar versiones anteriores de esta escena
    for viejo in cs.subdir(curso_id, "audio").glob(f"{escena_id}_*"):
        if viejo != ruta_final:
            viejo.unlink(missing_ok=True)
    cs.modificar(curso_id, lambda c: cs.buscar_escena(c, escena_id)[1].update(audio=audio))
    return audio


def duracion_escena(escena: dict) -> float:
    """Lo que dura la escena en el vídeo: la fijada a mano o voz + pausa."""
    voz = float((escena.get("audio") or {}).get("duracion") or 0)
    if escena.get("tipo") == "video" and escena.get("video"):
        v = escena["video"]
        clip = max(0.5, float(v.get("fin") or 0) - float(v.get("inicio") or 0))
        # si la voz en off es más larga, el clip se congela en su último fotograma
        return max(clip, voz + 0.3) if voz else clip
    fija = float(escena.get("duracion") or 0)
    if fija:
        return max(fija, voz + 0.2 if voz else 0)
    return voz + PAUSA_ESCENA if voz else DURACION_SIN_VOZ


# ─── Captura de diapositivas ─────────────────────────────────────────────────

def capturar_escenas(curso_id: str, escena_ids: list, log=print) -> dict:
    """PNG de cada escena {escena_id: ruta}. Una sola sesión de Chromium."""
    from playwright.sync_api import sync_playwright
    carpeta = cs.subdir(curso_id, "render/slides")
    salida = {}
    with sync_playwright() as p:
        nav = p.chromium.launch(args=["--no-sandbox"])
        pagina = nav.new_page(viewport={"width": ANCHO, "height": ALTO}, device_scale_factor=1)
        for eid in escena_ids:
            url = f"{FRONTEND_URL}/cursos/render/{curso_id}/{eid}"
            pagina.goto(url, wait_until="networkidle", timeout=120000)
            pagina.wait_for_selector("#slide[data-listo='1']", timeout=60000)
            pagina.evaluate("document.fonts.ready")
            pagina.wait_for_timeout(150)
            ruta = carpeta / f"{eid}.png"
            pagina.locator("#slide").screenshot(path=str(ruta))
            salida[eid] = str(ruta)
            log(f"   -> Diapositiva capturada ({len(salida)}/{len(escena_ids)})")
        nav.close()
    return salida


# ─── Subtítulos ──────────────────────────────────────────────────────────────

def _t_srt(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _bloques_subtitulo(texto: str, max_palabras: int = 9) -> list[str]:
    """Frases de hasta ~9 palabras, cortando preferiblemente en la puntuación."""
    bloques = []
    for frase in re.split(r"(?<=[.!?;:])\s+", texto.strip()):
        palabras = frase.split()
        while palabras:
            bloques.append(" ".join(palabras[:max_palabras]))
            palabras = palabras[max_palabras:]
    return [b for b in bloques if b]


def _srt_leccion(tramos: list) -> str:
    """tramos: [(inicio, duracion_voz, texto)]. Reparte cada narración en
    bloques con tiempo proporcional a su número de caracteres."""
    lineas, n = [], 1
    for inicio, dur_voz, texto in tramos:
        bloques = _bloques_subtitulo(texto)
        total = sum(len(b) for b in bloques) or 1
        t = inicio
        for b in bloques:
            d = dur_voz * len(b) / total
            lineas += [str(n), f"{_t_srt(t)} --> {_t_srt(t + d)}", b, ""]
            n += 1
            t += d
    return "\n".join(lineas)


# ─── Lección ─────────────────────────────────────────────────────────────────

def _segmento_diapositiva(png: str, audio: str | None, dur: float, transicion: str, salida: str):
    vf = f"scale={ANCHO}:{ALTO},format=yuv420p"
    if transicion == "fundido":
        vf += f",fade=t=in:st=0:d={FUNDIDO},fade=t=out:st={max(0, dur - FUNDIDO):.3f}:d={FUNDIDO}"
    args = ["-loop", "1", "-framerate", str(FPS), "-i", png]
    if audio:
        args += ["-i", audio]
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    args += ["-t", f"{dur:.3f}", "-vf", vf, "-af", "apad", "-r", str(FPS),
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-tune", "stillimage",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest", salida]
    # -shortest con apad: corta al -t del vídeo, el audio se rellena con silencio
    _ffmpeg(args)


def _segmento_video(curso_id: str, escena: dict, audio: str | None, salida: str):
    v = escena["video"]
    origen = str(cs.dir_curso(curso_id) / v["archivo"])
    ini = float(v.get("inicio") or 0)
    clip = max(0.5, float(v.get("fin") or 0) - ini)
    dur = duracion_escena(escena)
    vf = (f"scale={ANCHO}:{ALTO}:force_original_aspect_ratio=decrease,"
          f"pad={ANCHO}:{ALTO}:(ow-iw)/2:(oh-ih)/2,fps={FPS},format=yuv420p")
    if dur > clip + 0.05:  # voz más larga que el clip: congelar el último fotograma
        vf += f",tpad=stop_mode=clone:stop_duration={dur - clip:.3f}"
    args = ["-ss", f"{ini:.3f}", "-t", f"{clip:.3f}", "-i", origen]
    if audio:  # narración encima del clip (sustituye su sonido)
        args += ["-i", audio, "-map", "0:v", "-map", "1:a", "-af", "apad"]
    elif _tiene_audio(origen):  # sonido original del clip (grabación con micro)
        args += ["-map", "0:v", "-map", "0:a:0", "-af", "apad"]
    else:  # clip mudo: pista de silencio para que todos los segmentos sean iguales
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a"]
    args += ["-t", f"{dur:.3f}", "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest", salida]
    _ffmpeg(args)


def render_leccion(curso_id: str, leccion_id: str, log=print) -> dict:
    curso = cs.cargar(curso_id)
    _, leccion = cs.buscar_leccion(curso, leccion_id)
    escenas = leccion.get("escenas") or []
    if not escenas:
        raise ValueError("La lección no tiene escenas")

    log(f"-> Narración ({len(escenas)} escenas)...")
    for e in escenas:
        narrar_escena(curso_id, e["id"], log=log)
    curso = cs.cargar(curso_id)
    _, leccion = cs.buscar_leccion(curso, leccion_id)
    escenas = leccion["escenas"]

    log("-> Capturando diapositivas...")
    pngs = capturar_escenas(curso_id, [e["id"] for e in escenas if e.get("tipo") != "video"], log=log)

    log("-> Montando el vídeo...")
    tmp = cs.subdir(curso_id, f"render/tmp_{leccion_id}")
    lista, tramos, t = [], [], 0.0
    for i, e in enumerate(escenas):
        dur = duracion_escena(e)
        audio = str(cs.dir_curso(curso_id) / e["audio"]["archivo"]) if e.get("audio") else None
        seg = str(tmp / f"{i:03d}.mp4")
        if e.get("tipo") == "video" and e.get("video"):
            _segmento_video(curso_id, e, audio, seg)
        else:
            _segmento_diapositiva(pngs[e["id"]], audio, dur, e.get("transicion", "fundido"), seg)
        lista.append(seg)
        if e.get("audio") and e.get("narracion"):
            tramos.append((t, float(e["audio"]["duracion"]), e["narracion"]))
        t += dur
        log(f"   -> Escena {i + 1}/{len(escenas)} ({dur:.1f}s)")

    concat = tmp / "lista.txt"
    concat.write_text("".join(f"file '{Path(s).as_posix()}'\n" for s in lista), encoding="utf-8")
    unido = str(tmp / "unido.mp4")
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", unido])

    carpeta = cs.subdir(curso_id, "render")
    base = f"leccion_{leccion_id}"
    srt = carpeta / f"{base}.srt"
    srt.write_text(_srt_leccion(tramos), encoding="utf-8")
    final = carpeta / f"{base}.mp4"
    _mezclar_final(curso, unido, str(srt), str(final), log)
    shutil.rmtree(tmp, ignore_errors=True)

    dur_final = round(_duracion(str(final)), 2)
    render = {"archivo": _rel(curso_id, final), "srt": _rel(curso_id, srt),
              "duracion": dur_final, "fecha": cs.ahora()}
    cs.modificar(curso_id, lambda c: cs.buscar_leccion(c, leccion_id)[1].update(render=render))
    log(f"-> Lección renderizada: {final.name} ({dur_final:.1f}s)")
    return render


def _mezclar_final(curso: dict, video: str, srt: str, salida: str, log=print):
    """Música de fondo (con bajada automática bajo la voz) y subtítulos quemados."""
    musica = None
    if curso.get("musica"):
        m = Path(__file__).parent / "_music" / curso["musica"]
        musica = str(m) if m.exists() else None
    quemar = bool(curso.get("subtitulos")) and Path(srt).stat().st_size > 0
    if not musica and not quemar:
        shutil.copyfile(video, salida)
        return
    args = ["-i", video]
    filtros_a = None
    if musica:
        vol = float(curso.get("volumen_musica", 0.12))
        args += ["-stream_loop", "-1", "-i", musica]
        filtros_a = (f"[1:a]volume={vol}[m];[m][0:a]sidechaincompress=threshold=0.03:ratio=8:"
                     f"attack=20:release=400[md];[0:a][md]amix=inputs=2:duration=first:normalize=0[a]")
    if quemar:
        # pequeños y pegados abajo: en un curso la diapositiva es lo principal
        estilo = ("FontName=DejaVu Sans,FontSize=12,PrimaryColour=&H00FFFFFF,OutlineColour=&H99000000,"
                  "BorderStyle=3,Outline=1,Shadow=0,MarginV=14")
        ruta_srt = srt.replace("\\", "/").replace(":", "\\:")
        args += ["-vf", f"subtitles='{ruta_srt}':force_style='{estilo}'", "-c:v", "libx264",
                 "-preset", "medium", "-crf", "20"]
    else:
        args += ["-c:v", "copy"]
    if filtros_a:
        args += ["-filter_complex", filtros_a, "-map", "0:v", "-map", "[a]"]
    args += ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", salida]
    log("   -> Mezcla final (música / subtítulos)...")
    _ffmpeg(args)


# ─── Curso completo ──────────────────────────────────────────────────────────

def render_curso(curso_id: str, log=print) -> dict:
    """Renderiza las lecciones que falten o estén desactualizadas y las une."""
    curso = cs.cargar(curso_id)
    lecciones = [(m, l) for m in curso["modulos"] for l in m["lecciones"] if l.get("escenas")]
    if not lecciones:
        raise ValueError("El curso no tiene lecciones con escenas")
    archivos, capitulos, t = [], [], 0.0
    for m, l in lecciones:
        render = l.get("render") or {}
        if not render.get("archivo") or not (cs.dir_curso(curso_id) / render["archivo"]).exists():
            log(f"== {m['titulo']} · {l['titulo']}")
            render = render_leccion(curso_id, l["id"], log=log)
        archivos.append(str(cs.dir_curso(curso_id) / render["archivo"]))
        mm, ss = divmod(int(t), 60)
        hh, mm = divmod(mm, 60)
        capitulos.append(f"{hh:02d}:{mm:02d}:{ss:02d} {m['titulo']} — {l['titulo']}" if hh
                         else f"{mm:02d}:{ss:02d} {m['titulo']} — {l['titulo']}")
        t += float(render.get("duracion") or _duracion(archivos[-1]))
    carpeta = cs.subdir(curso_id, "render")
    lista = carpeta / "curso_lista.txt"
    lista.write_text("".join(f"file '{Path(a).as_posix()}'\n" for a in archivos), encoding="utf-8")
    final = carpeta / "curso_completo.mp4"
    log("-> Uniendo todas las lecciones...")
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", "-movflags", "+faststart", str(final)])
    lista.unlink(missing_ok=True)
    cap = carpeta / "capitulos.txt"
    cap.write_text("\n".join(capitulos) + "\n", encoding="utf-8")
    render = {"archivo": _rel(curso_id, final), "capitulos": _rel(curso_id, cap),
              "duracion": round(_duracion(str(final)), 2), "fecha": cs.ahora()}
    cs.modificar(curso_id, lambda c: c.update(render=render))
    log(f"-> Curso completo: {render['duracion'] / 60:.1f} min")
    try:
        import course_canales
        marcados = course_canales.registrar_subidas_al_terminar(curso_id)
        if not marcados:
            log("-> Sin canales vinculados: no hay subida")
        for v in marcados:
            log(f"-> Canal {v['channel_id']}: {v['estado']} ({v.get('motivo') or 'ya publicado'})")
    except Exception as e:  # noqa: BLE001
        log(f"-> No se registro la subida a los canales: {e}")
    return render
