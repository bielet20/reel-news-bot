"use client";

import { useEffect, useRef, useState } from "react";
import PublishModal from "../components/PublishModal";

const ESTILOS = [
  { id: "cinematico",  label: "Cinematico",  icon: "🎬", desc: "Dramático, iluminación oscura" },
  { id: "abstracto",   label: "Abstracto",   icon: "🌀", desc: "Arte fluido, colores vivos" },
  { id: "urbano",      label: "Urbano",      icon: "🌆", desc: "Neon, calle, noche" },
  { id: "naturaleza",  label: "Naturaleza",  icon: "🌿", desc: "Paisajes, luz dorada" },
  { id: "romantico",   label: "Romántico",   icon: "🌹", desc: "Cálido, bokeh suave" },
  { id: "minimalista", label: "Minimalista", icon: "⬜", desc: "Limpio, colores sutiles" },
];

interface JobState {
  id: string;
  status: "running" | "completed" | "failed";
  progress: { actual: number; total: number; label: string };
  output_files: string[];
  error: string | null;
  sync_letra?: string;
  voces?: { tipo?: string; f0_mediana?: number; fuente?: string } | null;
}

export default function MontajePage() {
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioPath, setAudioPath] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const [letra, setLetra] = useState("");
  const [letraLrc, setLetraLrc] = useState("");
  const [artista, setArtista] = useState("");
  const [titulo, setTitulo] = useState("");
  const [estilo, setEstilo] = useState("cinematico");
  const [mostrarLetra, setMostrarLetra] = useState(true);
  const [mostrarCabecera, setMostrarCabecera] = useState(true);
  const [aspect, setAspect] = useState<"16:9" | "9:16">("16:9");
  const [proveedores, setProveedores] = useState<{ id: string; label: string; disponible: boolean; nota: string }[]>([]);
  const [estado, setEstado] = useState<{
    comfy: boolean; lm_studio: boolean; problemas: string[];
    control_center?: boolean;
    arranque?: { activo: boolean; mensaje: string };
  } | null>(null);
  const [arrancando, setArrancando] = useState(false);
  const [provider, setProvider] = useState<string>("wan22");
  const [voz, setVoz] = useState<"auto" | "hombre" | "mujer" | "mixta">("auto");
  const modoVideo = provider !== "imagen";
  const [vozFile, setVozFile] = useState<File | null>(null);
  const [vozPath, setVozPath] = useState<string>("");
  const [uploadingVoz, setUploadingVoz] = useState(false);
  const [job, setJob] = useState<JobState | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [publishing, setPublishing] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Estado de las herramientas (ComfyUI, LM Studio, modelos) + generadores
  const cargarEstado = () => {
    fetch("/api/music-clip/estado")
      .then((r) => r.json())
      .then((e) => {
        setEstado(e);
        setProveedores(e.providers || []);
        setArrancando(Boolean(e.arranque?.activo));
      })
      .catch(() => {});
  };
  useEffect(() => {
    cargarEstado();
    const id = setInterval(cargarEstado, arrancando ? 3000 : 15000);
    return () => clearInterval(id);
  }, [arrancando]);

  const arrancarHerramientas = async () => {
    setArrancando(true);
    try {
      const r = await fetch("/api/music-clip/arrancar-herramientas", { method: "POST" });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setError(d.detail || "No se pudo arrancar (Centro de Control :8090).");
        setArrancando(false);
      }
    } catch {
      setError("No se pudo contactar con el backend.");
      setArrancando(false);
    }
    cargarEstado();
  };

  // Poll job status
  useEffect(() => {
    if (!job || job.status !== "running") {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/music-clip/jobs/${job.id}`);
        if (res.ok) {
          const data: JobState = await res.json();
          setJob(data);
          if (data.status !== "running") clearInterval(pollRef.current!);
        }
      } catch { /* retry */ }
    }, 2500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [job?.id, job?.status]);

  async function handleAudioSelect(file: File) {
    setAudioFile(file);
    setAudioPath("");
    setError("");
    setUploading(true);

    try {
      const fd = new FormData();
      fd.append("file", file);
      // Upload directo al backend para evitar el límite de body del proxy Next.js
      const backendUrl = typeof window !== "undefined"
        ? `${window.location.protocol}//${window.location.hostname}:8000`
        : "http://localhost:8000";
      const res = await fetch(`${backendUrl}/api/music-clip/upload-audio`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setAudioPath(data.path);
    } catch (e) {
      setError(`Error subiendo audio: ${e}`);
      setAudioFile(null);
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleAudioSelect(file);
  }

  async function handleVozSelect(file: File) {
    setVozFile(file);
    setVozPath("");
    setError("");
    setUploadingVoz(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const backendUrl = typeof window !== "undefined"
        ? `${window.location.protocol}//${window.location.hostname}:8000`
        : "http://localhost:8000";
      const res = await fetch(`${backendUrl}/api/music-clip/upload-audio`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setVozPath(data.path);
    } catch (e) {
      setError(`Error subiendo la pista de voz: ${e}`);
      setVozFile(null);
    } finally {
      setUploadingVoz(false);
    }
  }

  async function handleGenerate() {
    if (!audioPath) { setError("Sube una canción primero."); return; }
    if (!letra.trim()) { setError("Añade la letra de la canción."); return; }

    setError("");
    setSubmitting(true);
    setJob(null);

    try {
      const res = await fetch("/api/music-clip/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audio_path: audioPath,
          letra,
          letra_lrc: letraLrc.trim() || null,
          artista,
          titulo,
          estilo,
          mostrar_letra: mostrarLetra,
          mostrar_cabecera: mostrarCabecera,
          modo_fondo: modoVideo ? "video" : "imagen",
          provider,
          aspect,
          voz: modoVideo ? voz : "auto",
          pista_voz_path: modoVideo && voz !== "hombre" && vozPath ? vozPath : null,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const { job_id } = await res.json();
      setJob({ id: job_id, status: "running", progress: { actual: 0, total: 0, label: "Iniciando…" }, output_files: [], error: null });
    } catch (e) {
      setError(`${e}`);
    } finally {
      setSubmitting(false);
    }
  }

  const isRunning = job?.status === "running";
  const hasSections = letra.trim().split(/\n\s*\n/).filter(Boolean).length > 0;

  return (
    <main className="min-h-screen px-4 py-10">
      <div className="max-w-2xl mx-auto">

        {publishing && (
          <PublishModal filename={publishing} onClose={() => setPublishing(null)} />
        )}

        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--text)" }}>Montaje de videoclip</h1>
          <p style={{ color: "var(--muted)", fontSize: 14 }}>
            Sube tu canción y la letra — generamos un vídeo por sección (fondos IA
            relacionados con la letra) y un videoclip completo.
          </p>
        </div>

        <div className="space-y-5">

          {/* ── Audio upload ─── */}
          <Section title="Tu canción">
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={() => !audioFile && fileInputRef.current?.click()}
              style={{
                border: `2px dashed ${dragging ? "var(--accent)" : audioFile ? "var(--success)" : "var(--border)"}`,
                borderRadius: 12, padding: "24px 20px", textAlign: "center",
                cursor: audioFile ? "default" : "pointer",
                background: dragging ? "rgba(99,102,241,0.07)" : "var(--surface2)",
                transition: "all 0.2s",
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="audio/*"
                className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleAudioSelect(f); }}
              />
              {uploading ? (
                <p style={{ color: "var(--muted)", fontSize: 14 }}>⟳ Subiendo audio…</p>
              ) : audioFile ? (
                <div>
                  <p style={{ fontSize: 15, fontWeight: 700, color: "var(--success)", marginBottom: 4 }}>
                    ✓ {audioFile.name}
                  </p>
                  <p style={{ fontSize: 12, color: "var(--muted)", marginBottom: 10 }}>
                    {(audioFile.size / 1024 / 1024).toFixed(1)} MB
                  </p>
                  {audioPath && (
                    <audio
                      ref={audioRef}
                      controls
                      src={`/api/music-clip/audio-preview?path=${encodeURIComponent(audioPath)}`}
                      style={{ width: "100%", maxWidth: 360, borderRadius: 8 }}
                    />
                  )}
                  <button
                    onClick={(e) => { e.stopPropagation(); setAudioFile(null); setAudioPath(""); }}
                    style={{ display: "block", margin: "10px auto 0", fontSize: 12, color: "var(--muted)", background: "none", border: "none", cursor: "pointer" }}
                  >
                    ✕ Cambiar archivo
                  </button>
                </div>
              ) : (
                <>
                  <p style={{ fontSize: 32, marginBottom: 8 }}>🎵</p>
                  <p style={{ fontSize: 14, color: "var(--text)", marginBottom: 4 }}>
                    Arrastra aquí tu canción o <span style={{ color: "var(--accent)" }}>haz clic para seleccionar</span>
                  </p>
                  <p style={{ fontSize: 12, color: "var(--muted)" }}>MP3, WAV, FLAC, AAC, M4A, AIFF · máx 300 MB</p>
                </>
              )}
            </div>
          </Section>

          {/* ── Título y artista ─── */}
          <Section title="Canción">
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div>
                <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 4 }}>Título</label>
                <input
                  value={titulo}
                  onChange={(e) => setTitulo(e.target.value)}
                  placeholder="Nombre de la canción"
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 4 }}>Artista</label>
                <input
                  value={artista}
                  onChange={(e) => setArtista(e.target.value)}
                  placeholder="Tu nombre artístico"
                  style={inputStyle}
                />
              </div>
            </div>
          </Section>

          {/* ── Letra ─── */}
          <Section
            title="Letra"
            hint='Separa secciones con línea en blanco, o usa etiquetas como [Verso 1], [Estribillo]. La letra se sincroniza sola con el audio (Whisper).'
          >
            <textarea
              value={letra}
              onChange={(e) => setLetra(e.target.value)}
              placeholder={`[Verso 1]\nLinea de la canción...\nOtra línea...\n\n[Estribillo]\nEl estribillo aquí...\nMás letra...`}
              rows={14}
              style={{
                ...inputStyle,
                resize: "vertical",
                fontFamily: "ui-monospace, monospace",
                fontSize: 13,
                lineHeight: 1.6,
              }}
            />
            {letra.trim() && (
              <div style={{ marginTop: 6, display: "flex", gap: 8, flexWrap: "wrap" }}>
                {letra.trim().split(/\n\s*\n/).filter(Boolean).map((sec, i) => {
                  const firstLine = sec.trim().split("\n")[0];
                  const label = firstLine.startsWith("[") ? firstLine.replace(/[\[\]]/g, "") : `Sección ${i + 1}`;
                  return (
                    <span key={i} style={{
                      fontSize: 11, padding: "2px 8px", borderRadius: 20,
                      background: "rgba(99,102,241,0.15)", color: "var(--accent)",
                      border: "1px solid rgba(99,102,241,0.3)",
                    }}>
                      {label}
                    </span>
                  );
                })}
              </div>
            )}
            <details style={{ marginTop: 10 }}>
              <summary style={{ fontSize: 12, color: "var(--muted)", cursor: "pointer", userSelect: "none" }}>
                ¿Tienes la letra con tiempos (.lrc)? Pégala para sincronía exacta
              </summary>
              <textarea
                value={letraLrc}
                onChange={(e) => setLetraLrc(e.target.value)}
                placeholder={`[00:12.30]Primera línea cantada\n[00:15.80]Segunda línea\n[00:19.10]...`}
                rows={6}
                style={{ ...inputStyle, marginTop: 8, resize: "vertical", fontFamily: "ui-monospace, monospace", fontSize: 12 }}
              />
              <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                Si lo dejas vacío, la letra de arriba se alinea automáticamente con
                el audio. Con voz a cappella (abajo) la sincronía es mejor.
              </p>
            </details>
          </Section>

          {/* ── Estilo visual ─── */}
          <Section title="Estilo visual">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8 }}>
              {ESTILOS.map((e) => (
                <button
                  key={e.id}
                  type="button"
                  onClick={() => setEstilo(e.id)}
                  style={{
                    padding: "10px 8px", borderRadius: 10, textAlign: "center", cursor: "pointer",
                    border: `1px solid ${estilo === e.id ? "var(--accent)" : "var(--border)"}`,
                    background: estilo === e.id ? "rgba(99,102,241,0.12)" : "var(--surface2)",
                  }}
                >
                  <div style={{ fontSize: 22, marginBottom: 3 }}>{e.icon}</div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: estilo === e.id ? "var(--accent)" : "var(--text)" }}>
                    {e.label}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>{e.desc}</div>
                </button>
              ))}
            </div>
          </Section>

          {/* ── Formato ─── */}
          <Section title="Formato">
            <div style={{ display: "flex", gap: 8 }}>
              {([
                { id: "16:9", label: "16:9 horizontal", icon: "🖥️", desc: "1920×1080" },
                { id: "9:16", label: "9:16 vertical", icon: "📱", desc: "1080×1920 (reel)" },
              ] as const).map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setAspect(f.id)}
                  style={{
                    flex: 1, padding: "10px 8px", borderRadius: 10, textAlign: "center", cursor: "pointer",
                    border: `1px solid ${aspect === f.id ? "var(--accent)" : "var(--border)"}`,
                    background: aspect === f.id ? "rgba(99,102,241,0.12)" : "var(--surface2)",
                  }}
                >
                  <div style={{ fontSize: 20, marginBottom: 2 }}>{f.icon}</div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: aspect === f.id ? "var(--accent)" : "var(--text)" }}>{f.label}</div>
                  <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>{f.desc}</div>
                </button>
              ))}
            </div>
          </Section>

          {/* ── Fondos ─── */}
          <Section title="Fondos" hint="Un LLM saca un guion visual de la letra; el generador crea un vídeo por sección relacionado con lo que se canta.">
            {/* Estado de herramientas */}
            {estado && (
              <div style={{
                display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 10, fontSize: 11,
              }}>
                <span style={{ padding: "3px 9px", borderRadius: 20, background: estado.comfy ? "#0a2a1a" : "#2a0a0a", color: estado.comfy ? "var(--success)" : "var(--error)", border: `1px solid ${estado.comfy ? "#1a5a3a" : "#5a2020"}` }}>
                  {estado.comfy ? "● ComfyUI activo" : "○ ComfyUI apagado"}
                </span>
                <span style={{ padding: "3px 9px", borderRadius: 20, background: estado.lm_studio ? "#0a2a1a" : "#2a1a0a", color: estado.lm_studio ? "var(--success)" : "#d0a020", border: `1px solid ${estado.lm_studio ? "#1a5a3a" : "#5a4020"}` }}>
                  {estado.lm_studio ? "● LM Studio activo" : "○ LM Studio (opcional)"}
                </span>
                {estado.control_center && (!estado.comfy || !estado.lm_studio) && (
                  <button
                    onClick={arrancarHerramientas}
                    disabled={arrancando}
                    style={{
                      fontSize: 11, padding: "3px 11px", borderRadius: 20, cursor: arrancando ? "wait" : "pointer",
                      background: "#12233a", color: "var(--accent, #4c9ffe)", border: "1px solid #2c4a6e",
                    }}
                  >
                    {arrancando ? "⏳ arrancando…" : "▶ Arrancar ComfyUI/LM Studio"}
                  </button>
                )}
                {estado.control_center === false && (
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>
                    Centro de Control (:8090) apagado — no puedo arrancar desde aquí
                  </span>
                )}
                <button onClick={cargarEstado} style={{ fontSize: 11, background: "none", border: "none", color: "var(--muted)", cursor: "pointer", textDecoration: "underline" }}>
                  refrescar
                </button>
              </div>
            )}
            {arrancando && estado?.arranque?.mensaje && (
              <div style={{ fontSize: 11, color: "var(--accent, #4c9ffe)", marginBottom: 10 }}>
                {estado.arranque.mensaje}
              </div>
            )}
            {estado && estado.problemas.length > 0 && (
              <div style={{ fontSize: 11, color: "#d0a020", background: "#2a1a0a", border: "1px solid #5a4020", borderRadius: 8, padding: "8px 12px", marginBottom: 10 }}>
                {estado.problemas.map((p, i) => <div key={i}>⚠️ {p}</div>)}
              </div>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {(proveedores.length ? proveedores : [
                { id: "wan22", label: "Wan 2.2 T2V (local)", disponible: false, nota: "Cargando…" },
                { id: "imagen", label: "Imagen fija (Pollinations)", disponible: true, nota: "" },
              ]).map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setProvider(p.id)}
                  style={{
                    textAlign: "left", padding: "10px 12px", borderRadius: 10, cursor: "pointer",
                    border: `1px solid ${provider === p.id ? "var(--accent)" : "var(--border)"}`,
                    background: provider === p.id ? "rgba(99,102,241,0.12)" : "var(--surface2)",
                    opacity: p.disponible ? 1 : 0.65,
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 600, color: provider === p.id ? "var(--accent)" : "var(--text)" }}>
                    {provider === p.id ? "● " : "○ "}{p.label}
                    {!p.disponible && <span style={{ color: "var(--error)", fontWeight: 400 }}> · no listo</span>}
                  </div>
                  {p.nota && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>{p.nota}</div>}
                </button>
              ))}
              {provider !== "imagen" && !proveedores.find((p) => p.id === provider)?.disponible && (
                <p style={{ fontSize: 11, color: "var(--error)", margin: "2px 0 0" }}>
                  Este generador no está listo — si generas ahora, el job fallará con el motivo. Arréglalo o elige «Imagen fija».
                </p>
              )}
              {modoVideo && (
                <div style={{ marginTop: 4 }}>
                  <label style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", display: "block", marginBottom: 6 }}>
                    Voz de la canción
                  </label>
                  <select
                    value={voz}
                    onChange={(e) => setVoz(e.target.value as typeof voz)}
                    style={{
                      width: "100%", padding: "8px 10px", borderRadius: 8,
                      border: "1px solid var(--border)", background: "var(--surface2)", color: "var(--text)",
                    }}
                  >
                    <option value="auto">Detectar automáticamente</option>
                    <option value="mujer">Mujer</option>
                    <option value="hombre">Hombre</option>
                    <option value="mixta">Mixta (dúo hombre + mujer)</option>
                  </select>
                  <p style={{ fontSize: 11, color: "var(--muted)", margin: "6px 0 0" }}>
                    Pone a quien canta en pantalla y le sincroniza los labios con la letra (LatentSync).
                    En “auto” el sistema analiza el tono de voz.
                  </p>
                </div>
              )}
              {modoVideo && voz !== "hombre" && (
                <div style={{
                  border: `2px dashed ${vozFile ? "var(--success)" : "var(--border)"}`,
                  borderRadius: 10, padding: "14px", textAlign: "center", background: "var(--surface2)",
                }}>
                  <input
                    type="file"
                    accept="audio/*"
                    id="voz-acapella"
                    className="hidden"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) handleVozSelect(f); }}
                  />
                  {uploadingVoz ? (
                    <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>⟳ Subiendo…</p>
                  ) : vozFile ? (
                    <p style={{ fontSize: 12, color: "var(--success)", margin: 0 }}>
                      ✓ {vozFile.name}
                      <button
                        onClick={() => { setVozFile(null); setVozPath(""); }}
                        style={{ marginLeft: 8, fontSize: 11, color: "var(--muted)", background: "none", border: "none", cursor: "pointer" }}
                      >
                        ✕ quitar
                      </button>
                    </p>
                  ) : (
                    <label htmlFor="voz-acapella" style={{ fontSize: 12, color: "var(--text)", cursor: "pointer" }}>
                      Pista de voz a cappella <span style={{ color: "var(--muted)" }}>(opcional, mejora el lip-sync)</span> —{" "}
                      <span style={{ color: "var(--accent)" }}>seleccionar</span>
                    </label>
                  )}
                </div>
              )}
            </div>
          </Section>

          {/* ── Opciones ─── */}
          <Section title="Opciones">
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <Toggle
                label="Mostrar letra en el video"
                sublabel="Las líneas de la sección aparecen en pantalla"
                value={mostrarLetra}
                onChange={setMostrarLetra}
              />
              <Toggle
                label="Mostrar título y artista"
                sublabel="Aparece en el primer clip de la canción"
                value={mostrarCabecera}
                onChange={setMostrarCabecera}
              />
            </div>
          </Section>

          {/* ── Error ─── */}
          {error && (
            <p style={{ fontSize: 13, color: "var(--error)", background: "#2a0a0a", border: "1px solid #5a2020", borderRadius: 8, padding: "8px 12px" }}>
              {error}
            </p>
          )}

          {/* ── Botón generar ─── */}
          <button
            onClick={handleGenerate}
            disabled={submitting || isRunning || !audioPath || !letra.trim()}
            style={{
              width: "100%", padding: "14px 0", borderRadius: 12, fontSize: 15, fontWeight: 700,
              background: (!audioPath || !letra.trim() || isRunning) ? "var(--surface2)" : "var(--accent)",
              border: "none",
              color: (!audioPath || !letra.trim() || isRunning) ? "var(--muted)" : "#fff",
              cursor: (submitting || isRunning || !audioPath || !letra.trim()) ? "not-allowed" : "pointer",
              opacity: submitting ? 0.6 : 1,
              transition: "all 0.2s",
            }}
          >
            {submitting ? "Iniciando…" : isRunning ? "⟳ Generando clips…" : "🎬 Generar videoclips"}
          </button>
        </div>

        {/* ── Job progress ─── */}
        {job && (
          <div style={{ marginTop: 20 }}>
            <JobPanel job={job} onPublish={setPublishing} />
          </div>
        )}

        {/* ── Ayuda formato letra ─── */}
        <details style={{ marginTop: 24 }}>
          <summary style={{ fontSize: 12, color: "var(--muted)", cursor: "pointer", userSelect: "none" }}>
            ¿Cómo formato la letra?
          </summary>
          <div style={{ marginTop: 10, background: "var(--surface2)", borderRadius: 10, padding: 14 }}>
            <p style={{ fontSize: 12, color: "var(--muted)", marginBottom: 8 }}>
              <strong style={{ color: "var(--text)" }}>Con etiquetas (recomendado):</strong> cada sección empieza con una etiqueta entre corchetes.
            </p>
            <pre style={{ fontSize: 11, color: "#a78bfa", background: "var(--bg)", borderRadius: 7, padding: "8px 12px", lineHeight: 1.7, overflowX: "auto" }}>
{`[Verso 1]
No me busques donde estuve
porque ya no soy el mismo

[Estribillo]
Volar, volar, sin mirar atrás
el viento llama, el mar me llama ya

[Puente]
Y en silencio entendí
que el mundo empieza en ti`}
            </pre>
            <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 10 }}>
              <strong style={{ color: "var(--text)" }}>Sin etiquetas:</strong> separa secciones con una línea en blanco. El app las nombra automáticamente.
            </p>
          </div>
        </details>
      </div>
    </main>
  );
}

