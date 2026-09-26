"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ── Scanner types ──────────────────────────────────────────────────────────────

interface ScannerConfig {
  enabled: boolean;
  interval_min: number;
  score_min: number;
  auto_generate: boolean;
  auto_publish: boolean;
  publish_platforms: string[];
  pais: string;
  n_noticias: number;
}

interface ScannerStatus {
  config: ScannerConfig;
  last_run: string | null;
  next_run: string | null;
  running: boolean;
  last_error: string | null;
  unread: number;
}

interface ScannerNotif {
  id: string;
  tipo: string;
  titulo: string;
  fuente: string;
  score: number;
  link: string;
  gancho: string;
  documentacion?: string;
  verificadores?: string[];
  estado_verificacion?: string;
  item_id: string | null;
  leido: boolean;
  creado: string;
  auto_generado: boolean;
}

const SCANNER_CONFIG_DEFAULT: ScannerConfig = {
  enabled: false,
  interval_min: 30,
  score_min: 7.0,
  auto_generate: true,
  auto_publish: false,
  publish_platforms: ["youtube"],
  pais: "ES",
  n_noticias: 5,
};

// ── YT Scanner types ───────────────────────────────────────────────────────────

interface YtScannerConfig {
  enabled: boolean;
  interval_hours: number;
  score_min: number;
  min_views: number;
  max_age_days: number;
  n_por_nicho: number;
  auto_generate: boolean;
  auto_publish: boolean;
  publish_platforms: string[];
  nichos_activos: string[];
}

interface YtNichoMeta {
  nombre: string;
  emoji: string;
  color: string;
}

interface YtScannerStatus {
  config: YtScannerConfig;
  nichos: Record<string, YtNichoMeta>;
  last_run: string | null;
  next_run: string | null;
  running: boolean;
  last_error: string | null;
  unread: number;
}

interface YtNotif {
  id: string;
  titulo: string;
  canal: string;
  views: number;
  views_fmt: string;
  score: number;
  url: string;
  thumbnail: string;
  nicho: string;
  nicho_nombre: string;
  nicho_emoji: string;
  nicho_color: string;
  item_id: string | null;
  leido: boolean;
  creado: string;
  auto_generado: boolean;
}

interface AutoPubStatus {
  enabled: boolean;
  paused: boolean;
  daily_limit: number;
  published_today: number;
  queue_size: number;
  queue: { item_id: string; score: number; titulo: string; platforms: string[] }[];
  last_publish_at: string | null;
  minutes_until_next: number | null;
  publishing: boolean;
}

const YT_SCANNER_CONFIG_DEFAULT: YtScannerConfig = {
  enabled: false,
  interval_hours: 24,
  score_min: 6.5,
  min_views: 50000,
  max_age_days: 3,
  n_por_nicho: 3,
  auto_generate: true,
  auto_publish: false,
  publish_platforms: ["youtube"],
  nichos_activos: ["ia", "crypto", "finanzas", "tecnologia"],
};

// ── Prefs types ────────────────────────────────────────────────────────────────

interface GenerationPrefs {
  servicio_voz: string;
  voz: string;
  tipo_contenido: string;
  duracion_maxima: number;
  mostrar_subtitulos: boolean;
  mostrar_titulo: boolean;
  marca: string;
  generar_imagenes_ai: boolean;
  servicio_ai: string;
  musica_fondo: string | null;
  volumen_musica: number;
  volumen_voz: number;
}

const PREFS_DEFAULT: GenerationPrefs = {
  servicio_voz: "edge-tts",
  voz: "es-ES-AlvaroNeural",
  tipo_contenido: "noticia",
  duracion_maxima: 60,
  mostrar_subtitulos: true,
  mostrar_titulo: true,
  marca: "",
  generar_imagenes_ai: false,
  servicio_ai: "pollinations",
  musica_fondo: null,
  volumen_musica: 0.3,
  volumen_voz: 1.0,
};

// ── Types ──────────────────────────────────────────────────────────────────────

type ItemEstado = "pending" | "queued" | "generating" | "ready" | "failed" | "auto_publishing";
type ScheduledEstado = "scheduled" | "publishing" | "done" | "failed";

interface QueueItem {
  id: string;
  tipo: "url" | "texto" | "noticia" | "manual";
  contenido: string;
  titulo: string;
  estado: ItemEstado;
  job_id: string | null;
  output_file: string | null;
  youtube_url: string | null;
  uploads?: Record<string, { url: string | boolean; at: string }>;
  creado: string;
  error: string | null;
  distribute_log?: { ts: string; platforms: string[]; results: Record<string, { ok: boolean; url?: string; error?: string }> }[];
  // Enriquecimiento de noticias (solo tipo="noticia")
  fecha_noticia?: string;
  recencia_label?: string;
  recencia_horas?: number | null;
  fuente_noticia?: string;
  score_noticia?: number | null;
  veracidad_label?: string;
  veracidad_color?: string;
  veracidad_score?: number | null;
  veracidad_evidencia?: string;
  // Hilo temático
  hilo_id?: string | null;
}

interface ThreadEpisodio {
  item_id: string;
  titulo: string;
  youtube_url: string;
  fecha: string;
  numero: number;
}

interface Thread {
  id: string;
  nombre: string;
  descripcion: string;
  tema: string;
  episodios: ThreadEpisodio[];
  creado: string;
  actualizado: string;
}

interface OrphanVideo {
  filename: string;
  titulo: string;
  size: number;
  modified: string;
}

interface ScheduledItem {
  id: string;
  output_file: string;
  titulo: string;
  descripcion: string;
  platforms: string[];
  tipo_contenido: string;
  publish_at: string | null;
  estado: ScheduledEstado;
  results: Record<string, { status: string; url?: string; error?: string }>;
  creado: string;
  error: string | null;
}

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
  telegram: PlatformStatus;
  x: PlatformStatus;
  facebook?: PlatformStatus & { page_name?: string };
  whatsapp_canal?: PlatformStatus & { channel_jid?: string; channel_name?: string };
  whatsapp?: PlatformStatus & { ready?: boolean };
}

// ── Constants ──────────────────────────────────────────────────────────────────

const PLATFORMS = [
  { id: "youtube",        label: "YouTube",      icon: "▶" },
  { id: "tiktok",         label: "TikTok",       icon: "♪" },
  { id: "instagram",      label: "Instagram",    icon: "◉" },
  { id: "x",              label: "X",            icon: "✕" },
  { id: "telegram",       label: "Telegram",     icon: "✈" },
  { id: "facebook",       label: "Facebook",     icon: "f" },
  { id: "whatsapp_canal", label: "WA Canal",     icon: "⊕" },
];

const ESTADO_STYLE: Record<ItemEstado, { label: string; color: string; bg: string }> = {
  pending:         { label: "Pendiente",      color: "#94a3b8", bg: "#1e293b" },
  queued:          { label: "En cola",        color: "#c084fc", bg: "#1a0a30" },
  generating:      { label: "Generando…",     color: "#60a5fa", bg: "#0f2040" },
  ready:           { label: "Listo",          color: "#4ade80", bg: "#0a2010" },
  failed:          { label: "Error",          color: "#f87171", bg: "#2a0a0a" },
  auto_publishing: { label: "Publicando…",    color: "#fb923c", bg: "#1f1008" },
};

const SCH_STYLE: Record<ScheduledEstado, { label: string; color: string }> = {
  scheduled:  { label: "Programado",   color: "#facc15" },
  publishing: { label: "Publicando…",  color: "#60a5fa" },
  done:       { label: "Publicado",    color: "#4ade80" },
  failed:     { label: "Error",        color: "#f87171" },
};

// ── Voice Preview ─────────────────────────────────────────────────────────────

