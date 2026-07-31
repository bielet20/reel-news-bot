"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import HotspotOverlay from "../../components/HotspotOverlay";

interface Job {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  label: string;
  mode: string;
  logs: string;
  output_files: string[];
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

function VideoWithHotspots({ filename, onNew }: { filename: string; onNew: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  return (
    <div className="space-y-3">
      <div style={{ position: "relative" }}>
        <video
          ref={videoRef}
          src={`/videos/${filename}`}
          controls
          className="w-full rounded-xl max-h-[600px] mx-auto block"
          style={{ background: "#000" }}
        />
        <HotspotOverlay filename={filename} videoRef={videoRef} />
      </div>
      <div className="flex gap-2 justify-end">
        <Link
          href={`/hotspot-editor/${encodeURIComponent(filename)}`}
          className="text-sm px-4 py-2 rounded-lg font-medium"
          style={{ background: "var(--surface2)", color: "#a78bfa", border: "1px solid var(--border)" }}
        >
          ✏ Hotspots
        </Link>
        <a
          href={`/videos/${filename}`}
          download
          className="text-sm px-4 py-2 rounded-lg font-medium"
          style={{ background: "var(--accent)", color: "#fff" }}
        >
          ↓ Descargar
        </a>
        <button
          onClick={onNew}
          className="text-sm px-4 py-2 rounded-lg font-medium"
          style={{ background: "var(--surface2)", color: "var(--text)", border: "1px solid var(--border)" }}
        >
          + Nuevo reel
        </button>
      </div>
    </div>
  );
}

const STATUS_STYLE: Record<string, { label: string; color: string; bg: string }> = {
  pending:   { label: "En cola",      color: "var(--warning)",  bg: "#2a1f0a" },
  running:   { label: "Generando...", color: "#60a5fa",          bg: "#0a1a2a" },
  completed: { label: "Completado",   color: "var(--success)",  bg: "#0a2a1a" },
  failed:    { label: "Error",        color: "var(--error)",    bg: "#2a0a0a" },
};

export default function JobPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [job, setJob] = useState<Job | null>(null);
  const [notFound, setNotFound] = useState(false);
  const logRef = useRef<HTMLPreElement>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    async function poll() {
      try {
        const res = await fetch(`/api/jobs/${id}`);
        if (res.status === 404) { setNotFound(true); return; }
        const data: Job = await res.json();
        setJob(data);

        if (data.status === "completed" || data.status === "failed") {
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
      } catch {
        // retry on next tick
      }
    }

    poll();
    intervalRef.current = setInterval(poll, 2000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [id]);

  // Auto-scroll logs
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [job?.logs]);

  if (notFound) {
    return (
      <main className="min-h-screen flex items-center justify-center px-4">
        <div className="text-center">
          <p className="text-lg mb-4" style={{ color: "var(--muted)" }}>Job no encontrado</p>
          <Link href="/" className="text-sm" style={{ color: "var(--accent)" }}>← Volver al inicio</Link>
        </div>
      </main>
    );
  }

  if (!job) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p style={{ color: "var(--muted)" }}>Cargando...</p>
      </main>
    );
  }

  const st = STATUS_STYLE[job.status] || STATUS_STYLE.pending;
  const elapsed = job.started_at && job.completed_at
    ? ((new Date(job.completed_at).getTime() - new Date(job.started_at).getTime()) / 1000).toFixed(0)
    : null;

  return (
    <main className="min-h-screen px-4 py-10">
      <div className="max-w-2xl mx-auto">
        {/* Back */}
        <Link href="/" className="text-sm mb-6 inline-block" style={{ color: "var(--muted)" }}>
          ← Nuevo reel
        </Link>

        {/* Header */}
        <div className="rounded-2xl p-6 mb-4" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          <div className="flex items-start justify-between gap-4 mb-4">
            <div className="min-w-0">
              <p className="text-xs mb-1" style={{ color: "var(--muted)" }}>JOB #{job.id}</p>
              <h1 className="text-lg font-semibold truncate" style={{ color: "var(--text)" }}>
                {job.label}
              </h1>
            </div>
            <span
              className="shrink-0 text-sm font-medium px-3 py-1 rounded-full"
              style={{ color: st.color, background: st.bg, border: `1px solid ${st.color}40` }}
            >
              {job.status === "running" && <span className="inline-block animate-spin mr-1">⟳</span>}
              {st.label}
            </span>
          </div>

          {elapsed && (
            <p className="text-xs" style={{ color: "var(--muted)" }}>
              Tiempo: {elapsed}s
            </p>
          )}
        </div>

        {/* Log terminal */}
        <div className="rounded-2xl overflow-hidden mb-4" style={{ border: "1px solid var(--border)" }}>
          <div className="px-4 py-2 flex items-center gap-2" style={{ background: "var(--surface2)", borderBottom: "1px solid var(--border)" }}>
            <span className="w-3 h-3 rounded-full bg-red-500/60" />
            <span className="w-3 h-3 rounded-full bg-yellow-500/60" />
            <span className="w-3 h-3 rounded-full bg-green-500/60" />
            <span className="ml-2 text-xs" style={{ color: "var(--muted)" }}>log de generación</span>
          </div>
          <pre
            ref={logRef}
            className="text-xs p-4 overflow-auto whitespace-pre-wrap"
            style={{
              background: "#050408",
              color: "#c8c0e0",
              minHeight: "200px",
              maxHeight: "400px",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            {job.logs || (job.status === "pending" ? "Esperando inicio..." : "Sin logs aún...")}
          </pre>
        </div>

        {/* Output videos */}
        {job.status === "completed" && job.output_files.length > 0 && (
          <div className="rounded-2xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <h2 className="font-semibold mb-4" style={{ color: "var(--success)" }}>
              ✅ Reel generado
            </h2>
            {job.output_files.map((filename) => (
              <VideoWithHotspots key={filename} filename={filename} onNew={() => router.push("/")} />
            ))}
          </div>
        )}

        {/* Failed state */}
        {job.status === "failed" && (
          <div className="rounded-2xl p-5" style={{ background: "#1a0808", border: "1px solid #5a1515" }}>
            <p className="font-medium mb-2" style={{ color: "var(--error)" }}>❌ El job falló</p>
            <p className="text-sm" style={{ color: "var(--muted)" }}>
              Revisa el log de generación arriba para ver el error.
            </p>
            <button
              onClick={() => router.push("/")}
              className="mt-3 text-sm px-4 py-2 rounded-lg"
              style={{ background: "var(--surface2)", color: "var(--text)", border: "1px solid var(--border)" }}
            >
              ← Intentar de nuevo
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
