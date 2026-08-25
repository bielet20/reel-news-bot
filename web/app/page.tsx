"use client";

import { useEffect, useRef, useState } from "react";
import RecentVideos from "./components/RecentVideos";
import ImagePicker, { type ImageConfig } from "./components/ImagePicker";
import AvatarPicker, { type AvatarConfig } from "./components/AvatarPicker";
import VoicePicker, { type VoiceConfig } from "./components/VoicePicker";
import DiscoverPanel from "./components/DiscoverPanel";

type Mode = "url" | "texto" | "youtube" | "musica" | "tema" | "descubrir";

interface MusicItem {
  id: string;
  name: string;
  filename: string;
  duration_s?: number | null;
}

const MODES: { id: Mode; label: string; icon: string; desc: string }[] = [
  { id: "descubrir", label: "Descubrir",    icon: "🔭", desc: "Busca noticias virales y propone los mejores reels" },
  { id: "url",       label: "Artículo URL", icon: "🔗", desc: "Genera un reel desde un artículo web" },
  { id: "texto",     label: "Texto",        icon: "📝", desc: "Pega el contenido del artículo directamente" },
  { id: "youtube",   label: "YouTube",      icon: "▶️", desc: "Recorta el mejor tramo de un video" },
  { id: "musica",    label: "Música",       icon: "🎵", desc: "Reel musical con detección automática de coro" },
  { id: "tema",      label: "Tema",         icon: "🔍", desc: "Busca noticias sobre un tema y genera el reel" },
];

interface Attribution {
  titulo_original?: string;
  fuente?: string;
  url_original?: string;
  autor?: string;
  fecha_publicacion?: string;
  descripcion?: string;
  seccion?: string;
  url_autor?: string;
  caption?: string;
}

interface JobState {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  logs: string;
  output_files: string[];
  attribution?: Attribution | null;
  youtube_url?: string | null;
  youtube_status?: "subiendo" | "ok" | "error" | null;
  youtube_error?: string | null;
  subir_youtube?: boolean;
}

const STATUS_STYLE: Record<string, { label: string; color: string; bg: string }> = {
  pending:   { label: "En cola",      color: "var(--warning)",  bg: "#2a1f0a" },
  running:   { label: "Generando…",   color: "#60a5fa",          bg: "#0a1a2a" },
  completed: { label: "Completado",   color: "var(--success)",  bg: "#0a2a1a" },
  failed:    { label: "Error",        color: "var(--error)",    bg: "#2a0a0a" },
};

// ── Item de resumen para el modal de confirmación ─────────────────────────────
interface SummaryItem {
  label: string;
  value?: string;
  active: boolean;
  always?: boolean;       // siempre incluido, sin toggle
  onToggle?: () => void;  // muestra un toggle interactivo
  editValue?: string;     // valor actual del campo editable
  onEdit?: (v: string) => void; // muestra un input editable
  editPlaceholder?: string;
}
interface SummaryGroup { title: string; items: SummaryItem[] }

