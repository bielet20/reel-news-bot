"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";

interface PlatformStatus {
  connected: boolean;
  canal?: string;
  display_name?: string;
  username?: string;
  bot_username?: string;
  chat_id?: string;
  ready?: boolean;
}

interface AccountsStatus {
  youtube: PlatformStatus;
  tiktok: PlatformStatus;
  instagram: PlatformStatus;
  telegram: PlatformStatus;
  whatsapp: PlatformStatus;
  x: PlatformStatus;
  facebook?: PlatformStatus & { page_name?: string };
  whatsapp_canal?: PlatformStatus & { channel_jid?: string; channel_name?: string };
}

interface CredField {
  label: string;
  secret: boolean;
  has_value: boolean;
  masked: string;
}

type AllCreds = Record<string, Record<string, CredField>>;

const OAUTH_PLATFORMS = [
  {
    id: "youtube",
    name: "YouTube Shorts",
    icon: "▶️",
    accountLabel: (s: PlatformStatus) => s.canal || "Canal conectado",
    credFields: [
      { key: "client_id", label: "Client ID", secret: false },
      { key: "client_secret", label: "Client Secret", secret: true },
    ],
    setupSteps: [
      "Ve a console.cloud.google.com y crea un proyecto",
      'Activa "YouTube Data API v3" en APIs y Servicios',
      'Crea credenciales OAuth → Aplicación de escritorio',
      "Introduce el Client ID y Client Secret a continuación",
    ],
    setupLink: "https://console.cloud.google.com/",
    setupLinkLabel: "Google Cloud Console →",
  },
  {
    id: "tiktok",
    name: "TikTok",
    icon: "🎵",
    accountLabel: (s: PlatformStatus) => `@${s.display_name || "usuario"}`,
    credFields: [
      { key: "client_key", label: "Client Key", secret: false },
      { key: "client_secret", label: "Client Secret", secret: true },
    ],
    setupSteps: [
      "Ve a developers.tiktok.com y crea una app",
      'Añade el producto "Content Posting API"',
      "Configura Redirect URI: http://localhost:8000/api/accounts/tiktok/callback",
      "Introduce Client Key y Client Secret a continuación",
    ],
    setupLink: "https://developers.tiktok.com/",
    setupLinkLabel: "TikTok for Developers →",
  },
  {
    id: "instagram",
    name: "Instagram Reels",
    icon: "📸",
    accountLabel: (s: PlatformStatus) => `@${s.username || "usuario"}`,
    credFields: [
      { key: "app_id", label: "App ID", secret: false },
      { key: "app_secret", label: "App Secret", secret: true },
    ],
    setupSteps: [
      "Ve a developers.facebook.com y crea una app (tipo Business)",
      'Añade el producto "Instagram Graph API"',
      "Configura Redirect URI: http://localhost:8000/api/accounts/instagram/callback",
      "Necesitas una cuenta Instagram Business vinculada a una página de Facebook",
      "Introduce App ID y App Secret a continuación",
    ],
    setupLink: "https://developers.facebook.com/",
    setupLinkLabel: "Meta for Developers →",
  },
];

/* ── shared styles ── */
const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  borderRadius: 8,
  fontSize: 13,
  background: "var(--bg)",
  border: "1px solid var(--border)",
  color: "var(--text)",
  outline: "none",
  boxSizing: "border-box",
};

const btnPrimary: React.CSSProperties = {
  padding: "7px 16px",
  borderRadius: 8,
  fontSize: 13,
  fontWeight: 700,
  background: "var(--accent)",
  border: "none",
  color: "#fff",
  cursor: "pointer",
};

const btnGhost: React.CSSProperties = {
  padding: "6px 12px",
  borderRadius: 8,
  fontSize: 12,
  background: "var(--surface2)",
  border: "1px solid var(--border)",
  color: "var(--muted)",
  cursor: "pointer",
};

