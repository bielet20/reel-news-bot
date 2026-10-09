"use client";

// Subir un curso a YouTube (canal de cursos, por el Centro de Redes): elegir
// qué lecciones (o todas), si va también el curso entero con capítulos, y la
// privacidad: público, oculto (solo con enlace) o privado.

import { useCallback, useEffect, useRef, useState } from "react";
import { fmtDur } from "../tipos";
import { btn, btnPrimario, etiqueta, panel } from "./ui";

type Publicada = { url: string; video_id: string; privacidad: Privacidad; fecha: string; titulo?: string };
type Privacidad = "public" | "unlisted" | "private";
type Estado = {
  lecciones: { id: string; numero: number; titulo: string; modulo: string; duracion: number | null;
    renderizada: boolean; publicada: Publicada | null }[];
  completo: { renderizado: boolean; duracion: number | null; publicado: Publicada | null };
  todas_renderizadas: boolean;
};
type Resultado = { subidas: { id: string; url: string }[]; fallos: { id: string; titulo: string; error: string }[];
  saltadas: { id: string; titulo: string; motivo: string }[] };
type TareaPub = { id: string; estado: string; log: string[]; error: string; resultado?: Resultado };

const PRIVACIDADES: { valor: Privacidad; nombre: string; ayuda: string }[] = [
  { valor: "public", nombre: "🌍 Público", ayuda: "Lo ve todo el mundo y sale en el canal" },
  { valor: "unlisted", nombre: "🔗 Oculto", ayuda: "Solo quien tenga el enlace" },
  { valor: "private", nombre: "🔒 Privado", ayuda: "Solo tú (puedes publicarlo luego en YouTube Studio)" },
];
const NOMBRE: Record<Privacidad, string> = { public: "público", unlisted: "oculto", private: "privado" };
const CLAVE_PRIV = "cursos_privacidad_youtube";

