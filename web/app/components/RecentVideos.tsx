"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import HotspotOverlay from "./HotspotOverlay";
import PublishModal from "./PublishModal";

interface VideoFile {
  filename: string;
  size: number;
  modified: string;
}

export default function RecentVideos() {
  const [videos, setVideos] = useState<VideoFile[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [publishing, setPublishing] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [totalBytes, setTotalBytes] = useState<number | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    fetch("/api/output")
      .then((r) => r.json())
      .then(setVideos)
      .catch(() => {});
    fetch("/api/output/stats")
      .then((r) => r.json())
      .then((s) => setTotalBytes(s.total_bytes))
      .catch(() => {});
  }, []);

  if (videos.length === 0) return null;

  const publishingVideo = publishing ? videos.find((v) => v.filename === publishing) : null;

  function fmt(bytes: number) {
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }

  async function handleDelete(filename: string) {
    if (!confirm(`¿Eliminar "${filename}" y sus archivos asociados? Esto no se puede deshacer.`)) {
      return;
    }
    setDeleting(filename);
    try {
      const r = await fetch(`/api/output/${encodeURIComponent(filename)}`, { method: "DELETE" });
      if (!r.ok) throw new Error(await r.text());
      setVideos((prev) => prev.filter((v) => v.filename !== filename));
      if (selected === filename) setSelected(null);
      fetch("/api/output/stats")
        .then((res) => res.json())
        .then((s) => setTotalBytes(s.total_bytes))
        .catch(() => {});
    } catch {
      alert("No se pudo eliminar el video.");
    } finally {
      setDeleting(null);
    }
  }

  function fmtDate(iso: string) {
    return new Date(iso).toLocaleString("es-AR", {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    });
  }

  return (
    <div className="mt-8">
      {publishing && publishingVideo && (
        <PublishModal filename={publishing} onClose={() => setPublishing(null)} />
      )}

      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold" style={{ color: "var(--text)" }}>
          Videos generados
        </h2>
        {totalBytes !== null && (
          <span className="text-xs" style={{ color: "var(--muted)" }}>
            {videos.length} video{videos.length !== 1 ? "s" : ""} · {fmt(totalBytes)} en disco
          </span>
        )}
      </div>

      {selected && (
        <div className="mb-4 rounded-2xl overflow-hidden" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          <div className="flex items-center justify-between px-4 py-2" style={{ borderBottom: "1px solid var(--border)" }}>
            <span className="text-sm truncate" style={{ color: "var(--muted)" }}>{selected}</span>
            <div className="flex items-center gap-3">
              <Link
                href={`/hotspot-editor/${encodeURIComponent(selected)}`}
                onClick={(e) => e.stopPropagation()}
                className="text-xs px-3 py-1"
                style={{ color: "var(--accent)", border: "1px solid var(--accent)", borderRadius: 6 }}
              >
                ✏ Hotspots
              </Link>
              <button onClick={() => setSelected(null)} style={{ color: "var(--muted)" }}>✕</button>
            </div>
          </div>
          {/* wrapper relativo para el overlay */}
          <div style={{ position: "relative" }}>
            <video
              ref={videoRef}
              src={`/videos/${selected}`}
              controls
              className="w-full max-h-[600px] mx-auto block"
              style={{ background: "#000" }}
            />
            <HotspotOverlay filename={selected} videoRef={videoRef} />
          </div>
        </div>
      )}

      <div className="space-y-2">
        {videos.map((v) => (
          <div
            key={v.filename}
            className="flex items-center justify-between rounded-xl px-4 py-3 cursor-pointer transition-all"
            style={{
              background: selected === v.filename ? "var(--surface2)" : "var(--surface)",
              border: `1px solid ${selected === v.filename ? "var(--accent)" : "var(--border)"}`,
            }}
            onClick={() => setSelected(selected === v.filename ? null : v.filename)}
          >
            <div className="flex items-center gap-3 min-w-0">
              <span className="text-lg">🎬</span>
              <div className="min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: "var(--text)" }}>
                  {v.filename.replace(/_reel\.mp4$/, "").replace(/_music_reel\.mp4$/, "").replace(/-/g, " ")}
                </p>
                <p className="text-xs" style={{ color: "var(--muted)" }}>
                  {fmtDate(v.modified)} · {fmt(v.size)}
                </p>
              </div>
            </div>
            <div className="flex gap-2 ml-3 shrink-0">
              <button
                onClick={(e) => { e.stopPropagation(); setPublishing(v.filename); }}
                className="text-xs px-3 py-1.5 rounded-lg"
                style={{ background: "var(--accent)", color: "#fff", border: "none", cursor: "pointer", fontWeight: 600 }}
              >
                ↑ Publicar
              </button>
              <Link
                href={`/hotspot-editor/${encodeURIComponent(v.filename)}`}
                onClick={(e) => e.stopPropagation()}
                className="text-xs px-3 py-1.5 rounded-lg"
                style={{ background: "var(--surface2)", color: "#a78bfa", border: "1px solid var(--border)" }}
              >
                ✏ Hotspots
              </Link>
              <a
                href={`/videos/${v.filename}`}
                download
                onClick={(e) => e.stopPropagation()}
                className="text-xs px-3 py-1.5 rounded-lg"
                style={{ background: "var(--surface2)", color: "var(--muted)", border: "1px solid var(--border)" }}
              >
                ↓ Descargar
              </a>
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(v.filename); }}
                disabled={deleting === v.filename}
                className="text-xs px-3 py-1.5 rounded-lg"
                style={{
                  background: "var(--surface2)", color: "#f87171", border: "1px solid var(--border)",
                  cursor: deleting === v.filename ? "wait" : "pointer",
                  opacity: deleting === v.filename ? 0.6 : 1,
                }}
              >
                {deleting === v.filename ? "…" : "🗑 Eliminar"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
