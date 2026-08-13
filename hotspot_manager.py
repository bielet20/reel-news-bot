"""
hotspot_manager.py
Gestiona hotspots interactivos asociados a videos generados.
Persiste en un sidecar JSON: output/{video}.hotspots.json

burn_hotspots() renderiza los hotspots directamente sobre los frames
del MP4 para que el video resultante sea compartible en redes sociales.
"""

import json
import uuid
from pathlib import Path
from typing import Optional

OUTPUT_DIR = Path(__file__).parent / "output"
LIBRARY_DIR = Path(__file__).parent / "_library"


def _sidecar_path(filename: str) -> Path:
    return OUTPUT_DIR / f"{filename}.hotspots.json"


def _load(filename: str) -> dict:
    path = _sidecar_path(filename)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"video": filename, "hold_ms_default": 800, "hotspots": []}


def _save(filename: str, data: dict) -> None:
    _sidecar_path(filename).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_hotspots(filename: str) -> dict:
    return _load(filename)


def add_hotspot(filename: str, hotspot: dict) -> dict:
    data = _load(filename)
    hotspot["id"] = hotspot.get("id") or uuid.uuid4().hex[:8]
    data["hotspots"].append(hotspot)
    _save(filename, data)
    return hotspot


def update_hotspot(filename: str, hotspot_id: str, updates: dict) -> Optional[dict]:
    data = _load(filename)
    for i, h in enumerate(data["hotspots"]):
        if h["id"] == hotspot_id:
            data["hotspots"][i] = {**h, **updates, "id": hotspot_id}
            _save(filename, data)
            return data["hotspots"][i]
    return None


def delete_hotspot(filename: str, hotspot_id: str) -> bool:
    data = _load(filename)
    before = len(data["hotspots"])
    data["hotspots"] = [h for h in data["hotspots"] if h["id"] != hotspot_id]
    if len(data["hotspots"]) < before:
        _save(filename, data)
        return True
    return False


def update_config(filename: str, hold_ms_default: int) -> dict:
    data = _load(filename)
    data["hold_ms_default"] = hold_ms_default
    _save(filename, data)
    return data


# ──────────────────────────────────────────────────────────────────────────────
#  Burn hotspots into video frames
# ──────────────────────────────────────────────────────────────────────────────

