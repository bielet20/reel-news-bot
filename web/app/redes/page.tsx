"use client";

import { useEffect, useState } from "react";

// Centro de Redes: cuentas de cada red + canales (marcas) que las usan.
// Todas las aplicaciones publican por /api/redes/publicar.

type Estado = {
  conectada: boolean;
  motivo?: string;
  canal?: string;
  custom_url?: string;
  destino?: string;
  gestion?: string;
};
type Cuenta = {
  id: string;
  plataforma: string;
  nombre: string;
  channel_id?: string;
  handle?: string;
  origen?: string;
  estado: Estado;
  publicable: boolean;
};
type Canal = {
  id: string;
  nombre: string;
  tema?: string;
  web?: string;
  cuentas: Record<string, string>;
};
type Resumen = { cuentas: Cuenta[]; canales: Canal[]; plataformas: string[]; publicables: string[] };
type Resultado = { ok: boolean; url?: string; error?: string };
type Publicacion = {
  fecha: string;
  canal: string;
  titulo: string;
  origen?: string;
  privacidad?: string;
  resultados: Record<string, Resultado>;
};

const RED_NOMBRE: Record<string, string> = {
  youtube: "YouTube",
  facebook: "Facebook",
  instagram: "Instagram",
  tiktok: "TikTok",
  x: "X",
  telegram: "Telegram",
  whatsapp_canal: "Canal de WhatsApp",
};

const card: React.CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 16,
  padding: "16px 20px",
};
const inputStyle: React.CSSProperties = {
  padding: "7px 10px",
  borderRadius: 8,
  fontSize: 13,
  background: "var(--bg)",
  border: "1px solid var(--border)",
  color: "var(--text)",
  outline: "none",
  minWidth: 0,
};
const btn: React.CSSProperties = {
  padding: "6px 14px",
  borderRadius: 8,
  fontSize: 13,
  fontWeight: 600,
  background: "var(--surface2)",
  border: "1px solid var(--border)",
  color: "var(--text)",
  cursor: "pointer",
};
const btnPrimary: React.CSSProperties = { ...btn, background: "var(--accent)", border: "none", color: "#fff" };
const titulo: React.CSSProperties = { fontSize: 11, fontWeight: 700, color: "var(--muted)", margin: "0 0 10px", letterSpacing: 0.5 };