function CanalesContent() {
  const searchParams = useSearchParams();

  const [status, setStatus] = useState<AccountsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "error" } | null>(null);
  const [expandedSetup, setExpandedSetup] = useState<string | null>(null);

  // Telegram/X forms (existing connect flow)
  const [tgToken, setTgToken] = useState("");
  const [tgChatId, setTgChatId] = useState("");
  const [xApiKey, setXApiKey] = useState("");
  const [xApiSecret, setXApiSecret] = useState("");
  const [xAccessToken, setXAccessToken] = useState("");
  const [xAccessSecret, setXAccessSecret] = useState("");

  // WhatsApp QR
  const [waQr, setWaQr] = useState<string | null>(null);
  const [waQrLoading, setWaQrLoading] = useState(false);

  // Facebook
  const [fbPageId, setFbPageId] = useState("");
  const [fbAccessToken, setFbAccessToken] = useState("");

  // WhatsApp Canal
  const [waChannels, setWaChannels] = useState<{ jid: string; name: string; exact?: boolean }[]>([]);
  const [waChannelsLoading, setWaChannelsLoading] = useState(false);
  const [waSelectedJid, setWaSelectedJid] = useState("");
  const [waInviteUrl, setWaInviteUrl] = useState("");

  // ── Admin password ──────────────────────────────────────────
  const [adminConfigured, setAdminConfigured] = useState(false);
  const [showAdminForm, setShowAdminForm] = useState(false);
  const [adminNewPw, setAdminNewPw] = useState("");
  const [adminConfirmPw, setAdminConfirmPw] = useState("");
  const [adminCurrentPw, setAdminCurrentPw] = useState("");
  const [adminSaving, setAdminSaving] = useState(false);

  // ── Credentials state ───────────────────────────────────────
  const [allCreds, setAllCreds] = useState<AllCreds>({});
  const [openCredsPanel, setOpenCredsPanel] = useState<string | null>(null);
  // edit
  const [editCredsFor, setEditCredsFor] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [savingCreds, setSavingCreds] = useState(false);
  // reveal
  const [revealFor, setRevealFor] = useState<string | null>(null);
  const [revealPw, setRevealPw] = useState("");
  const [revealLoading, setRevealLoading] = useState(false);
  const [revealError, setRevealError] = useState<string | null>(null);
  const [revealedValues, setRevealedValues] = useState<Record<string, Record<string, string>>>({});

  const showToast = (msg: string, type: "ok" | "error") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  async function fetchStatus() {
    try {
      const res = await fetch("/api/accounts/status");
      if (res.ok) setStatus(await res.json());
    } finally {
      setLoading(false);
    }
  }

  async function fetchAdminStatus() {
    try {
      const res = await fetch("/api/admin/status");
      if (res.ok) {
        const d = await res.json();
        setAdminConfigured(d.configured);
      }
    } catch {}
  }

  async function fetchCreds() {
    try {
      const res = await fetch("/api/credentials");
      if (res.ok) setAllCreds(await res.json());
    } catch {}
  }

  useEffect(() => {
    fetchStatus();
    fetchAdminStatus();
    fetchCreds();

    for (const p of ["youtube", "tiktok", "instagram", "x"]) {
      if (searchParams.get(p) === "ok") {
        showToast(`✓ ${p.charAt(0).toUpperCase() + p.slice(1)} conectado correctamente`, "ok");
      }
    }
    const errParam = searchParams.get("error");
    if (errParam) {
      const msgs: Record<string, string> = {
        youtube_no_refresh: "Error: activa el acceso offline en Google Cloud Console",
        youtube_token_failed: "Error al obtener token de YouTube. Revisa las credenciales.",
        tiktok_auth_denied: "Autorización de TikTok denegada.",
        tiktok_token_failed: "Error al obtener token de TikTok.",
        instagram_no_business_account:
          "No se encontró cuenta Instagram Business vinculada a ninguna página de Facebook.",
        instagram_token_failed: "Error al obtener token de Instagram.",
      };
      showToast(msgs[errParam] || `Error: ${errParam}`, "error");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Admin handlers ──────────────────────────────────────────

  async function handleSaveAdminPw() {
    if (adminNewPw !== adminConfirmPw) {
      showToast("Las contraseñas no coinciden", "error");
      return;
    }
    setAdminSaving(true);
    try {
      const res = await fetch("/api/admin/set-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: adminNewPw, current_password: adminCurrentPw }),
      });
      const d = await res.json();
      if (!d.ok) {
        showToast(d.error || "Error al guardar contraseña", "error");
        return;
      }
      showToast("Contraseña de admin configurada", "ok");
      setAdminConfigured(true);
      setShowAdminForm(false);
      setAdminNewPw(""); setAdminConfirmPw(""); setAdminCurrentPw("");
    } catch {
      showToast("Error de conexión", "error");
    } finally {
      setAdminSaving(false);
    }
  }

  // ── Credentials handlers ────────────────────────────────────

  function openEditCreds(platform: string) {
    setEditCredsFor(platform);
    setEditValues({});
    setRevealFor(null);
    setRevealError(null);
  }

  async function handleSaveCreds(platform: string) {
    setSavingCreds(true);
    try {
      const res = await fetch(`/api/credentials/${platform}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credentials: editValues }),
      });
      const d = await res.json();
      if (!d.ok) {
        showToast(d.error || "Error al guardar", "error");
        return;
      }
      showToast("Credenciales guardadas", "ok");
      setEditCredsFor(null);
      setEditValues({});
      setRevealedValues((prev) => ({ ...prev, [platform]: {} }));
      await fetchCreds();
    } catch {
      showToast("Error de conexión", "error");
    } finally {
      setSavingCreds(false);
    }
  }

  async function handleReveal(platform: string) {
    setRevealLoading(true);
    setRevealError(null);
    try {
      const res = await fetch(`/api/credentials/${platform}/reveal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: revealPw }),
      });
      const d = await res.json();
      if (!d.ok) {
        setRevealError(d.error || "Error");
        return;
      }
      setRevealedValues((prev) => ({ ...prev, [platform]: d.credentials }));
      setRevealFor(null);
      setRevealPw("");
    } catch {
      setRevealError("Error de conexión");
    } finally {
      setRevealLoading(false);
    }
  }

  function hideRevealed(platform: string) {
    setRevealedValues((prev) => ({ ...prev, [platform]: {} }));
    setRevealFor(null);
    setRevealPw("");
    setRevealError(null);
  }

  // ── Existing connect handlers ────────────────────────────────

  async function handleConnect(platform: string) {
    setConnecting(platform);
    try {
      const res = await fetch(`/api/accounts/${platform}/connect`);
      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail || {};
        if (detail.error === "missing_credentials") {
          showToast("Guarda las credenciales primero (Client ID y Secret)", "error");
          setOpenCredsPanel(platform);
          openEditCreds(platform);
        } else {
          showToast(detail.message || "Error al conectar", "error");
          setExpandedSetup(platform);
        }
        return;
      }
      if (data.auth_url) window.location.href = data.auth_url;
    } catch {
      showToast("Error de conexión con el servidor", "error");
    } finally {
      setConnecting(null);
    }
  }

  async function handleDisconnect(platform: string) {
    setDisconnecting(platform);
    try {
      await fetch(`/api/accounts/${platform}`, { method: "DELETE" });
      await fetchStatus();
      showToast(`Cuenta de ${platform} desvinculada`, "ok");
    } finally {
      setDisconnecting(null);
    }
  }

  async function handleTelegramConnect() {
    if (!tgToken.trim() || !tgChatId.trim()) {
      showToast("Rellena el Bot Token y el Chat ID", "error");
      return;
    }
    setConnecting("telegram");
    try {
      const res = await fetch("/api/accounts/telegram/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bot_token: tgToken.trim(), chat_id: tgChatId.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        showToast((data.detail || {}).message || "Error al conectar Telegram", "error");
        return;
      }
      showToast(`✓ Telegram conectado (@${data.bot_username})`, "ok");
      setTgToken(""); setTgChatId("");
      await fetchStatus(); await fetchCreds();
    } catch {
      showToast("Error de conexión con el servidor", "error");
    } finally {
      setConnecting(null);
    }
  }

  async function handleTelegramDisconnect() {
    setDisconnecting("telegram");
    try {
      await fetch("/api/accounts/telegram/disconnect", { method: "DELETE" });
      await fetchStatus();
      showToast("Telegram desvinculado", "ok");
    } finally {
      setDisconnecting(null);
    }
  }

  async function handleXConnect() {
    if (!xApiKey || !xApiSecret || !xAccessToken || !xAccessSecret) {
      showToast("Rellena las 4 credenciales de X", "error");
      return;
    }
    setConnecting("x");
    try {
      const res = await fetch("/api/accounts/x/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: xApiKey.trim(),
          api_secret: xApiSecret.trim(),
          access_token: xAccessToken.trim(),
          access_secret: xAccessSecret.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        showToast((data.detail || {}).message || "Error al conectar X", "error");
        return;
      }
      showToast(`✓ X conectado (@${data.username})`, "ok");
      setXApiKey(""); setXApiSecret(""); setXAccessToken(""); setXAccessSecret("");
      await fetchStatus(); await fetchCreds();
    } catch {
      showToast("Error de conexión con el servidor", "error");
    } finally {
      setConnecting(null);
    }
  }

  async function handleXDisconnect() {
    setDisconnecting("x");
    try {
      await fetch("/api/accounts/x/disconnect", { method: "DELETE" });
      await fetchStatus();
      showToast("X desvinculado", "ok");
    } finally {
      setDisconnecting(null);
    }
  }

  async function handleFacebookConnect() {
    setConnecting("facebook");
    try {
      const res = await fetch("/api/accounts/facebook/oauth-connect");
      const data = await res.json();
      if (!res.ok) {
        showToast((data.detail || {}).message || "Error al conectar Facebook", "error");
        return;
      }
      window.location.href = data.auth_url;
    } catch {
      showToast("Error de conexión con el servidor", "error");
    } finally {
      setConnecting(null);
    }
  }

  async function handleFacebookDisconnect() {
    setDisconnecting("facebook");
    try {
      await fetch("/api/accounts/facebook", { method: "DELETE" });
      await fetchStatus();
      showToast("Facebook desvinculado", "ok");
    } finally {
      setDisconnecting(null);
    }
  }

  async function loadWaChannels() {
    setWaChannelsLoading(true);
    try {
      const endpoint = waInviteUrl.trim()
        ? "/api/accounts/whatsapp-canal/find-by-url"
        : "/api/accounts/whatsapp-canal/channels";
      const opts = waInviteUrl.trim()
        ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: waInviteUrl.trim() }) }
        : undefined;
      const res = await fetch(endpoint, opts);
      if (!res.ok) {
        showToast("No se pudieron obtener los canales. ¿WhatsApp está conectado?", "error");
        return;
      }
      const data = await res.json();
      const channels = Array.isArray(data) ? data : [];
      setWaChannels(channels);
      if (channels.length === 0) {
        showToast("No se encontraron canales. Asegúrate de ser admin de algún canal de WhatsApp.", "error");
      } else {
        // Auto-select if there's an exact match
        const exact = channels.find((c: { exact?: boolean }) => c.exact);
        if (exact) setWaSelectedJid(exact.jid);
      }
    } catch {
      showToast("Error al conectar con el sidecar de WhatsApp", "error");
    } finally {
      setWaChannelsLoading(false);
    }
  }

  async function handleWaCanelConnect() {
    if (!waSelectedJid) {
      showToast("Selecciona un canal", "error");
      return;
    }
    setConnecting("whatsapp_canal");
    try {
      const canal = waChannels.find((c) => c.jid === waSelectedJid);
      const res = await fetch("/api/accounts/whatsapp-canal/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel_jid: waSelectedJid, channel_name: canal?.name || "" }),
      });
      const data = await res.json();
      if (!res.ok) {
        showToast((data.detail || {}).message || "Error al guardar canal", "error");
        return;
      }
      showToast(`✓ Canal de WhatsApp configurado`, "ok");
      setWaSelectedJid("");
      await fetchStatus();
    } catch {
      showToast("Error de conexión", "error");
    } finally {
      setConnecting(null);
    }
  }

  async function handleWaCanelDisconnect() {
    setDisconnecting("whatsapp_canal");
    try {
      await fetch("/api/accounts/whatsapp_canal", { method: "DELETE" });
      await fetchStatus();
      showToast("Canal de WhatsApp desvinculado", "ok");
    } finally {
      setDisconnecting(null);
    }
  }

  async function handleWaQr() {
    setWaQrLoading(true);
    try {
      const res = await fetch("/api/accounts/whatsapp/qr");
      if (!res.ok) {
        const data = await res.json();
        showToast(data.detail || "QR no disponible", "error");
        return;
      }
      setWaQr((await res.json()).qr || null);
    } catch {
      showToast("No se pudo obtener el QR. ¿Está corriendo el sidecar?", "error");
    } finally {
      setWaQrLoading(false);
    }
  }

  // ── Credentials panel renderer ──────────────────────────────

  function renderCredsPanel(platform: string) {
    const fields = allCreds[platform] || {};
    const isEditing = editCredsFor === platform;
    const isRevealing = revealFor === platform;
    const revealed = revealedValues[platform] || {};
    const hasAnyValue = Object.values(fields).some((f) => f.has_value);

    return (
      <div style={{
        borderTop: "1px solid var(--border)",
        background: "var(--surface2)",
        padding: "14px 20px",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <p style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", margin: 0 }}>
            CREDENCIALES API
          </p>
          <div style={{ display: "flex", gap: 6 }}>
            {!isEditing && hasAnyValue && Object.keys(revealed).length === 0 && (
              <button
                onClick={() => {
                  if (!adminConfigured) {
                    showToast("Configura la contraseña de admin primero", "error");
                    setShowAdminForm(true);
                    return;
                  }
                  setRevealFor(platform);
                  setRevealPw("");
                  setRevealError(null);
                }}
                style={{ ...btnGhost, fontSize: 11, padding: "4px 10px" }}
              >
                Revelar secretos
              </button>
            )}
            {!isEditing && Object.keys(revealed).length > 0 && (
              <button
                onClick={() => hideRevealed(platform)}
                style={{ ...btnGhost, fontSize: 11, padding: "4px 10px" }}
              >
                Ocultar
              </button>
            )}
            <button
              onClick={() => {
                if (isEditing) {
                  setEditCredsFor(null);
                  setEditValues({});
                } else {
                  openEditCreds(platform);
                }
              }}
              style={{ ...btnGhost, fontSize: 11, padding: "4px 10px" }}
            >
              {isEditing ? "Cancelar" : hasAnyValue ? "Editar" : "Introducir credenciales"}
            </button>
          </div>
        </div>

        {/* Reveal password prompt */}
        {isRevealing && (
          <div style={{
            marginBottom: 12,
            padding: "10px 12px",
            background: "var(--bg)",
            borderRadius: 8,
            border: "1px solid var(--border)",
            display: "flex",
            gap: 8,
            alignItems: "center",
          }}>
            <input
              type="password"
              placeholder="Contraseña de admin"
              value={revealPw}
              onChange={(e) => { setRevealPw(e.target.value); setRevealError(null); }}
              onKeyDown={(e) => { if (e.key === "Enter") handleReveal(platform); }}
              autoFocus
              style={{ ...inputStyle, flex: 1, padding: "6px 10px" }}
            />
            <button
              onClick={() => handleReveal(platform)}
              disabled={revealLoading || !revealPw}
              style={{ ...btnPrimary, padding: "6px 12px", fontSize: 12, opacity: revealLoading || !revealPw ? 0.5 : 1 }}
            >
              {revealLoading ? "…" : "Ver"}
            </button>
            <button
              onClick={() => { setRevealFor(null); setRevealPw(""); setRevealError(null); }}
              style={{ ...btnGhost, padding: "6px 10px", fontSize: 12 }}
            >
              ✕
            </button>
          </div>
        )}
        {revealError && revealFor === platform && (
          <p style={{ fontSize: 11, color: "var(--error)", margin: "-8px 0 10px" }}>{revealError}</p>
        )}

        {/* Fields */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {Object.entries(fields).map(([key, field]) => {
            const revealedVal = revealed[key];
            const displayVal = revealedVal ?? (field.secret ? field.masked : field.masked);

            if (isEditing) {
              return (
                <div key={key}>
                  <p style={{ fontSize: 10, color: "var(--muted)", margin: "0 0 3px", fontWeight: 600 }}>
                    {field.label} {field.has_value && <span style={{ color: "var(--success)" }}>✓ guardado</span>}
                  </p>
                  <input
                    type={field.secret ? "password" : "text"}
                    placeholder={field.has_value ? "Deja vacío para conservar el valor actual" : `Introduce ${field.label}`}
                    value={editValues[key] ?? ""}
                    onChange={(e) => setEditValues((prev) => ({ ...prev, [key]: e.target.value }))}
                    style={inputStyle}
                  />
                </div>
              );
            }

            return (
              <div key={key} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 11, color: "var(--muted)", width: 110, flexShrink: 0 }}>{field.label}</span>
                {field.has_value ? (
                  <span style={{
                    fontFamily: "monospace",
                    fontSize: 12,
                    color: revealedVal ? "var(--text)" : "var(--muted)",
                    letterSpacing: field.secret && !revealedVal ? 2 : 0,
                  }}>
                    {displayVal || "—"}
                  </span>
                ) : (
                  <span style={{ fontSize: 11, color: "var(--muted)", fontStyle: "italic" }}>no configurado</span>
                )}
              </div>
            );
          })}
        </div>

        {isEditing && (
          <div style={{ marginTop: 12 }}>
            <button
              onClick={() => handleSaveCreds(platform)}
              disabled={savingCreds || Object.values(editValues).every((v) => !v)}
              style={{
                ...btnPrimary,
                opacity: savingCreds || Object.values(editValues).every((v) => !v) ? 0.5 : 1,
              }}
            >
              {savingCreds ? "Guardando…" : "Guardar"}
            </button>
          </div>
        )}
      </div>
    );
  }

  // ── Render ──────────────────────────────────────────────────

  const tgStatus = status?.telegram;
  const xStatus  = status?.x;
  const waStatus = status?.whatsapp;
  const fbStatus = status?.facebook;
  const waCanalStatus = status?.whatsapp_canal;

  return (
    <main className="min-h-screen px-4 py-10">
      <div className="max-w-2xl mx-auto">
        {/* Toast */}
        {toast && (
          <div style={{
            position: "fixed", top: 60, right: 20, zIndex: 9999,
            background: toast.type === "ok" ? "#0a2a1a" : "#2a0a0a",
            border: `1px solid ${toast.type === "ok" ? "var(--success)" : "var(--error)"}`,
            color: toast.type === "ok" ? "var(--success)" : "var(--error)",
            borderRadius: 10, padding: "10px 16px", fontSize: 13, fontWeight: 600,
            maxWidth: 380, boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
          }}>
            {toast.msg}
          </div>
        )}

        <div className="mb-6">
          <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--text)" }}>Canales</h1>
          <p style={{ color: "var(--muted)", fontSize: 14 }}>
            Conecta tus cuentas para publicar reels con un clic.
          </p>
        </div>

        {/* ── Admin password section ── */}
        <div style={{
          marginBottom: 20,
          background: adminConfigured ? "var(--surface)" : "#1a120a",
          border: `1px solid ${adminConfigured ? "var(--border)" : "#f59e0b40"}`,
          borderRadius: 12,
          padding: "12px 16px",
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
            <div>
              <p style={{ fontSize: 13, fontWeight: 600, color: adminConfigured ? "var(--text)" : "#f59e0b", margin: 0 }}>
                {adminConfigured ? "🔒 Admin configurado" : "⚠️ Contraseña de admin no configurada"}
              </p>
              <p style={{ fontSize: 11, color: "var(--muted)", margin: "2px 0 0" }}>
                {adminConfigured
                  ? "Necesaria para revelar secrets guardados"
                  : "Configúrala para poder revelar los secrets de tus credenciales"}
              </p>
            </div>
            <button
              onClick={() => setShowAdminForm(!showAdminForm)}
              style={{ ...btnGhost, fontSize: 11, padding: "5px 10px", flexShrink: 0 }}
            >
              {showAdminForm ? "Ocultar" : adminConfigured ? "Cambiar" : "Configurar"}
            </button>
          </div>

          {showAdminForm && (
            <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
              {adminConfigured && (
                <div>
                  <p style={{ fontSize: 10, color: "var(--muted)", margin: "0 0 3px", fontWeight: 600 }}>
                    CONTRASEÑA ACTUAL
                  </p>
                  <input
                    type="password"
                    placeholder="Contraseña actual"
                    value={adminCurrentPw}
                    onChange={(e) => setAdminCurrentPw(e.target.value)}
                    style={inputStyle}
                  />
                </div>
              )}
              <div>
                <p style={{ fontSize: 10, color: "var(--muted)", margin: "0 0 3px", fontWeight: 600 }}>
                  {adminConfigured ? "NUEVA CONTRASEÑA" : "CONTRASEÑA (mínimo 4 caracteres)"}
                </p>
                <input
                  type="password"
                  placeholder="Nueva contraseña"
                  value={adminNewPw}
                  onChange={(e) => setAdminNewPw(e.target.value)}
                  style={inputStyle}
                />
              </div>
              <input
                type="password"
                placeholder="Repite la contraseña"
                value={adminConfirmPw}
                onChange={(e) => setAdminConfirmPw(e.target.value)}
                style={inputStyle}
              />
              <button
                onClick={handleSaveAdminPw}
                disabled={adminSaving || !adminNewPw}
                style={{ ...btnPrimary, opacity: adminSaving || !adminNewPw ? 0.5 : 1, alignSelf: "flex-start" }}
              >
                {adminSaving ? "Guardando…" : "Guardar contraseña"}
              </button>
            </div>
          )}
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: 40, color: "var(--muted)" }}>Cargando…</div>
        ) : (
          <div className="space-y-4">
            {/* ── OAuth platforms ── */}
            {OAUTH_PLATFORMS.map((p) => {
              const st = status?.[p.id as keyof AccountsStatus];
              const isConnected = st?.connected;
              const isConnecting = connecting === p.id;
              const isDisconnecting = disconnecting === p.id;
              const showSetup = expandedSetup === p.id;
              const showCreds = openCredsPanel === p.id;
              const platformCreds = allCreds[p.id] || {};
              const hasCredsSaved = Object.values(platformCreds).some((f) => f.has_value);

              return (
                <div key={p.id} style={{
                  background: "var(--surface)",
                  border: `1px solid ${isConnected ? "var(--success)30" : "var(--border)"}`,
                  borderRadius: 16,
                  overflow: "hidden",
                }}>
                  {/* Main row */}
                  <div style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 14 }}>
                    <div style={{
                      width: 44, height: 44, borderRadius: 12,
                      background: "var(--surface2)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 22, flexShrink: 0,
                    }}>
                      {p.icon}
                    </div>

                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontWeight: 600, fontSize: 15, margin: 0, color: "var(--text)" }}>{p.name}</p>
                      {isConnected && st ? (
                        <p style={{ fontSize: 12, color: "var(--success)", margin: "2px 0 0" }}>
                          ✓ {p.accountLabel(st)}
                        </p>
                      ) : (
                        <p style={{ fontSize: 12, color: "var(--muted)", margin: "2px 0 0" }}>No conectado</p>
                      )}
                    </div>

                    <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                      {/* Credenciales toggle */}
                      <button
                        onClick={() => {
                          if (showCreds) {
                            setOpenCredsPanel(null);
                            setEditCredsFor(null);
                            setRevealFor(null);
                          } else {
                            setOpenCredsPanel(p.id);
                            if (!hasCredsSaved) openEditCreds(p.id);
                          }
                        }}
                        style={{
                          ...btnGhost,
                          color: hasCredsSaved ? "var(--text)" : "var(--muted)",
                          borderColor: hasCredsSaved ? "var(--accent)60" : "var(--border)",
                        }}
                      >
                        {hasCredsSaved ? "🔑" : "🔑"} {showCreds ? "Ocultar" : "Credenciales"}
                      </button>

                      {!isConnected && !showCreds && (
                        <button
                          onClick={() => setExpandedSetup(showSetup ? null : p.id)}
                          style={btnGhost}
                        >
                          {showSetup ? "Ocultar" : "¿Cómo?"}
                        </button>
                      )}

                      {isConnected ? (
                        <button
                          onClick={() => handleDisconnect(p.id)}
                          disabled={isDisconnecting}
                          style={{
                            padding: "7px 14px", borderRadius: 8, fontSize: 13, fontWeight: 600,
                            background: "#2a0a0a", border: "1px solid var(--error)40",
                            color: "var(--error)", cursor: "pointer",
                            opacity: isDisconnecting ? 0.5 : 1,
                          }}
                        >
                          {isDisconnecting ? "Desvinculando…" : "Desvincular"}
                        </button>
                      ) : (
                        <button
                          onClick={() => handleConnect(p.id)}
                          disabled={isConnecting}
                          style={{
                            ...btnPrimary,
                            opacity: isConnecting ? 0.6 : 1,
                          }}
                        >
                          {isConnecting ? "Conectando…" : "Conectar"}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Credentials panel */}
                  {showCreds && renderCredsPanel(p.id)}

                  {/* Setup guide */}
                  {showSetup && !isConnected && !showCreds && (
                    <div style={{
                      borderTop: "1px solid var(--border)",
                      background: "var(--surface2)",
                      padding: "14px 20px",
                    }}>
                      <p style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", marginBottom: 10 }}>
                        PASOS DE CONFIGURACIÓN
                      </p>
                      <ol style={{ listStyle: "decimal", paddingLeft: 18, margin: 0 }}>
                        {p.setupSteps.map((step, i) => (
                          <li key={i} style={{ fontSize: 12, color: "var(--text)", marginBottom: 5, lineHeight: 1.5 }}>
                            {step}
                          </li>
                        ))}
                      </ol>
                      <div style={{ marginTop: 10 }}>
                        <a
                          href={p.setupLink}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ fontSize: 12, color: "var(--accent)", textDecoration: "none" }}
                        >
                          {p.setupLinkLabel}
                        </a>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}

            {/* ── Telegram ── */}
            <div style={{
              background: "var(--surface)",
              border: `1px solid ${tgStatus?.connected ? "var(--success)30" : "var(--border)"}`,
              borderRadius: 16,
              overflow: "hidden",
            }}>
              <div style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 14 }}>
                <div style={{
                  width: 44, height: 44, borderRadius: 12,
                  background: "var(--surface2)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 22, flexShrink: 0,
                }}>
                  ✈️
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontWeight: 600, fontSize: 15, margin: 0, color: "var(--text)" }}>Telegram</p>
                  {tgStatus?.connected ? (
                    <p style={{ fontSize: 12, color: "var(--success)", margin: "2px 0 0" }}>
                      ✓ @{tgStatus.bot_username} → {tgStatus.chat_id}
                    </p>
                  ) : (
                    <p style={{ fontSize: 12, color: "var(--muted)", margin: "2px 0 0" }}>No conectado</p>
                  )}
                </div>
                <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                  {tgStatus?.connected && (
                    <button
                      onClick={() => setOpenCredsPanel(openCredsPanel === "telegram" ? null : "telegram")}
                      style={{ ...btnGhost, color: "var(--text)", borderColor: "var(--accent)60" }}
                    >
                      🔑 {openCredsPanel === "telegram" ? "Ocultar" : "Credenciales"}
                    </button>
                  )}
                  {tgStatus?.connected ? (
                    <button
                      onClick={handleTelegramDisconnect}
                      disabled={disconnecting === "telegram"}
                      style={{
                        padding: "7px 14px", borderRadius: 8, fontSize: 13, fontWeight: 600,
                        background: "#2a0a0a", border: "1px solid var(--error)40",
                        color: "var(--error)", cursor: "pointer",
                        opacity: disconnecting === "telegram" ? 0.5 : 1,
                      }}
                    >
                      {disconnecting === "telegram" ? "Desvinculando…" : "Desvincular"}
                    </button>
                  ) : (
                    <button
                      onClick={() => setExpandedSetup(expandedSetup === "telegram" ? null : "telegram")}
                      style={btnGhost}
                    >
                      {expandedSetup === "telegram" ? "Ocultar" : "Conectar"}
                    </button>
                  )}
                </div>
              </div>

              {/* Credentials view (when connected) */}
              {tgStatus?.connected && openCredsPanel === "telegram" && renderCredsPanel("telegram")}

              {/* Connect form (when not connected) */}
              {expandedSetup === "telegram" && !tgStatus?.connected && (
                <div style={{
                  borderTop: "1px solid var(--border)",
                  background: "var(--surface2)",
                  padding: "14px 20px",
                }}>
                  <p style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", marginBottom: 10 }}>
                    CONFIGURACIÓN TELEGRAM
                  </p>
                  <ol style={{ listStyle: "decimal", paddingLeft: 18, margin: "0 0 12px" }}>
                    {[
                      "Habla con @BotFather en Telegram y crea un bot con /newbot",
                      "Copia el token que te da BotFather",
                      "Añade el bot a tu canal/grupo y obtén el Chat ID (puedes usar @userinfobot)",
                    ].map((s, i) => (
                      <li key={i} style={{ fontSize: 12, color: "var(--text)", marginBottom: 5, lineHeight: 1.5 }}>{s}</li>
                    ))}
                  </ol>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <input
                      type="text"
                      placeholder="Bot Token (ej: 123456:ABC-DEF...)"
                      value={tgToken}
                      onChange={(e) => setTgToken(e.target.value)}
                      style={inputStyle}
                    />
                    <input
                      type="text"
                      placeholder="Chat ID o @username (ej: -100123456789)"
                      value={tgChatId}
                      onChange={(e) => setTgChatId(e.target.value)}
                      style={inputStyle}
                    />
                    <button
                      onClick={handleTelegramConnect}
                      disabled={connecting === "telegram"}
                      style={{ ...btnPrimary, opacity: connecting === "telegram" ? 0.6 : 1, alignSelf: "flex-start" }}
                    >
                      {connecting === "telegram" ? "Conectando…" : "Conectar"}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* ── X (Twitter) ── */}
            <div style={{
              background: "var(--surface)",
              border: `1px solid ${xStatus?.connected ? "var(--success)30" : "var(--border)"}`,
              borderRadius: 16,
              overflow: "hidden",
            }}>
              <div style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 14 }}>
                <div style={{
                  width: 44, height: 44, borderRadius: 12,
                  background: "var(--surface2)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 20, fontWeight: 900, flexShrink: 0, color: "var(--text)",
                }}>
                  𝕏
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontWeight: 600, fontSize: 15, margin: 0, color: "var(--text)" }}>X (Twitter)</p>
                  {xStatus?.connected ? (
                    <p style={{ fontSize: 12, color: "var(--success)", margin: "2px 0 0" }}>✓ @{xStatus.username}</p>
                  ) : (
                    <p style={{ fontSize: 12, color: "var(--muted)", margin: "2px 0 0" }}>No conectado</p>
                  )}
                </div>
                <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                  {xStatus?.connected && (
                    <button
                      onClick={() => setOpenCredsPanel(openCredsPanel === "x" ? null : "x")}
                      style={{ ...btnGhost, color: "var(--text)", borderColor: "var(--accent)60" }}
                    >
                      🔑 {openCredsPanel === "x" ? "Ocultar" : "Credenciales"}
                    </button>
                  )}
                  {xStatus?.connected ? (
                    <button
                      onClick={handleXDisconnect}
                      disabled={disconnecting === "x"}
                      style={{
                        padding: "7px 14px", borderRadius: 8, fontSize: 13, fontWeight: 600,
                        background: "#2a0a0a", border: "1px solid var(--error)40",
                        color: "var(--error)", cursor: "pointer",
                        opacity: disconnecting === "x" ? 0.5 : 1,
                      }}
                    >
                      {disconnecting === "x" ? "Desvinculando…" : "Desvincular"}
                    </button>
                  ) : (
                    <button
                      onClick={() => setExpandedSetup(expandedSetup === "x" ? null : "x")}
                      style={btnGhost}
                    >
                      {expandedSetup === "x" ? "Ocultar" : "Conectar"}
                    </button>
                  )}
                </div>
              </div>

              {/* Credentials view (when connected) */}
              {xStatus?.connected && openCredsPanel === "x" && renderCredsPanel("x")}

              {/* Connect form (when not connected) */}
              {expandedSetup === "x" && !xStatus?.connected && (
                <div style={{
                  borderTop: "1px solid var(--border)",
                  background: "var(--surface2)",
                  padding: "14px 20px",
                }}>
                  <p style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", marginBottom: 10 }}>
                    CONFIGURACIÓN X (TWITTER)
                  </p>
                  <ol style={{ listStyle: "decimal", paddingLeft: 18, margin: "0 0 12px" }}>
                    {[
                      "Ve a developer.twitter.com, crea un proyecto y una app",
                      'En "Keys and Tokens", copia API Key y API Secret',
                      "Genera Access Token y Access Token Secret (con permisos Read and Write)",
                      "El plan Free no permite subir videos. Necesitas el plan Basic (~$100/mes) para video upload.",
                    ].map((s, i) => (
                      <li key={i} style={{ fontSize: 12, color: "var(--text)", marginBottom: 5, lineHeight: 1.5 }}>{s}</li>
                    ))}
                  </ol>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {[
                      { label: "API Key (Consumer Key)", val: xApiKey, set: setXApiKey, ph: "Ej: AbCdEf12345…" },
                      { label: "API Secret (Consumer Secret)", val: xApiSecret, set: setXApiSecret, ph: "Ej: xYz789…" },
                      { label: "Access Token", val: xAccessToken, set: setXAccessToken, ph: "Ej: 123456789-AbCdEf…" },
                      { label: "Access Token Secret", val: xAccessSecret, set: setXAccessSecret, ph: "Ej: SecretXyz…" },
                    ].map(({ label, val, set, ph }) => (
                      <div key={label}>
                        <p style={{ fontSize: 10, color: "var(--muted)", margin: "0 0 3px", fontWeight: 600 }}>{label}</p>
                        <input
                          type="password"
                          placeholder={ph}
                          value={val}
                          onChange={(e) => set(e.target.value)}
                          style={inputStyle}
                        />
                      </div>
                    ))}
                    <button
                      onClick={handleXConnect}
                      disabled={connecting === "x"}
                      style={{ ...btnPrimary, opacity: connecting === "x" ? 0.6 : 1, alignSelf: "flex-start" }}
                    >
                      {connecting === "x" ? "Conectando…" : "Conectar"}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* ── WhatsApp ── */}
            <div style={{
              background: "var(--surface)",
              border: `1px solid ${waStatus?.connected ? "var(--success)30" : "var(--border)"}`,
              borderRadius: 16,
              overflow: "hidden",
            }}>
              <div style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 14 }}>
                <div style={{
                  width: 44, height: 44, borderRadius: 12,
                  background: "var(--surface2)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 22, flexShrink: 0,
                }}>
                  💬
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontWeight: 600, fontSize: 15, margin: 0, color: "var(--text)" }}>WhatsApp Status</p>
                  {waStatus?.connected && waStatus?.ready ? (
                    <p style={{ fontSize: 12, color: "var(--success)", margin: "2px 0 0" }}>✓ Conectado y listo</p>
                  ) : waStatus?.connected ? (
                    <p style={{ fontSize: 12, color: "#f59e0b", margin: "2px 0 0" }}>Autenticado — inicializando…</p>
                  ) : (
                    <p style={{ fontSize: 12, color: "var(--muted)", margin: "2px 0 0" }}>Esperando QR / Desconectado</p>
                  )}
                </div>
                <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                  <button
                    onClick={handleWaQr}
                    disabled={waQrLoading}
                    style={{ ...btnGhost, opacity: waQrLoading ? 0.6 : 1, color: "var(--text)" }}
                  >
                    {waQrLoading ? "Cargando…" : "Ver QR"}
                  </button>
                </div>
              </div>

              {waQr && (
                <div style={{
                  borderTop: "1px solid var(--border)",
                  background: "var(--surface2)",
                  padding: "16px 20px",
                  display: "flex", flexDirection: "column", alignItems: "center", gap: 10,
                }}>
                  <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>
                    Escanea este QR con WhatsApp (Ajustes → Dispositivos vinculados → Vincular dispositivo)
                  </p>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={waQr} alt="WhatsApp QR" style={{ width: 200, height: 200, borderRadius: 8 }} />
                  <button onClick={() => setWaQr(null)} style={{ ...btnGhost, color: "var(--muted)" }}>Ocultar QR</button>
                </div>
              )}

              <div style={{ borderTop: "1px solid var(--border)", background: "var(--surface2)", padding: "10px 20px" }}>
                <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>
                  El servicio de WhatsApp debe estar corriendo:{" "}
                  <code style={{ fontSize: 10, background: "var(--bg)", borderRadius: 4, padding: "1px 5px" }}>
                    cd wa_service && npm start
                  </code>
                </p>
              </div>
            </div>

            {/* ── Facebook Page ── */}
            <div style={{
              background: "var(--surface)",
              border: `1px solid ${fbStatus?.connected ? "var(--success)30" : "var(--border)"}`,
              borderRadius: 16, overflow: "hidden",
            }}>
              <div style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 14 }}>
                <div style={{ width: 44, height: 44, borderRadius: 12, background: "#1877F220", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, fontWeight: 900, color: "#1877F2", flexShrink: 0 }}>
                  f
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontWeight: 600, fontSize: 15, margin: 0, color: "var(--text)" }}>Facebook Página</p>
                  {fbStatus?.connected ? (
                    <p style={{ fontSize: 12, color: "var(--success)", margin: "2px 0 0" }}>✓ {fbStatus.page_name || "Página conectada"}</p>
                  ) : (
                    <p style={{ fontSize: 12, color: "var(--muted)", margin: "2px 0 0" }}>No conectado</p>
                  )}
                </div>
                <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                  {fbStatus?.connected ? (
                    <button onClick={handleFacebookDisconnect} disabled={disconnecting === "facebook"} style={{ padding: "7px 14px", borderRadius: 8, fontSize: 13, fontWeight: 600, background: "#2a0a0a", border: "1px solid var(--error)40", color: "var(--error)", cursor: "pointer", opacity: disconnecting === "facebook" ? 0.5 : 1 }}>
                      {disconnecting === "facebook" ? "Desvinculando…" : "Desvincular"}
                    </button>
                  ) : (
                    <button onClick={handleFacebookConnect} disabled={connecting === "facebook"} style={{ ...btnPrimary, opacity: connecting === "facebook" ? 0.6 : 1 }}>
                      {connecting === "facebook" ? "Redirigiendo…" : "Conectar"}
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* ── WhatsApp Canal ── */}
            <div style={{
              background: "var(--surface)",
              border: `1px solid ${waCanalStatus?.connected ? "var(--success)30" : "var(--border)"}`,
              borderRadius: 16, overflow: "hidden",
            }}>
              <div style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 14 }}>
                <div style={{ width: 44, height: 44, borderRadius: 12, background: "#25D36620", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, color: "#25D366", flexShrink: 0 }}>
                  ⊕
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontWeight: 600, fontSize: 15, margin: 0, color: "var(--text)" }}>WhatsApp Canal</p>
                  {waCanalStatus?.connected ? (
                    <p style={{ fontSize: 12, color: "var(--success)", margin: "2px 0 0" }}>
                      ✓ {waCanalStatus.channel_name || waCanalStatus.channel_jid}
                    </p>
                  ) : (
                    <p style={{ fontSize: 12, color: "var(--muted)", margin: "2px 0 0" }}>No configurado</p>
                  )}
                </div>
                <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                  {waCanalStatus?.connected ? (
                    <button onClick={handleWaCanelDisconnect} disabled={disconnecting === "whatsapp_canal"} style={{ padding: "7px 14px", borderRadius: 8, fontSize: 13, fontWeight: 600, background: "#2a0a0a", border: "1px solid var(--error)40", color: "var(--error)", cursor: "pointer", opacity: disconnecting === "whatsapp_canal" ? 0.5 : 1 }}>
                      {disconnecting === "whatsapp_canal" ? "Desvinculando…" : "Desvincular"}
                    </button>
                  ) : (
                    <button onClick={() => setExpandedSetup(expandedSetup === "whatsapp_canal" ? null : "whatsapp_canal")} style={btnGhost}>
                      {expandedSetup === "whatsapp_canal" ? "Ocultar" : "Configurar"}
                    </button>
                  )}
                </div>
              </div>
              {expandedSetup === "whatsapp_canal" && !waCanalStatus?.connected && (
                <div style={{ borderTop: "1px solid var(--border)", background: "var(--surface2)", padding: "14px 20px" }}>
                  <p style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", marginBottom: 8 }}>SELECCIONAR CANAL</p>
                  <p style={{ fontSize: 12, color: "var(--muted)", margin: "0 0 12px" }}>
                    Necesitas ser admin de un canal de WhatsApp. Primero vincula WhatsApp escaneando el QR de arriba.
                  </p>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <div>
                      <p style={{ fontSize: 10, color: "var(--muted)", margin: "0 0 4px", fontWeight: 600 }}>
                        URL DEL CANAL (opcional — para buscar tu canal directamente)
                      </p>
                      <input
                        type="text"
                        placeholder="https://whatsapp.com/channel/..."
                        value={waInviteUrl}
                        onChange={(e) => { setWaInviteUrl(e.target.value); setWaChannels([]); setWaSelectedJid(""); }}
                        style={inputStyle}
                      />
                    </div>
                    <button onClick={loadWaChannels} disabled={waChannelsLoading} style={{ ...btnGhost, alignSelf: "flex-start", opacity: waChannelsLoading ? 0.6 : 1 }}>
                      {waChannelsLoading ? "Buscando…" : waInviteUrl.trim() ? "Buscar mi canal" : "Cargar mis canales"}
                    </button>
                    {waChannels.length > 0 && (
                      <>
                        <select value={waSelectedJid} onChange={(e) => setWaSelectedJid(e.target.value)} style={inputStyle}>
                          <option value="">Selecciona un canal…</option>
                          {waChannels.map((ch) => (
                            <option key={ch.jid} value={ch.jid}>
                              {ch.name || ch.jid}{ch.exact ? " ✓" : ""}
                            </option>
                          ))}
                        </select>
                        <button onClick={handleWaCanelConnect} disabled={!waSelectedJid || connecting === "whatsapp_canal"} style={{ ...btnPrimary, alignSelf: "flex-start", opacity: !waSelectedJid || connecting === "whatsapp_canal" ? 0.5 : 1 }}>
                          {connecting === "whatsapp_canal" ? "Guardando…" : "Usar este canal"}
                        </button>
                      </>
                    )}
                    {waChannels.length === 0 && !waChannelsLoading && (
                      <p style={{ fontSize: 11, color: "var(--muted)" }}>
                        Si no aparecen canales, asegúrate de que WhatsApp está conectado y eres admin de algún canal.
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>

          </div>
        )}

        {/* Info box */}
        <div style={{
          marginTop: 24,
          background: "var(--surface2)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          padding: "14px 18px",
        }}>
          <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>
            <strong style={{ color: "var(--text)" }}>Los tokens se guardan localmente</strong> en{" "}
            <code style={{ fontSize: 11, background: "var(--bg)", borderRadius: 4, padding: "1px 5px" }}>_tokens/</code>
            {" "}y las credenciales OAuth en{" "}
            <code style={{ fontSize: 11, background: "var(--bg)", borderRadius: 4, padding: "1px 5px" }}>_config/credentials.json</code>
            . Para migrar a otro equipo, copia esas carpetas junto con el{" "}
            <code style={{ fontSize: 11, background: "var(--bg)", borderRadius: 4, padding: "1px 5px" }}>.env</code>.
          </p>
        </div>
      </div>
    </main>
  );
}

export default function CanalesPage() {
  return (
    <Suspense>
      <CanalesContent />
    </Suspense>
  );
}
