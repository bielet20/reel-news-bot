"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface Region { x: number; y: number; width: number; height: number }

interface Hotspot {
  id: string;
  type: "text" | "qr" | "image";
  time_start: number;
  time_end: number;
  region: Region;
  destination: string;
  label: string;
  hold_ms: number | null;
  font_size: number | null;
  library_id?: string;
  library_filename?: string;
}

interface HotspotData {
  video: string;
  hold_ms_default: number;
  hotspots: Hotspot[];
}

interface DraftRegion {
  startX: number; startY: number;
  endX: number; endY: number;
}

interface LibraryItem {
  id: string;
  name: string;
  type: "image" | "qr";
  filename: string;
  destination?: string;
}

interface Template {
  id: string;
  name: string;
  description: string;
  hotspots: Partial<Hotspot>[];
}

type ResizeHandle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w" | "move";

function getVideoRect(video: HTMLVideoElement) {
  const { videoWidth, videoHeight } = video;
  const box = video.getBoundingClientRect();
  if (!videoWidth || !videoHeight) return { left: 0, top: 0, width: box.width, height: box.height };
  const boxRatio = box.width / box.height;
  const vidRatio = videoWidth / videoHeight;
  let w: number, h: number, left: number, top: number;
  if (vidRatio > boxRatio) {
    w = box.width; h = box.width / vidRatio; left = 0; top = (box.height - h) / 2;
  } else {
    h = box.height; w = box.height * vidRatio; top = 0; left = (box.width - w) / 2;
  }
  return { left, top, width: w, height: h };
}

function normRect(r: DraftRegion): Region {
  return {
    x: Math.min(r.startX, r.endX), y: Math.min(r.startY, r.endY),
    width: Math.abs(r.endX - r.startX), height: Math.abs(r.endY - r.startY),
  };
}

function draftBounds(d: DraftRegion) {
  return { x: Math.min(d.startX, d.endX), y: Math.min(d.startY, d.endY), x2: Math.max(d.startX, d.endX), y2: Math.max(d.startY, d.endY) };
}

// ── Preview renderizado con PIL (texto y QR) ──────────────────────────────────

function LivePreviewImage({ type, label, destination, fontSize, libraryFilename, screenW, screenH, nativeW, nativeH }: {
  type: "text" | "qr" | "image"; label: string; destination: string; fontSize: number;
  libraryFilename: string;
  screenW: number; screenH: number; nativeW: number; nativeH: number;
}) {
  const [src, setSrc] = useState<string>("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (type === "image") {
      setSrc(libraryFilename ? `/library-files/${libraryFilename}` : "");
      return;
    }
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      const params = new URLSearchParams({
        type,
        label,
        destination,
        font_size: String(fontSize),
        pw: String(Math.max(10, Math.round(nativeW))),
        ph: String(Math.max(10, Math.round(nativeH))),
      });
      setSrc(`/api/hotspots/render-preview?${params}&_t=${Date.now()}`);
    }, 180);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [type, label, destination, fontSize, nativeW, nativeH, libraryFilename]);

  if (!src) return null;
  return (
    <img
      src={src}
      width={screenW}
      height={screenH}
      style={{ display: "block", width: screenW, height: screenH, imageRendering: "auto", objectFit: "contain" }}
      alt="preview"
    />
  );
}

// ── Library Picker Modal ──────────────────────────────────────────────────────