export default function SubirYoutube({ cursoId, onCerrar, onTarea }: {
  cursoId: string;
  onCerrar: () => void;
  onTarea: () => void;
}) {
  const [estado, setEstado] = useState<Estado | null>(null);
  const [error, setError] = useState("");
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());
  const [completo, setCompleto] = useState(false);
  const [privacidad, setPrivacidad] = useState<Privacidad>(() => {
    try { return (localStorage.getItem(CLAVE_PRIV) as Privacidad) || "public"; } catch { return "public"; }
  });
  const [tarea, setTarea] = useState<TareaPub | null>(null);
  const [enviando, setEnviando] = useState(false);
  const primera = useRef(true);

  const cargar = useCallback(async () => {
    const r = await fetch(`/api/cursos/${cursoId}/publicacion`);
    if (!r.ok) { setError("No se pudo leer el estado del curso"); return; }
    const e: Estado = await r.json();
    setEstado(e);
    if (primera.current) {
      // por defecto: todo lo renderizado que aún no está en YouTube
      primera.current = false;
      setMarcadas(new Set(e.lecciones.filter((l) => l.renderizada && !l.publicada).map((l) => l.id)));
    }
  }, [cursoId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    cargar();
  }, [cargar]);

  useEffect(() => {
    if (!tarea || tarea.estado !== "en_curso") return;
    const t = setInterval(async () => {
      const r = await fetch(`/api/cursos/tareas/${tarea.id}`);
      if (!r.ok) return;
      const d: TareaPub = await r.json();
      setTarea(d);
      if (d.estado !== "en_curso") cargar();
    }, 2500);
    return () => clearInterval(t);
  }, [tarea, cargar]);

  function elegirPrivacidad(p: Privacidad) {
    setPrivacidad(p);
    try { localStorage.setItem(CLAVE_PRIV, p); } catch { /* sin almacenamiento: da igual */ }
  }

  function alternar(id: string) {
    setMarcadas((prev) => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  }

  async function subir() {
    if (!estado) return;
    const lecciones = estado.lecciones.filter((l) => marcadas.has(l.id)).map((l) => l.id);
    const resubir = estado.lecciones.some((l) => marcadas.has(l.id) && l.publicada) || (completo && !!estado.completo.publicado);
    setEnviando(true);
    setError("");
    const r = await fetch(`/api/cursos/${cursoId}/publicar`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lecciones, completo, privacidad, resubir }),
    });
    setEnviando(false);
    if (!r.ok) { setError((await r.json().catch(() => ({}))).detail || "No se pudo empezar la subida"); return; }
    setTarea(await r.json());
    onTarea();
  }

  const subiendo = tarea?.estado === "en_curso";
  const renderizadas = estado?.lecciones.filter((l) => l.renderizada) ?? [];
  const faltan = (estado?.lecciones.length ?? 0) - renderizadas.length;
  const nMarcadas = estado?.lecciones.filter((l) => marcadas.has(l.id)).length ?? 0;
  const repetidas = estado?.lecciones.filter((l) => marcadas.has(l.id) && l.publicada).length ?? 0;
  const total = nMarcadas + (completo ? 1 : 0);
  const res = tarea?.resultado;

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 2000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ ...panel, width: "100%", maxWidth: 640, maxHeight: "calc(88vh / var(--zoom, 1))", overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p style={{ fontWeight: 800, fontSize: 16, margin: 0 }}>⬆ Subir el curso a YouTube</p>
          <button type="button" style={btn} onClick={onCerrar}>✕</button>
        </div>
        <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>
          Se sube al canal de cursos (RayverSec). Cada lección va a una lista de reproducción con el nombre del curso.
        </p>

        {error && <p style={{ color: "#f87171", fontSize: 13, margin: 0 }}>⚠ {error}</p>}
        {!estado ? <p style={{ color: "var(--muted)", margin: 0 }}>Cargando…</p> : (
          <>
            {faltan > 0 && (
              <p style={{ fontSize: 12, color: "#fbbf24", margin: 0 }}>
                ⚠ Faltan {faltan} de {estado.lecciones.length} lecciones por renderizar: solo se pueden subir las que ya tienen vídeo.
              </p>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <p style={{ ...etiqueta, flex: 1 }}>Lecciones ({nMarcadas} de {renderizadas.length} marcadas)</p>
                <button type="button" style={btn} disabled={subiendo}
                  onClick={() => setMarcadas(new Set(renderizadas.map((l) => l.id)))}>Todas</button>
                <button type="button" style={btn} disabled={subiendo}
                  onClick={() => setMarcadas(new Set(renderizadas.filter((l) => !l.publicada).map((l) => l.id)))}>Solo las no subidas</button>
                <button type="button" style={btn} disabled={subiendo} onClick={() => setMarcadas(new Set())}>Ninguna</button>
              </div>
              {estado.lecciones.map((l, i) => {
                const moduloNuevo = i === 0 || estado.lecciones[i - 1].modulo !== l.modulo;
                return (
                  <div key={l.id}>
                    {moduloNuevo && l.modulo && <p style={{ fontSize: 11, color: "var(--muted)", margin: "6px 0 2px" }}>{l.modulo}</p>}
                    <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, padding: "4px 6px", borderRadius: 6,
                      opacity: l.renderizada ? 1 : 0.5, cursor: l.renderizada && !subiendo ? "pointer" : "default",
                      background: marcadas.has(l.id) ? "var(--surface2)" : "transparent" }}>
                      <input type="checkbox" checked={marcadas.has(l.id)} disabled={!l.renderizada || subiendo} onChange={() => alternar(l.id)} />
                      <span style={{ flex: 1 }}>{l.numero}. {l.titulo}</span>
                      {l.duracion != null && <span style={{ fontSize: 11, color: "var(--muted)" }}>{fmtDur(l.duracion)}</span>}
                      {!l.renderizada && <span style={{ fontSize: 11, color: "var(--muted)" }}>sin renderizar</span>}
                      {l.publicada && (
                        <a href={l.publicada.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                          style={{ fontSize: 11, color: "#4ade80" }}>✓ subida ({NOMBRE[l.publicada.privacidad]}) ↗</a>
                      )}
                    </label>
                  </div>
                );
              })}
            </div>

            {estado.completo.renderizado && (
              <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, cursor: "pointer" }}>
                <input type="checkbox" checked={completo} disabled={subiendo} onChange={(e) => setCompleto(e.target.checked)} />
                <span style={{ flex: 1 }}>También el curso completo en un solo vídeo, con capítulos
                  {estado.completo.duracion != null && <span style={{ color: "var(--muted)" }}> ({fmtDur(estado.completo.duracion)})</span>}</span>
                {estado.completo.publicado && (
                  <a href={estado.completo.publicado.url} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: "#4ade80" }}>
                    ✓ subido ({NOMBRE[estado.completo.publicado.privacidad]}) ↗</a>
                )}
              </label>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <p style={etiqueta}>Visibilidad en YouTube</p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8 }}>
                {PRIVACIDADES.map((p) => (
                  <button key={p.valor} type="button" disabled={subiendo} onClick={() => elegirPrivacidad(p.valor)}
                    style={{ ...btn, whiteSpace: "normal", textAlign: "left", padding: "8px 10px",
                      border: privacidad === p.valor ? "2px solid var(--accent)" : "1px solid var(--border)" }}>
                    <b style={{ fontSize: 13 }}>{p.nombre}</b>
                    <span style={{ display: "block", fontSize: 11, color: "var(--muted)", marginTop: 2 }}>{p.ayuda}</span>
                  </button>
                ))}
              </div>
            </div>

            {repetidas > 0 && (
              <p style={{ fontSize: 12, color: "#fbbf24", margin: 0 }}>
                ⚠ {repetidas} de las marcadas ya están en YouTube: se subirán otra vez (quedarán duplicadas).
              </p>
            )}

            {tarea && (
              <div style={{ ...panel, padding: 10, fontSize: 12, display: "flex", flexDirection: "column", gap: 3, background: "var(--bg)" }}>
                <b>{subiendo ? "⟳ Subiendo…" : tarea.estado === "error" ? "✗ La subida falló" : "✓ Subida terminada"}</b>
                {tarea.log.slice(-8).map((l, i) => <span key={i} style={{ color: "var(--muted)", wordBreak: "break-all" }}>{l}</span>)}
                {res && res.fallos.length > 0 && (
                  <span style={{ color: "#f87171" }}>Fallaron {res.fallos.length}: quedan sin marcar como subidas, puedes volver a intentarlo.</span>
                )}
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button type="button" style={btn} onClick={onCerrar}>{subiendo ? "Cerrar (sigue subiendo)" : "Cerrar"}</button>
              <button type="button" style={btnPrimario} disabled={!total || subiendo || enviando} onClick={subir}>
                {subiendo ? "Subiendo…" : `⬆ Subir ${total} vídeo${total !== 1 ? "s" : ""} como ${NOMBRE[privacidad]}`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
