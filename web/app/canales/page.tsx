"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";

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

const PLATFORMS = [
  {
    id: "youtube",
    name: "YouTube Shorts",
    icon: "▶️",
    color: "#ff0000",
    accountLabel: (s: PlatformStatus) => s.canal || "Canal conectado",
    envVars: ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET"],
    setupSteps: [
      "Ve a console.cloud.google.com y crea un proyecto",
      'Activa "YouTube Data API v3" en APIs y Servicios',
      'Crea credenciales OAuth → Aplicación de escritorio',
      "Copia el Client ID y Client Secret al .env del proyecto",
    ],
    setupLink: "https://console.cloud.google.com/",
    setupLinkLabel: "Google Cloud Console →",
  },
  {
    id: "tiktok",
    name: "TikTok",
    icon: "🎵",
    color: "#010101",
    accountLabel: (s: PlatformStatus) => `@${s.display_name || "usuario"}`,
    envVars: ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"],
    setupSteps: [
      "Ve a developers.tiktok.com y crea una app",
      'Añade el producto "Content Posting API"',
      "Configura Redirect URI: http://localhost:8000/api/accounts/tiktok/callback",
      "Copia Client Key y Client Secret al .env del proyecto",
    ],
    setupLink: "https://developers.tiktok.com/",
    setupLinkLabel: "TikTok for Developers →",
  },
  {
    id: "instagram",
    name: "Instagram Reels",
    icon: "📸",
    color: "#e1306c",
    accountLabel: (s: PlatformStatus) => `@${s.username || "usuario"}`,
    envVars: ["INSTAGRAM_APP_ID", "INSTAGRAM_APP_SECRET"],
    setupSteps: [
      "Ve a developers.facebook.com y crea una app (tipo Business)",
      'Añade el producto "Instagram Graph API"',
      "Configura Redirect URI: http://localhost:8000/api/accounts/instagram/callback",
      "Necesitas una cuenta Instagram Business vinculada a una página de Facebook",
      "Copia App ID y App Secret al .env del proyecto",
    ],
    setupLink: "https://developers.facebook.com/",
    setupLinkLabel: "Meta for Developers →",
  },
];

function CanalesContent() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<AccountsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "error" } | null>(null);
  const [expandedSetup, setExpandedSetup] = useState<string | null>(null);

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

  useEffect(() => {
    fetchStatus();

    // Handle OAuth callback results from URL params
    for (const p of ["youtube", "tiktok", "instagram"]) {
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
        instagram_no_business_account: "No se encontró cuenta Instagram Business vinculada a ninguna página de Facebook.",
        instagram_token_failed: "Error al obtener token de Instagram.",
      };
      showToast(msgs[errParam] || `Error: ${errParam}`, "error");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleConnect(platform: string) {
    setConnecting(platform);
    try {
      const res = await fetch(`/api/accounts/${platform}/connect`);
      const data = await res.json();

      if (!res.ok) {
        const detail = data.detail || {};
        showToast(detail.message || "Error al conectar", "error");
        setExpandedSetup(platform);
        return;
      }

      if (data.auth_url) {
        window.location.href = data.auth_url;
      }
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

        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--text)" }}>Canales</h1>
          <p style={{ color: "var(--muted)", fontSize: 14 }}>
            Conecta tus cuentas para publicar reels con un clic desde la biblioteca de videos.
          </p>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: 40, color: "var(--muted)" }}>Cargando…</div>
        ) : (
          <div className="space-y-4">
            {PLATFORMS.map((p) => {
              const st = status?.[p.id as keyof AccountsStatus];
              const isConnected = st?.connected;
              const isConnecting = connecting === p.id;
              const isDisconnecting = disconnecting === p.id;
              const showSetup = expandedSetup === p.id;

              return (
                <div key={p.id} style={{
                  background: "var(--surface)",
                  border: `1px solid ${isConnected ? "var(--success)30" : "var(--border)"}`,
                  borderRadius: 16,
                  overflow: "hidden",
                }}>
                  {/* Main row */}
                  <div style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 14 }}>
                    {/* Icon */}
                    <div style={{
                      width: 44, height: 44, borderRadius: 12,
                      background: "var(--surface2)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 22, flexShrink: 0,
                    }}>
                      {p.icon}
                    </div>

                    {/* Info */}
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

                    {/* Actions */}
                    <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                      {!isConnected && (
                        <button
                          onClick={() => setExpandedSetup(showSetup ? null : p.id)}
                          style={{
                            padding: "6px 12px", borderRadius: 8, fontSize: 12,
                            background: "var(--surface2)", border: "1px solid var(--border)",
                            color: "var(--muted)", cursor: "pointer",
                          }}
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
                            padding: "7px 16px", borderRadius: 8, fontSize: 13, fontWeight: 700,
                            background: "var(--accent)", border: "none",
                            color: "#fff", cursor: "pointer",
                            opacity: isConnecting ? 0.6 : 1,
                          }}
                        >
                          {isConnecting ? "Conectando…" : "Conectar"}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Setup guide */}
                  {showSetup && !isConnected && (
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
                      <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}>
                        <a
                          href={p.setupLink}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ fontSize: 12, color: "var(--accent)", textDecoration: "none" }}
                        >
                          {p.setupLinkLabel}
                        </a>
                        <span style={{ fontSize: 12, color: "var(--muted)" }}>
                          Variables necesarias en .env: {p.envVars.join(", ")}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
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
            <code style={{ fontSize: 11, background: "var(--bg)", borderRadius: 4, padding: "1px 5px" }}>
              _tokens/
            </code>{" "}
            dentro del proyecto. Para usar en otro equipo, copia esa carpeta junto con el{" "}
            <code style={{ fontSize: 11, background: "var(--bg)", borderRadius: 4, padding: "1px 5px" }}>
              .env
            </code>
            .
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
