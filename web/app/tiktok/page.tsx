"use client";

// Publicar en TikTok (Content Posting API · Direct Post) siguiendo las normas de
// UX que TikTok revisa antes de aprobar la app:
//  - se muestra la cuenta (creator_info) antes de publicar
//  - privacidad SIN valor por defecto, con las opciones que permite la cuenta
//  - comentarios / dúo / stitch desmarcados; en gris si la cuenta los tiene desactivados
//  - declaración de contenido comercial (Tu marca / Contenido de marca)
//  - aviso de la Music Usage Confirmation (y Branded Content Policy si aplica)
//  - vista previa del vídeo y estado de la publicación tras enviarla

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

interface Creator {
  creator_avatar_url?: string;
  creator_username?: string;
  creator_nickname?: string;
  privacy_level_options?: string[];
  comment_disabled?: boolean;
  duet_disabled?: boolean;
  stitch_disabled?: boolean;
  max_video_post_duration_sec?: number;
}

interface Estado {
  servicio: boolean;
  conectado: boolean;
  connect_url: string;
  api_key?: boolean;
  creator?: Creator;
  error?: string;
}

interface VideoFile {
  filename: string;
  size: number;
  modified: string;
}

type Lang = "es" | "en";

const T = {
  es: {
    title: "Publicar en TikTok",
    subtitle: "Conecta tu cuenta, elige un vídeo, escribe el texto, elige la privacidad y publica.",
    account: "1 · Cuenta de TikTok",
    connect: "Conectar con TikTok",
    connecting: "Abriendo TikTok…",
    disconnect: "Desconectar",
    notConnected: "No hay ninguna cuenta de TikTok conectada.",
    postingAs: "Publicarás como",
    noKey: "Falta la API Key del servicio (TIKTOK_API_KEY). Añádela en Canales → TikTok.",
    noService: "El servicio de TikTok no responde.",
    connectedOk: "Cuenta de TikTok conectada.",
    connectError: "TikTok no autorizó la conexión",
    video: "2 · Elige un vídeo",
    noVideos: "No hay vídeos generados todavía.",
    tooLong: (max: number) => `Este vídeo supera la duración máxima que permite tu cuenta (${max} s).`,
    details: "3 · Texto y privacidad",
    caption: "Texto del vídeo",
    captionPh: "Escribe el texto y los hashtags…",
    whoCanView: "Quién puede ver este vídeo",
    choosePrivacy: "Selecciona la privacidad…",
    privacy: {
      PUBLIC_TO_EVERYONE: "Todo el mundo",
      MUTUAL_FOLLOW_FRIENDS: "Amigos",
      FOLLOWER_OF_CREATOR: "Seguidores",
      SELF_ONLY: "Solo yo",
    } as Record<string, string>,
    brandedNotPrivate: "La visibilidad del contenido de marca no puede ser «Solo yo».",
    allowUsers: "Permitir a los usuarios",
    comment: "Comentar",
    duet: "Dúo",
    stitch: "Stitch",
    disabledByAccount: "desactivado en tu cuenta de TikTok",
    commercial: "Divulgar contenido del vídeo",
    commercialHelp: "Actívalo si este vídeo promociona a ti, a una marca, un producto o un servicio.",
    yourBrand: "Tu marca",
    yourBrandHelp: "Te promocionas a ti o a tu propio negocio.",
    branded: "Contenido de marca",
    brandedHelp: "Promocionas otra marca o a un tercero.",
    labelPromo: "Tu vídeo se etiquetará como «Contenido promocional».",
    labelPaid: "Tu vídeo se etiquetará como «Colaboración pagada».",
    chooseOne: "Elige al menos una opción para continuar.",
    agreeMusic: ["Al publicar, aceptas la ", "Confirmación de uso de música", " de TikTok."],
    agreeBranded: ["Al publicar, aceptas la ", "Política de contenido de marca", " y la ", "Confirmación de uso de música", " de TikTok."],
    publish: "Publicar en TikTok",
    publishing: "Subiendo a TikTok…",
    processing: "Tu vídeo se ha enviado. TikTok lo está procesando; puede tardar unos minutos en aparecer en tu perfil.",
    done: "¡Publicado! Ya está en tu perfil de TikTok.",
    failed: "TikTok no pudo publicar el vídeo",
    status: "Estado",
    sandbox: "Modo Sandbox: la app aún no está aprobada, así que TikTok publica el vídeo en privado.",
  },
  en: {
    title: "Post to TikTok",
    subtitle: "Connect your account, pick a video, write the caption, choose the privacy and post.",
    account: "1 · TikTok account",
    connect: "Continue with TikTok",
    connecting: "Opening TikTok…",
    disconnect: "Disconnect",
    notConnected: "No TikTok account connected.",
    postingAs: "Posting as",
    noKey: "Missing the service API key (TIKTOK_API_KEY). Add it in Channels → TikTok.",
    noService: "The TikTok service is not responding.",
    connectedOk: "TikTok account connected.",
    connectError: "TikTok did not authorize the connection",
    video: "2 · Choose a video",
    noVideos: "No generated videos yet.",
    tooLong: (max: number) => `This video is longer than your account allows (${max} s).`,
    details: "3 · Caption and privacy",
    caption: "Caption",
    captionPh: "Write the caption and hashtags…",
    whoCanView: "Who can view this video",
    choosePrivacy: "Select privacy…",
    privacy: {
      PUBLIC_TO_EVERYONE: "Everyone",
      MUTUAL_FOLLOW_FRIENDS: "Friends",
      FOLLOWER_OF_CREATOR: "Followers",
      SELF_ONLY: "Only me",
    } as Record<string, string>,
    brandedNotPrivate: "Branded content visibility cannot be set to private.",
    allowUsers: "Allow users to",
    comment: "Comment",
    duet: "Duet",
    stitch: "Stitch",
    disabledByAccount: "disabled in your TikTok settings",
    commercial: "Disclose video content",
    commercialHelp: "Turn on to disclose that this video promotes goods or services in exchange for something of value.",
    yourBrand: "Your brand",
    yourBrandHelp: "You are promoting yourself or your own business.",
    branded: "Branded content",
    brandedHelp: "You are promoting another brand or a third party.",
    labelPromo: "Your photo/video will be labeled as 'Promotional content'.",
    labelPaid: "Your photo/video will be labeled as 'Paid partnership'.",
    chooseOne: "You need to indicate if your content promotes yourself, a third party, or both.",
    agreeMusic: ["By posting, you agree to TikTok's ", "Music Usage Confirmation", "."],
    agreeBranded: ["By posting, you agree to TikTok's ", "Branded Content Policy", " and ", "Music Usage Confirmation", "."],
    publish: "Post to TikTok",
    publishing: "Uploading to TikTok…",
    processing: "Your video was sent. TikTok is processing it; it may take a few minutes to appear on your profile.",
    done: "Posted! It is now on your TikTok profile.",
    failed: "TikTok could not post the video",
    status: "Status",
    sandbox: "Sandbox mode: the app is not approved yet, so TikTok posts the video privately.",
  },
};