// ── Job progress panel ────────────────────────────────────────────────────────

function JobPanel({ job, onPublish }: { job: JobState; onPublish: (f: string) => void }) {
  const total = job.progress.total || job.output_files.length;
  const actual = job.progress.actual || job.output_files.length;
  const pct = total > 0 ? Math.round((actual / total) * 100) : 0;

  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 16, overflow: "hidden" }}>
      {/* Header estado */}
      <div style={{
        padding: "14px 18px",
        background: job.status === "completed" ? "#0a2a1a" : job.status === "failed" ? "#2a0a0a" : "#0a1a2a",
        borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", gap: 10,
      }}>
        {job.status === "running" && <span style={{ fontSize: 16, animation: "spin 1s linear infinite" }}>⟳</span>}
        <div style={{ flex: 1 }}>
          <p style={{
            fontSize: 13, fontWeight: 700, margin: 0,
            color: job.status === "completed" ? "var(--success)" : job.status === "failed" ? "var(--error)" : "#60a5fa",
          }}>
            {job.status === "running"
              ? job.progress.label || "Generando…"
              : job.status === "completed"
              ? `✓ ${job.output_files.length} clip${job.output_files.length !== 1 ? "s" : ""} generado${job.output_files.length !== 1 ? "s" : ""}`
              : `✕ Error: ${job.error}`}
          </p>
          {job.status === "running" && total > 0 && (
            <p style={{ fontSize: 11, color: "var(--muted)", margin: "3px 0 0" }}>
              Clip {actual} de {total}
            </p>
          )}
          {job.status === "completed" && (
            <p style={{ fontSize: 11, color: "var(--muted)", margin: "3px 0 0" }}>
              {job.sync_letra === "lrc"
                ? "Letra sincronizada por LRC (exacta)"
                : job.sync_letra === "whisper"
                ? "Letra sincronizada con el audio (Whisper)"
                : "Letra repartida uniformemente (sin sincronía fina)"}
              {job.voces?.tipo && job.voces.tipo !== "manual"
                ? ` · voz: ${job.voces.tipo}${job.voces.f0_mediana ? ` (${job.voces.f0_mediana} Hz)` : ""}`
                : ""}
            </p>
          )}
        </div>
      </div>

      {/* Barra de progreso */}
      {job.status === "running" && total > 0 && (
        <div style={{ height: 3, background: "var(--border)" }}>
          <div style={{
            height: "100%", background: "var(--accent)", borderRadius: 2,
            width: `${pct}%`, transition: "width 0.5s ease",
          }} />
        </div>
      )}

      {/* Clips generados */}
      {job.output_files.length > 0 && (
        <div style={{ padding: "14px 18px" }}>
          <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", marginBottom: 12 }}>
            Clips generados
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {job.output_files.map((filename, i) => (
              <div key={filename} style={{ background: "var(--surface2)", borderRadius: 12, overflow: "hidden", border: "1px solid var(--border)" }}>
                {/* Label */}
                <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>
                    {/_full_reel\.mp4$/.test(filename)
                      ? "🎬 Videoclip completo"
                      : `Clip ${i + 1} — ${filename.replace(/_reel\.mp4$/, "").replace(/_/g, " ")}`}
                  </p>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      onClick={() => onPublish(filename)}
                      style={{ fontSize: 11, padding: "4px 10px", borderRadius: 6, background: "var(--accent)", border: "none", color: "#fff", cursor: "pointer", fontWeight: 600 }}
                    >
                      ↑ Publicar
                    </button>
                    <a
                      href={`/videos/${filename}`}
                      download
                      style={{ fontSize: 11, padding: "4px 10px", borderRadius: 6, background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)", textDecoration: "none" }}
                    >
                      ↓ Descargar
                    </a>
                  </div>
                </div>
                {/* Video */}
                <video
                  src={`/videos/${filename}`}
                  controls
                  style={{ width: "100%", maxHeight: 480, background: "#000", display: "block" }}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Helpers de UI ─────────────────────────────────────────────────────────────

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, overflow: "hidden" }}>
      <div style={{ padding: "10px 16px 8px", borderBottom: "1px solid var(--border)" }}>
        <p style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--muted)", margin: 0 }}>
          {title}
        </p>
        {hint && <p style={{ fontSize: 11, color: "var(--muted)", margin: "3px 0 0", opacity: 0.8 }}>{hint}</p>}
      </div>
      <div style={{ padding: "14px 16px" }}>
        {children}
      </div>
    </div>
  );
}

function Toggle({ label, sublabel, value, onChange }: {
  label: string; sublabel?: string; value: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label style={{ display: "flex", alignItems: "center", gap: 12, cursor: "pointer" }}>
      <div
        onClick={() => onChange(!value)}
        style={{
          width: 40, height: 22, borderRadius: 11, flexShrink: 0,
          background: value ? "var(--accent)" : "var(--surface2)",
          border: "1px solid var(--border)",
          position: "relative", transition: "background 0.2s", cursor: "pointer",
        }}
      >
        <div style={{
          position: "absolute", top: 3, left: value ? 20 : 3,
          width: 14, height: 14, borderRadius: "50%",
          background: "#fff", transition: "left 0.2s",
        }} />
      </div>
      <div>
        <p style={{ fontSize: 13, color: value ? "var(--text)" : "var(--muted)", margin: 0 }}>{label}</p>
        {sublabel && <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>{sublabel}</p>}
      </div>
    </label>
  );
}

const inputStyle = {
  width: "100%",
  background: "var(--bg)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "8px 12px",
  fontSize: 13,
  color: "var(--text)",
  outline: "none",
  boxSizing: "border-box" as const,
};