function LibraryPicker({ onSelect, onClose }: {
  onSelect: (item: LibraryItem) => void;
  onClose: () => void;
}) {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [filter, setFilter] = useState<"all" | "image" | "qr">("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch("/api/library").then((r) => r.json()).then(setItems).catch(() => {});
  }, []);

  const filtered = items
    .filter((i) => filter === "all" || i.type === filter)
    .filter((i) => !search || i.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 16, padding: 20, width: 480, maxHeight: "80vh", display: "flex", flexDirection: "column" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <p style={{ fontWeight: 700, fontSize: 15, margin: 0 }}>Elegir de biblioteca</p>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 18 }}>✕</button>
        </div>

        <input
          type="text"
          placeholder="Buscar..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 8, padding: "6px 10px", fontSize: 13, marginBottom: 10, width: "100%", boxSizing: "border-box" }}
        />

        <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
          {(["all", "image", "qr"] as const).map((t) => (
            <button key={t} onClick={() => setFilter(t)} style={{ background: filter === t ? "var(--accent)" : "var(--surface2)", color: filter === t ? "#fff" : "var(--muted)", border: "1px solid var(--border)", borderRadius: 20, padding: "3px 12px", fontSize: 11, cursor: "pointer" }}>
              {t === "all" ? "Todo" : t === "image" ? "Imágenes" : "QR"}
            </button>
          ))}
        </div>

        <div style={{ flex: 1, overflowY: "auto", display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))", gap: 8 }}>
          {filtered.length === 0 ? (
            <p style={{ color: "var(--muted)", fontSize: 12, gridColumn: "1/-1", textAlign: "center", paddingTop: 20 }}>
              No hay elementos.{" "}
              <a href="/library" target="_blank" style={{ color: "var(--accent)" }}>Ir a la biblioteca →</a>
            </p>
          ) : filtered.map((item) => (
            <button
              key={item.id}
              onClick={() => onSelect(item)}
              style={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 8, padding: 0, cursor: "pointer", overflow: "hidden", textAlign: "left" }}
            >
              <div style={{ width: "100%", aspectRatio: "1", overflow: "hidden", background: "#111" }}>
                <img src={`/library-files/${item.filename}`} alt={item.name} style={{ width: "100%", height: "100%", objectFit: "contain" }} />
              </div>
              <p style={{ fontSize: 10, color: "var(--text)", margin: "4px 6px 5px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.name}</p>
            </button>
          ))}
        </div>

        <a href="/library" target="_blank" style={{ display: "block", textAlign: "center", fontSize: 11, color: "var(--accent)", marginTop: 12, textDecoration: "none" }}>
          Gestionar biblioteca →
        </a>
      </div>
    </div>
  );
}

// ── Main editor ──────────────────────────────────────────────────────────────

