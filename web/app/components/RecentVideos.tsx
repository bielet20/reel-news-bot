"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import HotspotOverlay from "./HotspotOverlay";

interface VideoFile {
  filename: string;
  size: number;
  modified: string;
}

export default function RecentVideos() {
  const [videos, setVideos] = useState<VideoFile[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    fetch("/api/output")
      .then((r) => r.json())
      .then(setVideos)
      .catch(() => {});
  }, []);

  if (videos.length === 0) return null;

  function fmt(bytes: number) {
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }

  function fmtDate(iso: string) {
    return new Date(iso).toLocaleString("es-AR", {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    });
  }

  return (
    <div className="mt-8">
      <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--text)" }}>
        Videos generados
      </h2>

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
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