// Las subidas van directas al backend: el proxy de Next corta cuerpos grandes.
function backend(): string {
  if (typeof window === "undefined") return "";
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

function Punto({ ok }: { ok: boolean }) {
  return (
    <span style={{
      display: "inline-block", width: 8, height: 8, borderRadius: 8, flexShrink: 0,
      background: ok ? "var(--success)" : "var(--error)",
    }} />
  );
}

export default function RedesPage() {
  const [datos, setDatos] = useState<Resumen | null>(null);
  const [cargando, setCargando] = useState(true);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "error" } | null>(null);
  const [historial, setHistorial] = useState<Publicacion[]>([]);
  const [nuevaRed, setNuevaRed] = useState("youtube");
  const [nuevaNombre, setNuevaNombre] = useState("");
  const [canalNombre, setCanalNombre] = useState("");
  const [canalTema, setCanalTema] = useState("");
  const [pubCanal, setPubCanal] = useState("");
  const [pubTitulo, setPubTitulo] = useState("");
  const [pubPriv, setPubPriv] = useState("private");
  const [pubArchivo, setPubArchivo] = useState<File | null>(null);
  const [pubEstado, setPubEstado] = useState("");

  function aviso(msg: string, type: "ok" | "error" = "ok") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 5000);
  }

  async function cargar(comprobar = false) {
    setCargando(true);
    try {
      const r = await fetch(`/api/redes${comprobar ? "?comprobar=true" : ""}`);
      const d: Resumen = await r.json();
      setDatos(d);
      setPubCanal((c) => c || d.canales[0]?.id || "");
      const h = await fetch("/api/redes/publicaciones?limite=30");
      setHistorial(await h.json());
    } catch {
      aviso("No se pudo leer el Centro de Redes", "error");
    } finally {
      setCargando(false);
    }
  }

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("youtube") === "ok") aviso("Canal de YouTube conectado.");
    const err = q.get("error");
    if (err === "youtube_wrong_channel") aviso(`Elegiste «${q.get("canal") || "otro canal"}», que no es el de esa cuenta. Vuelve a conectar y elige el correcto.`, "error");
    else if (err) aviso(`No se pudo conectar (${err}).`, "error");
    if (q.toString()) window.history.replaceState(null, "", "/redes");
    cargar(!!q.get("youtube"));
  }, []);

  async function conectar(id: string) {
    const volver = `${window.location.origin}/redes`;
    const r = await fetch(`/api/redes/cuentas/${id}/conectar?volver=${encodeURIComponent(volver)}`);
    const d = await r.json().catch(() => ({}));
    if (!r.ok || !d.auth_url) return aviso(d.detail || "No se pudo abrir Google", "error");
    window.location.assign(d.auth_url);
  }

  async function crearCuenta() {
    const r = await fetch("/api/redes/cuentas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plataforma: nuevaRed, nombre: nuevaNombre }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) return aviso(d.detail || "No se pudo crear", "error");
    setNuevaNombre("");
    aviso(nuevaRed === "youtube" ? `Cuenta creada. Pulsa «Conectar» para autorizarla con Google.` : "Cuenta creada.");
    cargar();
  }

  async function quitarCuenta(c: Cuenta) {
    if (!window.confirm(`¿Quitar «${c.nombre}» del Centro? La autorización guardada no se borra.`)) return;
    const r = await fetch(`/api/redes/cuentas/${c.id}`, { method: "DELETE" });
    if (!r.ok) return aviso("No se pudo quitar", "error");
    cargar();
  }

  async function guardarCanal(id: string, cambios: Partial<Canal>) {
    const r = await fetch(`/api/redes/canales/${encodeURIComponent(id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre: cambios.nombre || "", tema: cambios.tema || "", cuentas: cambios.cuentas || {} }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) return aviso(d.detail || "No se pudo guardar el canal", "error");
    aviso("Canal guardado.");
    cargar();
  }

  async function publicar() {
    if (!pubArchivo || !pubCanal) return aviso("Elige canal y vídeo", "error");
    const fd = new FormData();
    fd.append("canal", pubCanal);
    fd.append("titulo", pubTitulo);
    fd.append("privacidad", pubPriv);
    fd.append("origen", "web /redes");
    fd.append("archivo", pubArchivo);
    setPubEstado("Enviando el vídeo…");
    try {
      const r = await fetch(`${backend()}/api/redes/publicar`, { method: "POST", body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "falló");
      setPubEstado("Subiendo a las redes…");
      for (;;) {
        await new Promise((res) => setTimeout(res, 3000));
        const t = await (await fetch(`/api/redes/trabajos/${d.trabajo}`)).json();
        if (t.estado === "subiendo") continue;
        const partes = Object.entries((t.resultados || {}) as Record<string, Resultado>).map(
          ([red, x]) => `${RED_NOMBRE[red] || red}: ${x.ok ? x.url : x.error}`,
        );
        setPubEstado(t.error || partes.join(" · ") || t.estado);
        break;
      }
      cargar();
    } catch (e) {
      setPubEstado(String((e as Error).message || e));
    }
  }

  const cuentas = datos?.cuentas || [];
  const porId = Object.fromEntries(cuentas.map((c) => [c.id, c]));
  const plataformas = datos?.plataformas || [];

  return (
    <main className="min-h-screen py-10">
      <div className="page-wrap">
        {toast && (
          <div style={{
            position: "fixed", top: 60, right: 20, zIndex: 9999,
            background: toast.type === "ok" ? "#0a2a1a" : "#2a0a0a",
            border: `1px solid ${toast.type === "ok" ? "var(--success)" : "var(--error)"}`,
            color: toast.type === "ok" ? "var(--success)" : "var(--error)",
            borderRadius: 10, padding: "10px 16px", fontSize: 13, fontWeight: 600, maxWidth: 420,
          }}>
            {toast.msg}
          </div>
        )}

        <div className="mb-6" style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap", justifyContent: "space-between" }}>
          <div>
            <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--text)" }}>Centro de Redes</h1>
            <p style={{ color: "var(--muted)", fontSize: 14, margin: 0 }}>
              Las cuentas de cada red y los canales que las usan. Reels, cursos y AI Studio publican desde aquí.
            </p>
          </div>
          <button style={btn} onClick={() => cargar(true)} disabled={cargando}>
            {cargando ? "Comprobando…" : "Comprobar conexiones"}
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* ── Canales ── */}
          <section>
            <p style={titulo}>CANALES</p>
            <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}>
              {(datos?.canales || []).map((ch) => (
                <div key={ch.id} style={card}>
                  <p style={{ fontWeight: 700, fontSize: 16, margin: 0, color: "var(--text)" }}>{ch.nombre}</p>
                  <p style={{ fontSize: 12, color: "var(--muted)", margin: "2px 0 12px" }}>
                    {ch.tema || "—"}{ch.web ? ` · ${ch.web}` : ""}
                  </p>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {plataformas.map((red) => {
                      const cid = ch.cuentas[red] || "";
                      const c = porId[cid];
                      const opciones = cuentas.filter((x) => x.plataforma === red);
                      if (!cid && !opciones.length) return null;
                      return (
                        <div key={red} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                          {c ? <Punto ok={c.estado.conectada} /> : <span style={{ width: 8 }} />}
                          <span style={{ width: 120, color: "var(--muted)", flexShrink: 0 }}>{RED_NOMBRE[red] || red}</span>
                          <select
                            value={cid}
                            style={{ ...inputStyle, flex: 1 }}
                            onChange={(e) => guardarCanal(ch.id, { cuentas: { [red]: e.target.value } })}
                          >
                            <option value="">— sin cuenta —</option>
                            {opciones.map((x) => <option key={x.id} value={x.id}>{x.nombre}</option>)}
                          </select>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
              <div style={{ ...card, display: "flex", flexDirection: "column", gap: 8 }}>
                <p style={{ fontWeight: 700, fontSize: 15, margin: 0, color: "var(--text)" }}>Nuevo canal</p>
                <input style={inputStyle} placeholder="Nombre (p. ej. Mi canal de viajes)" value={canalNombre} onChange={(e) => setCanalNombre(e.target.value)} />
                <input style={inputStyle} placeholder="De qué va" value={canalTema} onChange={(e) => setCanalTema(e.target.value)} />
                <button
                  style={btnPrimary}
                  onClick={async () => {
                    if (!canalNombre.trim()) return aviso("Pon un nombre al canal", "error");
                    await guardarCanal(canalNombre, { nombre: canalNombre, tema: canalTema });
                    setCanalNombre("");
                    setCanalTema("");
                  }}
                >
                  Crear canal
                </button>
                <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>
                  Luego asígnale una cuenta en cada red (créala abajo si es nueva).
                </p>
              </div>
            </div>
          </section>

          {/* ── Cuentas ── */}
          <section style={card}>
            <p style={titulo}>CUENTAS</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {cuentas.map((c) => (
                <div key={c.id} style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", fontSize: 13, padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                  <Punto ok={c.estado.conectada} />
                  <span style={{ width: 130, color: "var(--muted)" }}>{RED_NOMBRE[c.plataforma] || c.plataforma}</span>
                  <span style={{ fontWeight: 600, color: "var(--text)", minWidth: 160 }}>{c.nombre}</span>
                  <span style={{ color: c.estado.conectada ? "var(--muted)" : "var(--warning)", flex: 1, minWidth: 200 }}>
                    {c.estado.conectada
                      ? [c.estado.canal, c.estado.custom_url || c.handle, c.estado.destino].filter(Boolean).join(" · ") || "conectada"
                      : c.estado.motivo || "sin conectar"}
                    {c.estado.gestion ? ` — ${c.estado.gestion}` : ""}
                  </span>
                  {c.plataforma === "youtube" && (
                    <button style={c.estado.conectada ? btn : btnPrimary} onClick={() => conectar(c.id)}>
                      {c.estado.conectada ? "Reconectar" : "Conectar"}
                    </button>
                  )}
                  {c.origen === "sistema_reels" && <a href="/canales" style={{ ...btn, textDecoration: "none" }}>Abrir Canales</a>}
                  {c.origen !== "sistema_reels" && (
                    <button style={{ ...btn, color: "var(--muted)" }} onClick={() => quitarCuenta(c)}>Quitar</button>
                  )}
                </div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: 13, color: "var(--muted)" }}>Nueva cuenta:</span>
              <select style={inputStyle} value={nuevaRed} onChange={(e) => setNuevaRed(e.target.value)}>
                {/* Fase 1: solo YouTube se conecta desde el Centro */}
                <option value="youtube">YouTube</option>
              </select>
              <input style={{ ...inputStyle, flex: 1, minWidth: 180 }} placeholder="Nombre del canal" value={nuevaNombre} onChange={(e) => setNuevaNombre(e.target.value)} />
              <button style={btnPrimary} onClick={crearCuenta}>Añadir</button>
            </div>
          </section>

          {/* ── Publicar ── */}
          <section style={card}>
            <p style={titulo}>PUBLICAR UN VÍDEO</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <select style={inputStyle} value={pubCanal} onChange={(e) => setPubCanal(e.target.value)}>
                {(datos?.canales || []).map((ch) => <option key={ch.id} value={ch.id}>{ch.nombre}</option>)}
              </select>
              <input type="file" accept="video/*" onChange={(e) => setPubArchivo(e.target.files?.[0] || null)} style={{ fontSize: 13, color: "var(--muted)" }} />
              <input style={{ ...inputStyle, flex: 1, minWidth: 200 }} placeholder="Título" value={pubTitulo} onChange={(e) => setPubTitulo(e.target.value)} />
              <select style={inputStyle} value={pubPriv} onChange={(e) => setPubPriv(e.target.value)}>
                <option value="private">Privado</option>
                <option value="unlisted">Oculto</option>
                <option value="public">Público</option>
              </select>
              <button style={btnPrimary} onClick={publicar}>Publicar</button>
            </div>
            {pubEstado && <p style={{ fontSize: 13, color: "var(--muted)", margin: "10px 0 0", wordBreak: "break-all" }}>{pubEstado}</p>}
          </section>

          {/* ── Historial ── */}
          <section style={card}>
            <p style={titulo}>ÚLTIMAS PUBLICACIONES DESDE EL CENTRO</p>
            {!historial.length && <p style={{ fontSize: 13, color: "var(--muted)", margin: 0 }}>Aún no hay ninguna.</p>}
            {historial.map((p, i) => (
              <div key={i} style={{ fontSize: 13, padding: "6px 0", borderBottom: "1px solid var(--border)", display: "flex", gap: 10, flexWrap: "wrap" }}>
                <span style={{ color: "var(--muted)", width: 130 }}>{new Date(p.fecha).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" })}</span>
                <span style={{ width: 110, color: "var(--muted)" }}>{p.canal}</span>
                <span style={{ fontWeight: 600, color: "var(--text)", flex: 1, minWidth: 180 }}>{p.titulo}</span>
                {Object.entries(p.resultados).map(([red, r]) => (
                  <span key={red} style={{ color: r.ok ? "var(--success)" : "var(--error)" }}>
                    {RED_NOMBRE[red] || red}: {r.ok && r.url ? <a href={r.url} target="_blank" rel="noreferrer" style={{ color: "inherit" }}>ver</a> : r.error}
                  </span>
                ))}
                {p.origen && <span style={{ color: "var(--muted)" }}>({p.origen})</span>}
              </div>
            ))}
          </section>
        </div>
      </div>
    </main>
  );
}
