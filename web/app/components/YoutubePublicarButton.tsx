"use client";

import { useEffect, useState } from "react";

/**
 * Botón "Publicar" para vídeos de YouTube subidos en privado.
 * - Vídeo no registrado (subido antes del cambio o enlace manual): no muestra nada.
 * - Privado: botón "Publicar" (pide confirmación).
 * - Público: insignia "Público" con enlace al vídeo.
 * Backend: GET /api/youtube/publicacion/{id} y POST /api/youtube/publicacion/{id}/publicar
 */

type Estado = "cargando" | "no_registrado" | "privado" | "publicando" | "publico" | "error";

export function youtubeVideoId(url: string | null | undefined): string | null {
  if (!url) return null;
  const m =
    url.match(/[?&]v=([A-Za-z0-9_-]{6,20})/) ||
    url.match(/youtu\.be\/([A-Za-z0-9_-]{6,20})/) ||
    url.match(/youtube\.com\/(?:shorts|embed|live)\/([A-Za-z0-9_-]{6,20})/);
  return m ? m[1] : null;
}

const badge: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  padding: "1px 7px",
  borderRadius: 4,
  textDecoration: "none",
  whiteSpace: "nowrap",
};

export default function YoutubePublicarButton({
  youtubeUrl,
  size = "sm",
}: {
  youtubeUrl: string | null | undefined;
  size?: "sm" | "md";
}) {
  const videoId = youtubeVideoId(youtubeUrl);
  const [estado, setEstado] = useState<Estado>("cargando");
  const [mensaje, setMensaje] = useState<string>("");

  useEffect(() => {
    if (!videoId) return;
    let cancelado = false;
    fetch(`/api/youtube/publicacion/${encodeURIComponent(videoId)}`)
      .then(async (r) => {
        if (cancelado) return;
        // 404 = vídeo no registrado (subido antes del cambio o enlace manual)
        if (!r.ok) {
          setEstado("no_registrado");
          return;
        }
        const d: { estado?: string; alerta?: string | null } = await r.json();
        if (cancelado) return;
        if (d.estado === "publico") {
          setEstado("publico");
        } else {
          setEstado("privado");
          setMensaje(d.alerta || "");
        }
      })
      .catch(() => {
        if (!cancelado) setEstado("no_registrado");
      });
    return () => {
      cancelado = true;
    };
  }, [videoId]);

  const publicar = async () => {
    if (!videoId) return;
    if (!window.confirm("¿Publicar este vídeo en YouTube? Pasará de privado a público y lo verá todo el mundo.")) return;
    setEstado("publicando");
    setMensaje("");
    try {
      const r = await fetch(`/api/youtube/publicacion/${encodeURIComponent(videoId)}/publicar`, { method: "POST" });
      const d: { ok?: boolean; detail?: string; estado?: string } = await r.json().catch(() => ({}));
      if (r.ok && d.estado === "publico") {
        setEstado("publico");
        return;
      }
      setEstado("privado");
      setMensaje(d.detail || `Error ${r.status} al publicar. El vídeo sigue privado.`);
    } catch {
      setEstado("privado");
      setMensaje("No se pudo contactar con el servidor. El vídeo sigue privado.");
    }
  };

  if (!videoId || estado === "cargando" || estado === "no_registrado") return null;

  const fs = size === "md" ? 12 : 10;

  if (estado === "publico") {
    return (
      <a
        href={youtubeUrl ?? `https://www.youtube.com/watch?v=${videoId}`}
        target="_blank"
        rel="noopener noreferrer"
        title="El vídeo es público en YouTube"
        style={{ ...badge, fontSize: fs, background: "rgba(74,222,128,0.15)", color: "#4ade80" }}
      >
        ● Público
      </a>
    );
  }

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
      <span title="Subido en privado: solo tú lo ves" style={{ ...badge, fontSize: fs, background: "rgba(148,163,184,0.15)", color: "#94a3b8" }}>
        🔒 Privado
      </span>
      <button
        type="button"
        onClick={publicar}
        disabled={estado === "publicando"}
        style={{
          ...badge,
          fontSize: fs,
          border: "1px solid #f87171",
          background: estado === "publicando" ? "transparent" : "rgba(255,0,0,0.15)",
          color: "#f87171",
          cursor: estado === "publicando" ? "wait" : "pointer",
        }}
      >
        {estado === "publicando" ? "Publicando…" : "Publicar"}
      </button>
      {mensaje && <span style={{ fontSize: fs, color: "#fbbf24" }}>{mensaje}</span>}
    </span>
  );
}