const MUSIC_URL = "https://www.tiktok.com/legal/page/global/music-usage-confirmation/en";
const BRANDED_URL = "https://www.tiktok.com/legal/page/global/bc-policy/en";

const card: React.CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 14,
  padding: 20,
  marginBottom: 16,
};
const h2: React.CSSProperties = {
  fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em",
  color: "var(--muted)", margin: "0 0 14px",
};
const btn: React.CSSProperties = {
  background: "var(--accent)", color: "#fff", border: 0, borderRadius: 10,
  padding: "10px 18px", fontWeight: 600, cursor: "pointer",
};
const btnGhost: React.CSSProperties = {
  background: "transparent", color: "var(--muted)", border: "1px solid var(--border)",
  borderRadius: 10, padding: "8px 14px", cursor: "pointer",
};

function TikTokPage() {
  const params = useSearchParams();
  const router = useRouter();
  // Idioma en la URL (/tiktok?lang=en) para grabar la demo en inglés
  const lang: Lang = params.get("lang") === "en" ? "en" : "es";
  const t = T[lang];

  // Vuelta desde TikTok tras autorizar (?tiktok=ok|error)
  const vuelta = params.get("tiktok");
  const aviso = vuelta === "ok"
    ? { ok: true, msg: t.connectedOk }
    : vuelta === "error"
      ? { ok: false, msg: `${t.connectError}: ${params.get("motivo") || ""}` }
      : null;

  const [estado, setEstado] = useState<Estado | null>(null);
  const [connecting, setConnecting] = useState(false);

  const [videos, setVideos] = useState<VideoFile[]>([]);
  const [video, setVideo] = useState<string | null>(null);
  const [duracion, setDuracion] = useState<number | null>(null);

  const [caption, setCaption] = useState("");
  const [privacy, setPrivacy] = useState("");
  const [allowComment, setAllowComment] = useState(false);
  const [allowDuet, setAllowDuet] = useState(false);
  const [allowStitch, setAllowStitch] = useState(false);
  const [disclose, setDisclose] = useState(false);
  const [yourBrand, setYourBrand] = useState(false);
  const [branded, setBranded] = useState(false);

  const [enviando, setEnviando] = useState(false);
  const [publishId, setPublishId] = useState<string | null>(null);
  const [pubStatus, setPubStatus] = useState<string | null>(null);
  const [pubError, setPubError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const cargarEstado = useCallback(() => {
    fetch("/api/tiktok/estado")
      .then((r) => r.json())
      .then(setEstado)
      .catch(() => setEstado({ servicio: false, conectado: false, connect_url: "" }));
  }, []);

  useEffect(() => {
    cargarEstado();
    fetch("/api/output")
      .then((r) => r.json())
      .then((v: VideoFile[]) => setVideos(v.filter((x) => x.filename.endsWith(".mp4"))))
      .catch(() => {});
  }, [cargarEstado]);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const creator = estado?.creator;
  const opciones = creator?.privacy_level_options || [];
  const maxDur = creator?.max_video_post_duration_sec;
  const demasiadoLargo = !!(maxDur && duracion && duracion > maxDur);

  const comercialOk = !disclose || yourBrand || branded;
  const puedePublicar =
    !!estado?.conectado && !!creator && !!video && !!privacy && comercialOk && !demasiadoLargo && !enviando && !publishId;

  function cambiarIdioma(l: Lang) {
    router.replace(l === "en" ? "/tiktok?lang=en" : "/tiktok");
  }

  function conectar() {
    if (!estado?.connect_url) return;
    setConnecting(true);
    // Volver a esta misma página (y en el mismo idioma) tras autorizar en TikTok
    const url = new URL(estado.connect_url);
    url.searchParams.set("return", `${window.location.origin}/tiktok${lang === "en" ? "?lang=en" : ""}`);
    window.location.href = url.toString();
  }

  async function desconectar() {
    await fetch("/api/tiktok/desconectar", { method: "POST" }).catch(() => {});
    cambiarIdioma(lang);
    cargarEstado();
  }

  function elegirVideo(f: string) {
    setVideo(f);
    setDuracion(null);
    setPublishId(null);
    setPubStatus(null);
    setPubError(null);
  }

  async function publicar() {
    if (!puedePublicar || !video) return;
    setEnviando(true);
    setPubError(null);
    try {
      const r = await fetch("/api/tiktok/publicar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: video,
          titulo: caption,
          privacy_level: privacy,
          allow_comment: allowComment,
          allow_duet: allowDuet,
          allow_stitch: allowStitch,
          brand_organic: disclose && yourBrand,
          brand_content: disclose && branded,
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || r.statusText);
      setPublishId(data.publish_id);
      setPubStatus("PROCESSING_UPLOAD");
      pollRef.current = setInterval(async () => {
        try {
          const s = await fetch(`/api/tiktok/publicacion/${data.publish_id}`).then((x) => x.json());
          if (s.status) setPubStatus(s.status);
          if (s.status === "FAILED") setPubError(s.fail_reason || "FAILED");
          if (s.status === "PUBLISH_COMPLETE" || s.status === "FAILED") {
            if (pollRef.current) clearInterval(pollRef.current);
          }
        } catch {}
      }, 3000);
    } catch (e) {
      setPubError(e instanceof Error ? e.message : String(e));
    } finally {
      setEnviando(false);
    }
  }

  const agree = disclose && branded ? t.agreeBranded : t.agreeMusic;

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "32px 16px 64px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 26, fontWeight: 700, margin: 0 }}>{t.title}</h1>
          <p style={{ color: "var(--muted)", margin: "6px 0 20px" }}>{t.subtitle}</p>
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {(["es", "en"] as Lang[]).map((l) => (
            <button key={l} onClick={() => cambiarIdioma(l)}
              style={{ ...btnGhost, padding: "4px 10px", fontSize: 12,
                color: lang === l ? "var(--text)" : "var(--muted)",
                borderColor: lang === l ? "var(--accent)" : "var(--border)" }}>
              {l.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {aviso && (
        <div style={{ ...card, padding: 12, display: "flex", justifyContent: "space-between", gap: 12,
          borderColor: aviso.ok ? "var(--success)" : "var(--error)", color: aviso.ok ? "var(--success)" : "var(--error)" }}>
          {aviso.msg}
          <button onClick={() => cambiarIdioma(lang)} style={{ background: "none", border: 0, color: "inherit", cursor: "pointer" }}>✕</button>
        </div>
      )}

      {/* 1 · Cuenta */}
      <section style={card}>
        <h2 style={h2}>{t.account}</h2>
        {!estado ? (
          <p style={{ color: "var(--muted)" }}>…</p>
        ) : !estado.servicio ? (
          <p style={{ color: "var(--error)" }}>{t.noService} {estado.error}</p>
        ) : !estado.conectado ? (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
            <span style={{ color: "var(--muted)" }}>{t.notConnected}</span>
            <button style={{ ...btn, background: "#000", border: "1px solid #333" }} onClick={conectar} disabled={connecting}>
              {connecting ? t.connecting : `♪ ${t.connect}`}
            </button>
          </div>
        ) : !estado.api_key ? (
          <p style={{ color: "var(--warning)" }}>{t.noKey}</p>
        ) : creator ? (
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            {creator.creator_avatar_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={creator.creator_avatar_url} alt="" width={48} height={48}
                style={{ borderRadius: "50%", border: "1px solid var(--border)" }} />
            )}
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, color: "var(--muted)" }}>{t.postingAs}</div>
              <div style={{ fontWeight: 700 }}>
                {creator.creator_nickname}
                {creator.creator_username && (
                  <span style={{ color: "var(--muted)", fontWeight: 400 }}> @{creator.creator_username}</span>
                )}
              </div>
            </div>
            <button style={btnGhost} onClick={desconectar}>{t.disconnect}</button>
          </div>
        ) : (
          <p style={{ color: "var(--error)" }}>{estado.error}</p>
        )}
      </section>

      {/* 2 · Vídeo */}
      <section style={card}>
        <h2 style={h2}>{t.video}</h2>
        {videos.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>{t.noVideos}</p>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 200px", gap: 16 }}>
            <div style={{ maxHeight: 360, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
              {videos.map((v) => (
                <button key={v.filename} onClick={() => elegirVideo(v.filename)}
                  style={{ textAlign: "left", background: video === v.filename ? "var(--surface2)" : "transparent",
                    border: `1px solid ${video === v.filename ? "var(--accent)" : "var(--border)"}`,
                    borderRadius: 10, padding: "8px 12px", color: "var(--text)", cursor: "pointer" }}>
                  <div style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {v.filename.replace(/_reel\.mp4$/, "").replace(/[-_]+/g, " ")}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--muted)" }}>
                    {(v.size / 1024 / 1024).toFixed(1)} MB · {new Date(v.modified).toLocaleString(lang === "es" ? "es-ES" : "en-GB",
                      { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                  </div>
                </button>
              ))}
            </div>
            <div>
              {video ? (
                <video key={video} src={`/videos/${encodeURIComponent(video)}`} controls playsInline
                  onLoadedMetadata={(e) => setDuracion(e.currentTarget.duration)}
                  style={{ width: "100%", aspectRatio: "9 / 16", background: "#000", borderRadius: 10 }} />
              ) : (
                <div style={{ width: "100%", aspectRatio: "9 / 16", borderRadius: 10, border: "1px dashed var(--border)" }} />
              )}
            </div>
          </div>
        )}
        {demasiadoLargo && maxDur && <p style={{ color: "var(--error)", marginTop: 10 }}>{t.tooLong(maxDur)}</p>}
      </section>

      {/* 3 · Texto, privacidad, interacciones, contenido comercial */}
      <section style={card}>
        <h2 style={h2}>{t.details}</h2>

        <label style={{ fontSize: 13, fontWeight: 600 }}>{t.caption}</label>
        <textarea value={caption} onChange={(e) => setCaption(e.target.value.slice(0, 2200))}
          placeholder={t.captionPh} rows={4}
          style={{ width: "100%", marginTop: 6, background: "var(--surface2)", color: "var(--text)",
            border: "1px solid var(--border)", borderRadius: 10, padding: 10, resize: "vertical" }} />
        <div style={{ fontSize: 11, color: "var(--muted)", textAlign: "right" }}>{caption.length}/2200</div>

        <label style={{ fontSize: 13, fontWeight: 600, display: "block", marginTop: 14 }}>{t.whoCanView}</label>
        <select value={privacy} onChange={(e) => setPrivacy(e.target.value)} disabled={!creator}
          style={{ width: "100%", marginTop: 6, background: "var(--surface2)", color: privacy ? "var(--text)" : "var(--muted)",
            border: `1px solid ${privacy ? "var(--border)" : "var(--warning)"}`, borderRadius: 10, padding: 10 }}>
          <option value="" disabled>{t.choosePrivacy}</option>
          {opciones.map((o) => {
            const bloqueado = o === "SELF_ONLY" && disclose && branded;
            return (
              <option key={o} value={o} disabled={bloqueado} title={bloqueado ? t.brandedNotPrivate : ""}>
                {t.privacy[o] || o}{bloqueado ? ` — ${t.brandedNotPrivate}` : ""}
              </option>
            );
          })}
        </select>

        <div style={{ fontSize: 13, fontWeight: 600, marginTop: 16 }}>{t.allowUsers}</div>
        <div style={{ display: "flex", gap: 20, marginTop: 8, flexWrap: "wrap" }}>
          {([
            [t.comment, allowComment, setAllowComment, creator?.comment_disabled],
            [t.duet, allowDuet, setAllowDuet, creator?.duet_disabled],
            [t.stitch, allowStitch, setAllowStitch, creator?.stitch_disabled],
          ] as [string, boolean, (v: boolean) => void, boolean | undefined][]).map(([label, val, set, off]) => (
            <label key={label} title={off ? t.disabledByAccount : ""}
              style={{ display: "flex", alignItems: "center", gap: 6, opacity: off ? 0.4 : 1, cursor: off ? "not-allowed" : "pointer" }}>
              <input type="checkbox" checked={!off && val} disabled={!creator || off}
                onChange={(e) => set(e.target.checked)} />
              {label}
              {off && <span style={{ fontSize: 11, color: "var(--muted)" }}>({t.disabledByAccount})</span>}
            </label>
          ))}
        </div>

        <div style={{ borderTop: "1px solid var(--border)", marginTop: 18, paddingTop: 16 }}>
          <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, cursor: "pointer" }}>
            <span>
              <span style={{ fontWeight: 600 }}>{t.commercial}</span>
              <span style={{ display: "block", fontSize: 12, color: "var(--muted)" }}>{t.commercialHelp}</span>
            </span>
            <input type="checkbox" checked={disclose} disabled={!creator}
              onChange={(e) => { setDisclose(e.target.checked); if (!e.target.checked) { setYourBrand(false); setBranded(false); } }}
              style={{ width: 20, height: 20 }} />
          </label>

          {disclose && (
            <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>
              <label style={{ display: "flex", gap: 8, cursor: "pointer" }}>
                <input type="checkbox" checked={yourBrand} onChange={(e) => setYourBrand(e.target.checked)} />
                <span>{t.yourBrand}<span style={{ display: "block", fontSize: 12, color: "var(--muted)" }}>{t.yourBrandHelp}</span></span>
              </label>
              <label style={{ display: "flex", gap: 8, cursor: "pointer" }}>
                <input type="checkbox" checked={branded} onChange={(e) => {
                  setBranded(e.target.checked);
                  // El contenido de marca no puede ser privado
                  if (e.target.checked && privacy === "SELF_ONLY") setPrivacy("");
                }} />
                <span>{t.branded}<span style={{ display: "block", fontSize: 12, color: "var(--muted)" }}>{t.brandedHelp}</span></span>
              </label>
              <div style={{ fontSize: 13, color: comercialOk ? "var(--accent)" : "var(--warning)" }}>
                {!comercialOk ? t.chooseOne : branded ? t.labelPaid : t.labelPromo}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Publicar */}
      <section style={card}>
        <p style={{ fontSize: 13, color: "var(--muted)", marginTop: 0 }}>
          {agree.length === 3 ? (
            <>{agree[0]}<a href={MUSIC_URL} target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>{agree[1]}</a>{agree[2]}</>
          ) : (
            <>{agree[0]}<a href={BRANDED_URL} target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>{agree[1]}</a>
              {agree[2]}<a href={MUSIC_URL} target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>{agree[3]}</a>{agree[4]}</>
          )}
        </p>
        <button onClick={publicar} disabled={!puedePublicar}
          style={{ ...btn, width: "100%", padding: 14, fontSize: 15, opacity: puedePublicar ? 1 : 0.4,
            cursor: puedePublicar ? "pointer" : "not-allowed" }}>
          {enviando ? t.publishing : t.publish}
        </button>
        <p style={{ fontSize: 11, color: "var(--muted)", marginBottom: 0 }}>{t.sandbox}</p>

        {publishId && (
          <div style={{ marginTop: 14, padding: 12, borderRadius: 10, background: "var(--surface2)" }}>
            <div style={{ color: pubStatus === "PUBLISH_COMPLETE" ? "var(--success)" : "var(--text)" }}>
              {pubStatus === "PUBLISH_COMPLETE" ? t.done : pubStatus === "FAILED" ? "" : t.processing}
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
              {t.status}: {pubStatus} · publish_id {publishId}
            </div>
          </div>
        )}
        {pubError && <p style={{ color: "var(--error)", marginBottom: 0 }}>{t.failed}: {pubError}</p>}
      </section>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <TikTokPage />
    </Suspense>
  );
}
