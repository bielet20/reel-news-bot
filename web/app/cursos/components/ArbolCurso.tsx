"use client";

// Árbol del curso: módulos → lecciones. Renombrar en línea, reordenar,
// añadir / borrar y generar cada lección con la IA.

import type { Leccion, Modulo } from "../tipos";
import { duracionEscena, fmtDur, nuevoId } from "../tipos";
import { btn, etiqueta, panel } from "./ui";

const ESTADO: Record<string, { txt: string; color: string }> = {
  pendiente: { txt: "sin generar", color: "var(--muted)" },
  en_cola: { txt: "en cola", color: "#fbbf24" },
  generando: { txt: "generando…", color: "#60a5fa" },
  lista: { txt: "", color: "var(--success)" },
  error: { txt: "error", color: "#f87171" },
};

function mover<T>(lista: T[], i: number, d: number): T[] {
  const j = i + d;
  if (j < 0 || j >= lista.length) return lista;
  const n = [...lista];
  [n[i], n[j]] = [n[j], n[i]];
  return n;
}

const mini: React.CSSProperties = { ...btn, padding: "1px 6px", fontSize: 11 };
const inputTitulo: React.CSSProperties = {
  background: "transparent", border: "1px solid transparent", color: "inherit", font: "inherit",
  width: "100%", padding: "2px 4px", borderRadius: 5, outline: "none",
};

export default function ArbolCurso({
  modulos, leccionActiva, onSeleccionar, onModulos, onGenerar, onGenerarPendientes, ocupado,
}: {
  modulos: Modulo[];
  leccionActiva: string | null;
  onSeleccionar: (id: string) => void;
  onModulos: (m: Modulo[]) => void;
  onGenerar: (id: string) => void;
  onGenerarPendientes: () => void;
  ocupado: boolean;
}) {
  const setModulo = (i: number, m: Modulo) => onModulos(modulos.map((x, k) => (k === i ? m : x)));
  const pendientes = modulos.flatMap((m) => m.lecciones).filter((l) => !l.escenas.length).length;

  return (
    <div style={{ ...panel, padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <p style={etiqueta}>Temario</p>
        {pendientes > 0 && (
          <button type="button" style={{ ...mini, color: "var(--accent)" }} onClick={onGenerarPendientes} disabled={ocupado}>
            ✨ Generar {pendientes} pendiente{pendientes > 1 ? "s" : ""}
          </button>
        )}
      </div>
      {modulos.length === 0 && (
        <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>Sin temario. Sube documentación y pulsa «Proponer temario», o añade un módulo a mano.</p>
      )}
      {modulos.map((m, mi) => (
        <div key={m.id} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ fontSize: 11, color: "var(--muted)", width: 18 }}>{mi + 1}.</span>
            <input style={{ ...inputTitulo, fontWeight: 700, fontSize: 13 }} value={m.titulo}
              onChange={(e) => setModulo(mi, { ...m, titulo: e.target.value })} />
            <button type="button" style={mini} title="Subir" onClick={() => onModulos(mover(modulos, mi, -1))}>↑</button>
            <button type="button" style={mini} title="Bajar" onClick={() => onModulos(mover(modulos, mi, 1))}>↓</button>
            <button type="button" style={{ ...mini, color: "#f87171" }} title="Borrar módulo"
              onClick={() => window.confirm(`¿Borrar el módulo «${m.titulo}» y sus lecciones?`) && onModulos(modulos.filter((_, k) => k !== mi))}>✕</button>
          </div>
          {m.lecciones.map((l: Leccion, li) => {
            const activa = l.id === leccionActiva;
            const est = ESTADO[l.estado] || ESTADO.pendiente;
            const dur = l.escenas.reduce((s, e) => s + duracionEscena(e), 0);
            return (
              <div key={l.id} onClick={() => onSeleccionar(l.id)}
                style={{
                  marginLeft: 18, padding: "6px 8px", borderRadius: 9, cursor: "pointer",
                  background: activa ? "rgba(155,89,247,0.14)" : "var(--surface2)",
                  border: `1px solid ${activa ? "var(--accent)" : "var(--border)"}`,
                }}>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <input style={{ ...inputTitulo, fontSize: 12.5 }} value={l.titulo}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => setModulo(mi, { ...m, lecciones: m.lecciones.map((x, k) => (k === li ? { ...l, titulo: e.target.value } : x)) })} />
                  <button type="button" style={mini} onClick={(e) => { e.stopPropagation(); setModulo(mi, { ...m, lecciones: mover(m.lecciones, li, -1) }); }}>↑</button>
                  <button type="button" style={mini} onClick={(e) => { e.stopPropagation(); setModulo(mi, { ...m, lecciones: mover(m.lecciones, li, 1) }); }}>↓</button>
                  <button type="button" style={{ ...mini, color: "#f87171" }}
                    onClick={(e) => { e.stopPropagation(); if (window.confirm(`¿Borrar la lección «${l.titulo}»?`)) setModulo(mi, { ...m, lecciones: m.lecciones.filter((_, k) => k !== li) }); }}>✕</button>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 11, color: "var(--muted)", paddingLeft: 4, marginTop: 2, flexWrap: "wrap" }}>
                  {l.escenas.length > 0 && <span>{l.escenas.length} escenas · {fmtDur(dur)}</span>}
                  {l.render?.archivo && <span style={{ color: "var(--success)" }}>🎬 en vídeo</span>}
                  {est.txt && <span style={{ color: est.color }}>{est.txt}</span>}
                  {!l.escenas.length && l.estado !== "en_cola" && l.estado !== "generando" && (
                    <button type="button" style={{ ...mini, color: "var(--accent)" }}
                      onClick={(e) => { e.stopPropagation(); onGenerar(l.id); }}>✨ Generar</button>
                  )}
                </div>
                {l.estado === "error" && l.error && <p style={{ fontSize: 11, color: "#f87171", margin: "3px 0 0 4px" }}>{l.error}</p>}
              </div>
            );
          })}
          <button type="button" style={{ ...mini, marginLeft: 18, alignSelf: "flex-start" }}
            onClick={() => setModulo(mi, { ...m, lecciones: [...m.lecciones, { id: nuevoId(), titulo: "Nueva lección", resumen: "", objetivos: [], estado: "lista", error: "", escenas: [], render: null }] })}>
            + Lección
          </button>
        </div>
      ))}
      <button type="button" style={{ ...btn, alignSelf: "flex-start" }}
        onClick={() => onModulos([...modulos, { id: nuevoId(), titulo: `Módulo ${modulos.length + 1}`, lecciones: [] }])}>
        + Módulo
      </button>
    </div>
  );
}