export default function Home() {
  const [mode, setMode] = useState<Mode>("descubrir");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);

  const [url, setUrl] = useState("");
  const [urlFuente, setUrlFuente] = useState(""); // link original al usar Descubrir → Texto
  const [titulo, setTitulo] = useState("");
  const [fuente, setFuente] = useState("");
  const [texto, setTexto] = useState("");
  const [tema, setTema] = useState("");
  const [artista, setArtista] = useState("");
  const [modoYt, setModoYt] = useState("clip");
  const [ytAutoSegmento, setYtAutoSegmento] = useState(true);
  const [cookiesBrowser, setCookiesBrowser] = useState("chrome");
  const [musicaMostrarNombre, setMusicaMostrarNombre] = useState(false);
  const [tipoContenido, setTipoContenido] = useState<"noticia" | "curiosidad">("noticia");
  const [subirYoutube, setSubirYoutube] = useState(false);
  const [ytCredOk, setYtCredOk] = useState<boolean | null>(null);
  const [ytCanal, setYtCanal] = useState("");
  const [cantidad, setCantidad] = useState(1);
  const [duracion, setDuracion] = useState(60);
  const [marca, setMarca] = useState("");
  const [mostrarTitulo, setMostrarTitulo] = useState(false);
  const [mostrarSubtitulos, setMostrarSubtitulos] = useState(false);
  const [textoPersonalizadoEnabled, setTextoPersonalizadoEnabled] = useState(false);
  const [textoPersonalizado, setTextoPersonalizado] = useState("");
  const [imgConfig, setImgConfig] = useState<ImageConfig>({
    mode: "none", uploadedPaths: [], generateAi: false, servicioAi: "pollinations",
  });
  const [avatarConfig, setAvatarConfig] = useState<AvatarConfig>({
    enabled: false, imagePath: null, previewUrl: null, servicio: "auto",
  });
  const [voiceConfig, setVoiceConfig] = useState<VoiceConfig>({
    servicio: "auto", voz: null,
  });

  // Música de fondo
  const [musicaEnabled, setMusicaEnabled] = useState(false);
  const [musicaItem, setMusicaItem] = useState<MusicItem | null>(null);
  const [volumenMusica, setVolumenMusica] = useState(30);
  const [volumenVoz, setVolumenVoz] = useState(100);
  const [showMusicPicker, setShowMusicPicker] = useState(false);
  const [musicLibrary, setMusicLibrary] = useState<MusicItem[]>([]);
  const [previewingAudio, setPreviewingAudio] = useState(false);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const audioSourcesRef = useRef<AudioBufferSourceNode[]>([]);

  const [activeJob, setActiveJob] = useState<JobState | null>(null);
  const [logsExpanded, setLogsExpanded] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const stillUploading =
      activeJob?.status === "completed" && activeJob?.youtube_status === "subiendo";
    const isActive =
      activeJob && (activeJob.status === "pending" || activeJob.status === "running" || stillUploading);

    if (!isActive) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }
    intervalRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${activeJob!.id}`);
        if (!res.ok) return;
        const data = await res.json();
        setActiveJob((prev) => prev ? { ...prev, ...data } : null);
      } catch { /* retry */ }
    }, 2000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [activeJob?.id, activeJob?.status, activeJob?.youtube_status]);

  // Verificar credenciales de YouTube cuando se activa el toggle
  useEffect(() => {
    if (!subirYoutube || ytCredOk !== null) return;
    fetch("/api/youtube/status")
      .then((r) => r.json())
      .then((d) => { setYtCredOk(d.ok); setYtCanal(d.canal || ""); })
      .catch(() => setYtCredOk(false));
  }, [subirYoutube, ytCredOk]);

  useEffect(() => {
    if (logRef.current && logsExpanded) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [activeJob?.logs, logsExpanded]);

  // Construye el resumen para el modal de confirmación
  function buildSummary(): SummaryGroup[] {
    const modeInfo = MODES.find((m) => m.id === mode);

    const fuenteLabel =
      mode === "url" ? (url || "—") :
      mode === "texto" ? (titulo || "—") :
      mode === "youtube" ? (url || "—") :
      mode === "musica" ? (url || "—") :
      mode === "tema" ? (tema || "—") : "—";

    const voiceLabel =
      voiceConfig.servicio === "auto" ? "Automático (edge-tts / ElevenLabs)" :
      voiceConfig.servicio === "edge-tts" ? `edge-tts${voiceConfig.voz ? ` · ${voiceConfig.voz}` : ""}` :
      `ElevenLabs${voiceConfig.voz ? ` · ${voiceConfig.voz}` : ""}`;

    const fondoLabel =
      imgConfig.mode === "upload" ? `${imgConfig.uploadedPaths.length} imagen(es) subida(s)` :
      imgConfig.mode === "ai" ? `Generadas con IA (${imgConfig.servicioAi})` :
      "Degradado procedural (sin imágenes)";

    return [
      {
        title: "Fuente de contenido",
        items: [
          { label: modeInfo?.label ?? mode, value: fuenteLabel, active: true, always: true },
          ...(mode === "youtube" ? [
            { label: "Modo YouTube", value: modoYt === "clip" ? "Clip (video real)" : "Narrado (voz sintética)", active: true, always: true },
            { label: "Cantidad", value: `${cantidad} short(s)`, active: true, always: true },
            { label: "Recorte automático al mejor segmento", active: ytAutoSegmento },
          ] : []),
          ...(mode === "musica" ? [
            { label: "Nombre y artista en el video", active: musicaMostrarNombre },
            ...(artista ? [{ label: "Artista", value: artista, active: musicaMostrarNombre }] : []),
          ] : []),
          { label: "Duración máxima", value: `${duracion}s`, active: true, always: true },
        ],
      },
      ...(mode !== "youtube" && mode !== "musica" ? [{
        title: "Audio",
        items: [
          { label: "Narración", value: voiceLabel, active: true, always: true },
          {
            label: "Música de fondo",
            value: musicaEnabled && musicaItem
              ? `${musicaItem.name}  (voz ${volumenVoz}% · música ${volumenMusica}%)`
              : undefined,
            active: musicaEnabled && !!musicaItem,
          },
        ],
      }] : []),
      {
        title: "Fondo visual",
        items: [
          { label: "Imágenes de fondo", value: fondoLabel, active: true, always: imgConfig.mode === "none" },
          ...(avatarConfig.enabled && avatarConfig.imagePath ? [{
            label: "Avatar hablando",
            value: avatarConfig.servicio === "auto" ? "Auto (D-ID / SadTalker)" :
                   avatarConfig.servicio === "sadtalker" ? "SadTalker (local)" : "D-ID (cloud)",
            active: true,
          }] : [{ label: "Avatar hablando", active: false }]),
        ],
      },
      {
        title: "Publicar en YouTube",
        items: [
          {
            label: subirYoutube
              ? `Subir a YouTube (${tipoContenido === "noticia" ? "📰 Noticia" : "💡 Curiosidad"})`
              : "No subir a YouTube",
            active: subirYoutube,
            onToggle: () => setSubirYoutube((v) => !v),
          },
        ],
      },
      {
        title: "Texto en el video",
        items: [
          {
            label: "Subtítulos karaoke",
            active: mostrarSubtitulos,
            onToggle: () => setMostrarSubtitulos(!mostrarSubtitulos),
          },
          {
            label: "Título del artículo",
            active: mostrarTitulo,
            onToggle: () => setMostrarTitulo(!mostrarTitulo),
          },
          {
            label: "Texto personalizado",
            active: textoPersonalizadoEnabled,
            onToggle: () => setTextoPersonalizadoEnabled(!textoPersonalizadoEnabled),
            editValue: textoPersonalizado,
            onEdit: (v) => setTextoPersonalizado(v),
            editPlaceholder: "ej: nombre de la canción, fuente, subtítulo…",
          },
          {
            label: "Marca de agua",
            active: !!marca.trim(),
            editValue: marca,
            onEdit: (v) => setMarca(v),
            editPlaceholder: "ej: @micanal — vacío = sin marca",
          },
        ],
      },
    ];
  }

  async function doGenerate() {
    setError("");
    setSubmitting(true);
    setShowConfirm(false);
    setActiveJob(null);

    const body: Record<string, unknown> = { mode, duracion_maxima: duracion };

    if (mode === "url") body.url = url;
    else if (mode === "texto") { body.titulo = titulo; body.fuente = fuente; body.texto = texto; if (urlFuente) body.url_fuente = urlFuente; }
    else if (mode === "youtube") { body.url = url; body.modo_youtube = modoYt; body.cantidad_shorts = cantidad; body.youtube_auto_segmento = ytAutoSegmento; body.cookies_browser = cookiesBrowser; }
    else if (mode === "musica") { body.url = url; body.artista = artista; body.musica_mostrar_nombre = musicaMostrarNombre; body.cookies_browser = cookiesBrowser; }
    else if (mode === "tema") body.tema = tema;

    if (imgConfig.mode === "upload") body.imagenes_subidas = imgConfig.uploadedPaths;
    if (imgConfig.mode === "ai") { body.generar_imagenes_ai = true; body.servicio_ai = imgConfig.servicioAi; }

    if (avatarConfig.enabled && avatarConfig.imagePath) {
      body.avatar_imagen = avatarConfig.imagePath;
      body.avatar_servicio = avatarConfig.servicio;
    }

    body.servicio_voz = voiceConfig.servicio;
    if (voiceConfig.voz) body.voz = voiceConfig.voz;
    if (marca.trim()) body.marca = marca.trim();
    body.mostrar_titulo = mostrarTitulo;
    body.mostrar_subtitulos = mostrarSubtitulos;
    if (textoPersonalizadoEnabled && textoPersonalizado.trim())
      body.texto_personalizado = textoPersonalizado.trim();

    if (musicaEnabled && musicaItem) {
      body.musica_fondo = musicaItem.filename;
      body.volumen_musica = volumenMusica / 100;
      body.volumen_voz = volumenVoz / 100;
    }

    body.tipo_contenido = tipoContenido;
    body.subir_youtube  = subirYoutube;

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      const { job_id } = await res.json();
      setActiveJob({ id: job_id, status: "pending", logs: "", output_files: [], attribution: null });
      setLogsExpanded(false);
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setShowConfirm(true);
  }

  const isRunning = activeJob && (activeJob.status === "pending" || activeJob.status === "running");

  function handleUsarNoticia(noticia: { titulo: string; titulo_original: string; fuente: string; link: string; resumen: string }) {
    const textoLimpio = noticia.resumen
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    setMode("texto");
    setTitulo(noticia.titulo);
    setFuente(noticia.fuente || "");
    setTexto(textoLimpio || noticia.titulo_original);
    setUrlFuente(noticia.link || "");
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const stopPreview = () => {
    audioSourcesRef.current.forEach((s) => { try { s.stop(); } catch { /* already stopped */ } });
    audioSourcesRef.current = [];
    if (audioCtxRef.current) { audioCtxRef.current.close(); audioCtxRef.current = null; }
    setPreviewingAudio(false);
  };

  const previewAudioMix = async () => {
    stopPreview();
    setPreviewingAudio(true);
    try {
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      const sources: AudioBufferSourceNode[] = [];

      const voiceRes = await fetch("/api/tts/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servicio: voiceConfig.servicio, voz: voiceConfig.voz,
          texto: "Esta es una prueba del audio del reel. Así sonará la voz con la música de fondo configurada." }),
      });
      if (voiceRes.ok) {
        const voiceBuf = await ctx.decodeAudioData(await voiceRes.arrayBuffer());
        const voiceSrc = ctx.createBufferSource();
        voiceSrc.buffer = voiceBuf;
        const voiceGain = ctx.createGain();
        voiceGain.gain.value = volumenVoz / 100;
        voiceSrc.connect(voiceGain).connect(ctx.destination);
        voiceSrc.start();
        voiceSrc.onended = () => setPreviewingAudio(false);
        sources.push(voiceSrc);
      }

      if (musicaEnabled && musicaItem) {
        const musicRes = await fetch(`/music-files/${musicaItem.filename}`);
        if (musicRes.ok) {
          const musicBuf = await ctx.decodeAudioData(await musicRes.arrayBuffer());
          const musicSrc = ctx.createBufferSource();
          musicSrc.buffer = musicBuf;
          musicSrc.loop = true;
          const musicGain = ctx.createGain();
          musicGain.gain.value = volumenMusica / 100;
          musicSrc.connect(musicGain).connect(ctx.destination);
          musicSrc.start();
          sources.push(musicSrc);
        }
      }

      audioSourcesRef.current = sources;
      setTimeout(() => stopPreview(), 20000);
    } catch (err) {
      console.error("Preview error:", err);
      setPreviewingAudio(false);
    }
  };

  const loadMusicLibrary = async () => {
    try {
      const res = await fetch("/api/music");
      const data = await res.json();
      setMusicLibrary(data);
    } catch { /* ignore */ }
  };

  return (
    <main className="min-h-screen px-4 py-10">
      <div className="max-w-2xl mx-auto">
        <div className="mb-10 text-center">
          <h1 className="text-3xl font-bold mb-2" style={{ color: "var(--accent)" }}>
            Reel News Bot
          </h1>
          <p style={{ color: "var(--muted)" }}>
            Genera shorts automáticos para Instagram, TikTok y YouTube Shorts
          </p>
        </div>

        <div className="rounded-2xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          {/* Mode selector */}
          <div className="flex gap-2 flex-wrap mb-5">
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => { setMode(m.id); setError(""); }}
                className="px-3 py-1.5 rounded-lg text-sm font-medium transition-all"
                style={{
                  background: mode === m.id ? "var(--accent)" : "var(--surface2)",
                  color: mode === m.id ? "#fff" : "var(--muted)",
                  border: `1px solid ${mode === m.id ? "var(--accent)" : "var(--border)"}`,
                }}
              >
                {m.icon} {m.label}
              </button>
            ))}
          </div>

          <p className="text-sm mb-5" style={{ color: "var(--muted)" }}>
            {MODES.find((m) => m.id === mode)?.desc}
          </p>

          {mode === "descubrir" && (
            <DiscoverPanel onUsar={handleUsarNoticia} />
          )}

          <form onSubmit={handleSubmit} className={`space-y-4 ${mode === "descubrir" ? "hidden" : ""}`}>
            {(mode === "url" || mode === "youtube" || mode === "musica") && (
              <Field label={mode === "musica" ? "URL de YouTube o ruta de archivo" : "URL"}>
                <TextInput
                  value={url} onChange={setUrl}
                  placeholder={
                    mode === "youtube" ? "https://youtu.be/..." :
                    mode === "musica" ? "https://youtu.be/... o /ruta/cancion.mp3" :
                    "https://ejemplo.com/articulo"
                  }
                  required
                />
              </Field>
            )}

            {mode === "texto" && (
              <>
                {titulo && texto && (
                  <div className="text-xs px-3 py-2 rounded-lg"
                    style={{ background: "#0a1a2a", border: "1px solid #1a3a5a", color: "#60a5fa" }}>
                    ✓ Noticia cargada desde Descubrir. Puedes editar el texto o añadir más contenido antes de generar.
                  </div>
                )}
                <Field label="Título del artículo">
                  <TextInput value={titulo} onChange={setTitulo} placeholder="Título de la noticia" required />
                </Field>
                <Field label="Fuente (opcional)">
                  <TextInput value={fuente} onChange={setFuente} placeholder="ej: ConcoDeFi, El País…" />
                </Field>
                <Field label="Contenido del artículo">
                  <textarea
                    value={texto}
                    onChange={(e) => setTexto(e.target.value)}
                    placeholder="Pega aquí el texto completo del artículo…"
                    required
                    rows={8}
                    className="w-full rounded-lg px-3 py-2 text-sm resize-vertical"
                    style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", outline: "none" }}
                  />
                </Field>
              </>
            )}

            {mode === "tema" && (
              <Field label="Tema a buscar">
                <TextInput value={tema} onChange={setTema} placeholder="ej: inteligencia artificial, cripto, deportes…" required />
              </Field>
            )}

            {mode === "youtube" && (
              <>
                <div className="flex gap-4">
                  <Field label="Modo" className="flex-1">
                    <SelectInput value={modoYt} onChange={setModoYt} options={[
                      { value: "clip",    label: "Clip (video real recortado)" },
                      { value: "narrado", label: "Narrado (voz sintética)" },
                    ]} />
                  </Field>
                  <Field label="Cantidad" className="w-36">
                    <SelectInput value={String(cantidad)} onChange={(v) => setCantidad(Number(v))} options={[
                      { value: "1", label: "1 short" },
                      { value: "2", label: "2 shorts" },
                      { value: "3", label: "3 shorts" },
                    ]} />
                  </Field>
                </div>
                {modoYt === "clip" && (
                  <Field label="Navegador (cookies para descarga)">
                    <SelectInput value={cookiesBrowser} onChange={setCookiesBrowser} options={[
                      { value: "chrome",  label: "Chrome" },
                      { value: "safari",  label: "Safari" },
                      { value: "firefox", label: "Firefox" },
                      { value: "edge",    label: "Edge" },
                      { value: "brave",   label: "Brave" },
                    ]} />
                  </Field>
                )}
                <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                  <Toggle value={ytAutoSegmento} onChange={setYtAutoSegmento} />
                  <span style={{ fontSize: 13, color: ytAutoSegmento ? "var(--text)" : "var(--muted)" }}>
                    {ytAutoSegmento ? "Detección automática del mejor segmento activada" : "Sin recorte automático (usa el inicio del video)"}
                  </span>
                </label>
              </>
            )}

            {mode === "musica" && (
              <>
                <Field label="Artista (opcional)">
                  <TextInput value={artista} onChange={setArtista} placeholder="Nombre del artista" />
                </Field>
                <Field label="Navegador (cookies para descarga)">
                  <SelectInput value={cookiesBrowser} onChange={setCookiesBrowser} options={[
                    { value: "chrome",  label: "Chrome" },
                    { value: "safari",  label: "Safari" },
                    { value: "firefox", label: "Firefox" },
                    { value: "edge",    label: "Edge" },
                    { value: "brave",   label: "Brave" },
                  ]} />
                </Field>
                <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                  <Toggle value={musicaMostrarNombre} onChange={setMusicaMostrarNombre} />
                  <span style={{ fontSize: 13, color: musicaMostrarNombre ? "var(--text)" : "var(--muted)" }}>
                    {musicaMostrarNombre ? "Nombre de canción y artista visibles en el video" : "Sin nombre de canción ni artista"}
                  </span>
                </label>
              </>
            )}

            {(mode === "url" || mode === "texto" || mode === "tema") && (
              <Field label="Imágenes de fondo">
                <ImagePicker
                  value={imgConfig}
                  onChange={setImgConfig}
                  hasArticleUrl={mode === "url" && url.length > 0}
                  tituloParaAi={mode === "texto" ? titulo : mode === "tema" ? tema : url}
                />
              </Field>
            )}

            {(mode === "url" || mode === "texto" || mode === "tema") && (
              <Field label="Voz">
                <VoicePicker value={voiceConfig} onChange={setVoiceConfig} />
              </Field>
            )}

            {(mode === "url" || mode === "texto" || mode === "tema") && (
              <Field label="Música de fondo">
                <div style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 10, padding: 12 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", marginBottom: musicaEnabled ? 12 : 0 }}>
                    <Toggle value={musicaEnabled} onChange={setMusicaEnabled} />
                    <span style={{ fontSize: 13, color: "var(--muted)" }}>
                      {musicaEnabled ? "Música de fondo activada" : "Añadir música de fondo"}
                    </span>
                    {!musicaEnabled && (
                      <a href="/music" target="_blank" style={{ marginLeft: "auto", fontSize: 11, color: "var(--accent)", textDecoration: "none" }}>Gestionar →</a>
                    )}
                  </label>

                  {musicaEnabled && (
                    <>
                      <div style={{ marginBottom: 10 }}>
                        {musicaItem ? (
                          <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--surface)", borderRadius: 8, padding: "7px 10px" }}>
                            <span style={{ fontSize: 18 }}>🎵</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <p style={{ fontSize: 12, color: "var(--text)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{musicaItem.name}</p>
                              {musicaItem.duration_s && <p style={{ fontSize: 10, color: "var(--muted)", margin: 0 }}>{Math.floor(musicaItem.duration_s / 60)}:{String(Math.floor(musicaItem.duration_s % 60)).padStart(2, "0")}</p>}
                            </div>
                            <button onClick={() => { setShowMusicPicker(true); loadMusicLibrary(); }} style={{ background: "none", border: "1px solid var(--border)", borderRadius: 6, color: "var(--muted)", cursor: "pointer", fontSize: 11, padding: "3px 8px" }}>Cambiar</button>
                          </div>
                        ) : (
                          <button type="button" onClick={() => { setShowMusicPicker(true); loadMusicLibrary(); }} style={{ width: "100%", background: "var(--surface)", border: "1px dashed var(--border)", borderRadius: 8, padding: "10px 0", fontSize: 12, color: "var(--accent)", cursor: "pointer" }}>
                            🎵 Elegir pista de la biblioteca
                          </button>
                        )}
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
                        <div>
                          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                            <span style={{ fontSize: 11, color: "var(--muted)" }}>Voz</span>
                            <span style={{ fontSize: 11, color: "var(--text)", fontWeight: 600 }}>{volumenVoz}%</span>
                          </div>
                          <input type="range" min={0} max={100} value={volumenVoz} onChange={(e) => setVolumenVoz(Number(e.target.value))} style={{ width: "100%", accentColor: "var(--accent)" }} />
                        </div>
                        <div>
                          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                            <span style={{ fontSize: 11, color: "var(--muted)" }}>Música</span>
                            <span style={{ fontSize: 11, color: "var(--text)", fontWeight: 600 }}>{volumenMusica}%</span>
                          </div>
                          <input type="range" min={0} max={100} value={volumenMusica} onChange={(e) => setVolumenMusica(Number(e.target.value))} style={{ width: "100%", accentColor: "#fb923c" }} />
                        </div>
                      </div>

                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <button
                          type="button"
                          onClick={previewingAudio ? stopPreview : previewAudioMix}
                          style={{ flex: 1, background: previewingAudio ? "#5a2020" : "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "7px 0", fontSize: 12, color: previewingAudio ? "#f87171" : "var(--text)", cursor: "pointer" }}
                        >
                          {previewingAudio ? "⏹ Detener preview" : "▶ Preview del audio"}
                        </button>
                        <a href="/music" target="_blank" style={{ fontSize: 11, color: "var(--accent)", textDecoration: "none", whiteSpace: "nowrap" }}>Biblioteca →</a>
                      </div>
                    </>
                  )}
                </div>
              </Field>
            )}

            {/* Music Picker Modal */}
            {showMusicPicker && (
              <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 16, padding: 20, width: 440, maxHeight: "70vh", display: "flex", flexDirection: "column" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                    <p style={{ fontWeight: 700, fontSize: 15, margin: 0 }}>Elegir música de fondo</p>
                    <button onClick={() => setShowMusicPicker(false)} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 18 }}>✕</button>
                  </div>
                  <div style={{ flex: 1, overflowY: "auto" }}>
                    {musicLibrary.length === 0 ? (
                      <div style={{ textAlign: "center", paddingTop: 30 }}>
                        <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 10 }}>No hay música en la biblioteca.</p>
                        <a href="/music" target="_blank" style={{ color: "var(--accent)", fontSize: 13 }}>Subir música →</a>
                      </div>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {musicLibrary.map((item) => (
                          <button
                            key={item.id}
                            onClick={() => { setMusicaItem(item); setShowMusicPicker(false); }}
                            style={{ display: "flex", alignItems: "center", gap: 10, background: musicaItem?.id === item.id ? "rgba(99,102,241,0.15)" : "var(--surface2)", border: `1px solid ${musicaItem?.id === item.id ? "var(--accent)" : "var(--border)"}`, borderRadius: 10, padding: "10px 12px", cursor: "pointer", textAlign: "left" }}
                          >
                            <span style={{ fontSize: 22, flexShrink: 0 }}>🎵</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <p style={{ fontSize: 13, color: "var(--text)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.name}</p>
                              {item.duration_s && <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>{Math.floor(item.duration_s / 60)}:{String(Math.floor(item.duration_s % 60)).padStart(2, "0")}</p>}
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <a href="/music" target="_blank" style={{ display: "block", textAlign: "center", fontSize: 11, color: "var(--accent)", marginTop: 12, textDecoration: "none" }}>
                    Gestionar biblioteca de música →
                  </a>
                </div>
              </div>
            )}

            {(mode === "url" || mode === "texto" || mode === "tema") && (
              <Field label="Avatar hablando">
                <AvatarPicker value={avatarConfig} onChange={setAvatarConfig} />
              </Field>
            )}

            {/* ── Texto visible en el video ─────────────────────────────── */}
            <div style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 10, padding: 12 }}>
              <p style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)", marginBottom: 10 }}>Texto en el video</p>

              {/* Subtítulos karaoke */}
              <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", marginBottom: 8 }}>
                <Toggle value={mostrarSubtitulos} onChange={setMostrarSubtitulos} />
                <span style={{ fontSize: 13, color: mostrarSubtitulos ? "var(--text)" : "var(--muted)" }}>
                  {mostrarSubtitulos ? "Subtítulos karaoke activados" : "Sin subtítulos"}
                </span>
              </label>

              {/* Título del artículo */}
              <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", marginBottom: 8 }}>
                <Toggle value={mostrarTitulo} onChange={setMostrarTitulo} />
                <span style={{ fontSize: 13, color: mostrarTitulo ? "var(--text)" : "var(--muted)" }}>
                  {mostrarTitulo ? "Título del artículo visible" : "Sin título"}
                </span>
              </label>

              {/* Texto personalizado */}
              <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", marginBottom: textoPersonalizadoEnabled ? 6 : 0 }}>
                <Toggle value={textoPersonalizadoEnabled} onChange={setTextoPersonalizadoEnabled} />
                <span style={{ fontSize: 13, color: textoPersonalizadoEnabled ? "var(--text)" : "var(--muted)" }}>
                  {textoPersonalizadoEnabled ? "Texto personalizado activado" : "Añadir texto personalizado"}
                </span>
              </label>
              {textoPersonalizadoEnabled && (
                <input
                  type="text"
                  value={textoPersonalizado}
                  onChange={(e) => setTextoPersonalizado(e.target.value)}
                  placeholder="ej: nombre de la canción, fuente, subtítulo libre…"
                  style={{ width: "100%", marginTop: 6, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "7px 10px", fontSize: 13, color: "var(--text)", outline: "none", boxSizing: "border-box" }}
                />
              )}
            </div>

            {/* Marca de agua */}
            <Field label="Marca de agua (opcional)">
              <TextInput
                value={marca}
                onChange={setMarca}
                placeholder="ej: @micanal — vacío = sin marca"
              />
            </Field>

            {/* ── Publicar en YouTube ──────────────────────────────── */}
            <div style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 10, padding: 12 }}>
              <p style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)", marginBottom: 10 }}>Publicar en YouTube</p>

              <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", marginBottom: subirYoutube ? 12 : 0 }}>
                <Toggle value={subirYoutube} onChange={(v) => { setSubirYoutube(v); if (v && ytCredOk === null) setYtCredOk(null); }} />
                <span style={{ fontSize: 13, color: subirYoutube ? "var(--text)" : "var(--muted)" }}>
                  {subirYoutube ? "Subir y publicar en YouTube al terminar" : "No subir a YouTube"}
                </span>
              </label>

              {subirYoutube && (
                <>
                  {ytCredOk === false && (
                    <div style={{ fontSize: 11, color: "#f87171", background: "#2a1515", border: "1px solid #5a2020", borderRadius: 7, padding: "7px 10px", marginBottom: 10 }}>
                      ⚠️ Credenciales de YouTube no configuradas.{" "}
                      <span style={{ opacity: 0.8 }}>Ejecuta <code>python scripts/youtube_auth.py</code> y añade el token al .env</span>
                    </div>
                  )}
                  {ytCredOk === true && (
                    <div style={{ fontSize: 11, color: "#4ade80", background: "#0a2a1a", border: "1px solid #1a5a2a", borderRadius: 7, padding: "7px 10px", marginBottom: 10 }}>
                      ✓ Conectado al canal: <strong>{ytCanal}</strong>
                    </div>
                  )}

                  <p style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>Tipo de contenido</p>
                  <div style={{ display: "flex", gap: 8 }}>
                    {(["noticia", "curiosidad"] as const).map((t) => {
                      const info = t === "noticia"
                        ? { icon: "📰", label: "Noticia",    desc: "Playlist Últimas Noticias" }
                        : { icon: "💡", label: "Curiosidad", desc: "Playlist Curiosidades" };
                      return (
                        <button key={t} type="button" onClick={() => setTipoContenido(t)}
                          style={{ flex: 1, padding: "8px 6px", borderRadius: 8, border: `1px solid ${tipoContenido === t ? "var(--accent)" : "var(--border)"}`, background: tipoContenido === t ? "rgba(99,102,241,0.12)" : "var(--surface)", cursor: "pointer", textAlign: "center" }}>
                          <div style={{ fontSize: 18, marginBottom: 2 }}>{info.icon}</div>
                          <div style={{ fontSize: 12, fontWeight: 600, color: tipoContenido === t ? "var(--accent)" : "var(--text)" }}>{info.label}</div>
                          <div style={{ fontSize: 10, color: "var(--muted)" }}>{info.desc}</div>
                        </button>
                      );
                    })}
                  </div>
                </>
              )}
            </div>

            <Field label={`Duración máxima: ${duracion}s`}>
              <input
                type="range" min={20} max={60} value={duracion}
                onChange={(e) => setDuracion(Number(e.target.value))}
                className="w-full accent-purple-500 mt-1"
              />
              <div className="flex justify-between text-xs mt-1" style={{ color: "var(--muted)" }}>
                <span>20s</span><span>60s</span>
              </div>
            </Field>

            {error && (
              <p className="text-sm rounded-lg px-3 py-2" style={{ background: "#2a1515", color: "var(--error)", border: "1px solid #5a2020" }}>
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting || !!isRunning}
              className="w-full py-3 rounded-xl font-semibold text-white transition-all"
              style={{
                background: isRunning ? "var(--surface2)" : "var(--accent)",
                opacity: submitting ? 0.6 : 1,
                cursor: submitting || isRunning ? "not-allowed" : "pointer",
                border: isRunning ? "1px solid var(--border)" : "none",
                color: isRunning ? "var(--muted)" : "#fff",
              }}
            >
              {submitting ? "Iniciando…" : isRunning ? "⟳ Generando — espera o configura otro" : "Revisar y generar →"}
            </button>
          </form>
        </div>

        {/* Job panel inline */}
        {activeJob && (
          <JobPanel
            job={activeJob}
            logsExpanded={logsExpanded}
            onToggleLogs={() => setLogsExpanded((v) => !v)}
            onDismiss={() => setActiveJob(null)}
            logRef={logRef}
          />
        )}

        <RecentVideos />
      </div>

      {/* Modal de confirmación */}
      {showConfirm && (
        <ConfirmModal
          groups={buildSummary()}
          onCancel={() => setShowConfirm(false)}
          onConfirm={doGenerate}
        />
      )}
    </main>
  );
}

// ── Modal de confirmación ──────────────────────────────────────────────────────
function ConfirmModal({
  groups, onCancel, onConfirm,
}: {
  groups: SummaryGroup[];
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div style={{
      position: "fixed", inset: 0,
      background: "rgba(0,0,0,0.75)",
      zIndex: 2000,
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: "20px",
    }}>
      <div style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 18,
        width: "100%", maxWidth: 520,
        maxHeight: "85vh",
        display: "flex", flexDirection: "column",
        overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{ padding: "18px 20px 12px", borderBottom: "1px solid var(--border)" }}>
          <p style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Resumen del reel</p>
          <p style={{ fontSize: 12, color: "var(--muted)", margin: "4px 0 0" }}>
            El video incluirá únicamente lo que ves activado. Confirma para generar.
          </p>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: "auto", padding: "14px 20px" }}>
          {groups.map((group) => (
            <div key={group.title} style={{ marginBottom: 16 }}>
              <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: "0 0 8px" }}>
                {group.title}
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {group.items.map((item) => (
                  <div key={item.label}>
                    {item.onToggle ? (
                      <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                        <Toggle value={item.active} onChange={item.onToggle} />
                        <span style={{ fontSize: 13, color: item.active ? "var(--text)" : "var(--muted)" }}>
                          {item.label}
                          {item.active && item.value && (
                            <span style={{ color: "var(--muted)", marginLeft: 6, fontSize: 12 }}>{item.value}</span>
                          )}
                        </span>
                      </label>
                    ) : (
                      <div style={{ display: "flex", alignItems: "baseline", gap: 8, opacity: item.active || item.onEdit ? 1 : 0.38 }}>
                        <span style={{ fontSize: 13, color: item.active ? (item.always ? "var(--muted)" : "var(--success)") : "var(--muted)", flexShrink: 0 }}>
                          {item.active ? (item.always ? "·" : "✓") : (item.onEdit ? "·" : "—")}
                        </span>
                        <span style={{ fontSize: 13, color: item.active ? "var(--text)" : "var(--muted)" }}>
                          {item.label}
                          {item.active && item.value && (
                            <span style={{ color: "var(--muted)", marginLeft: 6, fontSize: 12 }}>{item.value}</span>
                          )}
                        </span>
                      </div>
                    )}
                    {item.onEdit && (item.active || !item.onToggle) && (
                      <input
                        value={item.editValue ?? ""}
                        onChange={(e) => item.onEdit!(e.target.value)}
                        placeholder={item.editPlaceholder}
                        style={{
                          width: "100%", marginTop: 5,
                          background: "var(--bg)", border: "1px solid var(--border)",
                          borderRadius: 8, padding: "6px 10px",
                          fontSize: 12, color: "var(--text)", outline: "none",
                          boxSizing: "border-box",
                        }}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div style={{
          padding: "14px 20px",
          borderTop: "1px solid var(--border)",
          display: "flex", gap: 10,
        }}>
          <button
            onClick={onCancel}
            style={{
              flex: 1, padding: "10px 0", borderRadius: 10,
              background: "var(--surface2)", border: "1px solid var(--border)",
              color: "var(--muted)", fontSize: 14, cursor: "pointer", fontWeight: 600,
            }}
          >
            Cancelar y editar
          </button>
          <button
            onClick={onConfirm}
            style={{
              flex: 2, padding: "10px 0", borderRadius: 10,
              background: "var(--accent)", border: "none",
              color: "#fff", fontSize: 14, cursor: "pointer", fontWeight: 700,
            }}
          >
            Confirmar y generar
          </button>
        </div>
      </div>
    </div>
  );
}

function JobPanel({
  job, logsExpanded, onToggleLogs, onDismiss, logRef,
}: {
  job: JobState;
  logsExpanded: boolean;
  onToggleLogs: () => void;
  onDismiss: () => void;
  logRef: React.RefObject<HTMLPreElement | null>;
}) {
  const st = STATUS_STYLE[job.status] || STATUS_STYLE.pending;
  const ytUploading = job.status === "completed" && job.youtube_status === "subiendo";

  return (
    <div className="mt-4 rounded-2xl overflow-hidden" style={{ border: `1px solid ${st.color}40` }}>
      <div className="flex items-center justify-between px-4 py-3"
        style={{ background: st.bg, borderBottom: `1px solid ${st.color}30` }}>
        <div className="flex items-center gap-2">
          {(job.status === "pending" || job.status === "running" || ytUploading) && (
            <span className="inline-block animate-spin text-base">⟳</span>
          )}
          <span className="text-sm font-medium" style={{ color: st.color }}>
            {ytUploading ? "Subiendo a YouTube…" : st.label}
          </span>
          <span className="text-xs" style={{ color: "var(--muted)" }}>#{job.id}</span>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={onToggleLogs} className="text-xs px-2 py-1 rounded"
            style={{ color: "var(--muted)", background: "var(--surface2)" }}>
            {logsExpanded ? "Ocultar log" : "Ver log"}
          </button>
          {(job.status === "completed" || job.status === "failed") && (
            <button type="button" onClick={onDismiss} className="text-xs px-2 py-1 rounded"
              style={{ color: "var(--muted)", background: "var(--surface2)" }}>
              ✕
            </button>
          )}
        </div>
      </div>

      {logsExpanded && (
        <pre ref={logRef} className="text-xs p-4 overflow-auto whitespace-pre-wrap"
          style={{ background: "#050408", color: "#c8c0e0", maxHeight: "300px", fontFamily: "ui-monospace, monospace" }}>
          {job.logs || (job.status === "pending" ? "Esperando inicio…" : "Sin logs aún…")}
        </pre>
      )}

      {job.status === "completed" && job.output_files.length > 0 && (
        <div className="p-4 space-y-3" style={{ background: "var(--surface)" }}>
          {job.output_files.map((filename) => (
            <div key={filename} className="space-y-3">
              <video src={`/videos/${filename}`} controls className="w-full rounded-xl"
                style={{ background: "#000", maxHeight: "500px" }} />
              <a href={`/videos/${filename}`} download className="block text-center text-sm py-2 rounded-lg font-medium"
                style={{ background: "var(--accent)", color: "#fff" }}>
                ↓ Descargar
              </a>
            </div>
          ))}
        </div>
      )}

      {job.status === "completed" && job.attribution && (
        <AttributionPanel attribution={job.attribution} />
      )}

      {/* Panel YouTube */}
      {job.subir_youtube && job.status === "completed" && (
        <div style={{ padding: "12px 16px", borderTop: "1px solid var(--border)", background: "var(--surface)" }}>
          <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", marginBottom: 8 }}>
            YouTube
          </p>
          {job.youtube_status === "subiendo" && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#60a5fa" }}>
              <span className="animate-spin">⟳</span> Subiendo el video al canal…
            </div>
          )}
          {job.youtube_status === "ok" && job.youtube_url && (
            <a href={job.youtube_url} target="_blank" rel="noopener noreferrer"
              style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#4ade80", fontWeight: 600, textDecoration: "none" }}>
              ✓ Publicado en YouTube →
              <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 280 }}>
                {job.youtube_url}
              </span>
            </a>
          )}
          {job.youtube_status === "error" && (
            <div style={{ fontSize: 12, color: "#f87171" }}>
              ⚠️ Error al subir a YouTube{job.youtube_error ? `: ${job.youtube_error}` : ""}
            </div>
          )}
        </div>
      )}

      {job.status === "failed" && (
        <div className="px-4 py-3 space-y-2" style={{ background: "var(--surface)" }}>
          {!logsExpanded && (
            <p className="text-xs" style={{ color: "var(--error)" }}>
              {job.logs.includes("No se pudo extraer suficiente texto")
                ? "El sitio web bloqueó la descarga del artículo. Prueba pegando el texto directamente en modo Texto."
                : job.logs.includes("No se pudo descargar")
                ? "No se pudo acceder a la URL. Prueba con modo Texto pegando el contenido."
                : "Algo salió mal. Abre el log para ver el detalle."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Panel de atribución de fuente ─────────────────────────────────────────────
function AttributionPanel({ attribution }: { attribution: Attribution }) {
  const [copied, setCopied] = useState(false);
  const [tipo, setTipo] = useState<"noticia" | "curiosidad">("noticia");

  const campos = [
    attribution.fuente            && { icon: "📰", label: "Fuente",   value: attribution.fuente },
    attribution.autor             && { icon: "✍️",  label: "Autor",    value: attribution.autor },
    attribution.fecha_publicacion && { icon: "📅", label: "Fecha",    value: attribution.fecha_publicacion.slice(0, 10) },
    attribution.seccion           && { icon: "📂", label: "Sección",  value: attribution.seccion },
  ].filter(Boolean) as { icon: string; label: string; value: string }[];

  if (!campos.length && !attribution.url_original) return null;

  function buildYouTubeDesc(): string {
    const titulo   = attribution.titulo_original || "";
    const fuente   = attribution.fuente || "";
    const autor    = attribution.autor || "";
    const fecha    = (attribution.fecha_publicacion || "").slice(0, 10);
    const seccion  = attribution.seccion || "";
    const url      = attribution.url_original || "";
    const desc     = attribution.descripcion || "";
    const fueteTag = fuente.replace(/[^a-zA-ZáéíóúÁÉÍÓÚñÑ]/g, "");

    const encabezado = tipo === "noticia"
      ? `🔴 ÚLTIMA HORA: ${titulo}`
      : `💡 ¿LO SABÍAS? ${titulo}`;

    const bloqueAtrib = [
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
      "📰 FUENTE ORIGINAL",
      fuente   ? `Medio:     ${fuente}`   : "",
      autor    ? `Autor:     ${autor}`    : "",
      fecha    ? `Publicado: ${fecha}`    : "",
      seccion  ? `Sección:   ${seccion}`  : "",
      url      ? `🔗 ${url}`             : "",
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ].filter(Boolean).join("\n");

    const hashTags = tipo === "noticia"
      ? `#Noticias #UltimaHora #NoticiasVerificadas${fueteTag ? ` #${fueteTag}` : ""}`
      : `#Curiosidades #SabíasQue #DatosInteresantes${fueteTag ? ` #${fueteTag}` : ""}`;

    return [
      encabezado,
      "",
      desc || "",
      desc ? "" : null,
      bloqueAtrib,
      "",
      "⚠️ Este vídeo es un resumen informativo. Los derechos del contenido",
      "original pertenecen al medio citado arriba.",
      "",
      "─────────────────────────────────",
      "🔔 SUSCRÍBETE para no perderte las últimas noticias verificadas",
      "👍 Dale like si te ha resultado útil",
      "─────────────────────────────────",
      "",
      hashTags,
    ].filter((l) => l !== null).join("\n");
  }

  function handleCopy() {
    const text = buildYouTubeDesc();
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    });
  }

  return (
    <div style={{ padding: "12px 16px", borderTop: "1px solid var(--border)", background: "var(--surface)" }}>
      <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", marginBottom: 8 }}>
        Fuente original
      </p>

      {/* Metadatos */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 12 }}>
        {campos.map(({ icon, label, value }) => (
          <div key={label} style={{ display: "flex", gap: 6, fontSize: 12 }}>
            <span>{icon}</span>
            <span style={{ color: "var(--muted)" }}>{label}:</span>
            <span style={{ color: "var(--text)" }}>{value}</span>
          </div>
        ))}
        {attribution.url_original && (
          <div style={{ display: "flex", gap: 6, fontSize: 12 }}>
            <span>🔗</span>
            <a href={attribution.url_original} target="_blank" rel="noopener noreferrer"
              style={{ color: "var(--accent)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 340 }}>
              {attribution.url_original}
            </a>
          </div>
        )}
        {attribution.url_autor && (
          <div style={{ display: "flex", gap: 6, fontSize: 12 }}>
            <span>👤</span>
            <a href={attribution.url_autor} target="_blank" rel="noopener noreferrer"
              style={{ color: "var(--accent)" }}>
              Perfil del autor
            </a>
          </div>
        )}
      </div>

      {/* Selector de tipo para la descripción */}
      <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)", marginBottom: 6 }}>
        Descripción para YouTube
      </p>
      <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        {(["noticia", "curiosidad"] as const).map((t) => {
          const info = t === "noticia" ? { icon: "📰", label: "Noticia" } : { icon: "💡", label: "Curiosidad" };
          return (
            <button key={t} type="button" onClick={() => setTipo(t)}
              style={{ flex: 1, padding: "5px 0", borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: "pointer", border: `1px solid ${tipo === t ? "var(--accent)" : "var(--border)"}`, background: tipo === t ? "rgba(99,102,241,0.12)" : "var(--surface2)", color: tipo === t ? "var(--accent)" : "var(--muted)" }}>
              {info.icon} {info.label}
            </button>
          );
        })}
      </div>

      {/* Preview de la descripción */}
      <pre style={{ fontSize: 10, color: "var(--muted)", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 7, padding: "8px 10px", maxHeight: 160, overflowY: "auto", whiteSpace: "pre-wrap", marginBottom: 8, fontFamily: "ui-monospace, monospace", lineHeight: 1.5 }}>
        {buildYouTubeDesc()}
      </pre>

      <button
        onClick={handleCopy}
        style={{ width: "100%", padding: "8px 0", borderRadius: 8, fontSize: 12, cursor: "pointer", background: copied ? "#0a2a1a" : "var(--accent)", border: `1px solid ${copied ? "var(--success)" : "transparent"}`, color: copied ? "var(--success)" : "#fff", fontWeight: 700 }}
      >
        {copied ? "✓ Copiado al portapapeles" : "📋 Copiar descripción para YouTube Studio"}
      </button>
    </div>
  );
}

// ── Componentes pequeños ───────────────────────────────────────────────────────
function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <div
      onClick={() => onChange(!value)}
      style={{
        width: 40, height: 22, borderRadius: 11,
        background: value ? "var(--accent)" : "var(--surface2)",
        border: "1px solid var(--border)",
        position: "relative", transition: "background 0.2s",
        flexShrink: 0, cursor: "pointer",
      }}
    >
      <div style={{
        position: "absolute", top: 3, left: value ? 20 : 3,
        width: 14, height: 14, borderRadius: "50%",
        background: "#fff", transition: "left 0.2s",
      }} />
    </div>
  );
}

function Field({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <label className="block text-sm font-medium mb-1.5" style={{ color: "var(--muted)" }}>{label}</label>
      {children}
    </div>
  );
}

function TextInput({ value, onChange, placeholder, required = false }: {
  value: string; onChange: (v: string) => void; placeholder?: string; required?: boolean;
}) {
  return (
    <input
      type="text" value={value} placeholder={placeholder} required={required}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-lg px-3 py-2 text-sm"
      style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", outline: "none" }}
    />
  );
}

function SelectInput({ value, onChange, options }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-lg px-3 py-2 text-sm"
      style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", outline: "none" }}
    >
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}
