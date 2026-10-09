"use client";

import { useEffect, useState } from "react";

type CursosConn = {
  nombre_canal: string;
  nombre_bot: string;
  chat_id: string;
  bot_token_configurado: boolean;
};

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

const card: React.CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 16,
  padding: "16px 20px",
};

export default function ConexionesPage() {
  const [cursos, setCursos] = useState<CursosConn | null>(null);
  const [nombreCanal, setNombreCanal] = useState("RiverSec");
  const [nombreBot, setNombreBot] = useState("RiverSec Bot");
  const [chatId, setChatId] = useState("");
  const [botToken, setBotToken] = useState("");
  const [tokenConfigurado, setTokenConfigurado] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "error" } | null>(null);
  const [ytClientId, setYtClientId] = useState("");
  const [ytClientSecret, setYtClientSecret] = useState("");
  const [ytSaving, setYtSaving] = useState(false);
  const [ytOk, setYtOk] = useState(false);
  const [saConfigurado, setSaConfigurado] = useState(false);
  const [saEmail, setSaEmail] = useState("");
  const [saProyecto, setSaProyecto] = useState("");
  const [saCargando, setSaCargando] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("youtube") === "ok") setYtOk(true);
  }, []);

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const res = await fetch("/api/conexiones/youtube-cursos");
        if (!res.ok) return;
        const data = await res.json();
        if (!vivo) return;
        const lista = !!data.service_account_configurado;
        setSaConfigurado(lista);
        setSaEmail(lista ? String(data.client_email || "") : "");
        setSaProyecto(lista ? String(data.project_id || "") : "");
      } catch {
        /* la tarjeta sigue usable */
      }
    })();
    return () => {
      vivo = false;
    };
  }, []);

  async function autorizarYoutube() {
    setYtSaving(true);
    try {
      const res = await fetch("/api/conexiones/youtube-cursos", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nombre: "RayverSec",
          handle: "@RAYVERSEC",
          canal_id: "UCbEnilZIVXwp9lNAv91j69g",
          client_id: ytClientId,
          client_secret: ytClientSecret,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        showToast("No se pudo guardar YouTube de cursos", "error");
        return;
      }
      window.location.assign("http://127.0.0.1:8000/api/conexiones/youtube-cursos/autorizar");
    } catch {
      showToast("No se pudo guardar YouTube de cursos", "error");
    } finally {
      setYtSaving(false);
    }
  }
  const showToast = (msg: string, type: "ok" | "error") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  function aplicarCuentaServicio(data: {
    service_account_configurado?: boolean;
    client_email?: string;
    project_id?: string;
  }) {
    const lista = !!data.service_account_configurado;
    setSaConfigurado(lista);
    setSaEmail(lista ? String(data.client_email || "") : "");
    setSaProyecto(lista ? String(data.project_id || "") : "");
  }

  async function cargarCuentaServicio(archivo: File) {
    setSaCargando(true);
    try {
      let texto = "";
      try {
        texto = await archivo.text();
      } catch {
        showToast("No se pudo leer el archivo.", "error");
        return;
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(texto);
      } catch {
        showToast("El archivo no es un JSON válido.", "error");
        return;
      }
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        showToast("El archivo no es un JSON válido.", "error");
        return;
      }
      const res = await fetch("/api/conexiones/youtube-cursos/json", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        const detalle =
          typeof data.detail === "string"
            ? data.detail
            : "No se pudo guardar la cuenta de servicio.";
        showToast(detalle, "error");
        return;
      }
      aplicarCuentaServicio(data);
      showToast("Cuenta de servicio guardada.", "ok");
    } catch {
      showToast("No se pudo guardar la cuenta de servicio.", "error");
    } finally {
      setSaCargando(false);
    }
  }

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const res = await fetch("/api/conexiones/telegram-cursos");
        if (!res.ok) throw new Error("no se pudo leer");
        const data: CursosConn = await res.json();
        if (!vivo) return;
        setCursos(data);
        setNombreCanal(data.nombre_canal || "RiverSec");
        setNombreBot(data.nombre_bot || "RiverSec Bot");
        setChatId(data.chat_id || "");
        setTokenConfigurado(!!data.bot_token_configurado);
      } catch {
        if (vivo) showToast("No se pudo cargar la conexion de cursos", "error");
      } finally {
        if (vivo) setLoading(false);
      }
    })();
    return () => {
      vivo = false;
    };
  }, []);

  async function guardar() {
    setSaving(true);
    try {
      const res = await fetch("/api/conexiones/telegram-cursos", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nombre_canal: nombreCanal,
          nombre_bot: nombreBot,
          chat_id: chatId,
          bot_token: botToken,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        showToast("No se pudo guardar la conexion de cursos", "error");
        return;
      }
      setTokenConfigurado(!!data.bot_token_configurado);
      setBotToken("");
      setCursos(data);
      showToast("Conexion de cursos guardada", "ok");
    } catch {
      showToast("No se pudo guardar la conexion de cursos", "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="min-h-screen py-10">
      <div className="page-wrap">
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
          <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--text)" }}>
            Gestor de conexiones
          </h1>
          <p style={{ color: "var(--muted)", fontSize: 14, margin: 0 }}>
            Dos conexiones de Telegram, separadas. La de noticias no se toca desde aqui.
          </p>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={card}>
            <p style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)", margin: "0 0 6px" }}>
              NOTICIAS
            </p>
            <p style={{ fontWeight: 600, fontSize: 15, margin: 0, color: "var(--text)" }}>
              Bieninforma2
            </p>
            <p style={{ fontSize: 13, color: "var(--muted)", margin: "8px 0 12px", lineHeight: 1.5 }}>
              Esta conexion ya se administra en Canales. Su token sigue en el archivo de siempre
              y este gestor no lo lee ni lo escribe.
            </p>
            <a href="/canales" style={{ ...btnPrimary, textDecoration: "none", display: "inline-block" }}>
              Abrir Canales
            </a>
          </div>

          <div style={card}>
            <p style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)", margin: "0 0 6px" }}>
              CURSOS
            </p>
            <p style={{ fontWeight: 600, fontSize: 15, margin: 0, color: "var(--text)" }}>
              RiverSec
            </p>
            <p style={{ fontSize: 13, color: "var(--muted)", margin: "8px 0 14px", lineHeight: 1.5 }}>
              Conexion nueva, vacia, para el canal de cursos. El bot es RiverSec Bot.
              Guardar escribe solo su archivo, sin llamar a Telegram.
            </p>

            {loading ? (
              <p style={{ fontSize: 13, color: "var(--muted)" }}>Cargando…</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>Nombre del canal</span>
                  <input
                    type="text"
                    value={nombreCanal}
                    onChange={(e) => setNombreCanal(e.target.value)}
                    style={inputStyle}
                  />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>Nombre del bot</span>
                  <input
                    type="text"
                    value={nombreBot}
                    onChange={(e) => setNombreBot(e.target.value)}
                    style={inputStyle}
                  />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>
                    Token del bot {tokenConfigurado ? "· guardado" : "· vacio"}
                  </span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    placeholder={tokenConfigurado ? "Deja vacio para conservar el token actual" : "Token del bot"}
                    value={botToken}
                    onChange={(e) => setBotToken(e.target.value)}
                    style={inputStyle}
                  />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>Identificador del canal</span>
                  <input
                    type="text"
                    placeholder="Chat ID o @canal"
                    value={chatId}
                    onChange={(e) => setChatId(e.target.value)}
                    style={inputStyle}
                  />
                </label>
                <button
                  type="button"
                  onClick={guardar}
                  disabled={saving}
                  style={{ ...btnPrimary, alignSelf: "flex-start", opacity: saving ? 0.6 : 1 }}
                >
                  {saving ? "Guardando…" : "Guardar"}
                </button>
                {cursos && (
                  <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>
                    Se guarda en un archivo distinto al de noticias.
                  </p>
                )}
              </div>
            )}
          </div>
          <div style={card}>
            <p style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)", margin: "0 0 6px" }}>
              CURSOS
            </p>
            <p style={{ fontWeight: 600, fontSize: 15, margin: 0, color: "var(--text)" }}>
              YouTube de cursos, canal @RAYVERSEC
            </p>
            <p style={{ fontSize: 13, color: "var(--muted)", margin: "8px 0 14px", lineHeight: 1.5 }}>
              Entra con la cuenta de Google dueña de @RAYVERSEC y elige ese canal. No es Bieninforma2.
            </p>
            {ytOk && (
              <p style={{ fontSize: 13, color: "var(--success)", margin: "0 0 12px", fontWeight: 600 }}>
                La autorización quedó guardada.
              </p>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>ID de cliente</span>
                <input
                  type="text"
                  autoComplete="off"
                  value={ytClientId}
                  onChange={(e) => setYtClientId(e.target.value)}
                  style={inputStyle}
                />
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>Secreto de cliente</span>
                <input
                  type="password"
                  autoComplete="new-password"
                  value={ytClientSecret}
                  onChange={(e) => setYtClientSecret(e.target.value)}
                  style={inputStyle}
                />
              </label>
              <label htmlFor="yt-sa-json" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>
                  Cargar JSON de la cuenta de servicio
                </span>
                <input
                  id="yt-sa-json"
                  type="file"
                  accept=".json"
                  disabled={saCargando}
                  onChange={(e) => {
                    const archivo = e.target.files?.[0];
                    e.currentTarget.value = "";
                    if (archivo) void cargarCuentaServicio(archivo);
                  }}
                  style={inputStyle}
                />
              </label>
              {saConfigurado && (
                <p style={{ fontSize: 13, color: "var(--success)", margin: 0, fontWeight: 600 }}>
                  Cuenta de servicio guardada: {saEmail} · {saProyecto}
                </p>
              )}
              <button
                type="button"
                onClick={autorizarYoutube}
                disabled={ytSaving}
                style={{ ...btnPrimary, alignSelf: "flex-start", opacity: ytSaving ? 0.6 : 1 }}
              >
                Autorizar con Google
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
