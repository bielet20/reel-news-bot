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
}

export default function MontajePage() {
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioPath, setAudioPath] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const [letra, setLetra] = useState("");
  const [artista, setArtista] = useState("");
  const [titulo, setTitulo] = useState("");
  const [estilo, setEstilo] = useState("cinematico");
  const [mostrarLetra, setMostrarLetra] = useState(true);
  const [mostrarCabecera, setMostrarCabecera] = useState(true);
  const [job, setJob] = useState<JobState | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [publishing, setPublishing] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
          artista,
          titulo,
          estilo,
          mostrar_letra: mostrarLetra,
          mostrar_cabecera: mostrarCabecera,
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
            Sube tu canción y la letra — generamos clips con imágenes AI sincronizados por secciones.
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
                  <p style={{ fontSize: 12, color: "var(--muted)" }}>MP3, WAV, FLAC, AAC, M4A · máx 50 MB</p>
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
            hint='Separa secciones con línea en blanco, o usa etiquetas como [Verso 1], [Estribillo]'
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
                    Clip {i + 1} — {filename.replace(/_reel\.mp4$/, "").replace(/_/g, " ")}
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