export default function HotspotEditor({ filename }: { filename: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<HotspotData | null>(null);
  const [draft, setDraft] = useState<DraftRegion | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [form, setForm] = useState<{
    type: "text" | "qr" | "image";
    time_start: number; time_end: number;
    destination: string; label: string;
    hold_ms: string; font_size: number;
    library_id: string; library_filename: string; library_name: string;
  } | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [burning, setBurning] = useState(false);
  const [burnedFile, setBurnedFile] = useState<string | null>(null);
  const [, forceUpdate] = useState(0);

  // Templates
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [showSaveTemplate, setShowSaveTemplate] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [savingTemplate, setSavingTemplate] = useState(false);

  // Library picker
  const [showLibraryPicker, setShowLibraryPicker] = useState(false);

  // QR save to library
  const [savingQrToLib, setSavingQrToLib] = useState(false);
  const [qrSavedMsg, setQrSavedMsg] = useState("");

  const resizeHandleRef = useRef<ResizeHandle | null>(null);
  const lastClientPosRef = useRef<{ x: number; y: number } | null>(null);

  const reload = useCallback(() => {
    fetch(`/api/hotspots/${encodeURIComponent(filename)}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setData(d))
      .catch(() => {});
  }, [filename]);

  const loadTemplates = useCallback(() => {
    fetch("/api/templates").then((r) => r.json()).then(setTemplates).catch(() => {});
  }, []);

  useEffect(() => { reload(); loadTemplates(); }, [reload, loadTemplates]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onLoad = () => forceUpdate((n) => n + 1);
    video.addEventListener("loadedmetadata", onLoad);
    return () => video.removeEventListener("loadedmetadata", onLoad);
  }, []);

  const clientToRel = useCallback((clientX: number, clientY: number): { x: number; y: number } | null => {
    const video = videoRef.current;
    if (!video) return null;
    const vr = getVideoRect(video);
    const box = video.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (clientX - box.left - vr.left) / vr.width)),
      y: Math.max(0, Math.min(1, (clientY - box.top - vr.top) / vr.height)),
    };
  }, []);

  // ── window-level resize/move listeners ──────────────────────────────────────
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!resizeHandleRef.current || !lastClientPosRef.current) return;
      const video = videoRef.current;
      if (!video) return;
      const vr = getVideoRect(video);
      const dx = (e.clientX - lastClientPosRef.current.x) / vr.width;
      const dy = (e.clientY - lastClientPosRef.current.y) / vr.height;
      lastClientPosRef.current = { x: e.clientX, y: e.clientY };
      const pos = clientToRel(e.clientX, e.clientY);
      setDraft((prev) => {
        if (!prev) return prev;
        const b = draftBounds(prev);
        let { x, y, x2, y2 } = b;
        const handle = resizeHandleRef.current!;
        if (handle === "move") {
          const w = x2 - x, h = y2 - y;
          x = Math.max(0, Math.min(1 - w, x + dx));
          y = Math.max(0, Math.min(1 - h, y + dy));
          x2 = x + w; y2 = y + h;
        } else {
          if (!pos) return prev;
          if (handle.includes("n")) y = Math.min(pos.y, y2 - 0.01);
          if (handle.includes("s")) y2 = Math.max(pos.y, y + 0.01);
          if (handle.includes("w")) x = Math.min(pos.x, x2 - 0.01);
          if (handle.includes("e")) x2 = Math.max(pos.x, x + 0.01);
        }
        return { startX: x, startY: y, endX: x2, endY: y2 };
      });
    };
    const onUp = () => { resizeHandleRef.current = null; lastClientPosRef.current = null; };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, [clientToRel]);

  // ── draw new region ─────────────────────────────────────────────────────────
  const onMouseDown = (e: React.MouseEvent) => {
    if (form || resizeHandleRef.current) return;
    const pos = clientToRel(e.clientX, e.clientY);
    if (!pos) return;
    e.preventDefault();
    setDrawing(true);
    setDraft({ startX: pos.x, startY: pos.y, endX: pos.x, endY: pos.y });
  };

  const onMouseMove = (e: React.MouseEvent) => {
    if (!drawing) return;
    const pos = clientToRel(e.clientX, e.clientY);
    if (!pos) return;
    setDraft((d) => d ? { ...d, endX: pos.x, endY: pos.y } : d);
  };

  const onMouseUp = (e: React.MouseEvent) => {
    if (!drawing || !draft) return;
    setDrawing(false);
    const pos = clientToRel(e.clientX, e.clientY);
    const finalDraft = { ...draft, endX: pos?.x ?? draft.endX, endY: pos?.y ?? draft.endY };
    const nr = normRect(finalDraft);
    if (nr.width < 0.01 || nr.height < 0.01) { setDraft(null); return; }
    setDraft(finalDraft);
    const t = videoRef.current?.currentTime ?? 0;
    const video = videoRef.current;
    const defaultFs = video?.videoHeight
      ? Math.max(24, Math.round(video.videoHeight * nr.height * 0.18))
      : 40;
    setForm({ type: "text", time_start: parseFloat(t.toFixed(2)), time_end: parseFloat((t + 10).toFixed(2)), destination: "", label: "", hold_ms: "", font_size: defaultFs, library_id: "", library_filename: "", library_name: "" });
    setEditId(null);
  };

  const onHandleMouseDown = (e: React.MouseEvent, handle: ResizeHandle) => {
    e.stopPropagation(); e.preventDefault();
    resizeHandleRef.current = handle;
    lastClientPosRef.current = { x: e.clientX, y: e.clientY };
  };

  // ── save / delete / edit ────────────────────────────────────────────────────
  const saveHotspot = async () => {
    if (!form || !draft) return;
    const region = normRect(draft);
    setSaving(true); setMsg("");
    try {
      const body = {
        type: form.type,
        time_start: form.time_start,
        time_end: form.time_end,
        region,
        destination: form.destination,
        label: form.label,
        hold_ms: form.hold_ms ? parseInt(form.hold_ms) : null,
        font_size: form.font_size || null,
        library_id: form.library_id || null,
        library_filename: form.library_filename || null,
      };
      const enc = encodeURIComponent(filename);
      const url = editId ? `/api/hotspots/${enc}/${editId}` : `/api/hotspots/${enc}`;
      const r = await fetch(url, { method: editId ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error(await r.text());
      reload(); setForm(null); setDraft(null); setEditId(null); setMsg("Guardado ✓");
    } catch (err) { setMsg(`Error: ${err}`); }
    finally { setSaving(false); }
  };

  const startEdit = (h: Hotspot) => {
    setEditId(h.id);
    setDraft({ startX: h.region.x, startY: h.region.y, endX: h.region.x + h.region.width, endY: h.region.y + h.region.height });
    const video = videoRef.current;
    const defaultFs = h.font_size ?? (video?.videoHeight
      ? Math.max(24, Math.round(video.videoHeight * h.region.height * 0.18))
      : 40);
    setForm({ type: h.type, time_start: h.time_start, time_end: h.time_end, destination: h.destination, label: h.label, hold_ms: h.hold_ms?.toString() ?? "", font_size: defaultFs, library_id: h.library_id ?? "", library_filename: h.library_filename ?? "", library_name: "" });
  };

  const deleteHotspot = async (id: string) => {
    await fetch(`/api/hotspots/${encodeURIComponent(filename)}/${id}`, { method: "DELETE" });
    reload();
  };

  const cancelForm = () => { setForm(null); setDraft(null); setEditId(null); };

  const burnIntoVideo = async () => {
    setBurning(true); setBurnedFile(null); setMsg("");
    try {
      const r = await fetch(`/api/hotspots/${encodeURIComponent(filename)}/burn`, { method: "POST" });
      if (!r.ok) throw new Error((await r.json()).detail || await r.text());
      const { output_filename } = await r.json();
      setBurnedFile(output_filename);
    } catch (err) { setMsg(`Error al quemar: ${err}`); }
    finally { setBurning(false); }
  };

  // ── templates ───────────────────────────────────────────────────────────────
  const saveAsTemplate = async () => {
    if (!templateName.trim() || !data) return;
    setSavingTemplate(true);
    try {
      await fetch("/api/templates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: templateName.trim(), hotspots: data.hotspots }),
      });
      loadTemplates();
      setShowSaveTemplate(false);
      setTemplateName("");
      setMsg("Plantilla guardada ✓");
    } catch { setMsg("Error al guardar plantilla"); }
    finally { setSavingTemplate(false); }
  };

  const applyTemplate = async () => {
    const tmpl = templates.find((t) => t.id === selectedTemplate);
    if (!tmpl || !data) return;
    const video = videoRef.current;
    const duration = video?.duration ?? 30;
    for (const h of tmpl.hotspots) {
      const region = (h.region as Region) ?? { x: 0.1, y: 0.1, width: 0.3, height: 0.15 };
      const body = {
        type: h.type ?? "text",
        time_start: 0,
        time_end: Math.min(10, duration),
        region,
        destination: h.destination ?? "",
        label: h.label ?? "",
        hold_ms: h.hold_ms ?? null,
        font_size: h.font_size ?? null,
        library_id: h.library_id ?? null,
        library_filename: h.library_filename ?? null,
      };
      await fetch(`/api/hotspots/${encodeURIComponent(filename)}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
    }
    reload();
    setSelectedTemplate("");
    setMsg(`Plantilla "${tmpl.name}" aplicada ✓`);
  };

  const deleteTemplate = async (id: string) => {
    await fetch(`/api/templates/${id}`, { method: "DELETE" });
    loadTemplates();
  };

  // ── QR save to library ──────────────────────────────────────────────────────
  const saveQrToLibrary = async () => {
    if (!form || form.type !== "qr" || !form.destination.trim()) return;
    setSavingQrToLib(true); setQrSavedMsg("");
    try {
      await fetch("/api/library/qr", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ destination: form.destination.trim(), name: form.label || form.destination }),
      });
      setQrSavedMsg("QR guardado en biblioteca ✓");
    } catch { setQrSavedMsg("Error al guardar"); }
    finally { setSavingQrToLib(false); }
  };

  // ── overlay rendering ────────────────────────────────────────────────────────
  const renderOverlay = () => {
    const video = videoRef.current;
    if (!video) return null;
    const vr = getVideoRect(video);

    const savedOverlays = data?.hotspots
      .filter((h) => h.id !== editId)
      .map((h) => (
        <div
          key={h.id}
          onClick={() => startEdit(h)}
          style={{ position: "absolute", left: vr.left + h.region.x * vr.width, top: vr.top + h.region.y * vr.height, width: h.region.width * vr.width, height: h.region.height * vr.height, border: "2px dashed #60a5fa", borderRadius: 4, cursor: "pointer", boxSizing: "border-box", pointerEvents: "all", overflow: "hidden" }}
          title={`${h.label || h.destination || h.library_filename || ""} — clic para editar`}
        >
          {h.type === "image" && h.library_filename && (
            <img src={`/library-files/${h.library_filename}`} alt="" style={{ width: "100%", height: "100%", objectFit: "contain", pointerEvents: "none" }} />
          )}
          <span style={{ fontSize: 9, background: "#1a1a2e", color: "#60a5fa", padding: "1px 4px", borderRadius: 3, position: "absolute", top: 2, right: 2 }}>
            {h.type === "qr" ? "QR" : h.type === "image" ? "IMG" : "T"} {h.time_start}s
          </span>
        </div>
      ));

    let draftEl = null;
    if (draft && form) {
      const nr = normRect(draft);
      const left   = vr.left + nr.x * vr.width;
      const top    = vr.top  + nr.y * vr.height;
      const w      = nr.width * vr.width;
      const h      = nr.height * vr.height;
      const right  = left + w;
      const bottom = top  + h;
      const midX   = (left + right) / 2;
      const midY   = (top  + bottom) / 2;
      const HS = 9;
      const nativeW = nr.width * (video.videoWidth || vr.width);
      const nativeH = nr.height * (video.videoHeight || vr.height);

      const handles: { handle: ResizeHandle; x: number; y: number; cursor: string }[] = [
        { handle: "nw", x: left,  y: top,    cursor: "nw-resize" },
        { handle: "n",  x: midX,  y: top,    cursor: "n-resize"  },
        { handle: "ne", x: right, y: top,    cursor: "ne-resize" },
        { handle: "e",  x: right, y: midY,   cursor: "e-resize"  },
        { handle: "se", x: right, y: bottom, cursor: "se-resize" },
        { handle: "s",  x: midX,  y: bottom, cursor: "s-resize"  },
        { handle: "sw", x: left,  y: bottom, cursor: "sw-resize" },
        { handle: "w",  x: left,  y: midY,   cursor: "w-resize"  },
      ];

      draftEl = (
        <>
          <div style={{ position: "absolute", left, top, width: w, height: h, pointerEvents: "none", zIndex: 4, overflow: "hidden", borderRadius: 4 }}>
            <LivePreviewImage
              type={form.type} label={form.label} destination={form.destination}
              fontSize={form.font_size} libraryFilename={form.library_filename}
              screenW={w} screenH={h} nativeW={nativeW} nativeH={nativeH}
            />
          </div>
          <div style={{ position: "absolute", left, top, width: w, height: h, border: "2px solid #7c3aed", borderRadius: 4, boxSizing: "border-box", cursor: "move", pointerEvents: "all", zIndex: 5 }} onMouseDown={(e) => onHandleMouseDown(e, "move")} />
          {handles.map(({ handle, x, y, cursor }) => (
            <div key={handle} onMouseDown={(e) => onHandleMouseDown(e, handle)} style={{ position: "absolute", left: x - HS / 2, top: y - HS / 2, width: HS, height: HS, background: "#fff", border: "2px solid #7c3aed", borderRadius: 2, cursor, pointerEvents: "all", zIndex: 10, boxSizing: "border-box" }} />
          ))}
        </>
      );
    } else if (draft && !form) {
      const nr = normRect(draft);
      draftEl = <div style={{ position: "absolute", left: vr.left + nr.x * vr.width, top: vr.top + nr.y * vr.height, width: nr.width * vr.width, height: nr.height * vr.height, border: "2px solid #f59e0b", borderRadius: 4, background: "rgba(245,158,11,0.12)", pointerEvents: "none", boxSizing: "border-box" }} />;
    }

    return <>{savedOverlays}{draftEl}</>;
  };

  const inp = (label: string, node: React.ReactNode) => (
    <label style={{ display: "block", marginBottom: 10 }}>
      <span style={{ color: "var(--muted)", fontSize: 11, display: "block", marginBottom: 4 }}>{label}</span>
      {node}
    </label>
  );
  const sx = { background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 8, padding: "6px 10px", width: "100%", fontSize: 13 } as const;

  return (
    <>
      {showLibraryPicker && (
        <LibraryPicker
          onSelect={(item) => {
            setForm((f) => f ? { ...f, library_id: item.id, library_filename: item.filename, library_name: item.name } : f);
            setShowLibraryPicker(false);
          }}
          onClose={() => setShowLibraryPicker(false)}
        />
      )}

      <div style={{ display: "flex", gap: 20, alignItems: "flex-start", flexWrap: "wrap" }}>

        {/* columna video */}
        <div style={{ flex: "1 1 320px" }}>
          <p style={{ color: "var(--muted)", fontSize: 12, marginBottom: 8 }}>
            {form
              ? "Ves el preview en vivo · arrastra los handles para redimensionar · arrastra el interior para mover."
              : "Pausa el video y arrastra un rectángulo sobre la zona interactiva."}
          </p>
          <div style={{ position: "relative", lineHeight: 0, cursor: form ? "default" : "crosshair" }} ref={overlayRef} onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={onMouseUp}>
            <video ref={videoRef} src={`/videos/${filename}`} controls style={{ width: "100%", borderRadius: 12, display: "block", background: "#000", maxHeight: 500 }} />
            <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
              {renderOverlay()}
            </div>
          </div>
        </div>

        {/* columna derecha */}
        <div style={{ flex: "0 0 290px" }}>

          {/* Plantillas */}
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, padding: 14, marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <p style={{ color: "var(--text)", fontWeight: 600, fontSize: 13, margin: 0 }}>Plantillas</p>
              <a href="/library" target="_blank" style={{ fontSize: 11, color: "var(--accent)", textDecoration: "none" }}>Biblioteca →</a>
            </div>

            {templates.length > 0 && (
              <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
                <select value={selectedTemplate} onChange={(e) => setSelectedTemplate(e.target.value)} style={{ ...sx, flex: 1 }}>
                  <option value="">Seleccionar plantilla...</option>
                  {templates.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.hotspots.length})</option>)}
                </select>
                <button onClick={applyTemplate} disabled={!selectedTemplate} title="Aplicar" style={{ background: selectedTemplate ? "var(--accent)" : "var(--surface2)", color: selectedTemplate ? "#fff" : "var(--muted)", border: "none", borderRadius: 8, padding: "6px 10px", cursor: selectedTemplate ? "pointer" : "not-allowed", fontSize: 12 }}>
                  Aplicar
                </button>
              </div>
            )}

            {templates.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 8, maxHeight: 100, overflowY: "auto" }}>
                {templates.map((t) => (
                  <div key={t.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "var(--surface2)", borderRadius: 6, padding: "4px 8px" }}>
                    <span style={{ fontSize: 11, color: "var(--text)" }}>{t.name} <span style={{ color: "var(--muted)" }}>({t.hotspots.length})</span></span>
                    <button onClick={() => deleteTemplate(t.id)} style={{ background: "none", border: "none", color: "var(--error)", cursor: "pointer", fontSize: 12 }}>✕</button>
                  </div>
                ))}
              </div>
            )}

            {data && data.hotspots.length > 0 && !showSaveTemplate && (
              <button onClick={() => setShowSaveTemplate(true)} style={{ width: "100%", background: "var(--surface2)", color: "var(--muted)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 0", fontSize: 12, cursor: "pointer" }}>
                + Guardar como plantilla
              </button>
            )}

            {showSaveTemplate && (
              <div style={{ marginTop: 6 }}>
                <input
                  type="text"
                  placeholder="Nombre de la plantilla"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && saveAsTemplate()}
                  autoFocus
                  style={{ ...sx, marginBottom: 6 }}
                />
                <div style={{ display: "flex", gap: 6 }}>
                  <button onClick={saveAsTemplate} disabled={savingTemplate || !templateName.trim()} style={{ flex: 1, background: savingTemplate ? "var(--surface2)" : "var(--accent)", color: savingTemplate ? "var(--muted)" : "#fff", border: "none", borderRadius: 8, padding: "6px 0", fontSize: 12, cursor: "pointer" }}>
                    {savingTemplate ? "Guardando..." : "Guardar"}
                  </button>
                  <button onClick={() => { setShowSaveTemplate(false); setTemplateName(""); }} style={{ background: "var(--surface2)", color: "var(--muted)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px", fontSize: 12, cursor: "pointer" }}>
                    ✕
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Form nuevo/editar hotspot */}
          {form && (
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, padding: 16, marginBottom: 16 }}>
              <p style={{ color: "var(--text)", fontWeight: 600, fontSize: 14, marginBottom: 12 }}>
                {editId ? "Editar hotspot" : "Nuevo hotspot"}
              </p>

              {inp("Tipo", (
                <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as "text" | "qr" | "image" })} style={sx}>
                  <option value="text">Texto / Enlace</option>
                  <option value="qr">Código QR</option>
                  <option value="image">Imagen de biblioteca</option>
                </select>
              ))}

              {inp("Inicio (s)", (
                <input type="number" step="0.1" value={form.time_start} onChange={(e) => setForm({ ...form, time_start: parseFloat(e.target.value) })} style={sx} />
              ))}

              {inp("Fin (s)", (
                <input type="number" step="0.1" value={form.time_end} onChange={(e) => setForm({ ...form, time_end: parseFloat(e.target.value) })} style={sx} />
              ))}

              {/* Tipo imagen: selector de biblioteca */}
              {form.type === "image" && (
                <div style={{ marginBottom: 10 }}>
                  <span style={{ color: "var(--muted)", fontSize: 11, display: "block", marginBottom: 4 }}>Imagen</span>
                  {form.library_filename ? (
                    <div style={{ display: "flex", gap: 8, alignItems: "center", background: "var(--surface2)", borderRadius: 8, padding: 8 }}>
                      <img src={`/library-files/${form.library_filename}`} alt="" style={{ width: 48, height: 48, objectFit: "contain", borderRadius: 4, background: "#111" }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ fontSize: 11, color: "var(--text)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{form.library_name || form.library_filename}</p>
                      </div>
                      <button onClick={() => setShowLibraryPicker(true)} style={{ background: "none", border: "1px solid var(--border)", borderRadius: 6, color: "var(--muted)", cursor: "pointer", fontSize: 11, padding: "3px 7px" }}>Cambiar</button>
                    </div>
                  ) : (
                    <button onClick={() => setShowLibraryPicker(true)} style={{ width: "100%", background: "var(--surface2)", border: "1px dashed var(--border)", borderRadius: 8, padding: "10px 0", fontSize: 12, color: "var(--accent)", cursor: "pointer" }}>
                      Elegir de biblioteca
                    </button>
                  )}
                </div>
              )}

              {/* Tipo texto y QR: campo destino */}
              {form.type !== "image" && inp("Destino (URL o texto)", (
                <input type="text" value={form.destination} onChange={(e) => setForm({ ...form, destination: e.target.value })} placeholder="https://... o texto libre" style={sx} />
              ))}

              {/* QR: botón guardar en biblioteca */}
              {form.type === "qr" && form.destination.trim() && (
                <div style={{ marginBottom: 10 }}>
                  <button onClick={saveQrToLibrary} disabled={savingQrToLib} style={{ background: "none", border: "1px solid var(--border)", borderRadius: 8, color: "#fb923c", cursor: savingQrToLib ? "not-allowed" : "pointer", fontSize: 11, padding: "5px 10px", width: "100%" }}>
                    {savingQrToLib ? "Guardando..." : "Guardar QR en biblioteca"}
                  </button>
                  {qrSavedMsg && <p style={{ fontSize: 11, color: qrSavedMsg.startsWith("Error") ? "var(--error)" : "var(--success)", marginTop: 4 }}>{qrSavedMsg}</p>}
                </div>
              )}

              {form.type === "text" && inp("Etiqueta (opcional)", (
                <input type="text" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="Ver más..." style={sx} />
              ))}

              {form.type === "text" && (
                <label style={{ display: "block", marginBottom: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ color: "var(--muted)", fontSize: 11 }}>Tamaño de fuente (px en video)</span>
                    <span style={{ color: "var(--text)", fontSize: 12, fontWeight: 600 }}>{form.font_size}px</span>
                  </div>
                  <input type="range" min={10} max={120} step={1} value={form.font_size} onChange={(e) => setForm({ ...form, font_size: parseInt(e.target.value) })} style={{ width: "100%", accentColor: "var(--accent)" }} />
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
                    <span>10px</span><span>120px</span>
                  </div>
                </label>
              )}

              {inp("Duración pulsación ms (vacío = global)", (
                <input type="number" value={form.hold_ms} onChange={(e) => setForm({ ...form, hold_ms: e.target.value })} placeholder={data?.hold_ms_default?.toString() ?? "800"} style={sx} />
              ))}

              {msg && <p style={{ fontSize: 12, color: msg.startsWith("Error") ? "var(--error)" : "var(--success)", marginBottom: 8 }}>{msg}</p>}

              <div style={{ display: "flex", gap: 8 }}>
                <button onClick={saveHotspot} disabled={saving} style={{ flex: 1, background: "var(--accent)", color: "#fff", border: "none", borderRadius: 8, padding: "8px 0", fontSize: 13, cursor: "pointer" }}>
                  {saving ? "Guardando..." : "Guardar"}
                </button>
                <button onClick={cancelForm} style={{ background: "var(--surface2)", color: "var(--muted)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 12px", fontSize: 13, cursor: "pointer" }}>✕</button>
              </div>
            </div>
          )}

          {/* Lista hotspots */}
          {data && data.hotspots.length > 0 && (
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, padding: 14, marginBottom: 16 }}>
              <p style={{ color: "var(--text)", fontWeight: 600, fontSize: 13, marginBottom: 10 }}>Hotspots ({data.hotspots.length})</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {data.hotspots.map((h) => (
                  <div key={h.id} style={{ background: "var(--surface2)", borderRadius: 8, padding: "8px 10px", border: editId === h.id ? "1px solid var(--accent)" : "1px solid transparent" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <div style={{ minWidth: 0 }}>
                        <span style={{ fontSize: 11, color: h.type === "qr" ? "#fb923c" : h.type === "image" ? "#4ade80" : "#60a5fa", background: "var(--surface)", padding: "1px 6px", borderRadius: 4, marginRight: 6 }}>
                          {h.type === "qr" ? "QR" : h.type === "image" ? "IMG" : "T"}
                        </span>
                        <span style={{ fontSize: 12, color: "var(--text)" }}>{h.label || h.destination || h.library_filename || "(sin etiqueta)"}</span>
                        <p style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
                          {h.time_start}s – {h.time_end}s{h.font_size ? ` · ${h.font_size}px` : ""}
                        </p>
                      </div>
                      <div style={{ display: "flex", gap: 4, flexShrink: 0, marginLeft: 8 }}>
                        <button onClick={() => startEdit(h)} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 13 }}>✏</button>
                        <button onClick={() => deleteHotspot(h.id)} style={{ background: "none", border: "none", color: "var(--error)", cursor: "pointer", fontSize: 13 }}>✕</button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {data && data.hotspots.length === 0 && !form && (
            <p style={{ color: "var(--muted)", fontSize: 13, textAlign: "center", paddingTop: 16 }}>
              Arrastra un área sobre el video para crear el primer hotspot.
            </p>
          )}

          {/* Burn */}
          {data && data.hotspots.length > 0 && (
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, padding: 14 }}>
              <p style={{ color: "var(--text)", fontWeight: 600, fontSize: 13, marginBottom: 8 }}>Compartir en redes sociales</p>
              <p style={{ color: "var(--muted)", fontSize: 11, marginBottom: 12, lineHeight: 1.5 }}>
                Quema los hotspots directamente sobre los frames del video para compartirlo en cualquier plataforma.
              </p>
              <button onClick={burnIntoVideo} disabled={burning} style={{ width: "100%", background: burning ? "var(--surface2)" : "#7c3aed", color: burning ? "var(--muted)" : "#fff", border: "none", borderRadius: 8, padding: "9px 0", fontSize: 13, cursor: burning ? "not-allowed" : "pointer", fontWeight: 600 }}>
                {burning ? "Procesando video..." : "Quemar hotspots en video"}
              </button>
              {msg && <p style={{ fontSize: 12, color: msg.startsWith("Error") ? "var(--error)" : "var(--success)", marginTop: 8 }}>{msg}</p>}
              {burnedFile && (
                <div style={{ marginTop: 10, padding: "10px 12px", background: "#0a2a1a", border: "1px solid #1a5a3a", borderRadius: 8 }}>
                  <p style={{ color: "#4ade80", fontSize: 12, marginBottom: 6 }}>Video generado</p>
                  <a href={`/videos/${burnedFile}`} download={burnedFile} style={{ display: "block", textAlign: "center", background: "#15803d", color: "#fff", padding: "7px 0", borderRadius: 7, fontSize: 13, textDecoration: "none", fontWeight: 600 }}>
                    Descargar {burnedFile}
                  </a>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
