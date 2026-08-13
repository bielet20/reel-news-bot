"use client";

import { useEffect, useRef, useState } from "react";

interface PlatformStatus {
  connected: boolean;
  canal?: string;
  display_name?: string;
  username?: string;
}

interface AccountsStatus {
  youtube: PlatformStatus;
  tiktok: PlatformStatus;
  instagram: PlatformStatus;
}

interface PublishResult {
  status: "pending" | "uploading" | "ok" | "error";
  url?: string;
  video_id?: string;
  publish_id?: string;
  media_id?: string;
  error?: string;
}

interface PublishJob {
  id: string;
  status: "running" | "completed" | "failed";
  results: Record<string, PublishResult>;
}

const PLATFORMS = [
  { id: "youtube",   name: "YouTube Shorts", icon: "▶️" },
  { id: "tiktok",   name: "TikTok",          icon: "🎵" },
  { id: "instagram", name: "Instagram",      icon: "📸" },
];

const TIKTOK_PRIVACY = [
  { value: "SELF_ONLY",              label: "Solo yo (borrador)" },
  { value: "FOLLOWER_OF_CREATOR",    label: "Solo seguidores" },
  { value: "MUTUAL_FOLLOW_FRIENDS",  label: "Amigos mutuos" },
  { value: "PUBLIC_TO_EVERYONE",     label: "Público" },
];