function VoicePreview({ voz, servicio }: { voz: string; servicio: string }) {
  const [loading, setLoading] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  async function preview() {
    setLoading(true);
    setAudioUrl(null);
    try {
      const res = await fetch("/api/tts/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servicio, voz, texto: "Hola, soy la voz que narrará tus reels. ¿Qué te parece cómo sueno?" }),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setAudioUrl(url);
      setTimeout(() => {
        audioRef.current?.play();
      }, 50);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <button onClick={preview} disabled={loading} style={{
        ...btnSecondary, fontSize: 12, padding: "5px 14px",
        opacity: loading ? 0.6 : 1,
      }}>
        {loading ? "Cargando…" : "▶ Escuchar voz"}
      </button>
      <span style={{ fontSize: 11, color: "var(--muted)" }}>{voz}</span>
      {audioUrl && <audio ref={audioRef} src={audioUrl} style={{ display: "none" }} />}
    </div>
  );
}

// ── Publish Sheet ──────────────────────────────────────────────────────────────

interface CaptionData {
  tiktok: string;
  instagram: string;
  x: string;
  titulo: string;
  hook: string;
  descripcion_youtube?: string;
}

function PublishSheet({
  item,
  accounts,
  onClose,
  onScheduled,
}: {
  item: QueueItem;
  accounts: AccountsStatus | null;
  onClose: () => void;
  onScheduled: () => void;
}) {
  const [platforms, setPlatforms] = useState<string[]>(() =>
    accounts
      ? Object.entries(accounts)
          .filter(([, v]) => (v as PlatformStatus).connected)
          .map(([k]) => k)
      : []
  );
  const [titulo, setTitulo] = useState(
    item.titulo || (item.output_file?.replace(/_reel\.mp4$/, "").replace(/_/g, " ") ?? "")
  );
  const [desc, setDesc] = useState("");
  const [tiktokCaption, setTiktokCaption] = useState("");
  const [igCaption, setIgCaption] = useState("");
  const [xCaption, setXCaption] = useState("");
  const [captionLoading, setCaptionLoading] = useState(false);
  const [captionLoaded, setCaptionLoaded] = useState(false);
  const [tipo, setTipo] = useState<"noticia" | "curiosidad">("noticia");
  const [scheduleMode, setScheduleMode] = useState<"now" | "later">("now");
  const [autoDistribute, setAutoDistribute] = useState(false);
  const [distPlatforms, setDistPlatforms] = useState<string[]>(["telegram"]);
  const [distTextos, setDistTextos] = useState<Record<string, string>>({});
  const [publishAt, setPublishAt] = useState(() => {
    const d = new Date();
    d.setHours(d.getHours() + 1, 0, 0, 0);
    return d.toISOString().slice(0, 16);
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [alreadyUploaded, setAlreadyUploaded] = useState<{ platforms: Record<string, { url: string | boolean; at: string }> } | null>(null);

  useEffect(() => {
    if (!item.output_file) return;
    setCaptionLoading(true);
    fetch(`/api/publish/caption?filename=${encodeURIComponent(item.output_file)}`)
      .then((r) => r.ok ? r.json() : null)
      .then((data: CaptionData | null) => {
        if (data) {
          setTiktokCaption(data.tiktok);
          setIgCaption(data.instagram);
          if (data.x) setXCaption(data.x);
          // Usar el hook como título YouTube (más punchy que el slug del item)
          setTitulo(data.hook || data.titulo || titulo);
          if (data.descripcion_youtube) setDesc(data.descripcion_youtube);
          // Pre-poblar textos de auto-distribución
          const hook = data.hook || data.titulo || "";
          const hashLine = data.x.split("\n").find((l) => l.startsWith("#")) ?? "";
          setDistTextos({
            telegram: [`🔴 ${data.titulo || hook}`, hook !== data.titulo ? hook : "", hashLine].filter(Boolean).join("\n\n"),
            x: data.x.slice(0, 270),
            whatsapp: [data.titulo || hook, hook !== data.titulo ? hook : ""].filter(Boolean).join("\n\n"),
          });
          setCaptionLoaded(true);
        }
      })
      .catch(() => {})
      .finally(() => setCaptionLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.output_file]);

  function toggle(id: string) {
    setPlatforms((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function handleSubmit(force = false) {
    if (platforms.length === 0) return;
    setSubmitting(true);
    setError("");
    setAlreadyUploaded(null);
    try {
      const body: Record<string, unknown> = {
        output_file: item.output_file,
        titulo,
        descripcion: desc,
        tiktok_caption: tiktokCaption,
        instagram_caption: igCaption,
        x_caption: xCaption,
        platforms,
        tipo_contenido: tipo,
        publish_at: scheduleMode === "later" ? new Date(publishAt).toISOString() : null,
        queue_item_id: item.id,
        auto_distribute: autoDistribute,
        distribute_platforms: distPlatforms,
        distribute_textos: distTextos,
        force,
      };
      const res = await fetch("/api/gestor/scheduled", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.status === 409) {
        const data = await res.json();
        const platforms = data.detail?.platforms ?? data.platforms ?? {};
        setAlreadyUploaded({ platforms });
        return;
      }
      if (!res.ok) throw new Error(await res.text());
      onScheduled();
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)",
      zIndex: 3000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
    }}>
      <div style={{
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 18, width: "100%", maxWidth: 460,
        maxHeight: "90vh", display: "flex", flexDirection: "column", overflow: "hidden",
      }}>
        <div style={{ padding: "18px 20px 12px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <p style={{ fontWeight: 700, fontSize: 16, margin: 0 }}>Publicar reel</p>
            <p style={{ fontSize: 11, color: "var(--muted)", margin: "2px 0 0" }}>{item.output_file}</p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 18 }}>✕</button>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px", display: "flex", flexDirection: "column", gap: 14 }}>

          {/* Plataformas */}
          <div>
            <Label>Publicar en</Label>
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              {PLATFORMS.map((p) => {
                const st = accounts?.[p.id as keyof AccountsStatus] as PlatformStatus | undefined;
                const connected = st?.connected;
                const sel = platforms.includes(p.id);
                const name = p.id === "youtube" ? st?.canal
                  : p.id === "tiktok" ? st?.display_name
                  : p.id === "instagram" ? st?.username
                  : p.id === "facebook" ? (accounts?.facebook as { page_name?: string })?.page_name
                  : p.id === "whatsapp_canal" ? (accounts?.whatsapp_canal as { channel_name?: string })?.channel_name || "Canal configurado"
                  : null;
                return (
                  <label key={p.id} style={{
                    display: "flex", alignItems: "center", gap: 10, padding: "9px 12px",
                    borderRadius: 10, cursor: connected ? "pointer" : "default",
                    background: sel && connected ? "rgba(99,102,241,0.1)" : "var(--surface2)",
                    border: `1px solid ${sel && connected ? "var(--accent)" : "var(--border)"}`,
                    opacity: connected ? 1 : 0.4,
                  }}>
                    <input type="checkbox" checked={sel && !!connected} disabled={!connected}
                      onChange={() => connected && toggle(p.id)}
                      style={{ accentColor: "var(--accent)", width: 14, height: 14 }} />
                    <span style={{ fontSize: 15 }}>{p.icon}</span>
                    <div style={{ flex: 1 }}>
                      <p style={{ fontSize: 13, fontWeight: 600, margin: 0 }}>{p.label}</p>
                      {connected && name
                        ? <p style={{ fontSize: 11, color: "var(--success)", margin: 0 }}>✓ {name}</p>
                        : <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>No conectado</p>}
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Título */}
          <div>
            <Label>Título</Label>
            <input value={titulo} onChange={(e) => setTitulo(e.target.value)}
              placeholder="Título del video"
              style={inputStyle} />
          </div>

          {/* Captions por plataforma */}
          {platforms.includes("tiktok") && (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: 0 }}>Caption TikTok</p>
                {captionLoading && <span style={{ fontSize: 10, color: "var(--muted)" }}>Generando…</span>}
                {captionLoaded && !captionLoading && <span style={{ fontSize: 10, color: "var(--success)" }}>✓ Auto</span>}
              </div>
              <textarea value={tiktokCaption} onChange={(e) => setTiktokCaption(e.target.value)}
                placeholder="Caption viral para TikTok…" rows={4}
                style={{ ...inputStyle, resize: "vertical", fontSize: 11 }} />
              <p style={{ fontSize: 10, color: "var(--muted)", margin: "3px 0 0" }}>
                {tiktokCaption.length} chars · TikTok recomienda &lt;150 en el título
              </p>
            </div>
          )}
          {platforms.includes("instagram") && (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: 0 }}>Caption Instagram</p>
                {captionLoading && <span style={{ fontSize: 10, color: "var(--muted)" }}>Generando…</span>}
                {captionLoaded && !captionLoading && <span style={{ fontSize: 10, color: "var(--success)" }}>✓ Auto</span>}
              </div>
              <textarea value={igCaption} onChange={(e) => setIgCaption(e.target.value)}
                placeholder="Caption optimizado para Instagram…" rows={6}
                style={{ ...inputStyle, resize: "vertical", fontSize: 11 }} />
              <p style={{ fontSize: 10, color: "var(--muted)", margin: "3px 0 0" }}>
                {igCaption.length} chars
              </p>
            </div>
          )}
          {platforms.includes("x") && (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: 0 }}>Tweet (X)</p>
                {captionLoading && <span style={{ fontSize: 10, color: "var(--muted)" }}>Generando…</span>}
                {captionLoaded && !captionLoading && <span style={{ fontSize: 10, color: "var(--success)" }}>✓ Auto</span>}
              </div>
              <textarea value={xCaption} onChange={(e) => setXCaption(e.target.value)}
                placeholder="Texto del tweet…" rows={3}
                style={{ ...inputStyle, resize: "vertical", fontSize: 11 }} />
              <p style={{ fontSize: 10, color: xCaption.length > 280 ? "var(--error)" : "var(--muted)", margin: "3px 0 0" }}>
                {xCaption.length}/280 chars
              </p>
            </div>
          )}

          {/* Descripción genérica (YouTube, Telegram, WhatsApp) */}
          {platforms.some((p) => !["tiktok", "instagram", "x"].includes(p)) && (
            <div>
              <Label>Descripción</Label>
              <textarea value={desc} onChange={(e) => setDesc(e.target.value)}
                placeholder="Descripción opcional" rows={2}
                style={{ ...inputStyle, resize: "vertical" }} />
            </div>
          )}

          {/* Tipo YouTube */}
          {platforms.includes("youtube") && (
            <div>
              <Label>Tipo de contenido (YouTube)</Label>
              <div style={{ display: "flex", gap: 8 }}>
                {(["noticia", "curiosidad"] as const).map((t) => (
                  <button key={t} onClick={() => setTipo(t)} style={{
                    flex: 1, padding: "7px 0", borderRadius: 8, fontSize: 12, fontWeight: 600,
                    cursor: "pointer",
                    border: `1px solid ${tipo === t ? "var(--accent)" : "var(--border)"}`,
                    background: tipo === t ? "rgba(99,102,241,0.12)" : "var(--surface2)",
                    color: tipo === t ? "var(--accent)" : "var(--muted)",
                  }}>
                    {t === "noticia" ? "Noticia" : "Curiosidad"}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Programar */}
          <div>
            <Label>Cuándo publicar</Label>
            <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
              {(["now", "later"] as const).map((m) => (
                <button key={m} onClick={() => setScheduleMode(m)} style={{
                  flex: 1, padding: "7px 0", borderRadius: 8, fontSize: 12, fontWeight: 600,
                  cursor: "pointer",
                  border: `1px solid ${scheduleMode === m ? "var(--accent)" : "var(--border)"}`,
                  background: scheduleMode === m ? "rgba(99,102,241,0.12)" : "var(--surface2)",
                  color: scheduleMode === m ? "var(--accent)" : "var(--muted)",
                }}>
                  {m === "now" ? "Ahora" : "Programar"}
                </button>
              ))}
            </div>
            {scheduleMode === "later" && (
              <input type="datetime-local" value={publishAt}
                onChange={(e) => setPublishAt(e.target.value)}
                style={inputStyle} />
            )}
          </div>

          {/* Auto-distribución */}
          {platforms.includes("youtube") && (
            <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <input type="checkbox" checked={autoDistribute} onChange={(e) => setAutoDistribute(e.target.checked)}
                  style={{ accentColor: "var(--accent)", width: 15, height: 15 }} />
                <span style={{ fontSize: 13, fontWeight: 600 }}>Auto-distribuir tras subir a YouTube</span>
              </label>
              {autoDistribute && (
                <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {(["telegram", "x", "whatsapp"] as const).map((p) => {
                      const icons: Record<string, string> = { telegram: "✈️ Telegram", x: "𝕏 X", whatsapp: "💬 WhatsApp" };
                      const sel = distPlatforms.includes(p);
                      return (
                        <label key={p} style={{
                          display: "flex", alignItems: "center", gap: 5, padding: "4px 10px",
                          borderRadius: 7, cursor: "pointer", fontSize: 12,
                          background: sel ? "rgba(99,102,241,0.12)" : "var(--surface2)",
                          border: `1px solid ${sel ? "var(--accent)" : "var(--border)"}`,
                          color: sel ? "var(--accent)" : "var(--muted)", fontWeight: 600,
                        }}>
                          <input type="checkbox" checked={sel} style={{ accentColor: "var(--accent)" }}
                            onChange={(e) => setDistPlatforms((prev) =>
                              e.target.checked ? [...prev, p] : prev.filter((x) => x !== p)
                            )} />
                          {icons[p]}
                        </label>
                      );
                    })}
                  </div>
                  {distPlatforms.map((p) => (
                    <div key={p}>
                      <p style={{ fontSize: 10, color: "var(--muted)", margin: "0 0 3px", textTransform: "uppercase" }}>{p}</p>
                      <textarea
                        value={distTextos[p] ?? ""}
                        onChange={(e) => setDistTextos((t) => ({ ...t, [p]: e.target.value }))}
                        rows={3}
                        style={{ ...inputStyle, width: "100%", fontSize: 11, resize: "vertical", boxSizing: "border-box" }}
                      />
                    </div>
                  ))}
                  <p style={{ fontSize: 10, color: "var(--muted)", margin: 0 }}>
                    La URL de YouTube se añadirá automáticamente al texto al subirse.
                  </p>
                </div>
              )}
            </div>
          )}

          {alreadyUploaded && (
            <div style={{ background: "#1a1500", border: "1px solid #a16207", borderRadius: 10, padding: "12px 14px" }}>
              <p style={{ fontSize: 13, fontWeight: 700, color: "#facc15", margin: "0 0 6px" }}>
                Ya subido anteriormente
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
                {Object.entries(alreadyUploaded.platforms).map(([p, info]) => (
                  <div key={p} style={{ fontSize: 12, color: "#fef3c7", display: "flex", justifyContent: "space-between" }}>
                    <span style={{ textTransform: "capitalize" }}>{p}</span>
                    <span style={{ color: "#a16207" }}>
                      {new Date(info.at).toLocaleDateString("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                      {typeof info.url === "string" && info.url !== "true" && (
                        <a href={info.url} target="_blank" rel="noopener noreferrer" style={{ marginLeft: 8, color: "#facc15" }}>Ver</a>
                      )}
                    </span>
                  </div>
                ))}
              </div>
              <p style={{ fontSize: 11, color: "#a16207", margin: "0 0 10px" }}>
                Este reel ya fue subido y confirmado. Volver a subirlo creara un duplicado.
              </p>
              <button onClick={() => handleSubmit(true)} style={{
                ...btnPrimary, background: "#92400e", fontSize: 12, padding: "7px 14px",
              }}>
                Forzar re-subida de todas formas
              </button>
            </div>
          )}

          {error && (
            <p style={{ fontSize: 12, color: "var(--error)", background: "#2a0a0a", padding: "8px 12px", borderRadius: 8, margin: 0 }}>
              {error}
            </p>
          )}
        </div>

        <div style={{ padding: "14px 20px", borderTop: "1px solid var(--border)", display: "flex", gap: 10 }}>
          <button onClick={onClose} style={btnSecondary}>Cancelar</button>
          {!alreadyUploaded && (
            <button onClick={() => handleSubmit(false)} disabled={submitting || platforms.length === 0} style={{
              ...btnPrimary,
              opacity: submitting || platforms.length === 0 ? 0.5 : 1,
              cursor: submitting || platforms.length === 0 ? "not-allowed" : "pointer",
            }}>
              {submitting ? "Enviando…" : scheduleMode === "later" ? "Programar" : "Publicar ahora"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Discover mini-panel ────────────────────────────────────────────────────────

interface Noticia {
  titulo: string;
  link: string;
  resumen: string;
  fuente: string;
  score: number;
  categoria: string;
  gancho?: string;
  documentacion?: string;
  verificadores?: string[];
  estado_verificacion?: string;
  origen?: string;
}

function DiscoverMini({ onAdd }: { onAdd: (n: Noticia) => void }) {
  const [tema, setTema] = useState("");
  const [loading, setLoading] = useState(false);
  const [noticias, setNoticias] = useState<Noticia[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");

  async function buscar() {
    setLoading(true);
    setError("");
    setNoticias([]);
    setSelected(new Set());
    try {
      const body = tema.trim()
        ? { tema: tema.trim(), pais: "ES", variado: false, n_retornar: 8 }
        : { pais: "ES", variado: true, n_retornar: 8 };
      const res = await fetch("/api/news/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setNoticias(data.noticias || []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function toggleSel(link: string) {
    setSelected((prev) => {
      const n = new Set(prev);
      n.has(link) ? n.delete(link) : n.add(link);
      return n;
    });
  }

  function addSelected() {
    noticias.filter((n) => selected.has(n.link)).forEach(onAdd);
    setSelected(new Set());
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <input value={tema} onChange={(e) => setTema(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && buscar()}
          placeholder="Tema (vacío = variado)"
          style={{ ...inputStyle, flex: 1 }} />
        <button onClick={buscar} disabled={loading} style={{ ...btnPrimary, padding: "0 18px", flexShrink: 0 }}>
          {loading ? "…" : "Buscar"}
        </button>
      </div>
      {error && <p style={{ fontSize: 12, color: "var(--error)", marginBottom: 8 }}>{error}</p>}
      {noticias.length > 0 && (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 280, overflowY: "auto" }}>
            {noticias.map((n) => (
              <label key={n.link} style={{
                display: "flex", gap: 10, padding: "9px 12px", borderRadius: 10, cursor: "pointer",
                background: selected.has(n.link) ? "rgba(99,102,241,0.1)" : "var(--surface2)",
                border: `1px solid ${selected.has(n.link) ? "var(--accent)" : "var(--border)"}`,
              }}>
                <input type="checkbox" checked={selected.has(n.link)} onChange={() => toggleSel(n.link)}
                  style={{ accentColor: "var(--accent)", marginTop: 2, flexShrink: 0 }} />
                <div style={{ minWidth: 0 }}>
                  <p style={{ fontSize: 13, fontWeight: 600, margin: 0, color: "var(--text)", lineHeight: 1.3 }}>{n.titulo}</p>
                  <p style={{ fontSize: 11, color: "var(--muted)", margin: "2px 0 0" }}>
                    {n.origen || n.fuente} · score {n.score}
                    {n.verificadores?.length ? ` · contrastada por ${n.verificadores.join(", ")}` : ""}
                  </p>
                  {n.documentacion && (
                    <p style={{ fontSize: 11, color: "var(--text)", opacity: 0.75, margin: "2px 0 0" }}>{n.documentacion}</p>
                  )}
                </div>
              </label>
            ))}
          </div>
          {selected.size > 0 && (
            <button onClick={addSelected} style={{ ...btnPrimary, marginTop: 10, width: "100%" }}>
              Añadir {selected.size} noticia{selected.size > 1 ? "s" : ""} a la cola
            </button>
          )}
        </>
      )}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

type AddMode = "url" | "texto" | "descubrir" | "subir";

export default function GestorPage() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [scheduled, setScheduled] = useState<ScheduledItem[]>([]);
  const [accounts, setAccounts] = useState<AccountsStatus | null>(null);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadsOpen, setThreadsOpen] = useState(false);
  const [newThreadNombre, setNewThreadNombre] = useState("");
  const [newThreadTema, setNewThreadTema] = useState("");

  const [prefs, setPrefs] = useState<GenerationPrefs>(PREFS_DEFAULT);
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [prefsSaving, setPrefsSaving] = useState(false);
  const [prefsToast, setPrefsToast] = useState("");
  const [musicTracks, setMusicTracks] = useState<{ id: string; name: string; filename: string }[]>([]);
  const prefsInitialized = useRef(false);

  // Modal de generación con opciones
  const [regenModal, setRegenModal] = useState<QueueItem | null>(null);
  const [regenOpts, setRegenOpts] = useState({
    musica_activa: false,
    musica_fondo: null as string | null,
    mostrar_titulo: true,
    mostrar_subtitulos: true,
    largo: false,
  });
  const [ttsStatus, setTtsStatus] = useState<{ edge_tts: boolean; elevenlabs: boolean } | null>(null);

  const [scannerStatus, setScannerStatus] = useState<ScannerStatus | null>(null);
  const [scannerConfig, setScannerConfig] = useState<ScannerConfig>(SCANNER_CONFIG_DEFAULT);
  const [scannerOpen, setScannerOpen] = useState(false);
  const [scannerSaving, setScannerSaving] = useState(false);
  const [scannerRunning, setScannerRunning] = useState(false);
  const [notifs, setNotifs] = useState<ScannerNotif[]>([]);
  const [notifsOpen, setNotifsOpen] = useState(false);
  const [notifSelected, setNotifSelected] = useState<Set<string>>(new Set());
  const [ytNotifSelected, setYtNotifSelected] = useState<Set<string>>(new Set());
  const [highlightedItemId, setHighlightedItemId] = useState<string | null>(null);
  const scannerPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // YT Scanner
  const [ytStatus, setYtStatus] = useState<YtScannerStatus | null>(null);
  const [ytConfig, setYtConfig] = useState<YtScannerConfig>(YT_SCANNER_CONFIG_DEFAULT);
  const [ytNichos, setYtNichos] = useState<Record<string, YtNichoMeta>>({});
  const [ytOpen, setYtOpen] = useState(false);
  const [ytNotifsOpen, setYtNotifsOpen] = useState(false);
  const [ytNotifs, setYtNotifs] = useState<YtNotif[]>([]);
  const [ytSaving, setYtSaving] = useState(false);
  const [ytRunning, setYtRunning] = useState(false);
  const ytPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Autopublisher
  const [autoPubStatus, setAutoPubStatus] = useState<AutoPubStatus | null>(null);
  const [autoPubOpen, setAutoPubOpen] = useState(false);
  const autoPubPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Videos manuales (orphans)
  const [orphans, setOrphans] = useState<OrphanVideo[]>([]);
  const [importingOrphan, setImportingOrphan] = useState<string | null>(null);
  const [orphansOpen, setOrphansOpen] = useState(true);

  // Distribución
  interface DistribConfig {
    telegram_grupos: { chat_id: string; nombre: string }[];
    telegram_grupos_enabled: boolean;
    reddit_subreddits: string[];
    reddit_enabled: boolean;
    delay_entre_posts: number;
  }
  const [distribOpen, setDistribOpen] = useState(false);
  const [distribCfg, setDistribCfg] = useState<DistribConfig | null>(null);
  const [distribSaving, setDistribSaving] = useState(false);
  const [distribTgInput, setDistribTgInput] = useState({ chat_id: "", nombre: "" });
  const [distribSubInput, setDistribSubInput] = useState("");
  const [distribTestId, setDistribTestId] = useState<string | null>(null);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const [addMode, setAddMode] = useState<AddMode>("url");
  const [urlInput, setUrlInput] = useState("");
  const [textoInput, setTextoInput] = useState("");
  const [tituloInput, setTituloInput] = useState("");
  const [adding, setAdding] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitulo, setUploadTitulo] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");

  const [publishItem, setPublishItem] = useState<QueueItem | null>(null);
  const [quickPublishing, setQuickPublishing] = useState<Record<string, boolean>>({});
  const [quickPublishDone, setQuickPublishDone] = useState<Record<string, boolean>>({});
  const [quickPublishWarning, setQuickPublishWarning] = useState<Record<string, string>>({});
  const [previewFile, setPreviewFile] = useState<string | null>(null);
  const [fechaFilter, setFechaFilter] = useState<"all" | "1h" | "6h" | "24h" | "7d" | "30d">("all");
  const [distributeOpen, setDistributeOpen] = useState<string | null>(null);
  const [ytUrlDraft, setYtUrlDraft] = useState<Record<string, string>>({});
  const [distributing, setDistributing] = useState<string | null>(null);
  const [distributeResults, setDistributeResults] = useState<Record<string, Record<string, { ok: boolean; url?: string; error?: string }>>>({});
  const [distributePlatforms, setDistributePlatforms] = useState<Record<string, string[]>>({});
  const [distributeText, setDistributeText] = useState<Record<string, string>>({});
  const [distributePlatformTexts, setDistributePlatformTexts] = useState<Record<string, Record<string, string>>>({});
  const [distributeCapLoading, setDistributeCapLoading] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchItems = useCallback(async () => {
    try {
      const [qi, si] = await Promise.all([
        fetch("/api/gestor/items").then((r) => r.json()),
        fetch("/api/gestor/scheduled").then((r) => r.json()),
      ]);
      setItems(qi);
      setScheduled(si);
    } catch { /* ignore */ }
  }, []);

  const fetchThreads = useCallback(async () => {
    try {
      const data = await fetch("/api/threads").then((r) => r.json());
      setThreads(Array.isArray(data) ? data : []);
    } catch { /* ignore */ }
  }, []);

  const fetchScanner = useCallback(async () => {
    try {
      const [st, nf] = await Promise.all([
        fetch("/api/scanner/status").then((r) => r.json()),
        fetch("/api/scanner/notifications").then((r) => r.json()),
      ]);
      setScannerStatus(st);
      setScannerConfig(st.config);
      setNotifs(Array.isArray(nf) ? nf : []);
    } catch { /* ignore */ }
  }, []);

  const fetchYtScanner = useCallback(async () => {
    try {
      const [st, nf] = await Promise.all([
        fetch("/api/yt-scanner/status").then((r) => r.json()),
        fetch("/api/yt-scanner/notifications").then((r) => r.json()),
      ]);
      setYtStatus(st);
      setYtConfig(st.config);
      setYtNichos(st.nichos || {});
      setYtNotifs(Array.isArray(nf) ? nf : []);
    } catch { /* ignore */ }
  }, []);

  const fetchAutoPub = useCallback(async () => {
    try {
      const st = await fetch("/api/autopublisher/status").then((r) => r.json());
      setAutoPubStatus(st);
    } catch { /* ignore */ }
  }, []);

  const fetchOrphans = useCallback(async () => {
    try {
      const data = await fetch("/api/gestor/orphans").then((r) => r.json());
      setOrphans(Array.isArray(data) ? data : []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetch("/api/accounts/status").then((r) => r.json()).then(setAccounts).catch(() => {});
    fetch("/api/prefs/generation").then((r) => r.json()).then((d) => { setPrefs(d); prefsInitialized.current = true; }).catch(() => { prefsInitialized.current = true; });
    fetch("/api/tts/status").then((r) => r.json()).then(setTtsStatus).catch(() => {});
    fetch("/api/music").then((r) => r.json()).then((d) => setMusicTracks(Array.isArray(d) ? d : [])).catch(() => {});
    fetchItems();
    fetchScanner();
    fetchYtScanner();
    fetchAutoPub();
    fetchStorage();
    fetchThreads();
    fetchOrphans();
  }, [fetchItems, fetchScanner, fetchYtScanner, fetchAutoPub, fetchThreads, fetchOrphans]);

  // Poll scanner mientras esté corriendo o haya config activa
  useEffect(() => {
    const isActive = scannerStatus?.running || scannerStatus?.config?.enabled;
    if (isActive) {
      if (!scannerPollRef.current) {
        scannerPollRef.current = setInterval(fetchScanner, 10000);
      }
    } else {
      if (scannerPollRef.current) {
        clearInterval(scannerPollRef.current);
        scannerPollRef.current = null;
      }
    }
    return () => {
      if (scannerPollRef.current) { clearInterval(scannerPollRef.current); scannerPollRef.current = null; }
    };
  }, [scannerStatus, fetchScanner]);

  // Auto-guardar prefs cuando cambian (debounce 800ms)
  useEffect(() => {
    if (!prefsInitialized.current) return;
    const timer = setTimeout(() => {
      fetch("/api/prefs/generation", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(prefs),
      }).then(() => {
        setPrefsToast("✓ Guardado");
        setTimeout(() => setPrefsToast(""), 2000);
      }).catch(() => {});
    }, 800);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefs]);

  // Poll YT scanner mientras esté activo
  useEffect(() => {
    const isActive = ytStatus?.running || ytStatus?.config?.enabled;
    if (isActive) {
      if (!ytPollRef.current) ytPollRef.current = setInterval(fetchYtScanner, 15000);
    } else {
      if (ytPollRef.current) { clearInterval(ytPollRef.current); ytPollRef.current = null; }
    }
    return () => { if (ytPollRef.current) { clearInterval(ytPollRef.current); ytPollRef.current = null; } };
  }, [ytStatus, fetchYtScanner]);

  // Poll autopublisher cada 10s cuando está activo o publicando
  useEffect(() => {
    const isActive = autoPubStatus?.enabled || autoPubStatus?.publishing;
    if (isActive) {
      if (!autoPubPollRef.current) autoPubPollRef.current = setInterval(fetchAutoPub, 10000);
    } else {
      if (autoPubPollRef.current) { clearInterval(autoPubPollRef.current); autoPubPollRef.current = null; }
    }
    return () => { if (autoPubPollRef.current) { clearInterval(autoPubPollRef.current); autoPubPollRef.current = null; } };
  }, [autoPubStatus, fetchAutoPub]);

  // Poll mientras hay items generando o publicaciones activas
  useEffect(() => {
    const hasActive =
      items.some((i) => i.estado === "generating" || i.estado === "queued") ||
      scheduled.some((s) => s.estado === "publishing");

    if (hasActive) {
      if (!pollRef.current) {
        pollRef.current = setInterval(fetchItems, 3000);
      }
    } else {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [items, scheduled, fetchItems]);

  async function handleAdd() {
    let contenido = "";
    let titulo = tituloInput.trim();
    let tipo: "url" | "texto" = addMode === "url" ? "url" : "texto";

    if (addMode === "url") {
      contenido = urlInput.trim();
      if (!contenido) return;
    } else {
      contenido = textoInput.trim();
      if (!contenido) return;
    }

    setAdding(true);
    try {
      await fetch("/api/gestor/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tipo, contenido, titulo }),
      });
      setUrlInput("");
      setTextoInput("");
      setTituloInput("");
      await fetchItems();
    } finally {
      setAdding(false);
    }
  }

  async function uploadVideo() {
    if (!uploadFile) return;
    setUploading(true);
    setUploadError("");
    try {
      const fd = new FormData();
      fd.append("file", uploadFile);
      fd.append("titulo", uploadTitulo.trim());
      const res = await fetch("/api/gestor/upload-video", { method: "POST", body: fd });
      if (!res.ok) throw new Error(await res.text());
      setUploadFile(null);
      setUploadTitulo("");
      await fetchItems();
      await fetchOrphans();
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  async function addNoticia(n: Noticia) {
    await fetch("/api/gestor/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tipo: "noticia",
        contenido: JSON.stringify(n),
        titulo: n.titulo,
      }),
    });
    await fetchItems();
  }

  async function generateItem(id: string) {
    await fetch(`/api/gestor/items/${id}/generate`, { method: "POST" });
    await fetchItems();
    // Inicia polling
    if (!pollRef.current) {
      pollRef.current = setInterval(fetchItems, 3000);
    }
  }

  function openRegenModal(item: QueueItem) {
    setRegenOpts({
      musica_activa: prefs.musica_fondo !== null && prefs.musica_fondo !== "",
      musica_fondo: prefs.musica_fondo ?? null,
      mostrar_titulo: prefs.mostrar_titulo,
      mostrar_subtitulos: prefs.mostrar_subtitulos,
      largo: false,
    });
    setRegenModal(item);
  }

  async function confirmRegen() {
    if (!regenModal) return;
    const item = regenModal;
    setRegenModal(null);

    const overrides = {
      musica_fondo: regenOpts.musica_activa ? (regenOpts.musica_fondo ?? "") : "",
      mostrar_titulo: regenOpts.mostrar_titulo,
      mostrar_subtitulos: regenOpts.mostrar_subtitulos,
      largo: regenOpts.largo,
    };

    const endpoint = (item.estado === "failed" || item.estado === "ready")
      ? `/api/gestor/items/${item.id}/retry`
      : `/api/gestor/items/${item.id}/generate`;

    await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(overrides),
    });
    await fetchItems();
    if (!pollRef.current) pollRef.current = setInterval(fetchItems, 3000);
  }

  async function generateAll() {
    const pending = items.filter((i) => i.estado === "pending");
    for (const i of pending) {
      await fetch(`/api/gestor/items/${i.id}/generate`, { method: "POST" });
    }
    await fetchItems();
    if (!pollRef.current) {
      pollRef.current = setInterval(fetchItems, 3000);
    }
  }

  async function generateSelected() {
    const toGenerate = items.filter((i) => i.estado === "pending" && selectedIds.has(i.id));
    for (const i of toGenerate) {
      await fetch(`/api/gestor/items/${i.id}/generate`, { method: "POST" });
    }
    setSelectedIds(new Set());
    await fetchItems();
    if (!pollRef.current) {
      pollRef.current = setInterval(fetchItems, 3000);
    }
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    const pendingIds = filteredItems.filter((i) => i.estado === "pending").map((i) => i.id);
    const allSelected = pendingIds.every((id) => selectedIds.has(id));
    if (allSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        pendingIds.forEach((id) => next.delete(id));
        return next;
      });
    } else {
      setSelectedIds((prev) => new Set([...prev, ...pendingIds]));
    }
  }

  async function savePrefs(updated: GenerationPrefs) {
    setPrefsSaving(true);
    try {
      const res = await fetch("/api/prefs/generation", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updated),
      });
      if (!res.ok) throw new Error(await res.text());
      setPrefs(updated);
      setPrefsToast("Guardado");
      setTimeout(() => setPrefsToast(""), 2500);
    } catch {
      setPrefsToast("Error al guardar");
      setTimeout(() => setPrefsToast(""), 3000);
    } finally {
      setPrefsSaving(false);
    }
  }

  async function saveYoutubeUrl(itemId: string, url: string) {
    await fetch(`/api/gestor/items/${itemId}/youtube_url`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ youtube_url: url }),
    });
    await fetchItems();
  }

  async function openDistribute(item: QueueItem) {
    const ytUrl = item.youtube_url || ytUrlDraft[item.id] || "";
    const titulo = item.titulo || "";
    setDistributePlatforms((p) => ({ ...p, [item.id]: p[item.id] ?? ["telegram"] }));
    setDistributeOpen(item.id);

    // Si ya tenemos textos generados, no regeneramos
    if (distributePlatformTexts[item.id]) return;

    if (item.output_file) {
      setDistributeCapLoading(item.id);
      try {
        const res = await fetch(`/api/publish/caption?filename=${encodeURIComponent(item.output_file)}`);
        if (res.ok) {
          const data: CaptionData = await res.json();
          const hook = data.hook || "";
          const tit = data.titulo || titulo;
          const urlLine = ytUrl ? `▶️ ${ytUrl}` : "";
          const hashLine = data.x.split("\n").find((l) => l.startsWith("#")) ?? "";
          const xText = [data.x, ytUrl ? `▶️ ${ytUrl}` : ""].filter(Boolean).join("\n").slice(0, 280);
          const tgText = [
            tit ? `🔴 ${tit}` : "",
            hook && hook !== tit ? hook : "",
            urlLine,
            hashLine,
          ].filter(Boolean).join("\n\n");
          const waText = [tit, hook && hook !== tit ? hook : "", urlLine].filter(Boolean).join("\n\n");
          setDistributePlatformTexts((t) => ({
            ...t,
            [item.id]: { telegram: tgText, x: xText, whatsapp: waText },
          }));
          return;
        }
      } catch { /* fall through */ } finally {
        setDistributeCapLoading(null);
      }
    }

    // Fallback sin caption
    const fallback = `${titulo}\n\n▶️ ${ytUrl}\n\n#IA #InteligenciaArtificial #Tecnologia`;
    setDistributePlatformTexts((t) => ({
      ...t,
      [item.id]: { telegram: fallback, x: `${titulo}\n▶️ ${ytUrl}\n#IA #Tecnologia`.slice(0, 280), whatsapp: fallback },
    }));
  }

  async function distributeItem(itemId: string) {
    const platforms = distributePlatforms[itemId] ?? ["telegram"];
    const platTexts = distributePlatformTexts[itemId] ?? {};
    const textos: Record<string, string> = {};
    for (const p of platforms) {
      if (platTexts[p]?.trim()) textos[p] = platTexts[p];
    }
    const texto = distributeText[itemId] ?? "";
    const hasContent = Object.values(textos).some((t) => t.trim()) || texto.trim();
    if (!platforms.length || !hasContent) return;
    setDistributing(itemId);
    setDistributeResults((r) => ({ ...r, [itemId]: {} }));
    try {
      const res = await fetch(`/api/gestor/items/${itemId}/distribute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platforms, texto, textos }),
      });
      const data = await res.json();
      setDistributeResults((r) => ({ ...r, [itemId]: data.results ?? {} }));
      await fetchItems();
    } catch {
      setDistributeResults((r) => ({ ...r, [itemId]: { _error: { ok: false, error: "Error de red" } } }));
    } finally {
      setDistributing(null);
    }
  }

  async function saveScannerConfig(cfg: ScannerConfig) {
    setScannerSaving(true);
    try {
      const res = await fetch("/api/scanner/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cfg),
      });
      if (!res.ok) throw new Error(await res.text());
      setScannerConfig(cfg);
      await fetchScanner();
    } finally {
      setScannerSaving(false);
    }
  }

  async function runScannerNow() {
    setScannerRunning(true);
    try {
      await fetch("/api/scanner/run", { method: "POST" });
      // Poll más rápido durante el escaneo
      if (!scannerPollRef.current) {
        scannerPollRef.current = setInterval(fetchScanner, 3000);
      }
      await fetchScanner();
    } finally {
      setScannerRunning(false);
    }
  }

  async function markNotifsRead() {
    await fetch("/api/scanner/notifications/read-all", { method: "POST" });
    setNotifs((prev) => prev.map((n) => ({ ...n, leido: true })));
    setScannerStatus((prev) => prev ? { ...prev, unread: 0 } : prev);
  }

  async function clearNotifs() {
    await fetch("/api/scanner/notifications", { method: "DELETE" });
    setNotifs([]);
    setScannerStatus((prev) => prev ? { ...prev, unread: 0 } : prev);
  }

  async function saveYtConfig(cfg: YtScannerConfig) {
    setYtSaving(true);
    try {
      await fetch("/api/yt-scanner/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cfg),
      });
      await fetchYtScanner();
    } finally {
      setYtSaving(false);
    }
  }

  async function runYtScannerNow() {
    setYtRunning(true);
    await fetch("/api/yt-scanner/run", { method: "POST" });
    setTimeout(() => { fetchYtScanner(); setYtRunning(false); }, 2000);
    if (!ytPollRef.current) ytPollRef.current = setInterval(fetchYtScanner, 5000);
  }

  async function markYtNotifsRead() {
    await fetch("/api/yt-scanner/notifications/read-all", { method: "POST" });
    setYtNotifs((prev) => prev.map((n) => ({ ...n, leido: true })));
    setYtStatus((prev) => prev ? { ...prev, unread: 0 } : prev);
  }

  async function clearYtNotifs() {
    await fetch("/api/yt-scanner/notifications", { method: "DELETE" });
    setYtNotifs([]);
    setYtStatus((prev) => prev ? { ...prev, unread: 0 } : prev);
  }

  async function retryAll() {
    const failed = items.filter((i) => i.estado === "failed");
    for (const i of failed) {
      await fetch(`/api/gestor/items/${i.id}/retry`, { method: "POST" });
    }
    await fetchItems();
    if (!pollRef.current) {
      pollRef.current = setInterval(fetchItems, 3000);
    }
  }

  async function deleteItem(id: string, withFiles = false) {
    await fetch(`/api/gestor/items/${id}?files=${withFiles}`, { method: "DELETE" });
    setItems((prev) => withFiles ? prev.map((i) => i.id === id ? { ...i, output_file: null } : i).filter((i) => i.id !== id) : prev.filter((i) => i.id !== id));
    if (withFiles) fetchStorage();
  }

  async function deleteItemFiles(id: string) {
    await fetch(`/api/gestor/items/${id}/delete-files`, { method: "POST" });
    setItems((prev) => prev.map((i) => i.id === id ? { ...i, output_file: null } : i));
    fetchStorage();
  }

  async function quickPublish(item: QueueItem, force = false) {
    if (quickPublishing[item.id]) return;
    if (!item.output_file || !accounts) return;
    const connectedPlatforms = PLATFORMS
      .filter((p) => (accounts[p.id as keyof AccountsStatus] as PlatformStatus | undefined)?.connected)
      .map((p) => p.id);
    if (connectedPlatforms.length === 0) return;

    setQuickPublishing((s) => ({ ...s, [item.id]: true }));
    setQuickPublishDone((s) => ({ ...s, [item.id]: false }));
    setQuickPublishWarning((s) => ({ ...s, [item.id]: "" }));
    try {
      let igCaption = "", tiktokCaption = "", xCaption = "";
      let titulo = item.titulo || item.output_file.replace(/_reel\.mp4$/, "").replace(/_/g, " ");
      let desc = "";
      try {
        const cap = await fetch(`/api/publish/caption?filename=${encodeURIComponent(item.output_file)}`).then((r) => r.json());
        igCaption     = cap.instagram || "";
        tiktokCaption = cap.tiktok || "";
        xCaption      = cap.x || "";
        titulo        = cap.hook || cap.titulo || titulo;
        desc          = cap.descripcion_youtube || "";
      } catch {}

      const res = await fetch("/api/gestor/scheduled", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          output_file:       item.output_file,
          titulo,
          descripcion:       desc,
          tiktok_caption:    tiktokCaption,
          instagram_caption: igCaption,
          x_caption:         xCaption,
          platforms:         connectedPlatforms,
          tipo_contenido:    "noticia",
          publish_at:        null,
          queue_item_id:     item.id,
          force,
        }),
      });
      if (res.status === 409) {
        const data = await res.json();
        const platforms = data.detail?.platforms ?? data.platforms ?? {};
        const names = Object.keys(platforms).join(", ");
        setQuickPublishWarning((s) => ({ ...s, [item.id]: names || "plataformas desconocidas" }));
        return;
      }
      if (!res.ok) throw new Error(await res.text());
      setQuickPublishDone((s) => ({ ...s, [item.id]: true }));
      fetchItems();
      setTimeout(() => setQuickPublishDone((s) => ({ ...s, [item.id]: false })), 4000);
    } catch {
      // fall back silently — user can use full modal
    } finally {
      setQuickPublishing((s) => ({ ...s, [item.id]: false }));
    }
  }

  const [storageStats, setStorageStats] = useState<{
    total_bytes: number; mp4_bytes: number; mp3_bytes: number; other_bytes: number;
    file_count: number; uploaded_bytes: number; pending_bytes: number;
    disk_total: number; disk_free: number; disk_used: number;
  } | null>(null);
  const [storageOpen, setStorageOpen] = useState(false);
  const [cleanupLoading, setCleanupLoading] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<{ freed_bytes: number; cleaned_items: number; orphan_bytes: number } | null>(null);

  // Archivo de noticias
  interface ArchivedItem {
    id: string; titulo: string; fuente: string; contenido: string; tipo: string;
    score_noticia: number | null; guion: string; uploads: Record<string, {url?: string; at: string}>;
    youtube_url: string; publish_platforms: string[]; creado: string; archivado: string;
    puede_regenerar: boolean;
  }
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [archiveItems, setArchiveItems] = useState<ArchivedItem[]>([]);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);

  async function fetchArchive() {
    setArchiveLoading(true);
    try {
      const r = await fetch("/api/gestor/archive");
      if (r.ok) setArchiveItems(await r.json());
    } finally {
      setArchiveLoading(false);
    }
  }

  async function runAutoCleanup(dry_run = false) {
    setCleanupLoading(true);
    try {
      const r = await fetch(`/api/storage/cleanup-auto?dry_run=${dry_run}`, { method: "POST" });
      if (r.ok) {
        const d = await r.json();
        setCleanupResult({ freed_bytes: d.freed_bytes, cleaned_items: d.archived, orphan_bytes: 0 });
        fetchStorage();
      }
    } finally {
      setCleanupLoading(false);
    }
  }

  async function regenerateArchived(id: string) {
    setRegeneratingId(id);
    try {
      const r = await fetch(`/api/gestor/archive/${id}/regenerate`, { method: "POST" });
      if (r.ok) { fetchItems(); }
    } finally {
      setRegeneratingId(null);
    }
  }

  async function fetchDistrib() {
    const r = await fetch("/api/distribucion/config");
    if (r.ok) setDistribCfg(await r.json());
  }

  async function saveDistrib(patch: Partial<DistribConfig>) {
    setDistribSaving(true);
    try {
      const base = distribCfg || { telegram_grupos: [], telegram_grupos_enabled: true, reddit_subreddits: [], reddit_enabled: false, delay_entre_posts: 8 };
      const r = await fetch("/api/distribucion/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...base, ...patch }),
      });
      if (r.ok) setDistribCfg(await r.json());
    } finally {
      setDistribSaving(false);
    }
  }

  async function testTelegramGrupo(chat_id: string) {
    setDistribTestId(chat_id);
    try {
      const r = await fetch("/api/distribucion/test/telegram", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id }),
      });
      const d = await r.json();
      alert(d.ok ? "Mensaje enviado correctamente" : `Error: ${d.error}`);
    } finally {
      setDistribTestId(null);
    }
  }

  async function fetchStorage() {
    const r = await fetch("/api/storage/stats");
    if (r.ok) setStorageStats(await r.json());
  }

  async function runCleanup(mode: string, older_than_days = 7, dry_run = false) {
    setCleanupLoading(true);
    setCleanupResult(null);
    const r = await fetch("/api/storage/cleanup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, older_than_days, dry_run }),
    });
    const data = await r.json();
    setCleanupResult(data);
    setCleanupLoading(false);
    if (!dry_run) { await fetchItems(); fetchStorage(); }
  }

  async function cancelScheduled(id: string) {
    await fetch(`/api/gestor/scheduled/${id}`, { method: "DELETE" });
    setScheduled((prev) => prev.filter((s) => s.id !== id));
  }

  async function importOrphan(filename: string, titulo: string) {
    setImportingOrphan(filename);
    try {
      const r = await fetch("/api/gestor/import-output", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename, titulo }),
      });
      if (!r.ok) throw new Error(await r.text());
      await fetchItems();
      await fetchOrphans();
    } catch (e) {
      alert(`Error importando: ${e}`);
    } finally {
      setImportingOrphan(null);
    }
  }

  const pendingCount = items.filter((i) => i.estado === "pending").length;
  const readyCount = items.filter((i) => i.estado === "ready").length;
  const selectedPendingCount = items.filter((i) => i.estado === "pending" && selectedIds.has(i.id)).length;

  // Filtro de fecha para ítems de tipo noticia
  const FECHA_FILTERS: { key: typeof fechaFilter; label: string; maxHoras: number | null }[] = [
    { key: "all",  label: "Todo",          maxHoras: null },
    { key: "1h",   label: "Última hora",   maxHoras: 1 },
    { key: "6h",   label: "Últimas 6h",    maxHoras: 6 },
    { key: "24h",  label: "Hoy",           maxHoras: 24 },
    { key: "7d",   label: "Esta semana",   maxHoras: 168 },
    { key: "30d",  label: "Este mes",      maxHoras: 720 },
  ];
  const activeFiltro = FECHA_FILTERS.find((f) => f.key === fechaFilter)!;
  const filteredItems = fechaFilter === "all" ? items : items.filter((item) => {
    if (item.tipo !== "noticia") return true;
    if (item.recencia_horas == null) return true;
    return item.recencia_horas <= (activeFiltro.maxHoras ?? Infinity);
  });
  const filteredPendingIds = filteredItems.filter((i) => i.estado === "pending").map((i) => i.id);
  const allFilteredPendingSelected = filteredPendingIds.length > 0 && filteredPendingIds.every((id) => selectedIds.has(id));

  // ¿Usará ElevenLabs con la config actual?
  const usaElevenLabs =
    prefs.servicio_voz === "elevenlabs" ||
    (prefs.servicio_voz === "auto" && ttsStatus?.elevenlabs === true);

  const unreadCount = notifs.filter((n) => !n.leido).length;

  return (
    <main style={{ maxWidth: 1200, margin: "0 auto", padding: "28px 16px 60px" }}>
      {/* ── HEADER ── */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px", color: "var(--text)" }}>
            Gestor Automatizado
          </h1>
          <p style={{ fontSize: 13, color: "var(--muted)", margin: 0 }}>
            Añade contenido, genera reels en lote y programa la publicación.
          </p>
        </div>
        {/* Botones de notificaciones */}
        <div style={{ display: "flex", gap: 8 }}>
          {/* YT Scanner */}
          {(() => {
            const ytUnread = ytStatus?.unread ?? 0;
            return (
              <button onClick={() => { setYtNotifsOpen((v) => !v); if (ytUnread > 0) markYtNotifsRead(); }}
                style={{
                  position: "relative", background: ytUnread > 0 ? "rgba(239,68,68,0.12)" : "var(--surface2)",
                  border: `1px solid ${ytUnread > 0 ? "#ef4444" : "var(--border)"}`,
                  borderRadius: 10, padding: "8px 12px", cursor: "pointer", fontSize: 16,
                  display: "flex", alignItems: "center", gap: 5,
                }}>
                <span>📺</span>
                {ytUnread > 0 && (
                  <span style={{
                    position: "absolute", top: -6, right: -6, background: "#ef4444",
                    color: "#fff", borderRadius: "50%", width: 18, height: 18,
                    fontSize: 10, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center",
                  }}>{ytUnread}</span>
                )}
              </button>
            );
          })()}
          {/* News scanner bell */}
          <button onClick={() => { setNotifsOpen((v) => !v); if (unreadCount > 0) markNotifsRead(); }}
            style={{
              position: "relative", background: unreadCount > 0 ? "rgba(99,102,241,0.12)" : "var(--surface2)",
              border: `1px solid ${unreadCount > 0 ? "var(--accent)" : "var(--border)"}`,
              borderRadius: 10, padding: "8px 12px", cursor: "pointer", fontSize: 16,
            }}>
            🔔
            {unreadCount > 0 && (
              <span style={{
                position: "absolute", top: -6, right: -6, background: "#ef4444",
                color: "#fff", borderRadius: "50%", width: 18, height: 18,
                fontSize: 10, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                {unreadCount}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* ── NOTIFICACIONES PANEL ── */}
      {notifsOpen && (
        <div style={{
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 16, padding: 20, marginBottom: 20,
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <p style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: 0 }}>
              Alertas virales ({notifs.length})
            </p>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {notifSelected.size > 0 && (
                <button
                  onClick={async () => {
                    const sel = notifs.filter((n) => notifSelected.has(n.id) && !n.auto_generado);
                    for (const n of sel) {
                      await fetch("/api/gestor/items", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ tipo: "noticia", contenido: JSON.stringify(n), titulo: n.titulo }),
                      });
                    }
                    if (sel.length) { await fetchItems(); if (!pollRef.current) pollRef.current = setInterval(fetchItems, 3000); }
                    setNotifSelected(new Set());
                  }}
                  style={{ ...btnPrimary, fontSize: 11, padding: "4px 12px" }}
                >
                  Generar seleccionadas ({notifSelected.size})
                </button>
              )}
              {notifs.length > 0 && (
                <button onClick={clearNotifs} style={{ ...btnSecondary, fontSize: 11, padding: "4px 10px" }}>
                  Limpiar
                </button>
              )}
            </div>
          </div>
          {notifs.length === 0 ? (
            <p style={{ fontSize: 13, color: "var(--muted)", textAlign: "center", padding: "16px 0" }}>
              Sin alertas. El scanner notificará cuando detecte noticias virales.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 340, overflowY: "auto" }}>
              {notifs.map((n) => {
                const isSel = notifSelected.has(n.id);
                return (
                <div key={n.id} style={{
                  padding: "11px 14px", borderRadius: 12,
                  background: isSel ? "rgba(99,102,241,0.12)" : n.leido ? "var(--surface2)" : "rgba(99,102,241,0.07)",
                  border: `1px solid ${isSel ? "var(--accent)" : n.leido ? "var(--border)" : "var(--accent)"}`,
                  opacity: n.leido && !isSel ? 0.7 : 1,
                }}>
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                    {/* Checkbox */}
                    {!n.auto_generado && (
                      <button
                        onClick={() => setNotifSelected((prev) => { const s = new Set(prev); s.has(n.id) ? s.delete(n.id) : s.add(n.id); return s; })}
                        style={{ marginTop: 2, width: 16, height: 16, borderRadius: 4, border: `1px solid ${isSel ? "var(--accent)" : "var(--border)"}`, background: isSel ? "var(--accent)" : "transparent", color: "#fff", fontSize: 10, cursor: "pointer", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}
                      >
                        {isSel ? "✓" : ""}
                      </button>
                    )}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontSize: 13, fontWeight: 600, margin: 0, color: "var(--text)", lineHeight: 1.3 }}>
                        {n.titulo}
                      </p>
                      <p style={{ fontSize: 11, color: "var(--muted)", margin: "3px 0 0" }}>
                        {n.fuente} · score {n.score.toFixed(1)} · {fmtDate(n.creado)}
                        {n.verificadores?.length ? ` · contrastada por ${n.verificadores.join(", ")}` : ""}
                        {n.gancho && <span style={{ color: "var(--accent)", marginLeft: 6 }}>{n.gancho}</span>}
                      </p>
                      {n.documentacion && (
                        <p style={{ fontSize: 11, color: "var(--text)", opacity: 0.75, margin: "2px 0 0" }}>{n.documentacion}</p>
                      )}
                      {n.auto_generado && n.item_id && (
                        <button
                          onClick={() => {
                            setNotifsOpen(false);
                            setHighlightedItemId(n.item_id);
                            setTimeout(() => {
                              document.getElementById(`queue-item-${n.item_id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
                            }, 100);
                            setTimeout(() => setHighlightedItemId(null), 2500);
                          }}
                          style={{ background: "none", border: "none", padding: 0, cursor: "pointer", fontSize: 11, color: "#4ade80", margin: "2px 0 0", display: "block", textAlign: "left" }}
                        >
                          En cola → ver en gestor ↓
                        </button>
                      )}
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 5, flexShrink: 0 }}>
                      <span style={{
                        fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 5,
                        background: n.score >= 8.5 ? "#0a2010" : "#1a1a2e",
                        color: n.score >= 8.5 ? "#4ade80" : "#c084fc",
                      }}>
                        {n.score >= 8.5 ? "Viral" : "Alto"}
                      </span>
                      {!n.auto_generado && (
                        <button
                          onClick={async () => {
                            await fetch("/api/gestor/items", {
                              method: "POST",
                              headers: { "Content-Type": "application/json" },
                              body: JSON.stringify({ tipo: "noticia", contenido: JSON.stringify(n), titulo: n.titulo }),
                            });
                            await fetchItems();
                            if (!pollRef.current) pollRef.current = setInterval(fetchItems, 3000);
                          }}
                          style={{ ...btnPrimary, fontSize: 11, padding: "3px 10px" }}
                        >
                          Generar
                        </button>
                      )}
                    </div>
                  </div>
                </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── YT NOTIFICACIONES PANEL ── */}
      {ytNotifsOpen && (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 16, padding: 20, marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <p style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: 0 }}>
              Tendencias YouTube ({ytNotifs.length})
            </p>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {ytNotifSelected.size > 0 && (
                <button
                  onClick={async () => {
                    const sel = ytNotifs.filter((n) => ytNotifSelected.has(n.id) && !n.auto_generado);
                    for (const n of sel) {
                      await fetch("/api/gestor/items", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ tipo: "url", contenido: n.url, titulo: n.titulo }),
                      });
                    }
                    if (sel.length) { await fetchItems(); if (!pollRef.current) pollRef.current = setInterval(fetchItems, 3000); }
                    setYtNotifSelected(new Set());
                  }}
                  style={{ ...btnPrimary, fontSize: 11, padding: "4px 12px" }}
                >
                  Generar seleccionadas ({ytNotifSelected.size})
                </button>
              )}
              {ytNotifs.length > 0 && (
                <button onClick={clearYtNotifs} style={{ ...btnSecondary, fontSize: 11, padding: "4px 10px" }}>Limpiar</button>
              )}
            </div>
          </div>
          {ytNotifs.length === 0 ? (
            <p style={{ fontSize: 13, color: "var(--muted)", textAlign: "center", padding: "16px 0" }}>
              Sin tendencias. Activa el scanner de YouTube y lanza un escaneo.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, maxHeight: 420, overflowY: "auto" }}>
              {ytNotifs.map((n) => {
                const isSel = ytNotifSelected.has(n.id);
                return (
                <div key={n.id} style={{
                  display: "flex", gap: 12, padding: "11px 14px", borderRadius: 12,
                  background: isSel ? "rgba(239,68,68,0.10)" : n.leido ? "var(--surface2)" : "rgba(239,68,68,0.06)",
                  border: `1px solid ${isSel ? "#ef4444" : n.leido ? "var(--border)" : "#ef444440"}`,
                  opacity: n.leido && !isSel ? 0.75 : 1,
                }}>
                  {/* Checkbox */}
                  {!n.auto_generado && (
                    <button
                      onClick={() => setYtNotifSelected((prev) => { const s = new Set(prev); s.has(n.id) ? s.delete(n.id) : s.add(n.id); return s; })}
                      style={{ marginTop: 2, width: 16, height: 16, borderRadius: 4, border: `1px solid ${isSel ? "#ef4444" : "var(--border)"}`, background: isSel ? "#ef4444" : "transparent", color: "#fff", fontSize: 10, cursor: "pointer", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", alignSelf: "center" }}
                    >
                      {isSel ? "✓" : ""}
                    </button>
                  )}
                  {/* Thumbnail */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={n.thumbnail} alt="" style={{ width: 88, height: 50, borderRadius: 6, objectFit: "cover", flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontSize: 13, fontWeight: 600, margin: 0, color: "var(--text)", lineHeight: 1.3 }}>{n.titulo}</p>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
                      <span style={{ fontSize: 10, fontWeight: 700, padding: "1px 7px", borderRadius: 4, background: n.nicho_color + "22", color: n.nicho_color }}>
                        {n.nicho_emoji} {n.nicho_nombre}
                      </span>
                      <span style={{ fontSize: 11, color: "var(--muted)" }}>{n.canal}</span>
                      <span style={{ fontSize: 11, color: "var(--muted)" }}>· {n.views_fmt} vistas</span>
                      <span style={{ fontSize: 11, fontWeight: 700, padding: "1px 7px", borderRadius: 4,
                        background: n.score >= 8 ? "#0a2010" : "#1a1a2e",
                        color: n.score >= 8 ? "#4ade80" : "#c084fc" }}>
                        {n.score.toFixed(1)} {n.score >= 8 ? "Viral" : "Alto"}
                      </span>
                    </div>
                    {n.auto_generado && n.item_id && (
                      <button
                        onClick={() => {
                          setYtNotifsOpen(false);
                          setHighlightedItemId(n.item_id);
                          setTimeout(() => {
                            document.getElementById(`queue-item-${n.item_id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
                          }, 100);
                          setTimeout(() => setHighlightedItemId(null), 2500);
                        }}
                        style={{ background: "none", border: "none", padding: 0, cursor: "pointer", fontSize: 11, color: "#4ade80", margin: "3px 0 0", display: "block", textAlign: "left" }}
                      >
                        En cola → ver en gestor ↓
                      </button>
                    )}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 5, flexShrink: 0, alignItems: "flex-end" }}>
                    {!n.auto_generado && (
                      <button
                        onClick={async () => {
                          await fetch("/api/gestor/items", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ tipo: "url", contenido: n.url, titulo: n.titulo }),
                          });
                          await fetchItems();
                          if (!pollRef.current) pollRef.current = setInterval(fetchItems, 3000);
                        }}
                        style={{ ...btnPrimary, fontSize: 11, padding: "3px 10px" }}
                      >
                        Generar
                      </button>
                    )}
                    <a href={n.url} target="_blank" rel="noopener noreferrer"
                      style={{ fontSize: 10, color: "var(--muted)", textDecoration: "none" }}>
                      Ver ▶
                    </a>
                  </div>
                </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── YT SCANNER CONFIG ── */}
      <div style={{
        background: "var(--surface)", border: `1px solid ${ytConfig.enabled ? "rgba(239,68,68,0.4)" : "var(--border)"}`,
        borderRadius: 16, marginBottom: 20, overflow: "hidden",
      }}>
        <button onClick={() => setYtOpen((v) => !v)}
          style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 20px", background: "none", border: "none", cursor: "pointer" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 15 }}>📺</span>
            <p style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: 0 }}>
              Tendencias YouTube por nicho
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {ytStatus?.running && <span style={{ fontSize: 11, color: "#60a5fa", fontWeight: 700 }}>Escaneando…</span>}
            {ytStatus?.last_error && <span style={{ fontSize: 11, color: "var(--error)", fontWeight: 700 }}>Error</span>}
            <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 5,
              background: ytConfig.enabled ? "rgba(239,68,68,0.15)" : "var(--surface2)",
              color: ytConfig.enabled ? "#f87171" : "var(--muted)" }}>
              {ytConfig.enabled ? "Activo" : "Inactivo"}
            </span>
            {(ytStatus?.unread ?? 0) > 0 && !ytNotifsOpen && (
              <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 5, background: "rgba(239,68,68,0.15)", color: "#f87171" }}>
                {ytStatus!.unread} nuevas
              </span>
            )}
            <span style={{ color: "var(--muted)", fontSize: 13 }}>{ytOpen ? "▲" : "▼"}</span>
          </div>
        </button>

        {ytOpen && (
          <div style={{ borderTop: "1px solid var(--border)", padding: "18px 20px", display: "flex", flexDirection: "column", gap: 16 }}>

            {/* Enable + run now */}
            <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <input type="checkbox" checked={ytConfig.enabled}
                  onChange={(e) => { const c = { ...ytConfig, enabled: e.target.checked }; setYtConfig(c); saveYtConfig(c); }}
                  style={{ accentColor: "#ef4444", width: 16, height: 16 }} />
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>Activar scanner diario</span>
              </label>
              <button onClick={runYtScannerNow} disabled={ytRunning || ytStatus?.running}
                style={{ ...btnSecondary, fontSize: 12, padding: "5px 14px", opacity: (ytRunning || ytStatus?.running) ? 0.5 : 1 }}>
                {ytStatus?.running ? "Escaneando…" : "Escanear ahora"}
              </button>
              {ytStatus?.last_run && (
                <span style={{ fontSize: 11, color: "var(--muted)" }}>
                  Último: {fmtDate(ytStatus.last_run)}
                  {ytStatus.next_run && ` · Próximo: ${fmtDate(ytStatus.next_run)}`}
                </span>
              )}
            </div>

            {/* Nichos */}
            <div>
              <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: "0 0 8px" }}>
                Nichos a monitorizar
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {Object.entries(ytNichos).map(([id, meta]) => {
                  const active = ytConfig.nichos_activos.includes(id);
                  return (
                    <label key={id} style={{
                      display: "flex", alignItems: "center", gap: 6,
                      padding: "6px 12px", borderRadius: 8, cursor: "pointer",
                      background: active ? meta.color + "18" : "var(--surface2)",
                      border: `1px solid ${active ? meta.color + "60" : "var(--border)"}`,
                    }}>
                      <input type="checkbox" checked={active} style={{ accentColor: meta.color }}
                        onChange={(e) => {
                          const next = e.target.checked
                            ? [...ytConfig.nichos_activos, id]
                            : ytConfig.nichos_activos.filter((x) => x !== id);
                          setYtConfig((c) => ({ ...c, nichos_activos: next }));
                        }} />
                      <span style={{ fontSize: 12, fontWeight: 600, color: active ? meta.color : "var(--muted)" }}>
                        {meta.emoji} {meta.nombre}
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Sliders */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              {[
                { label: "Cada cuántas horas", key: "interval_hours" as const, min: 6, max: 168, step: 6, unit: "h" },
                { label: "Vídeos por nicho", key: "n_por_nicho" as const, min: 1, max: 10, step: 1, unit: "" },
                { label: "Score mínimo", key: "score_min" as const, min: 4, max: 9, step: 0.5, unit: "" },
                { label: "Antigüedad máx (días)", key: "max_age_days" as const, min: 1, max: 14, step: 1, unit: "d" },
              ].map(({ label, key, min, max, step, unit }) => (
                <div key={key}>
                  <p style={{ fontSize: 11, color: "var(--muted)", margin: "0 0 4px" }}>
                    {label}: <strong style={{ color: "var(--text)" }}>{ytConfig[key]}{unit}</strong>
                  </p>
                  <input type="range" min={min} max={max} step={step}
                    value={ytConfig[key] as number}
                    onChange={(e) => setYtConfig((c) => ({ ...c, [key]: Number(e.target.value) }))}
                    style={{ width: "100%", accentColor: "#ef4444" }} />
                </div>
              ))}
            </div>

            {/* Min views */}
            <div>
              <p style={{ fontSize: 11, color: "var(--muted)", margin: "0 0 4px" }}>
                Vistas mínimas: <strong style={{ color: "var(--text)" }}>
                  {ytConfig.min_views >= 1_000_000 ? `${(ytConfig.min_views / 1_000_000).toFixed(1)}M` : `${(ytConfig.min_views / 1_000).toFixed(0)}K`}
                </strong>
              </p>
              <input type="range" min={10000} max={5000000} step={10000}
                value={ytConfig.min_views}
                onChange={(e) => setYtConfig((c) => ({ ...c, min_views: Number(e.target.value) }))}
                style={{ width: "100%", accentColor: "#ef4444" }} />
            </div>

            {/* Auto generate + auto publish */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <label style={{
                display: "flex", alignItems: "center", gap: 7, padding: "6px 12px", borderRadius: 8, cursor: "pointer",
                background: ytConfig.auto_generate ? "rgba(239,68,68,0.1)" : "var(--surface2)",
                border: `1px solid ${ytConfig.auto_generate ? "#ef4444" : "var(--border)"}`,
              }}>
                <input type="checkbox" checked={ytConfig.auto_generate}
                  onChange={(e) => setYtConfig((c) => ({ ...c, auto_generate: e.target.checked }))}
                  style={{ accentColor: "#ef4444" }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: ytConfig.auto_generate ? "#ef4444" : "var(--muted)" }}>
                  Auto-generar shorts
                </span>
              </label>
              <label style={{
                display: "flex", alignItems: "center", gap: 7, padding: "6px 12px", borderRadius: 8, cursor: "pointer",
                background: ytConfig.auto_publish ? "rgba(239,68,68,0.1)" : "var(--surface2)",
                border: `1px solid ${ytConfig.auto_publish ? "#ef4444" : "var(--border)"}`,
              }}>
                <input type="checkbox" checked={ytConfig.auto_publish}
                  onChange={(e) => setYtConfig((c) => ({ ...c, auto_publish: e.target.checked }))}
                  style={{ accentColor: "#ef4444" }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: ytConfig.auto_publish ? "#ef4444" : "var(--muted)" }}>
                  Auto-publicar tras generar
                </span>
              </label>
            </div>

            {ytConfig.auto_publish && (
              <div>
                <p style={{ fontSize: 11, color: "var(--muted)", margin: "0 0 6px" }}>Publicar automáticamente en</p>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {PLATFORMS.map((p) => {
                    const sel = (ytConfig.publish_platforms || []).includes(p.id);
                    return (
                      <label key={p.id} style={{
                        display: "flex", alignItems: "center", gap: 6, padding: "5px 10px",
                        borderRadius: 8, cursor: "pointer",
                        background: sel ? "rgba(239,68,68,0.1)" : "var(--surface2)",
                        border: `1px solid ${sel ? "#ef4444" : "var(--border)"}`,
                      }}>
                        <input type="checkbox" checked={sel}
                          onChange={() => setYtConfig((c) => ({
                            ...c,
                            publish_platforms: sel
                              ? (c.publish_platforms || []).filter((x) => x !== p.id)
                              : [...(c.publish_platforms || []), p.id],
                          }))}
                          style={{ accentColor: "#ef4444" }} />
                        <span style={{ fontSize: 12, fontWeight: 600, color: sel ? "#ef4444" : "var(--muted)" }}>
                          {p.icon} {p.label}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Save */}
            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={() => saveYtConfig(ytConfig)} disabled={ytSaving}
                style={{ ...btnPrimary, opacity: ytSaving ? 0.6 : 1, background: "#ef4444" }}>
                {ytSaving ? "Guardando…" : "Guardar configuración"}
              </button>
            </div>

            {ytStatus?.last_error && (
              <p style={{ fontSize: 12, color: "var(--error)", background: "#2a0a0a", padding: "8px 12px", borderRadius: 8, margin: 0 }}>
                Error: {ytStatus.last_error}
              </p>
            )}
          </div>
        )}
      </div>

      {/* ── SCANNER ── */}
      <div style={{
        background: "var(--surface)", border: `1px solid ${scannerConfig.enabled ? "rgba(99,102,241,0.4)" : "var(--border)"}`,
        borderRadius: 16, marginBottom: 20, overflow: "hidden",
      }}>
        <button
          onClick={() => setScannerOpen((v) => !v)}
          style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 20px", background: "none", border: "none", cursor: "pointer" }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 15 }}>📡</span>
            <p style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: 0 }}>
              Scanner de noticias virales
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {scannerStatus?.running && (
              <span style={{ fontSize: 11, color: "#60a5fa", fontWeight: 700 }}>Escaneando…</span>
            )}
            {scannerStatus?.last_error && (
              <span style={{ fontSize: 11, color: "var(--error)", fontWeight: 700 }}>Error</span>
            )}
            <span style={{
              fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 5,
              background: scannerConfig.enabled ? "rgba(74,222,128,0.15)" : "var(--surface2)",
              color: scannerConfig.enabled ? "#4ade80" : "var(--muted)",
            }}>
              {scannerConfig.enabled ? "Activo" : "Inactivo"}
            </span>
            {unreadCount > 0 && !notifsOpen && (
              <span style={{
                fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 5,
                background: "rgba(99,102,241,0.15)", color: "var(--accent)",
              }}>
                {unreadCount} nuevas
              </span>
            )}
            <span style={{ color: "var(--muted)", fontSize: 13 }}>{scannerOpen ? "▲" : "▼"}</span>
          </div>
        </button>

        {scannerOpen && (
          <div style={{ padding: "0 20px 20px", borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 14 }}>

            {/* Estado */}
            {(scannerStatus?.last_run || scannerStatus?.next_run || scannerStatus?.last_error) && (
              <div style={{ display: "flex", gap: 16, marginTop: 14, flexWrap: "wrap" }}>
                {scannerStatus.last_run && (
                  <div>
                    <Label>Último escaneo</Label>
                    <p style={{ fontSize: 12, color: "var(--text)", margin: 0 }}>{fmtDate(scannerStatus.last_run)}</p>
                  </div>
                )}
                {scannerStatus.next_run && scannerConfig.enabled && (
                  <div>
                    <Label>Próximo escaneo</Label>
                    <p style={{ fontSize: 12, color: "var(--text)", margin: 0 }}>{fmtDate(scannerStatus.next_run)}</p>
                  </div>
                )}
                {scannerStatus.last_error && (
                  <div style={{ flex: 1 }}>
                    <Label>Último error</Label>
                    <p style={{ fontSize: 11, color: "var(--error)", margin: 0 }}>{scannerStatus.last_error.slice(0, 120)}</p>
                  </div>
                )}
              </div>
            )}

            {/* Enable/disable + intervalo */}
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr 1fr", gap: 10, alignItems: "end", marginTop: scannerStatus?.last_run ? 0 : 14 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <input type="checkbox" checked={scannerConfig.enabled}
                  onChange={(e) => setScannerConfig({ ...scannerConfig, enabled: e.target.checked })}
                  style={{ accentColor: "var(--accent)", width: 16, height: 16 }} />
                <span style={{ fontSize: 13, fontWeight: 700, color: scannerConfig.enabled ? "#4ade80" : "var(--muted)" }}>
                  {scannerConfig.enabled ? "Activo" : "Inactivo"}
                </span>
              </label>
              <div>
                <Label>Intervalo: {scannerConfig.interval_min}min</Label>
                <input type="range" min={10} max={120} step={5} value={scannerConfig.interval_min}
                  onChange={(e) => setScannerConfig({ ...scannerConfig, interval_min: Number(e.target.value) })}
                  style={{ width: "100%", accentColor: "var(--accent)" }} />
              </div>
              <div>
                <Label>Score mínimo: {scannerConfig.score_min}</Label>
                <input type="range" min={5} max={9.5} step={0.5} value={scannerConfig.score_min}
                  onChange={(e) => setScannerConfig({ ...scannerConfig, score_min: Number(e.target.value) })}
                  style={{ width: "100%", accentColor: "var(--accent)" }} />
              </div>
            </div>

            {/* Noticias por scan + país */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div>
                <Label>Noticias por escaneo: {scannerConfig.n_noticias}</Label>
                <input type="range" min={1} max={10} step={1} value={scannerConfig.n_noticias}
                  onChange={(e) => setScannerConfig({ ...scannerConfig, n_noticias: Number(e.target.value) })}
                  style={{ width: "100%", accentColor: "var(--accent)" }} />
              </div>
              <div>
                <Label>País</Label>
                <select value={scannerConfig.pais}
                  onChange={(e) => setScannerConfig({ ...scannerConfig, pais: e.target.value })}
                  style={inputStyle}>
                  <option value="ES">España (ES)</option>
                  <option value="MX">México (MX)</option>
                  <option value="AR">Argentina (AR)</option>
                  <option value="US">Global (US)</option>
                  <option value="LATAM">Latinoamérica</option>
                </select>
              </div>
            </div>

            {/* Auto-generate + auto-publish */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <label style={{
                display: "flex", alignItems: "center", gap: 7, padding: "6px 12px", borderRadius: 8, cursor: "pointer",
                background: scannerConfig.auto_generate ? "rgba(99,102,241,0.1)" : "var(--surface2)",
                border: `1px solid ${scannerConfig.auto_generate ? "var(--accent)" : "var(--border)"}`,
              }}>
                <input type="checkbox" checked={scannerConfig.auto_generate}
                  onChange={(e) => setScannerConfig({ ...scannerConfig, auto_generate: e.target.checked })}
                  style={{ accentColor: "var(--accent)" }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: scannerConfig.auto_generate ? "var(--accent)" : "var(--muted)" }}>
                  Auto-generar reels
                </span>
              </label>
              <label style={{
                display: "flex", alignItems: "center", gap: 7, padding: "6px 12px", borderRadius: 8, cursor: "pointer",
                background: scannerConfig.auto_publish ? "rgba(99,102,241,0.1)" : "var(--surface2)",
                border: `1px solid ${scannerConfig.auto_publish ? "var(--accent)" : "var(--border)"}`,
              }}>
                <input type="checkbox" checked={scannerConfig.auto_publish}
                  onChange={(e) => setScannerConfig({ ...scannerConfig, auto_publish: e.target.checked })}
                  style={{ accentColor: "var(--accent)" }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: scannerConfig.auto_publish ? "var(--accent)" : "var(--muted)" }}>
                  Auto-publicar tras generar
                </span>
              </label>
            </div>

            {/* Plataformas si auto-publish */}
            {scannerConfig.auto_publish && (
              <div>
                <Label>Publicar automáticamente en</Label>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {PLATFORMS.map((p) => {
                    const sel = scannerConfig.publish_platforms.includes(p.id);
                    return (
                      <label key={p.id} style={{
                        display: "flex", alignItems: "center", gap: 6, padding: "5px 10px",
                        borderRadius: 8, cursor: "pointer",
                        background: sel ? "rgba(99,102,241,0.1)" : "var(--surface2)",
                        border: `1px solid ${sel ? "var(--accent)" : "var(--border)"}`,
                      }}>
                        <input type="checkbox" checked={sel}
                          onChange={() => setScannerConfig({
                            ...scannerConfig,
                            publish_platforms: sel
                              ? scannerConfig.publish_platforms.filter((x) => x !== p.id)
                              : [...scannerConfig.publish_platforms, p.id],
                          })}
                          style={{ accentColor: "var(--accent)" }} />
                        <span style={{ fontSize: 12, fontWeight: 600, color: sel ? "var(--accent)" : "var(--muted)" }}>
                          {p.icon} {p.label}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Botones */}
            <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
              <button onClick={() => saveScannerConfig(scannerConfig)} disabled={scannerSaving} style={{
                ...btnPrimary, opacity: scannerSaving ? 0.6 : 1,
              }}>
                {scannerSaving ? "Guardando…" : "Guardar"}
              </button>
              <button onClick={runScannerNow} disabled={scannerRunning || scannerStatus?.running} style={{
                ...btnSecondary,
                opacity: (scannerRunning || scannerStatus?.running) ? 0.6 : 1,
                cursor: (scannerRunning || scannerStatus?.running) ? "not-allowed" : "pointer",
              }}>
                {scannerStatus?.running ? "Escaneando…" : "Escanear ahora"}
              </button>
            </div>

          </div>
        )}
      </div>

      {/* ── AUTOPUBLICADOR ── */}
      {autoPubStatus && (
        <div style={{
          background: "var(--surface)",
          border: `1px solid ${autoPubStatus.enabled ? "rgba(251,146,60,0.4)" : "var(--border)"}`,
          borderRadius: 16, marginBottom: 20, overflow: "hidden",
        }}>
          <button
            onClick={() => setAutoPubOpen((v) => !v)}
            style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 20px", background: "none", border: "none", cursor: "pointer" }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 15 }}>🤖</span>
              <p style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: 0 }}>
                Autopublicador
              </p>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {autoPubStatus.publishing && (
                <span style={{ fontSize: 11, color: "#fb923c", fontWeight: 700 }}>Publicando…</span>
              )}
              <span style={{
                fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 5,
                background: autoPubStatus.enabled ? (autoPubStatus.paused ? "rgba(251,191,36,0.15)" : "rgba(251,146,60,0.15)") : "var(--surface2)",
                color: autoPubStatus.enabled ? (autoPubStatus.paused ? "#fbbf24" : "#fb923c") : "var(--muted)",
              }}>
                {autoPubStatus.enabled ? (autoPubStatus.paused ? "Pausado" : "Activo") : "Inactivo"}
              </span>
              <span style={{
                fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 5,
                background: "rgba(251,146,60,0.1)", color: "#fb923c",
              }}>
                {autoPubStatus.published_today}/{autoPubStatus.daily_limit} hoy
              </span>
              <span style={{ color: "var(--muted)", fontSize: 13 }}>{autoPubOpen ? "▲" : "▼"}</span>
            </div>
          </button>

          {autoPubOpen && (
            <div style={{ padding: "0 20px 20px", borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 14 }}>

              {/* Barra de progreso diaria */}
              <div style={{ marginTop: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <Label>Publicados hoy</Label>
                  <span style={{ fontSize: 12, color: "var(--text)" }}>
                    {autoPubStatus.published_today} / {autoPubStatus.daily_limit}
                  </span>
                </div>
                <div style={{ height: 6, background: "var(--surface2)", borderRadius: 3, overflow: "hidden" }}>
                  <div style={{
                    height: "100%", borderRadius: 3,
                    width: `${Math.min(100, (autoPubStatus.published_today / autoPubStatus.daily_limit) * 100)}%`,
                    background: autoPubStatus.published_today >= autoPubStatus.daily_limit ? "#f87171" : "#fb923c",
                    transition: "width 0.3s",
                  }} />
                </div>
              </div>

              {/* Cola */}
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                <div>
                  <Label>En cola</Label>
                  <p style={{ fontSize: 13, color: "var(--text)", margin: 0, fontWeight: 700 }}>{autoPubStatus.queue_size} reels</p>
                </div>
                {autoPubStatus.minutes_until_next !== null && (
                  <div>
                    <Label>Próxima publicación</Label>
                    <p style={{ fontSize: 12, color: "var(--text)", margin: 0 }}>
                      {autoPubStatus.minutes_until_next === 0 ? "Ahora" : `en ${autoPubStatus.minutes_until_next} min`}
                    </p>
                  </div>
                )}
                {autoPubStatus.last_publish_at && (
                  <div>
                    <Label>Última publicación</Label>
                    <p style={{ fontSize: 12, color: "var(--text)", margin: 0 }}>{fmtDate(autoPubStatus.last_publish_at)}</p>
                  </div>
                )}
              </div>

              {/* Próximos en cola */}
              {autoPubStatus.queue.length > 0 && (
                <div>
                  <Label>Próximos en cola (por viralidad)</Label>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 4 }}>
                    {autoPubStatus.queue.map((q, i) => (
                      <div key={q.item_id} style={{
                        display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
                        background: "var(--surface2)", borderRadius: 8, fontSize: 12,
                      }}>
                        <span style={{ color: "#fb923c", fontWeight: 700, minWidth: 28 }}>⭐{q.score.toFixed(1)}</span>
                        <span style={{ flex: 1, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{q.titulo}</span>
                        <button
                          onClick={async () => {
                            await fetch(`/api/autopublisher/queue/${q.item_id}`, { method: "DELETE" });
                            fetchAutoPub();
                          }}
                          style={{ background: "none", border: "none", cursor: "pointer", color: "var(--muted)", fontSize: 12, padding: 0 }}
                        >✕</button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Controles */}
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <label style={{
                  display: "flex", alignItems: "center", gap: 7, padding: "6px 12px", borderRadius: 8, cursor: "pointer",
                  background: autoPubStatus.enabled ? "rgba(251,146,60,0.1)" : "var(--surface2)",
                  border: `1px solid ${autoPubStatus.enabled ? "#fb923c" : "var(--border)"}`,
                }}>
                  <input type="checkbox" checked={autoPubStatus.enabled}
                    onChange={async (e) => {
                      await fetch("/api/autopublisher/config", {
                        method: "POST", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ enabled: e.target.checked }),
                      });
                      fetchAutoPub();
                    }}
                    style={{ accentColor: "#fb923c" }} />
                  <span style={{ fontSize: 12, fontWeight: 600, color: autoPubStatus.enabled ? "#fb923c" : "var(--muted)" }}>
                    Activar autopublicador
                  </span>
                </label>

                {autoPubStatus.enabled && (
                  <button
                    onClick={async () => {
                      await fetch("/api/autopublisher/config", {
                        method: "POST", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ paused: !autoPubStatus.paused }),
                      });
                      fetchAutoPub();
                    }}
                    style={{
                      padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600,
                      cursor: "pointer", border: "1px solid var(--border)",
                      background: autoPubStatus.paused ? "rgba(74,222,128,0.1)" : "rgba(248,113,113,0.1)",
                      color: autoPubStatus.paused ? "#4ade80" : "#f87171",
                    }}
                  >
                    {autoPubStatus.paused ? "▶ Reanudar" : "⏸ Pausar"}
                  </button>
                )}

                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Label>Máx/día:</Label>
                  <input
                    type="number" min={1} max={50} value={autoPubStatus.daily_limit}
                    onChange={async (e) => {
                      const v = parseInt(e.target.value);
                      if (v >= 1 && v <= 50) {
                        await fetch("/api/autopublisher/config", {
                          method: "POST", headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ daily_limit: v }),
                        });
                        fetchAutoPub();
                      }
                    }}
                    style={{ ...inputStyle, width: 60, padding: "4px 8px" }}
                  />
                </div>
              </div>

            </div>
          )}
        </div>
      )}

      {/* ── AÑADIR ── */}
      <Section title="Añadir contenido">
        <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
          {(["url", "texto", "descubrir", "subir"] as AddMode[]).map((m) => (
            <button key={m} onClick={() => setAddMode(m)} style={{
              padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600,
              cursor: "pointer",
              border: `1px solid ${addMode === m ? "var(--accent)" : "var(--border)"}`,
              background: addMode === m ? "rgba(99,102,241,0.12)" : "var(--surface2)",
              color: addMode === m ? "var(--accent)" : "var(--muted)",
            }}>
              {m === "url" ? "URL" : m === "texto" ? "Texto manual" : m === "descubrir" ? "Descubrir" : "Subir video"}
            </button>
          ))}
        </div>

        {addMode === "url" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input value={tituloInput} onChange={(e) => setTituloInput(e.target.value)}
              placeholder="Título (opcional)" style={inputStyle} />
            <div style={{ display: "flex", gap: 8 }}>
              <input value={urlInput} onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAdd()}
                placeholder="https://…" style={{ ...inputStyle, flex: 1 }} />
              <button onClick={handleAdd} disabled={adding || !urlInput.trim()} style={{
                ...btnPrimary, padding: "0 18px", flexShrink: 0,
                opacity: adding || !urlInput.trim() ? 0.5 : 1,
              }}>
                {adding ? "…" : "Añadir"}
              </button>
            </div>
          </div>
        )}

        {addMode === "texto" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input value={tituloInput} onChange={(e) => setTituloInput(e.target.value)}
              placeholder="Título" style={inputStyle} />
            <textarea value={textoInput} onChange={(e) => setTextoInput(e.target.value)}
              placeholder="Pega el texto de la noticia o curiosidad…" rows={4}
              style={{ ...inputStyle, resize: "vertical" }} />
            <button onClick={handleAdd} disabled={adding || !textoInput.trim()} style={{
              ...btnPrimary, alignSelf: "flex-end", padding: "8px 20px",
              opacity: adding || !textoInput.trim() ? 0.5 : 1,
            }}>
              {adding ? "…" : "Añadir a cola"}
            </button>
          </div>
        )}

        {addMode === "descubrir" && (
          <DiscoverMini onAdd={addNoticia} />
        )}

        {addMode === "subir" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input
              value={uploadTitulo}
              onChange={(e) => setUploadTitulo(e.target.value)}
              placeholder="Título (opcional)"
              style={inputStyle}
            />
            <label style={{
              display: "flex", alignItems: "center", gap: 10, padding: "12px 14px",
              borderRadius: 10, border: `2px dashed ${uploadFile ? "var(--accent)" : "var(--border)"}`,
              cursor: "pointer", background: "var(--surface2)",
            }}>
              <input
                type="file"
                accept="video/mp4,video/*"
                style={{ display: "none" }}
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null;
                  setUploadFile(f);
                  setUploadError("");
                  if (f && !uploadTitulo.trim()) {
                    setUploadTitulo(f.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " "));
                  }
                }}
              />
              <span style={{ fontSize: 20 }}>🎬</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                {uploadFile ? (
                  <>
                    <p style={{ fontSize: 13, fontWeight: 600, margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {uploadFile.name}
                    </p>
                    <p style={{ fontSize: 11, color: "var(--muted)", margin: "2px 0 0" }}>
                      {(uploadFile.size / 1024 / 1024).toFixed(1)} MB
                    </p>
                  </>
                ) : (
                  <p style={{ fontSize: 13, color: "var(--muted)", margin: 0 }}>
                    Haz clic para seleccionar un .mp4
                  </p>
                )}
              </div>
              {uploadFile && (
                <span
                  style={{ fontSize: 16, color: "var(--muted)", cursor: "pointer", flexShrink: 0 }}
                  onClick={(e) => { e.preventDefault(); setUploadFile(null); setUploadError(""); }}
                >✕</span>
              )}
            </label>
            {uploadError && (
              <p style={{ fontSize: 12, color: "var(--error)", margin: 0 }}>{uploadError}</p>
            )}
            <button
              onClick={uploadVideo}
              disabled={uploading || !uploadFile}
              style={{
                ...btnPrimary, alignSelf: "flex-end", padding: "8px 20px",
                opacity: uploading || !uploadFile ? 0.5 : 1,
                cursor: uploading || !uploadFile ? "not-allowed" : "pointer",
              }}
            >
              {uploading ? "Subiendo…" : "Añadir a cola"}
            </button>
          </div>
        )}
      </Section>

      {/* ── PREFERENCIAS ── */}
      <div style={{
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 16, marginBottom: 20, overflow: "hidden",
      }}>
        <button
          onClick={() => {
            setPrefsOpen((v) => !v);
            fetch("/api/music").then((r) => r.json()).then((d) => setMusicTracks(Array.isArray(d) ? d : [])).catch(() => {});
          }}
          style={{
            width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "14px 20px", background: "none", border: "none", cursor: "pointer",
          }}
        >
          <p style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: 0 }}>
            Preferencias de generación
          </p>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 11, color: "var(--muted)" }}>
              {prefs.voz || "auto"} · {prefs.tipo_contenido} · {prefs.duracion_maxima}s
            </span>
            {usaElevenLabs && (
              <span style={{ fontSize: 11, fontWeight: 700, color: "#fb923c", background: "#2a1800", padding: "2px 7px", borderRadius: 5 }}>
                ⚠ ElevenLabs (de pago)
              </span>
            )}
            {prefsToast && (
              <span style={{ fontSize: 11, color: prefsToast === "Guardado" ? "var(--success)" : "var(--error)", fontWeight: 700 }}>
                {prefsToast}
              </span>
            )}
            <span style={{ color: "var(--muted)", fontSize: 13 }}>{prefsOpen ? "▲" : "▼"}</span>
          </div>
        </button>

        {prefsOpen && (
          <div style={{ padding: "0 20px 20px", borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 14 }}>

            {/* Voz */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 10, marginTop: 14 }}>
              <div>
                <Label>Servicio de voz</Label>
                <select value={prefs.servicio_voz} onChange={(e) => setPrefs({ ...prefs, servicio_voz: e.target.value })}
                  style={inputStyle}>
                  <option value="edge-tts">Edge TTS (gratis)</option>
                  <option value="elevenlabs">ElevenLabs (de pago)</option>
                  <option value="auto">Auto (ElevenLabs si hay key)</option>
                </select>
              </div>
              <div>
                <Label>Voz en español</Label>
                {prefs.servicio_voz === "elevenlabs" ? (
                  <input value={prefs.voz} onChange={(e) => setPrefs({ ...prefs, voz: e.target.value })}
                    placeholder="voice_id de ElevenLabs"
                    style={inputStyle} />
                ) : (
                  <select value={prefs.voz} onChange={(e) => setPrefs({ ...prefs, voz: e.target.value })}
                    style={inputStyle}>
                    <optgroup label="España">
                      <option value="es-ES-AlvaroNeural">Álvaro — España (hombre)</option>
                      <option value="es-ES-ElviraNeural">Elvira — España (mujer)</option>
                      <option value="es-ES-XimenaNeural">Ximena — España (mujer)</option>
                    </optgroup>
                    <optgroup label="México">
                      <option value="es-MX-JorgeNeural">Jorge — México (hombre)</option>
                      <option value="es-MX-DaliaNeural">Dalia — México (mujer)</option>
                    </optgroup>
                    <optgroup label="Argentina">
                      <option value="es-AR-TomasNeural">Tomás — Argentina (hombre)</option>
                      <option value="es-AR-ElenaNeural">Elena — Argentina (mujer)</option>
                    </optgroup>
                    <optgroup label="Colombia">
                      <option value="es-CO-GonzaloNeural">Gonzalo — Colombia (hombre)</option>
                      <option value="es-CO-SalomeNeural">Salomé — Colombia (mujer)</option>
                    </optgroup>
                    <optgroup label="Chile">
                      <option value="es-CL-LorenzoNeural">Lorenzo — Chile (hombre)</option>
                      <option value="es-CL-CatalinaNeural">Catalina — Chile (mujer)</option>
                    </optgroup>
                    <optgroup label="Venezuela">
                      <option value="es-VE-SebastianNeural">Sebastián — Venezuela (hombre)</option>
                      <option value="es-VE-PaolaNeural">Paola — Venezuela (mujer)</option>
                    </optgroup>
                    <optgroup label="Perú">
                      <option value="es-PE-AlexNeural">Alex — Perú (hombre)</option>
                      <option value="es-PE-CamilaNeural">Camila — Perú (mujer)</option>
                    </optgroup>
                    <optgroup label="EEUU (español)">
                      <option value="es-US-AlonsoNeural">Alonso — EEUU (hombre)</option>
                      <option value="es-US-PalomaNeural">Paloma — EEUU (mujer)</option>
                    </optgroup>
                    <optgroup label="Otros">
                      <option value="es-BO-MarceloNeural">Marcelo — Bolivia</option>
                      <option value="es-UY-MateoNeural">Mateo — Uruguay</option>
                      <option value="es-PY-MarioNeural">Mario — Paraguay</option>
                      <option value="es-EC-LuisNeural">Luis — Ecuador</option>
                      <option value="es-GT-AndresNeural">Andrés — Guatemala</option>
                      <option value="es-HN-CarlosNeural">Carlos — Honduras</option>
                      <option value="es-PR-VictorNeural">Víctor — Puerto Rico</option>
                      <option value="es-DO-EmilioNeural">Emilio — Rep. Dominicana</option>
                      <option value="es-CU-ManuelNeural">Manuel — Cuba</option>
                      <option value="es-SV-RodrigoNeural">Rodrigo — El Salvador</option>
                      <option value="es-NI-FedericoNeural">Federico — Nicaragua</option>
                      <option value="es-PA-RobertoNeural">Roberto — Panamá</option>
                      <option value="es-CR-JuanNeural">Juan — Costa Rica</option>
                    </optgroup>
                  </select>
                )}
              </div>
            </div>
            {/* Preview de voz */}
            {prefs.servicio_voz !== "elevenlabs" && (
              <VoicePreview voz={prefs.voz} servicio={prefs.servicio_voz} />
            )}

            {/* Aviso ElevenLabs */}
            {(prefs.servicio_voz === "elevenlabs" || (prefs.servicio_voz === "auto" && ttsStatus?.elevenlabs)) && (
              <div style={{
                display: "flex", alignItems: "flex-start", gap: 10,
                padding: "10px 14px", borderRadius: 10,
                background: "#2a1800", border: "1px solid #92400e",
              }}>
                <span style={{ fontSize: 16, flexShrink: 0 }}>⚠</span>
                <div>
                  <p style={{ fontSize: 12, fontWeight: 700, color: "#fb923c", margin: "0 0 2px" }}>
                    {prefs.servicio_voz === "elevenlabs" ? "ElevenLabs activado" : "Modo auto: usará ElevenLabs"}
                  </p>
                  <p style={{ fontSize: 11, color: "#fed7aa", margin: 0 }}>
                    {prefs.servicio_voz === "auto"
                      ? "Tienes ELEVENLABS_API_KEY configurada — el modo auto la usa primero. Cada reel consume créditos. Cambia a \"Edge TTS\" para usar la voz gratuita."
                      : "Cada reel generado consumirá créditos de ElevenLabs. Usa \"Edge TTS\" para generación gratuita."}
                  </p>
                  <button onClick={() => setPrefs({ ...prefs, servicio_voz: "edge-tts", voz: "es-ES-AlvaroNeural" })}
                    style={{ marginTop: 6, fontSize: 11, padding: "3px 10px", borderRadius: 6, cursor: "pointer", background: "none", border: "1px solid #fb923c", color: "#fb923c", fontWeight: 600 }}>
                    Cambiar a Edge TTS gratis (Alvaro)
                  </button>
                </div>
              </div>
            )}

            {/* Tipo + Duración */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div>
                <Label>Tipo de contenido</Label>
                <div style={{ display: "flex", gap: 6 }}>
                  {(["noticia", "curiosidad"] as const).map((t) => (
                    <button key={t} onClick={() => setPrefs({ ...prefs, tipo_contenido: t })} style={{
                      flex: 1, padding: "7px 0", borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: "pointer",
                      border: `1px solid ${prefs.tipo_contenido === t ? "var(--accent)" : "var(--border)"}`,
                      background: prefs.tipo_contenido === t ? "rgba(99,102,241,0.12)" : "var(--surface2)",
                      color: prefs.tipo_contenido === t ? "var(--accent)" : "var(--muted)",
                    }}>
                      {t === "noticia" ? "Noticia" : "Curiosidad"}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <Label>Duración máxima: {prefs.duracion_maxima}s</Label>
                <input type="range" min={20} max={90} step={5} value={prefs.duracion_maxima}
                  onChange={(e) => setPrefs({ ...prefs, duracion_maxima: Number(e.target.value) })}
                  style={{ width: "100%", accentColor: "var(--accent)", marginTop: 6 }} />
              </div>
            </div>

            {/* Toggles */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              {([
                ["mostrar_subtitulos", "Subtítulos"],
                ["mostrar_titulo", "Título visible"],
                ["generar_imagenes_ai", "Imágenes IA"],
              ] as [keyof GenerationPrefs, string][]).map(([key, label]) => (
                <label key={key} style={{
                  display: "flex", alignItems: "center", gap: 7, padding: "6px 12px",
                  borderRadius: 8, cursor: "pointer",
                  background: prefs[key] ? "rgba(99,102,241,0.1)" : "var(--surface2)",
                  border: `1px solid ${prefs[key] ? "var(--accent)" : "var(--border)"}`,
                }}>
                  <input type="checkbox" checked={!!prefs[key]}
                    onChange={(e) => setPrefs({ ...prefs, [key]: e.target.checked })}
                    style={{ accentColor: "var(--accent)" }} />
                  <span style={{ fontSize: 12, fontWeight: 600, color: prefs[key] ? "var(--accent)" : "var(--muted)" }}>
                    {label}
                  </span>
                </label>
              ))}
            </div>

            {/* Marca */}
            <div>
              <Label>Marca de agua</Label>
              <input value={prefs.marca} onChange={(e) => setPrefs({ ...prefs, marca: e.target.value })}
                placeholder="@micanal — vacío = sin marca"
                style={inputStyle} />
            </div>

            {/* Música de fondo */}
            <div>
              <Label>Música de fondo</Label>
              <select value={prefs.musica_fondo ?? ""} onChange={(e) => setPrefs({ ...prefs, musica_fondo: e.target.value || null })}
                style={inputStyle}>
                <option value="">Sin música</option>
                {musicTracks.map((t) => (
                  <option key={t.id} value={t.filename}>{t.name || t.filename}</option>
                ))}
              </select>
              {musicTracks.length === 0 && (
                <p style={{ fontSize: 11, color: "var(--muted)", margin: "4px 0 0" }}>
                  Sube pistas en la sección de música para habilitarlas aquí.
                </p>
              )}
            </div>

            {/* Volúmenes */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div>
                <Label>Volumen voz: {Math.round(prefs.volumen_voz * 100)}%</Label>
                <input type="range" min={0} max={1} step={0.05} value={prefs.volumen_voz}
                  onChange={(e) => setPrefs({ ...prefs, volumen_voz: Number(e.target.value) })}
                  style={{ width: "100%", accentColor: "var(--accent)" }} />
              </div>
              <div>
                <Label>Volumen música: {Math.round(prefs.volumen_musica * 100)}%</Label>
                <input type="range" min={0} max={1} step={0.05} value={prefs.volumen_musica}
                  onChange={(e) => setPrefs({ ...prefs, volumen_musica: Number(e.target.value) })}
                  style={{ width: "100%", accentColor: "var(--accent)" }} />
              </div>
            </div>

            {/* Estado de guardado automático */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8, minHeight: 28 }}>
              {prefsToast && (
                <span style={{ fontSize: 12, color: prefsToast.startsWith("✓") ? "#4ade80" : "var(--error)", fontWeight: 600 }}>
                  {prefsToast}
                </span>
              )}
              <span style={{ fontSize: 11, color: "var(--muted)" }}>Se guarda automáticamente</span>
            </div>
          </div>
        )}
      </div>

      {/* ── ALMACENAMIENTO ── */}
      {storageStats && (() => {
        const fmt = (b: number) => b >= 1e9 ? `${(b/1e9).toFixed(1)} GB` : `${(b/1e6).toFixed(0)} MB`;
        const pct = (b: number) => Math.min(100, Math.round(b / storageStats.disk_total * 100));
        const diskUsedPct = pct(storageStats.disk_used);
        const outputPct = pct(storageStats.total_bytes);
        return (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 16, padding: "14px 20px", marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 14 }}>💾</span>
              <p style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: 0 }}>
                Almacenamiento · output {fmt(storageStats.total_bytes)} · disco libre {fmt(storageStats.disk_free)}
              </p>
            </div>
            <button onClick={() => setStorageOpen((v) => !v)} style={{ ...btnSecondary, fontSize: 11, padding: "3px 10px" }}>
              {storageOpen ? "Cerrar" : "Gestionar"}
            </button>
          </div>
          {/* Barra disco completo */}
          <div style={{ height: 8, borderRadius: 4, background: "var(--surface2)", overflow: "hidden", marginBottom: 6 }}>
            <div style={{ height: "100%", width: `${diskUsedPct}%`, borderRadius: 4, background: diskUsedPct > 85 ? "var(--error)" : diskUsedPct > 65 ? "#f59e0b" : "var(--accent)" }} />
          </div>
          <p style={{ fontSize: 11, color: "var(--muted)", margin: "0 0 8px" }}>
            Disco: {fmt(storageStats.disk_used)} usados de {fmt(storageStats.disk_total)} ({diskUsedPct}%) — Output: {fmt(storageStats.total_bytes)} ({storageStats.file_count} archivos, {outputPct}% del disco)
          </p>
          {/* Breakdown del output */}
          {storageStats.total_bytes > 0 && (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 4, background: "rgba(248,113,113,0.15)", color: "#f87171" }}>MP4: {fmt(storageStats.mp4_bytes)}</span>
              <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 4, background: "rgba(96,165,250,0.15)", color: "#60a5fa" }}>MP3: {fmt(storageStats.mp3_bytes)}</span>
              <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 4, background: "rgba(74,222,128,0.15)", color: "#4ade80" }}>Subidos: {fmt(storageStats.uploaded_bytes)}</span>
              <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 4, background: "rgba(163,163,163,0.15)", color: "var(--muted)" }}>Sin subir: {fmt(storageStats.pending_bytes)}</span>
            </div>
          )}
          {/* Panel de limpieza */}
          {storageOpen && (
            <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
              <p style={{ fontSize: 12, fontWeight: 700, color: "var(--text)", margin: "0 0 10px" }}>Limpieza de archivos</p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  onClick={() => runCleanup("uploaded", 0, true)}
                  disabled={cleanupLoading}
                  style={{ ...btnSecondary, fontSize: 11, padding: "4px 12px" }}
                  title="Ver cuánto se liberaría sin borrar nada"
                >
                  Simular limpieza subidos
                </button>
                <button
                  onClick={() => { if (confirm("¿Borrar archivos de reels ya subidos a alguna plataforma?")) runCleanup("uploaded"); }}
                  disabled={cleanupLoading}
                  style={{ ...btnSecondary, fontSize: 11, padding: "4px 12px", borderColor: "#f59e0b", color: "#f59e0b" }}
                >
                  Borrar archivos subidos
                </button>
                <button
                  onClick={() => { if (confirm("¿Borrar archivos de reels ready con más de 7 días?")) runCleanup("older_than", 7); }}
                  disabled={cleanupLoading}
                  style={{ ...btnSecondary, fontSize: 11, padding: "4px 12px", borderColor: "#f59e0b", color: "#f59e0b" }}
                >
                  Borrar &gt;7 días
                </button>
                <button
                  onClick={() => { if (confirm("¿Borrar TODOS los archivos de reels ready (se puede regenerar desde la cola)?")) runCleanup("all_files"); }}
                  disabled={cleanupLoading}
                  style={{ ...btnSecondary, fontSize: 11, padding: "4px 12px", borderColor: "var(--error)", color: "var(--error)" }}
                >
                  Borrar todos los archivos
                </button>
                <button onClick={() => { fetchStorage(); setCleanupResult(null); }} style={{ ...btnSecondary, fontSize: 11, padding: "4px 10px" }}>
                  Actualizar
                </button>
              </div>
              {cleanupLoading && <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 8 }}>Procesando...</p>}
              {cleanupResult && (
                <div style={{ marginTop: 8, padding: "8px 12px", borderRadius: 8, background: "var(--surface2)", fontSize: 12 }}>
                  {cleanupResult.cleaned_items > 0 || cleanupResult.freed_bytes > 0 ? (
                    <>
                      <span style={{ color: "#4ade80", fontWeight: 700 }}>
                        {cleanupResult.cleaned_items} items · {fmt(cleanupResult.freed_bytes)} liberados
                      </span>
                      {cleanupResult.orphan_bytes > 0 && (
                        <span style={{ color: "var(--muted)", marginLeft: 8 }}>
                          + {fmt(cleanupResult.orphan_bytes)} en archivos huérfanos
                        </span>
                      )}
                    </>
                  ) : (
                    <span style={{ color: "var(--muted)" }}>Sin archivos para limpiar con ese criterio.</span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
        );
      })()}

      {/* ── ARCHIVO DE NOTICIAS ── */}
      {(() => {
        const uploadedCount = items.filter(i => i.uploads && Object.keys(i.uploads).length > 0).length;
        return (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "14px 16px", marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: "var(--text)" }}>Archivo de noticias</span>
              {archiveItems.length > 0 && (
                <span style={{ fontSize: 11, color: "var(--muted)", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4, padding: "2px 6px" }}>
                  {archiveItems.length} archivados
                </span>
              )}
              <span style={{ fontSize: 11, color: "#94a3b8" }}>Auto-limpieza: archiva y borra del disco los subidos con más de 7 días</span>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => { setArchiveOpen(v => !v); if (!archiveOpen) fetchArchive(); }}
                style={{ fontSize: 12, padding: "4px 12px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)", cursor: "pointer" }}>
                {archiveOpen ? "Cerrar" : "Ver archivo"}
              </button>
              <button onClick={() => runAutoCleanup(true)} disabled={cleanupLoading}
                style={{ fontSize: 12, padding: "4px 12px", borderRadius: 6, border: "1px solid #fb923c", background: "transparent", color: "#fb923c", cursor: "pointer", opacity: cleanupLoading ? 0.5 : 1 }}>
                Simular limpieza
              </button>
              <button onClick={() => { if (confirm(`¿Archivar y borrar del disco los ${uploadedCount} items subidos con más de 7 días?`)) runAutoCleanup(false); }} disabled={cleanupLoading}
                style={{ fontSize: 12, padding: "4px 12px", borderRadius: 6, border: "1px solid var(--border)", background: "#1e1e1e", color: "var(--text)", cursor: "pointer", opacity: cleanupLoading ? 0.5 : 1 }}>
                Limpiar ahora
              </button>
            </div>
          </div>

          {cleanupResult && (
            <div style={{ marginTop: 8, fontSize: 12, color: "#4ade80" }}>
              {cleanupResult.cleaned_items} items archivados · {(cleanupResult.freed_bytes / 1024 / 1024).toFixed(0)} MB liberados
            </div>
          )}

          {archiveOpen && (
            <div style={{ marginTop: 12 }}>
              {archiveLoading ? (
                <span style={{ fontSize: 12, color: "var(--muted)" }}>Cargando...</span>
              ) : archiveItems.length === 0 ? (
                <span style={{ fontSize: 12, color: "var(--muted)" }}>El archivo está vacío.</span>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 400, overflowY: "auto" }}>
                  {archiveItems.map(a => {
                    const plats = Object.keys(a.uploads || {}).filter(p => a.uploads[p]);
                    const ytUrl = a.youtube_url || (a.uploads?.youtube as {url?: string})?.url || "";
                    return (
                      <div key={a.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", background: "var(--bg)", borderRadius: 6, border: "1px solid var(--border)" }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {a.titulo || "(sin título)"}
                          </div>
                          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2, display: "flex", gap: 8, flexWrap: "wrap" }}>
                            {a.score_noticia && <span style={{ color: "#fb923c" }}>{a.score_noticia.toFixed(1)}⭐</span>}
                            {plats.length > 0 && <span>Subido: {plats.join(", ")}</span>}
                            {ytUrl && <a href={ytUrl} target="_blank" rel="noreferrer" style={{ color: "#60a5fa" }}>Ver en YouTube</a>}
                            <span>Archivado: {new Date(a.archivado).toLocaleDateString("es-ES")}</span>
                          </div>
                        </div>
                        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                          {a.guion && (
                            <button title={a.guion.slice(0, 300)} style={{ fontSize: 11, padding: "3px 8px", borderRadius: 5, border: "1px solid var(--border)", background: "transparent", color: "var(--muted)", cursor: "help" }}>
                              Guion
                            </button>
                          )}
                          {a.puede_regenerar && (
                            <button onClick={() => regenerateArchived(a.id)} disabled={regeneratingId === a.id}
                              style={{ fontSize: 11, padding: "3px 10px", borderRadius: 5, border: "1px solid #4ade80", background: "transparent", color: "#4ade80", cursor: "pointer", opacity: regeneratingId === a.id ? 0.5 : 1 }}>
                              {regeneratingId === a.id ? "..." : "Regenerar"}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
        );
      })()}

      {/* ── DISTRIBUCIÓN ── */}
      {(() => {
        const tgs = distribCfg?.telegram_grupos ?? [];
        const subs = distribCfg?.reddit_subreddits ?? [];
        return (
          <div style={{ background: "var(--card)", borderRadius: 12, padding: "14px 18px", marginBottom: 18 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: "var(--text)" }}>
                Distribución automática
                {(tgs.length > 0 || subs.length > 0) && (
                  <span style={{ marginLeft: 8, fontSize: 11, color: "var(--muted)", fontWeight: 400 }}>
                    {tgs.length > 0 && `${tgs.length} grupo${tgs.length > 1 ? "s" : ""} Telegram`}
                    {tgs.length > 0 && subs.length > 0 && " · "}
                    {subs.length > 0 && `${subs.length} subreddit${subs.length > 1 ? "s" : ""}`}
                  </span>
                )}
              </span>
              <button
                onClick={() => { setDistribOpen(v => !v); if (!distribOpen && !distribCfg) fetchDistrib(); }}
                style={{ ...btnSecondary, fontSize: 11, padding: "3px 10px" }}
              >
                {distribOpen ? "Cerrar" : "Configurar"}
              </button>
            </div>

            {distribOpen && distribCfg && (
              <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 20 }}>

                {/* Telegram grupos */}
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>Grupos de Telegram</span>
                    <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "var(--muted)", cursor: "pointer" }}>
                      <input
                        type="checkbox"
                        checked={distribCfg.telegram_grupos_enabled}
                        onChange={e => saveDistrib({ telegram_grupos_enabled: e.target.checked })}
                      />
                      Activo
                    </label>
                  </div>
                  <p style={{ fontSize: 11, color: "var(--muted)", margin: "0 0 8px" }}>
                    El bot debe ser admin del grupo/canal. Obtén el chat_id enviando un mensaje y consultando
                    https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates
                  </p>
                  {tgs.map((g, i) => (
                    <div key={g.chat_id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5, fontSize: 12 }}>
                      <span style={{ flex: 1, color: "var(--text)" }}>{g.nombre || g.chat_id} <span style={{ color: "var(--muted)" }}>({g.chat_id})</span></span>
                      <button
                        onClick={() => testTelegramGrupo(g.chat_id)}
                        disabled={distribTestId === g.chat_id}
                        style={{ ...btnSecondary, fontSize: 10, padding: "2px 8px" }}
                      >
                        {distribTestId === g.chat_id ? "..." : "Test"}
                      </button>
                      <button
                        onClick={() => saveDistrib({ telegram_grupos: tgs.filter((_, j) => j !== i) })}
                        style={{ background: "transparent", border: "1px solid #f87171", color: "#f87171", borderRadius: 5, fontSize: 10, padding: "2px 8px", cursor: "pointer" }}
                      >
                        Quitar
                      </button>
                    </div>
                  ))}
                  <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                    <input
                      placeholder="Chat ID (ej: -1001234567890)"
                      value={distribTgInput.chat_id}
                      onChange={e => setDistribTgInput(v => ({ ...v, chat_id: e.target.value }))}
                      style={{ flex: 1, fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)" }}
                    />
                    <input
                      placeholder="Nombre (opcional)"
                      value={distribTgInput.nombre}
                      onChange={e => setDistribTgInput(v => ({ ...v, nombre: e.target.value }))}
                      style={{ flex: 1, fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)" }}
                    />
                    <button
                      disabled={!distribTgInput.chat_id.trim()}
                      onClick={() => {
                        if (!distribTgInput.chat_id.trim()) return;
                        saveDistrib({ telegram_grupos: [...tgs, { chat_id: distribTgInput.chat_id.trim(), nombre: distribTgInput.nombre.trim() }] });
                        setDistribTgInput({ chat_id: "", nombre: "" });
                      }}
                      style={{ ...btnPrimary, fontSize: 12, padding: "4px 12px" }}
                    >
                      Añadir
                    </button>
                  </div>
                </div>

                {/* Reddit */}
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>Subreddits de Reddit</span>
                    <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "var(--muted)", cursor: "pointer" }}>
                      <input
                        type="checkbox"
                        checked={distribCfg.reddit_enabled}
                        onChange={e => saveDistrib({ reddit_enabled: e.target.checked })}
                      />
                      Activo
                    </label>
                  </div>
                  <p style={{ fontSize: 11, color: "var(--muted)", margin: "0 0 8px" }}>
                    Requiere REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME y REDDIT_PASSWORD en el .env.
                    Crea la app en reddit.com/prefs/apps (tipo: script).
                  </p>
                  {subs.map((s, i) => (
                    <div key={s} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5, fontSize: 12 }}>
                      <span style={{ flex: 1, color: "var(--text)" }}>r/{s}</span>
                      <button
                        onClick={() => saveDistrib({ reddit_subreddits: subs.filter((_, j) => j !== i) })}
                        style={{ background: "transparent", border: "1px solid #f87171", color: "#f87171", borderRadius: 5, fontSize: 10, padding: "2px 8px", cursor: "pointer" }}
                      >
                        Quitar
                      </button>
                    </div>
                  ))}
                  <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                    <input
                      placeholder="Subreddit (ej: es o r/es)"
                      value={distribSubInput}
                      onChange={e => setDistribSubInput(e.target.value)}
                      style={{ flex: 1, fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)" }}
                    />
                    <button
                      disabled={!distribSubInput.trim()}
                      onClick={() => {
                        const s = distribSubInput.trim().replace(/^r\//, "");
                        if (!s) return;
                        saveDistrib({ reddit_subreddits: [...subs, s] });
                        setDistribSubInput("");
                      }}
                      style={{ ...btnPrimary, fontSize: 12, padding: "4px 12px" }}
                    >
                      Añadir
                    </button>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10 }}>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>Pausa entre posts:</span>
                    <input
                      type="number" min={5} max={120}
                      value={distribCfg.delay_entre_posts}
                      onChange={e => saveDistrib({ delay_entre_posts: parseInt(e.target.value) || 8 })}
                      style={{ width: 60, fontSize: 12, padding: "3px 6px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)" }}
                    />
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>segundos</span>
                  </div>
                </div>

                {distribSaving && <span style={{ fontSize: 11, color: "var(--muted)" }}>Guardando...</span>}
              </div>
            )}
          </div>
        );
      })()}

      {/* ── COLA ── */}
      <Section
        title={`Cola de generación${items.length > 0 ? ` (${filteredItems.length}${filteredItems.length !== items.length ? `/${items.length}` : ""})` : ""}`}
        action={
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end", alignItems: "center" }}>
            {items.some((i) => i.estado === "failed") && (
              <button onClick={retryAll} style={{ ...btnSecondary, fontSize: 12, padding: "5px 14px" }}>
                Reintentar fallidos
              </button>
            )}
            {pendingCount > 0 && (
              <>
                <button
                  onClick={toggleSelectAll}
                  style={{ ...btnSecondary, fontSize: 12, padding: "5px 14px" }}
                >
                  {allFilteredPendingSelected ? "Deseleccionar" : "Seleccionar todas"}
                </button>
                {selectedPendingCount > 0 && (
                  <button onClick={generateSelected} style={{ ...btnPrimary, fontSize: 12, padding: "5px 14px" }}>
                    Generar seleccionadas ({selectedPendingCount})
                  </button>
                )}
                {selectedPendingCount === 0 && pendingCount > 1 && (
                  <button onClick={generateAll} style={{ ...btnPrimary, fontSize: 12, padding: "5px 14px" }}>
                    Generar todas ({pendingCount})
                  </button>
                )}
              </>
            )}
          </div>
        }
      >
        {/* Filtros de fecha */}
        {items.some((i) => i.tipo === "noticia") && (
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 10 }}>
            {FECHA_FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setFechaFilter(f.key)}
                style={{
                  fontSize: 11, padding: "3px 10px", borderRadius: 20, cursor: "pointer",
                  fontWeight: fechaFilter === f.key ? 700 : 400,
                  background: fechaFilter === f.key ? "var(--accent)" : "var(--surface)",
                  color: fechaFilter === f.key ? "#fff" : "var(--muted)",
                  border: fechaFilter === f.key ? "none" : "1px solid var(--border)",
                  transition: "all 0.15s",
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
        )}

        {filteredItems.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--muted)", textAlign: "center", padding: "24px 0" }}>
            {items.length === 0
              ? "No hay items en la cola. Añade una URL, texto o noticia arriba."
              : `Sin noticias de "${activeFiltro.label.toLowerCase()}". Prueba con un rango más amplio.`}
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {filteredItems.map((item) => {
              const est = ESTADO_STYLE[item.estado];
              const distOpen = distributeOpen === item.id;
              const distRes = distributeResults[item.id] ?? {};
              const hasYtUrl = !!(item.youtube_url || ytUrlDraft[item.id]);
              const isHighlighted = highlightedItemId === item.id;
              return (
                <div key={item.id} id={`queue-item-${item.id}`} style={{
                  borderRadius: 12,
                  background: isHighlighted ? "rgba(74,222,128,0.08)" : item.estado === "pending" && selectedIds.has(item.id) ? "rgba(99,102,241,0.06)" : "var(--surface2)",
                  border: `1px solid ${isHighlighted ? "#4ade80" : item.estado === "pending" && selectedIds.has(item.id) ? "rgba(99,102,241,0.4)" : "var(--border)"}`,
                  overflow: "hidden",
                  transition: "background 0.4s, border-color 0.4s",
                }}>
                  {/* ── Fila principal ── */}
                  <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 14px" }}>
                    {/* Checkbox para items pendientes */}
                    {item.estado === "pending" && (
                      <input
                        type="checkbox"
                        checked={selectedIds.has(item.id)}
                        onChange={() => toggleSelect(item.id)}
                        style={{ accentColor: "var(--accent)", width: 15, height: 15, flexShrink: 0, cursor: "pointer" }}
                      />
                    )}
                    {/* Tipo badge */}
                    <span style={{
                      fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 5,
                      background: "var(--surface)", color: "var(--muted)", flexShrink: 0,
                    }}>
                      {item.tipo.toUpperCase()}
                    </span>

                    {/* Título */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontSize: 13, fontWeight: 600, margin: 0, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {item.titulo || truncate(item.contenido, 60)}
                      </p>
                      {/* Metadatos de fecha/fuente + veracidad para noticias */}
                      {item.tipo === "noticia" && (item.recencia_label || item.fuente_noticia || item.veracidad_label) && (
                        <p style={{ fontSize: 11, color: "var(--muted)", margin: "2px 0 0", display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                          {item.recencia_label && (
                            <span style={{
                              color: (item.recencia_horas ?? 999) <= 3 ? "#4ade80" : (item.recencia_horas ?? 999) <= 24 ? "#facc15" : "var(--muted)",
                              fontWeight: 600,
                            }}>
                              {item.recencia_label}
                            </span>
                          )}
                          {item.recencia_label && item.fuente_noticia && <span style={{ opacity: 0.4 }}>·</span>}
                          {item.fuente_noticia && <span>{item.fuente_noticia}</span>}
                          {item.veracidad_label && (
                            <>
                              <span style={{ opacity: 0.4 }}>·</span>
                              <span
                                title={item.veracidad_evidencia ? `Fuentes: ${item.veracidad_evidencia}` : item.veracidad_label}
                                style={{
                                  fontWeight: 700, color: item.veracidad_color || "var(--muted)",
                                  cursor: item.veracidad_evidencia ? "help" : "default",
                                }}
                              >
                                {item.veracidad_label === "Verificada" ? "✓" : item.veracidad_label === "Sin confirmar" ? "✗" : "⚠"} {item.veracidad_label}
                              </span>
                            </>
                          )}
                          {item.hilo_id && (() => {
                            const h = threads.find((t) => t.id === item.hilo_id);
                            return h ? (
                              <>
                                <span style={{ opacity: 0.4 }}>·</span>
                                <span style={{ color: "var(--accent)", fontWeight: 600 }}>
                                  {h.nombre} #{(h.episodios.findIndex((e) => e.item_id === item.id) + 1) || h.episodios.length + 1}
                                </span>
                              </>
                            ) : null;
                          })()}
                        </p>
                      )}
                      {item.error && (
                        <p style={{ fontSize: 11, color: "var(--error)", margin: "2px 0 0" }}>{item.error.slice(0, 80)}</p>
                      )}
                      {/* Badges de plataformas subidas */}
                      {(item.youtube_url || (item.uploads && Object.keys(item.uploads).length > 0)) && (
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
                          {item.youtube_url && (
                            <a href={item.youtube_url} target="_blank" rel="noopener noreferrer"
                              style={{ fontSize: 10, fontWeight: 700, padding: "1px 7px", borderRadius: 4, background: "rgba(255,0,0,0.15)", color: "#f87171", textDecoration: "none" }}>
                              ▶ YouTube
                            </a>
                          )}
                          {Object.entries(item.uploads || {}).filter(([p]) => p !== "youtube").map(([platform, info]) => {
                            const icons: Record<string, string> = { telegram: "✈ Telegram", x: "✕ X", instagram: "◈ Instagram", tiktok: "♪ TikTok", whatsapp: "● WhatsApp", facebook: "f Facebook", whatsapp_canal: "📢 Canal WA" };
                            const url = typeof info.url === "string" && info.url.startsWith("http") ? info.url : undefined;
                            const label = icons[platform] || platform;
                            return url ? (
                              <a key={platform} href={url} target="_blank" rel="noopener noreferrer"
                                style={{ fontSize: 10, fontWeight: 700, padding: "1px 7px", borderRadius: 4, background: "rgba(74,222,128,0.12)", color: "#4ade80", textDecoration: "none" }}>
                                {label}
                              </a>
                            ) : (
                              <span key={platform} style={{ fontSize: 10, fontWeight: 700, padding: "1px 7px", borderRadius: 4, background: "rgba(74,222,128,0.12)", color: "#4ade80" }}>
                                {label}
                              </span>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    {/* Estado */}
                    <span style={{
                      fontSize: 11, fontWeight: 700, padding: "3px 9px", borderRadius: 6,
                      background: est.bg, color: est.color, flexShrink: 0,
                    }}>
                      {est.label}
                    </span>

                    {/* Acciones */}
                    <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                      {item.estado === "ready" && item.output_file && (
                        <button
                          onClick={() => setPreviewFile((f) => f === item.output_file ? null : item.output_file!)}
                          style={{ ...btnSecondary, fontSize: 12, padding: "4px 12px" }}
                        >
                          {previewFile === item.output_file ? "Ocultar" : "▶ Ver"}
                        </button>
                      )}
                      {item.estado === "ready" && (
                        <>
                          <button
                            onClick={() => quickPublish(item)}
                            disabled={quickPublishing[item.id]}
                            title="Publicar ahora en todas las plataformas conectadas"
                            style={{
                              ...btnPrimary,
                              fontSize: 12, padding: "4px 10px",
                              background: quickPublishDone[item.id] ? "#22c55e" : quickPublishWarning[item.id] ? "#92400e" : undefined,
                              opacity: quickPublishing[item.id] ? 0.6 : 1,
                            }}
                          >
                            {quickPublishing[item.id] ? "…" : quickPublishDone[item.id] ? "✓" : quickPublishWarning[item.id] ? "!" : "⚡"}
                          </button>
                          {quickPublishWarning[item.id] && (
                            <button
                              onClick={() => quickPublish(item, true)}
                              title={`Ya subido a ${quickPublishWarning[item.id]}. Haz clic para forzar re-subida.`}
                              style={{ ...btnSecondary, fontSize: 11, padding: "4px 8px", border: "1px solid #a16207", color: "#facc15" }}
                            >
                              Re-subir
                            </button>
                          )}
                          <button onClick={() => setPublishItem(item)} style={{ ...btnSecondary, fontSize: 12, padding: "4px 12px" }}>
                            Publicar
                          </button>
                          <button
                            onClick={() => distOpen ? setDistributeOpen(null) : openDistribute(item)}
                            style={{
                              ...btnSecondary, fontSize: 12, padding: "4px 12px",
                              ...(item.youtube_url ? { borderColor: "#4ade80", color: "#4ade80" } : {}),
                            }}
                            title="Compartir enlace YouTube en redes"
                          >
                            {distOpen ? "Cerrar" : item.youtube_url ? "Distribuir YT" : "Añadir YT"}
                          </button>
                          <button
                            onClick={() => openRegenModal(item)}
                            style={{ ...btnSecondary, fontSize: 12, padding: "4px 10px" }}
                            title="Regenerar con opciones"
                          >
                            ↺
                          </button>
                        </>
                      )}
                      {(item.estado === "pending" || item.estado === "failed") && (
                        <>
                          <button
                            onClick={() => item.estado === "failed"
                              ? fetch(`/api/gestor/items/${item.id}/retry`, { method: "POST" }).then(fetchItems)
                              : generateItem(item.id)
                            }
                            style={{ ...btnSecondary, fontSize: 12, padding: "4px 12px" }}
                          >
                            {item.estado === "failed" ? "Reintentar" : "Generar"}
                          </button>
                          <button
                            onClick={() => openRegenModal(item)}
                            style={{ ...btnSecondary, fontSize: 12, padding: "4px 10px" }}
                            title="Generar con opciones"
                          >
                            ⚙
                          </button>
                        </>
                      )}
                      {/* Asignar hilo */}
                      {threads.length > 0 && (
                        <select
                          value={item.hilo_id ?? ""}
                          onChange={async (e) => {
                            const hilo_id = e.target.value || null;
                            await fetch(`/api/gestor/items/${item.id}/hilo`, {
                              method: "PATCH",
                              headers: { "Content-Type": "application/json" },
                              body: JSON.stringify({ hilo_id }),
                            });
                            // Si asignamos hilo, registrar como episodio
                            if (hilo_id) {
                              await fetch(`/api/threads/${hilo_id}/episodios`, {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ item_id: item.id, titulo: item.titulo || item.contenido?.slice(0, 60) }),
                              });
                              fetchThreads();
                            }
                            fetchItems();
                          }}
                          style={{ fontSize: 11, padding: "3px 6px", borderRadius: 5, border: "1px solid var(--border)", background: "var(--surface)", color: item.hilo_id ? "var(--accent)" : "var(--muted)", cursor: "pointer", maxWidth: 110 }}
                          title="Asignar a hilo temático"
                        >
                          <option value="">Hilo...</option>
                          {threads.map((h) => (
                            <option key={h.id} value={h.id}>{h.nombre}</option>
                          ))}
                        </select>
                      )}
                      {item.output_file && (
                        <button
                          onClick={() => { if (confirm("¿Borrar el archivo MP4/MP3 del disco? El item permanece en la cola.")) deleteItemFiles(item.id); }}
                          style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 12, padding: "2px 4px", lineHeight: 1 }}
                          title="Borrar archivos del disco"
                        >🗑</button>
                      )}
                      <button onClick={() => deleteItem(item.id)} style={{
                        background: "none", border: "none", color: "var(--muted)",
                        cursor: "pointer", fontSize: 15, padding: "2px 4px", lineHeight: 1,
                      }} title="Eliminar item">✕</button>
                    </div>
                  </div>

                  {/* ── Reproductor inline ── */}
                  {previewFile === item.output_file && item.output_file && (
                    <div style={{ padding: "10px 14px", borderTop: "1px solid var(--border)" }}>
                      <video
                        src={`/videos/${item.output_file}`}
                        controls
                        autoPlay
                        style={{ width: "100%", maxWidth: 280, borderRadius: 10, display: "block", background: "#000" }}
                      />
                      <a
                        href={`/videos/${item.output_file}`}
                        download={item.output_file}
                        style={{ display: "inline-block", marginTop: 7, fontSize: 11, color: "var(--accent)", textDecoration: "none", fontWeight: 600 }}
                      >
                        Descargar MP4
                      </a>
                    </div>
                  )}

                  {/* ── Panel YouTube + Distribución ── */}
                  {item.estado === "ready" && distOpen && (
                    <div style={{ padding: "14px", borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 10 }}>

                      {/* URL de YouTube */}
                      <div>
                        <p style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.07em", margin: "0 0 5px" }}>
                          Enlace YouTube
                        </p>
                        <div style={{ display: "flex", gap: 6 }}>
                          <input
                            value={ytUrlDraft[item.id] ?? item.youtube_url ?? ""}
                            onChange={(e) => setYtUrlDraft((d) => ({ ...d, [item.id]: e.target.value }))}
                            placeholder="https://youtu.be/..."
                            style={{ ...inputStyle, flex: 1, fontSize: 12 }}
                          />
                          <button
                            onClick={async () => {
                              const url = ytUrlDraft[item.id] ?? "";
                              await saveYoutubeUrl(item.id, url);
                              // Regenerar textos con la nueva URL
                              setDistributePlatformTexts((t) => { const n = { ...t }; delete n[item.id]; return n; });
                              await openDistribute({ ...item, youtube_url: url });
                            }}
                            style={{ ...btnSecondary, fontSize: 12, padding: "4px 14px", flexShrink: 0 }}
                          >
                            Guardar
                          </button>
                        </div>
                      </div>

                      {/* Plataformas + textos por plataforma */}
                      {hasYtUrl && (
                        <>
                          <div>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 7 }}>
                              <p style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.07em", margin: 0 }}>
                                Publicar en
                              </p>
                              {distributeCapLoading === item.id && (
                                <span style={{ fontSize: 10, color: "var(--muted)" }}>Generando textos…</span>
                              )}
                              {distributePlatformTexts[item.id] && distributeCapLoading !== item.id && (
                                <button
                                  onClick={async () => {
                                    setDistributePlatformTexts((t) => { const n = { ...t }; delete n[item.id]; return n; });
                                    await openDistribute(item);
                                  }}
                                  style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", fontSize: 10, padding: 0 }}
                                >
                                  ↺ Regenerar
                                </button>
                              )}
                            </div>
                            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                              {(["telegram", "x", "whatsapp"] as const).map((p) => {
                                const icons: Record<string, string> = { telegram: "✈️ Telegram", x: "𝕏 X / Twitter", whatsapp: "💬 WhatsApp" };
                                const sel = (distributePlatforms[item.id] ?? ["telegram"]).includes(p);
                                return (
                                  <label key={p} style={{
                                    display: "flex", alignItems: "center", gap: 6, padding: "5px 12px",
                                    borderRadius: 8, cursor: "pointer", fontSize: 12,
                                    background: sel ? "rgba(99,102,241,0.12)" : "var(--surface)",
                                    border: `1px solid ${sel ? "var(--accent)" : "var(--border)"}`,
                                    color: sel ? "var(--accent)" : "var(--muted)", fontWeight: 600,
                                  }}>
                                    <input type="checkbox" checked={sel} style={{ accentColor: "var(--accent)" }}
                                      onChange={(e) => setDistributePlatforms((prev) => {
                                        const cur = prev[item.id] ?? ["telegram"];
                                        return { ...prev, [item.id]: e.target.checked ? [...cur, p] : cur.filter((x) => x !== p) };
                                      })} />
                                    {icons[p]}
                                  </label>
                                );
                              })}
                            </div>
                          </div>

                          {/* Texto por cada plataforma seleccionada */}
                          {(["telegram", "x", "whatsapp"] as const)
                            .filter((p) => (distributePlatforms[item.id] ?? ["telegram"]).includes(p))
                            .map((p) => {
                              const icons: Record<string, string> = { telegram: "✈️ Telegram", x: "𝕏 X / Twitter (max 280)", whatsapp: "💬 WhatsApp" };
                              const platText = distributePlatformTexts[item.id]?.[p] ?? "";
                              const charCount = platText.length;
                              return (
                                <div key={p}>
                                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                    <p style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.07em", margin: 0 }}>
                                      {icons[p]}
                                    </p>
                                    {p === "x" && (
                                      <span style={{ fontSize: 10, color: charCount > 280 ? "var(--error)" : "var(--muted)" }}>{charCount}/280</span>
                                    )}
                                  </div>
                                  <textarea
                                    value={platText}
                                    onChange={(e) => setDistributePlatformTexts((t) => ({
                                      ...t,
                                      [item.id]: { ...t[item.id], [p]: e.target.value },
                                    }))}
                                    rows={p === "x" ? 3 : 4}
                                    style={{ ...inputStyle, width: "100%", fontSize: 12, resize: "vertical", boxSizing: "border-box" }}
                                  />
                                </div>
                              );
                            })
                          }

                          {/* Resultados */}
                          {Object.keys(distRes).length > 0 && (
                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                              {Object.entries(distRes).map(([p, r]) => (
                                <div key={p} style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 8 }}>
                                  <span style={{ fontWeight: 700, color: r.ok ? "#4ade80" : "var(--error)" }}>
                                    {r.ok ? "✓" : "✗"} {p}
                                  </span>
                                  {r.url && <a href={r.url} target="_blank" rel="noreferrer" style={{ color: "var(--accent)", fontSize: 11 }}>Ver</a>}
                                  {r.error && <span style={{ color: "var(--error)", fontSize: 11 }}>{r.error.slice(0, 60)}</span>}
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Botón publicar */}
                          <button
                            onClick={() => distributeItem(item.id)}
                            disabled={distributing === item.id}
                            style={{ ...btnPrimary, alignSelf: "flex-start", padding: "7px 20px", opacity: distributing === item.id ? 0.6 : 1 }}
                          >
                            {distributing === item.id ? "Publicando…" : "Publicar enlace"}
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Section>

      {/* ── VIDEOS MANUALES ── */}
      {orphans.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <button
            onClick={() => setOrphansOpen((v) => !v)}
            style={{
              width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
              background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.3)",
              borderRadius: 12, padding: "10px 16px", cursor: "pointer",
            }}
          >
            <span style={{ fontSize: 13, fontWeight: 700, color: "#fbbf24" }}>
              {orphans.length} video{orphans.length !== 1 ? "s" : ""} manual{orphans.length !== 1 ? "es" : ""} sin importar
            </span>
            <span style={{ fontSize: 12, color: "#fbbf24" }}>{orphansOpen ? "▲" : "▼"}</span>
          </button>

          {orphansOpen && (
            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
              {orphans.map((v) => (
                <div key={v.filename} style={{
                  display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
                  borderRadius: 10, background: "var(--surface2)", border: "1px solid var(--border)",
                }}>
                  <span style={{ fontSize: 16, flexShrink: 0 }}>🎬</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontSize: 13, fontWeight: 600, margin: 0, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {v.titulo}
                    </p>
                    <p style={{ fontSize: 11, color: "var(--muted)", margin: "2px 0 0" }}>
                      {fmtDate(v.modified)} · {(v.size / 1024 / 1024).toFixed(1)} MB · {v.filename}
                    </p>
                  </div>
                  <button
                    onClick={() => importOrphan(v.filename, v.titulo)}
                    disabled={importingOrphan === v.filename}
                    style={{
                      ...btnPrimary, padding: "7px 16px", fontSize: 12, flexShrink: 0,
                      opacity: importingOrphan === v.filename ? 0.6 : 1,
                      cursor: importingOrphan === v.filename ? "wait" : "pointer",
                    }}
                  >
                    {importingOrphan === v.filename ? "Importando…" : "Importar a cola"}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── PROGRAMADOS ── */}
      {(scheduled.length > 0 || readyCount > 0) && (
        <Section title={`Publicaciones programadas${scheduled.length > 0 ? ` (${scheduled.length})` : ""}`}>
          {scheduled.length === 0 ? (
            <p style={{ fontSize: 13, color: "var(--muted)", textAlign: "center", padding: "16px 0" }}>
              Cuando publiques un reel listo, aparecerá aquí.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {scheduled.map((s) => {
                const est = SCH_STYLE[s.estado];
                const platformIcons = s.platforms.map((p) => PLATFORMS.find((x) => x.id === p)?.icon ?? p).join(" ");
                return (
                  <div key={s.id} style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "11px 14px", borderRadius: 12,
                    background: "var(--surface2)", border: "1px solid var(--border)",
                  }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontSize: 13, fontWeight: 600, margin: 0, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {s.titulo || s.output_file}
                      </p>
                      <p style={{ fontSize: 11, color: "var(--muted)", margin: "2px 0 0" }}>
                        {platformIcons}
                        {s.publish_at
                          ? ` · ${fmtDate(s.publish_at)}`
                          : " · Publicar ahora"}
                      </p>
                      {/* Results */}
                      {s.estado === "done" && Object.entries(s.results).map(([plat, r]) => (
                        <span key={plat} style={{ fontSize: 11, color: r.status === "ok" ? "var(--success)" : "var(--error)", marginRight: 8 }}>
                          {PLATFORMS.find((p) => p.id === plat)?.label}: {r.status === "ok" ? "✓" : (r.error ?? "Error") }
                          {r.url && <a href={r.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)", marginLeft: 4 }}>Ver →</a>}
                        </span>
                      ))}
                      {s.error && <p style={{ fontSize: 11, color: "var(--error)", margin: "2px 0 0" }}>{s.error.slice(0, 80)}</p>}
                    </div>

                    <span style={{ fontSize: 11, fontWeight: 700, color: est.color, flexShrink: 0 }}>
                      {est.label}
                    </span>

                    {(s.estado === "scheduled" || s.estado === "failed") && (
                      <button onClick={() => cancelScheduled(s.id)} style={{
                        background: "none", border: "none", color: "var(--muted)",
                        cursor: "pointer", fontSize: 15, padding: "2px 4px",
                      }} title="Cancelar">✕</button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Section>
      )}

      {/* ── HILOS TEMÁTICOS ── */}
      <Section
        title={`Hilos temáticos${threads.length > 0 ? ` (${threads.length})` : ""}`}
        action={
          <button
            onClick={() => setThreadsOpen((o) => !o)}
            style={{ ...btnSecondary, fontSize: 12, padding: "4px 12px" }}
          >
            {threadsOpen ? "Cerrar" : "+ Nuevo hilo"}
          </button>
        }
      >
        {/* Formulario nuevo hilo */}
        {threadsOpen && (
          <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
            <input
              placeholder="Nombre del hilo (ej: Crisis de Ceuta)"
              value={newThreadNombre}
              onChange={(e) => setNewThreadNombre(e.target.value)}
              style={{ ...inputStyle, flex: 2, minWidth: 180 }}
            />
            <input
              placeholder="Palabra clave (ej: ceuta)"
              value={newThreadTema}
              onChange={(e) => setNewThreadTema(e.target.value)}
              style={{ ...inputStyle, flex: 1, minWidth: 120 }}
            />
            <button
              disabled={!newThreadNombre.trim()}
              onClick={async () => {
                if (!newThreadNombre.trim()) return;
                await fetch("/api/threads", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ nombre: newThreadNombre.trim(), tema: newThreadTema.trim() }),
                });
                setNewThreadNombre("");
                setNewThreadTema("");
                setThreadsOpen(false);
                fetchThreads();
              }}
              style={{ ...btnPrimary, fontSize: 12, padding: "5px 14px" }}
            >
              Crear
            </button>
          </div>
        )}

        {threads.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--muted)", textAlign: "center", padding: "12px 0" }}>
            Agrupa noticias relacionadas en un hilo para crear series de videos vinculadas.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {threads.map((hilo) => (
              <div key={hilo.id} style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 10, padding: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: hilo.episodios.length > 0 ? 8 : 0 }}>
                  <div>
                    <p style={{ fontWeight: 700, fontSize: 13, margin: 0 }}>{hilo.nombre}</p>
                    {hilo.tema && <p style={{ fontSize: 11, color: "var(--muted)", margin: "2px 0 0" }}>#{hilo.tema}</p>}
                    <p style={{ fontSize: 11, color: "var(--muted)", margin: "2px 0 0" }}>
                      {hilo.episodios.length} episodio{hilo.episodios.length !== 1 ? "s" : ""}
                      {hilo.episodios.filter((e) => e.youtube_url).length > 0 && (
                        <span style={{ color: "#4ade80" }}> · {hilo.episodios.filter((e) => e.youtube_url).length} publicados</span>
                      )}
                    </p>
                  </div>
                  <button
                    onClick={async () => {
                      if (!confirm(`¿Eliminar el hilo "${hilo.nombre}"?`)) return;
                      await fetch(`/api/threads/${hilo.id}`, { method: "DELETE" });
                      fetchThreads();
                    }}
                    style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 13, padding: "2px 4px" }}
                    title="Eliminar hilo"
                  >✕</button>
                </div>
                {/* Episodios */}
                {hilo.episodios.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {hilo.episodios.map((ep) => (
                      <div key={ep.item_id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                        <span style={{ color: "var(--muted)", fontWeight: 700, minWidth: 22 }}>#{ep.numero}</span>
                        <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text)" }}>{ep.titulo}</span>
                        {ep.youtube_url ? (
                          <a href={ep.youtube_url} target="_blank" rel="noopener noreferrer"
                            style={{ fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 4, background: "rgba(255,0,0,0.12)", color: "#f87171", textDecoration: "none", flexShrink: 0 }}>
                            YT
                          </a>
                        ) : (
                          <span style={{ fontSize: 10, color: "var(--muted)", flexShrink: 0 }}>pendiente</span>
                        )}
                        <button
                          onClick={async () => {
                            await fetch(`/api/threads/${hilo.id}/episodios/${ep.item_id}`, { method: "DELETE" });
                            fetchThreads();
                          }}
                          style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 11, padding: "1px 3px" }}
                          title="Quitar del hilo"
                        >✕</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Publish sheet */}
      {publishItem && (
        <PublishSheet
          item={publishItem}
          accounts={accounts}
          onClose={() => setPublishItem(null)}
          onScheduled={fetchItems}
        />
      )}

      {/* Modal: generar con opciones */}
      {regenModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
          zIndex: 1200, display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div style={{
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 16, padding: 24, width: 380, display: "flex", flexDirection: "column", gap: 16,
          }}>
            {/* Cabecera */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <p style={{ fontWeight: 700, fontSize: 15, margin: 0 }}>
                  {regenModal.estado === "ready" ? "Regenerar" : "Generar"} con opciones
                </p>
                <p style={{ fontSize: 11, color: "var(--muted)", margin: "3px 0 0", maxWidth: 290, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {regenModal.titulo || regenModal.contenido?.slice(0, 60)}
                </p>
              </div>
              <button onClick={() => setRegenModal(null)} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 18, padding: 0, lineHeight: 1 }}>✕</button>
            </div>

            {/* Música de fondo */}
            <div style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 10, padding: 12 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", marginBottom: regenOpts.musica_activa ? 10 : 0 }}>
                <input
                  type="checkbox"
                  checked={regenOpts.musica_activa}
                  onChange={(e) => setRegenOpts((o) => ({ ...o, musica_activa: e.target.checked }))}
                  style={{ accentColor: "var(--accent)", width: 16, height: 16 }}
                />
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>Música de fondo</span>
              </label>
              {regenOpts.musica_activa && (
                <select
                  value={regenOpts.musica_fondo ?? ""}
                  onChange={(e) => setRegenOpts((o) => ({ ...o, musica_fondo: e.target.value || null }))}
                  style={{ ...inputStyle, width: "100%", fontSize: 12 }}
                >
                  <option value="">Sin pista seleccionada</option>
                  {musicTracks.map((t) => (
                    <option key={t.id} value={t.filename}>{t.name || t.filename}</option>
                  ))}
                </select>
              )}
            </div>

            {/* Título y subtítulos */}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={regenOpts.mostrar_titulo}
                  onChange={(e) => setRegenOpts((o) => ({ ...o, mostrar_titulo: e.target.checked }))}
                  style={{ accentColor: "var(--accent)", width: 16, height: 16 }}
                />
                <span style={{ fontSize: 13, color: "var(--text)" }}>Mostrar título en el video</span>
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={regenOpts.mostrar_subtitulos}
                  onChange={(e) => setRegenOpts((o) => ({ ...o, mostrar_subtitulos: e.target.checked }))}
                  style={{ accentColor: "var(--accent)", width: 16, height: 16 }}
                />
                <span style={{ fontSize: 13, color: "var(--text)" }}>Mostrar subtítulos</span>
              </label>
            </div>

            {/* Video largo */}
            <div style={{ background: "var(--bg)", border: `1px solid ${regenOpts.largo ? "var(--accent)" : "var(--border)"}`, borderRadius: 10, padding: 12 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={regenOpts.largo}
                  onChange={(e) => setRegenOpts((o) => ({ ...o, largo: e.target.checked }))}
                  style={{ accentColor: "var(--accent)", width: 16, height: 16 }}
                />
                <div>
                  <span style={{ fontSize: 13, fontWeight: 600, color: regenOpts.largo ? "var(--accent)" : "var(--text)" }}>Video largo (7-10 min)</span>
                  <p style={{ fontSize: 11, color: "var(--muted)", margin: "2px 0 0" }}>Guion de 4 actos — historia completa, mayor retención</p>
                </div>
              </label>
            </div>

            {/* Botones */}
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button onClick={() => setRegenModal(null)} style={{ ...btnSecondary, fontSize: 13 }}>Cancelar</button>
              <button onClick={confirmRegen} style={{ ...btnPrimary, fontSize: 13 }}>
                {regenModal.estado === "ready" ? "Regenerar" : "Generar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function Section({
  title, children, action,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 16, padding: "20px", marginBottom: 20,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <p style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: 0 }}>
          {title}
        </p>
        {action}
      </div>
      {children}
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: "0 0 7px" }}>
      {children}
    </p>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%",
  background: "var(--bg)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "8px 12px",
  fontSize: 13,
  color: "var(--text)",
  outline: "none",
  boxSizing: "border-box",
};

const btnPrimary: React.CSSProperties = {
  background: "var(--accent)",
  border: "none",
  borderRadius: 8,
  color: "#fff",
  fontSize: 13,
  fontWeight: 700,
  padding: "9px 18px",
  cursor: "pointer",
};

const btnSecondary: React.CSSProperties = {
  background: "var(--surface2)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  color: "var(--muted)",
  fontSize: 13,
  fontWeight: 600,
  padding: "9px 18px",
  cursor: "pointer",
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleString("es-ES", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}
