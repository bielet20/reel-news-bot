"use client";

import { useEffect, useRef, useState } from "react";

interface MusicItem {
  id: string;
  name: string;
  filename: string;
  duration_s?: number | null;
  created_at: string;
}

function fmtDuration(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export default function MusicPage() {
  const [items, setItems] = useState<MusicItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState("");
  const [playingId, setPlayingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  const reload = () => {
    fetch("/api/music")
      .then((r) => r.json())
      .then(setItems)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { reload(); }, []);

  const uploadFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setMsg("");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("name", nameRef.current?.value.trim() || file.name.replace(/\.[^.]+$/, ""));
    try {
      const r = await fetch("/api/music/upload", { method: "POST", body: fd });
      if (!r.ok) throw new Error((await r.json()).detail || "Error al subir");
      setMsg("Pista guardada en la biblioteca");
      if (nameRef.current) nameRef.current.value = "";
      reload();
    } catch (err) { setMsg(`Error: ${err}`); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const deleteItem = async (id: string) => {
    if (playingId === id) stopPlayback();
    await fetch(`/api/music/${id}`, { method: "DELETE" });
    setItems((prev) => prev.filter((i) => i.id !== id));
  };

  const stopPlayback = () => {
    if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
    setPlayingId(null);
  };

  const togglePlay = (item: MusicItem) => {
    if (playingId === item.id) { stopPlayback(); return; }
    stopPlayback();
    const audio = new Audio(`/music-files/${item.filename}`);
    audioRef.current = audio;
    audio.volume = 0.7;
    audio.play();
    audio.onended = () => setPlayingId(null);
    setPlayingId(item.id);
  };

  const sx = {
    bg: { background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 8, padding: "7px 10px", fontSize: 13 } as const,
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "24px 20px", maxWidth: 700, margin: "0 auto" }}>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <a href="/" style={{ color: "var(--muted)", textDecoration: "none", fontSize: 13 }}>← Volver</a>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Biblioteca de música</h1>
      </div>

      {/* Upload */}
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: 16, marginBottom: 20 }}>
        <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 10 }}>Subir pista de música</p>
        <input
          ref={nameRef}
          type="text"
          placeholder="Nombre de la pista (opcional)"
          style={{ ...sx.bg, width: "100%", boxSizing: "border-box", marginBottom: 8 }}
        />
        <input ref={fileRef} type="file" accept="audio/*,.mp3,.wav,.ogg,.m4a,.aac,.flac" onChange={uploadFile} style={{ display: "none" }} />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          style={{ width: "100%", background: uploading ? "var(--surface2)" : "var(--accent)", color: uploading ? "var(--muted)" : "#fff", border: "none", borderRadius: 8, padding: "8px 0", fontSize: 13, cursor: uploading ? "not-allowed" : "pointer", fontWeight: 600 }}
        >
          {uploading ? "Subiendo..." : "Elegir archivo de audio"}
        </button>
        <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 6 }}>MP3, WAV, OGG, M4A, AAC, FLAC</p>
      </div>

      {msg && <p style={{ fontSize: 12, color: msg.startsWith("Error") ? "var(--error)" : "var(--success)", marginBottom: 12 }}>{msg}</p>}

      {/* Track list */}
      {loading ? (
        <p style={{ color: "var(--muted)", fontSize: 13 }}>Cargando...</p>
      ) : items.length === 0 ? (
        <p style={{ color: "var(--muted)", fontSize: 13, textAlign: "center", paddingTop: 40 }}>
          No hay pistas en la biblioteca. Sube tu primera pista arriba.
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {items.map((item) => {
            const isPlaying = playingId === item.id;
            return (
              <div
                key={item.id}
                style={{ background: "var(--surface)", border: `1px solid ${isPlaying ? "var(--accent)" : "var(--border)"}`, borderRadius: 10, padding: "10px 14px", display: "flex", alignItems: "center", gap: 12 }}
              >
                {/* Play button */}
                <button
                  onClick={() => togglePlay(item)}
                  style={{ width: 36, height: 36, borderRadius: "50%", background: isPlaying ? "var(--accent)" : "var(--surface2)", border: "1px solid var(--border)", cursor: "pointer", fontSize: 14, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", color: isPlaying ? "#fff" : "var(--text)" }}
                  title={isPlaying ? "Pausar" : "Reproducir"}
                >
                  {isPlaying ? "⏹" : "▶"}
                </button>

                {/* Info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontSize: 13, color: "var(--text)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.name}</p>
                  <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>
                    {item.duration_s ? fmtDuration(item.duration_s) : "—"}
                    <span style={{ marginLeft: 8 }}>{item.filename.split(".").pop()?.toUpperCase()}</span>
                  </p>
                </div>

                {/* Waveform placeholder (animated when playing) */}
                {isPlaying && (
                  <div style={{ display: "flex", alignItems: "center", gap: 2, height: 20, flexShrink: 0 }}>
                    {[1, 2, 3, 4, 5].map((i) => (
                      <div key={i} style={{ width: 3, background: "var(--accent)", borderRadius: 2, animation: `pulse${i % 3} 0.8s ease-in-out infinite`, animationDelay: `${i * 0.1}s`, height: `${8 + (i % 3) * 5}px` }} />
                    ))}
                  </div>
                )}

                {/* Delete */}
                <button
                  onClick={() => deleteItem(item.id)}
                  style={{ background: "none", border: "none", color: "var(--error)", cursor: "pointer", fontSize: 15, padding: 0, flexShrink: 0 }}
                  title="Eliminar"
                >
                  ✕
                </button>
              </div>
            );
          })}
        </div>
      )}

      <style>{`
        @keyframes pulse0 { 0%,100%{transform:scaleY(1)} 50%{transform:scaleY(2)} }
        @keyframes pulse1 { 0%,100%{transform:scaleY(0.8)} 50%{transform:scaleY(1.8)} }
        @keyframes pulse2 { 0%,100%{transform:scaleY(1.2)} 50%{transform:scaleY(0.6)} }
      `}</style>
    </div>
  );
}