def _render_text_overlay(text: str, label: str, px: int, py: int,
                          pw: int, ph: int, font_size: int = 0) -> "Image.Image":
    """Renderiza un overlay de texto/enlace como imagen RGBA."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fondo semitransparente con bordes redondeados
    radius = max(4, min(pw, ph) // 10)
    draw.rounded_rectangle([0, 0, pw - 1, ph - 1], radius=radius, fill=(0, 0, 0, 190))

    # Fuentes del sistema (macOS + Linux fallback)
    _FONT_BOLD = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    _FONT_REGULAR = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    def _font(bold: bool, size: int):
        for path in (_FONT_BOLD if bold else _FONT_REGULAR):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    pad = max(5, min(pw, ph) // 12)
    available_w = pw - pad * 2

    # Tamaño de fuente: usa el valor del usuario o escala con la región
    if not font_size:
        font_size = max(14, min(ph // 4, 48))
    # Texto destino algo más pequeño para que quepan más líneas (especialmente URLs)
    small_size = max(10, int(font_size * 0.78))

    def _tw(s: str, fnt) -> int:
        try:
            return draw.textbbox((0, 0), s, font=fnt)[2]
        except Exception:
            return len(s) * (font_size // 2)

    def _truncate(s: str, fnt, max_w: int) -> str:
        if _tw(s, fnt) <= max_w:
            return s
        while len(s) > 1 and _tw(s[:-1] + "…", fnt) > max_w:
            s = s[:-1]
        return s[:-1] + "…" if s else "…"

    def _char_chunks(word: str, fnt, max_w: int) -> list:
        """Rompe un token largo en fragmentos que caben en max_w."""
        chunks, chunk = [], ""
        for ch in word:
            if _tw(chunk + ch, fnt) <= max_w:
                chunk += ch
            else:
                if chunk:
                    chunks.append(chunk)
                chunk = ch
        if chunk:
            chunks.append(chunk)
        return chunks or [word[:1]]

    def _wrap(s: str, fnt, max_w: int, max_lines: int) -> list:
        """Word-wrap con rotura por carácter para tokens largos (URLs, etc.)."""
        lines: list = []
        line = ""

        def flush_line():
            lines.append(line)

        for word in s.split(" "):
            if not word:
                continue
            sep = " " if line else ""
            if _tw(line + sep + word, fnt) <= max_w:
                line += sep + word
            else:
                # El token no cabe en la línea actual
                if line:
                    flush_line()
                    if len(lines) >= max_lines:
                        return lines
                    line = ""
                # ¿Cabe solo en una línea nueva?
                if _tw(word, fnt) <= max_w:
                    line = word
                else:
                    # Romper carácter a carácter
                    for chunk in _char_chunks(word, fnt, max_w):
                        if _tw(line + chunk, fnt) <= max_w:
                            line += chunk
                        else:
                            if line:
                                flush_line()
                                if len(lines) >= max_lines:
                                    return lines
                            line = chunk

        if line and len(lines) < max_lines:
            lines.append(line)
        return lines

    y = pad

    # Icono ↗ en esquina superior derecha
    ico_fnt = _font(False, max(8, small_size - 1))
    ico = "->"
    ico_w = _tw(ico, ico_fnt)
    draw.text((pw - pad - ico_w, pad), ico, font=ico_fnt, fill=(160, 160, 255, 210))

    # Etiqueta (dorado, negrita)
    if label:
        fnt_lbl = _font(True, font_size)
        lbl = _truncate(label, fnt_lbl, available_w - ico_w - 4)
        draw.text((pad, y), lbl, font=fnt_lbl, fill=(255, 209, 0, 255))
        y += font_size + max(2, pad // 3)

    # Texto destino con word-wrap
    if text and y < ph - pad:
        fnt_txt = _font(False, small_size)
        line_h = small_size + 3
        max_lines = max(1, (ph - y - pad) // line_h)
        lines = _wrap(text, fnt_txt, available_w, max_lines)
        for line in lines:
            if y + line_h > ph - pad:
                break
            draw.text((pad, y), line, font=fnt_txt, fill=(210, 210, 210, 220))
            y += line_h

    return img


def _render_qr_overlay(destination: str, px: int, py: int,
                        pw: int, ph: int) -> "Image.Image":
    """Renderiza un QR code como imagen RGBA."""
    import qrcode
    from PIL import Image

    side = min(pw, ph)
    qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(destination)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="white", back_color="black").convert("RGB")
    qr_img = qr_img.resize((side, side), Image.NEAREST)

    # Fondo cuadrado con padding
    canvas = Image.new("RGBA", (pw, ph), (0, 0, 0, 200))
    offset_x = (pw - side) // 2
    offset_y = (ph - side) // 2
    canvas.paste(qr_img, (offset_x, offset_y))
    return canvas


def _render_image_overlay(library_id: str, library_filename: str,
                           pw: int, ph: int) -> "Image.Image":
    """Carga una imagen de la biblioteca y la redimensiona a la región."""
    from PIL import Image
    path = None
    if library_filename:
        path = LIBRARY_DIR / library_filename
    elif library_id:
        matches = list(LIBRARY_DIR.glob(f"{library_id}*"))
        path = matches[0] if matches else None
    if not path or not path.exists():
        img = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        return img
    img = Image.open(str(path)).convert("RGBA")
    img = img.resize((pw, ph), Image.LANCZOS)
    return img


def burn_hotspots(filename: str, output_filename: Optional[str] = None) -> str:
    """
    Renderiza los hotspots definidos en el sidecar JSON directamente sobre
    los frames del video y exporta un nuevo MP4 listo para compartir.

    Devuelve el nombre del archivo generado (relativo a OUTPUT_DIR).
    """
    import numpy as np
    from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip

    data = _load(filename)
    hotspots = data.get("hotspots", [])
    if not hotspots:
        raise ValueError("Este video no tiene hotspots definidos.")

    src_path = OUTPUT_DIR / filename
    if not src_path.exists():
        raise FileNotFoundError(f"Video no encontrado: {src_path}")

    if output_filename is None:
        stem = Path(filename).stem
        output_filename = f"{stem}_hotspots.mp4"
    out_path = OUTPUT_DIR / output_filename

    video = VideoFileClip(str(src_path))
    vw, vh = video.size  # ancho, alto en píxeles

    overlay_clips = []
    for h in hotspots:
        r = h["region"]
        px = int(r["x"] * vw)
        py = int(r["y"] * vh)
        pw = max(1, int(r["width"] * vw))
        ph = max(1, int(r["height"] * vh))

        dest = h.get("destination", "")
        label = h.get("label", "")
        t_start = float(h.get("time_start", 0))
        t_end = float(h.get("time_end", video.duration))
        duration = max(0.1, t_end - t_start)

        user_fs = int(h.get("font_size") or 0)
        htype = h.get("type", "text")
        if htype == "qr" and dest:
            pil_img = _render_qr_overlay(dest, px, py, pw, ph)
        elif htype == "image":
            lib_id = h.get("library_id", "")
            lib_fn = h.get("library_filename", "")
            if not lib_id and not lib_fn:
                continue
            pil_img = _render_image_overlay(lib_id, lib_fn, pw, ph)
        else:
            pil_img = _render_text_overlay(dest, label, px, py, pw, ph, user_fs)

        arr = np.array(pil_img)
        rgb = arr[:, :, :3]
        alpha = arr[:, :, 3] / 255.0

        clip = (
            ImageClip(rgb)
            .set_mask(ImageClip(alpha, ismask=True).set_duration(duration))
            .set_duration(duration)
            .set_start(t_start)
            .set_position((px, py))
        )
        overlay_clips.append(clip)

    final = CompositeVideoClip([video] + overlay_clips, size=(vw, vh))
    final = final.set_audio(video.audio)

    import os
    import tempfile
    temp_audio = os.path.join(tempfile.gettempdir(), f"_burn_audio_{os.getpid()}.m4a")
    final.write_videofile(
        str(out_path),
        codec="libx264", audio_codec="aac",
        fps=video.fps, preset="fast", threads=4,
        logger=None, temp_audiofile=temp_audio, remove_temp=True,
    )
    video.close()
    final.close()
    return output_filename