export default function PublishModal({
  filename,
  onClose,
}: {
  filename: string;
  onClose: () => void;
}) {
  const [accounts, setAccounts] = useState<AccountsStatus | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [titulo, setTitulo] = useState(
    filename.replace(/_reel\.mp4$/, "").replace(/_music_reel\.mp4$/, "").replace(/_/g, " ")
  );
  const [descripcion, setDescripcion] = useState("");
  const [tipoContenido, setTipoContenido] = useState<"noticia" | "curiosidad">("noticia");
  const [tiktokPrivacy, setTiktokPrivacy] = useState("SELF_ONLY");
  const [job, setJob] = useState<PublishJob | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetch("/api/accounts/status")
      .then((r) => r.json())
      .then((data: AccountsStatus) => {
        setAccounts(data);
        // Pre-select connected platforms
        setSelected(
          Object.entries(data)
            .filter(([, v]) => v.connected)
            .map(([k]) => k)
        );
      })
      .catch(() => {});
  }, []);

  // Poll publish job
  useEffect(() => {
    if (!job || job.status !== "running") {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/publish/${job.id}`);
        if (res.ok) {
          const data: PublishJob = await res.json();
          setJob(data);
          if (data.status !== "running") clearInterval(pollRef.current!);
        }
      } catch { /* retry */ }
    }, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [job?.id, job?.status]);

  function togglePlatform(id: string) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function handlePublish() {
    if (selected.length === 0) return;
    setSubmitting(true);
    try {
      const res = await fetch("/api/publish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename,
          titulo,
          descripcion,
          platforms: selected,
          tipo_contenido: tipoContenido,
          tiktok_privacy: tiktokPrivacy,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const { job_id } = await res.json();
      setJob({ id: job_id, status: "running", results: Object.fromEntries(selected.map((p) => [p, { status: "pending" }])) });
    } catch (e) {
      alert(`Error: ${e}`);
    } finally {
      setSubmitting(false);
    }
  }

  const isDone = job && job.status !== "running";

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)",
      zIndex: 3000, display: "flex", alignItems: "center", justifyContent: "center",
      padding: 20,
    }}>
      <div style={{
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 18, width: "100%", maxWidth: 460,
        maxHeight: "90vh", display: "flex", flexDirection: "column", overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{ padding: "18px 20px 12px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <p style={{ fontWeight: 700, fontSize: 16, margin: 0 }}>Publicar reel</p>
            <p style={{ fontSize: 11, color: "var(--muted)", margin: "3px 0 0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 320 }}>
              {filename}
            </p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 18, padding: 4 }}>✕</button>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>

          {/* Platform selector */}
          <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", marginBottom: 10 }}>
            Publicar en
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
            {PLATFORMS.map((p) => {
              const st = accounts?.[p.id as keyof AccountsStatus];
              const connected = st?.connected;
              const isSelected = selected.includes(p.id);
              const accountName =
                p.id === "youtube" ? st?.canal :
                p.id === "tiktok" ? st?.display_name :
                st?.username;

              return (
                <label
                  key={p.id}
                  style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "10px 12px", borderRadius: 10, cursor: connected ? "pointer" : "default",
                    background: isSelected && connected ? "rgba(99,102,241,0.1)" : "var(--surface2)",
                    border: `1px solid ${isSelected && connected ? "var(--accent)" : "var(--border)"}`,
                    opacity: connected ? 1 : 0.45,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={isSelected && !!connected}
                    disabled={!connected}
                    onChange={() => connected && togglePlatform(p.id)}
                    style={{ accentColor: "var(--accent)", width: 15, height: 15 }}
                  />
                  <span style={{ fontSize: 18 }}>{p.icon}</span>
                  <div style={{ flex: 1 }}>
                    <p style={{ fontSize: 13, fontWeight: 600, margin: 0, color: "var(--text)" }}>{p.name}</p>
                    {connected && accountName ? (
                      <p style={{ fontSize: 11, color: "var(--success)", margin: 0 }}>✓ {accountName}</p>
                    ) : (
                      <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>
                        No conectado —{" "}
                        <a href="/canales" style={{ color: "var(--accent)" }}>conectar →</a>
                      </p>
                    )}
                  </div>
                </label>
              );
            })}
          </div>

          {/* Title */}
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", display: "block", marginBottom: 6 }}>
              Título
            </label>
            <input
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Título del video"
              style={{ width: "100%", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 12px", fontSize: 13, color: "var(--text)", outline: "none", boxSizing: "border-box" }}
            />
          </div>

          {/* Description / caption */}
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", display: "block", marginBottom: 6 }}>
              Descripción / caption
            </label>
            <textarea
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              placeholder="Descripción para Instagram y TikTok (opcional)"
              rows={3}
              style={{ width: "100%", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 12px", fontSize: 12, color: "var(--text)", outline: "none", resize: "vertical", boxSizing: "border-box" }}
            />
          </div>

          {/* YouTube content type */}
          {selected.includes("youtube") && accounts?.youtube.connected && (
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", display: "block", marginBottom: 6 }}>
                Tipo (YouTube)
              </label>
              <div style={{ display: "flex", gap: 8 }}>
                {(["noticia", "curiosidad"] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTipoContenido(t)}
                    style={{
                      flex: 1, padding: "7px 0", borderRadius: 8, fontSize: 12, fontWeight: 600,
                      cursor: "pointer",
                      border: `1px solid ${tipoContenido === t ? "var(--accent)" : "var(--border)"}`,
                      background: tipoContenido === t ? "rgba(99,102,241,0.12)" : "var(--surface2)",
                      color: tipoContenido === t ? "var(--accent)" : "var(--muted)",
                    }}
                  >
                    {t === "noticia" ? "📰 Noticia" : "💡 Curiosidad"}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* TikTok privacy */}
          {selected.includes("tiktok") && accounts?.tiktok.connected && (
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", display: "block", marginBottom: 6 }}>
                Privacidad (TikTok)
              </label>
              <select
                value={tiktokPrivacy}
                onChange={(e) => setTiktokPrivacy(e.target.value)}
                style={{ width: "100%", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px", fontSize: 13, color: "var(--text)", outline: "none" }}
              >
                {TIKTOK_PRIVACY.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          )}

          {/* Publish results */}
          {job && (
            <div style={{ borderTop: "1px solid var(--border)", paddingTop: 14, marginTop: 4 }}>
              <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", marginBottom: 10 }}>
                Estado de publicación
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {PLATFORMS.filter((p) => selected.includes(p.id)).map((p) => {
                  const r = job.results[p.id] as PublishResult | undefined;
                  return (
                    <div key={p.id} style={{
                      display: "flex", alignItems: "center", gap: 10,
                      padding: "8px 12px", borderRadius: 8, background: "var(--surface2)",
                      border: "1px solid var(--border)",
                    }}>
                      <span style={{ fontSize: 16 }}>{p.icon}</span>
                      <span style={{ fontSize: 13, color: "var(--text)", flex: 1 }}>{p.name}</span>
                      <span style={{ fontSize: 12, fontWeight: 600, color:
                        r?.status === "ok" ? "var(--success)" :
                        r?.status === "error" ? "var(--error)" :
                        r?.status === "uploading" ? "#60a5fa" :
                        "var(--muted)"
                      }}>
                        {r?.status === "ok" ? "✓ Publicado" :
                         r?.status === "error" ? `✕ ${r.error?.slice(0, 40)}` :
                         r?.status === "uploading" ? "⟳ Subiendo…" :
                         "En espera"}
                      </span>
                      {r?.status === "ok" && r.url && (
                        <a href={r.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, color: "var(--accent)" }}>Ver →</a>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "14px 20px", borderTop: "1px solid var(--border)", display: "flex", gap: 10 }}>
          <button
            onClick={onClose}
            style={{
              flex: 1, padding: "10px 0", borderRadius: 10,
              background: "var(--surface2)", border: "1px solid var(--border)",
              color: "var(--muted)", fontSize: 14, cursor: "pointer", fontWeight: 600,
            }}
          >
            {isDone ? "Cerrar" : "Cancelar"}
          </button>
          {!isDone && (
            <button
              onClick={handlePublish}
              disabled={submitting || selected.length === 0}
              style={{
                flex: 2, padding: "10px 0", borderRadius: 10,
                background: selected.length === 0 ? "var(--surface2)" : "var(--accent)",
                border: "none", color: selected.length === 0 ? "var(--muted)" : "#fff",
                fontSize: 14, fontWeight: 700,
                cursor: submitting || selected.length === 0 ? "not-allowed" : "pointer",
                opacity: submitting ? 0.6 : 1,
              }}
            >
              {submitting ? "Iniciando…" : `Publicar${selected.length > 0 ? ` en ${selected.length} plataforma${selected.length > 1 ? "s" : ""}` : ""}`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
