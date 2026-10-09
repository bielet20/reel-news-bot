"use client";

// Línea de tiempo de la lección: cada escena es un bloque de ancho
// proporcional a su duración. Arrastrar para reordenar, zoom, insertar
// diapositivas o clips de vídeo (grabaciones de pantalla), duplicar, borrar.
// Pista inferior: la voz de cada escena. Cabezal durante la vista previa.

import { useRef, useState } from "react";
import type { Escena } from "../tipos";
import { duracionEscena, fmtDur, LAYOUTS } from "../tipos";
import { btn, btnPeligro, etiqueta, panel } from "./ui";

const ICONO_LAYOUT: Record<string, string> = {
  portada: "🏁", vinetas: "☰", imagen_texto: "🖼", imagen_completa: "🌄", codigo: "⌨", cita: "❝",
  comparacion: "⚖", pasos: "①", resumen: "✔", cuestionario: "?",
};

export default function Timeline({
  escenas, seleccion, tiempoActual, onSeleccionar, onEscenas, onNuevaDiapositiva, onNuevoVideo, onDuplicar, onBorrar,
}: {
  escenas: Escena[];
  seleccion: string | null;
  tiempoActual: number | null;
  onSeleccionar: (id: string) => void;
  onEscenas: (e: Escena[]) => void;
  onNuevaDiapositiva: (despuesDe: number) => void;
  onNuevoVideo: (f: File, despuesDe: number) => void;
  onDuplicar: (id: string) => void;
  onBorrar: (id: string) => void;
}) {
  const [pxSeg, setPxSeg] = useState(12);
  const [arrastrando, setArrastrando] = useState<number | null>(null);
  const [destino, setDestino] = useState<number | null>(null);
  const videoRef = useRef<HTMLInputElement>(null);
  const idxSel = escenas.findIndex((e) => e.id === seleccion);
  const total = escenas.reduce((s, e) => s + duracionEscena(e), 0);

  function soltar(i: number) {
    if (arrastrando === null || arrastrando === i) { setArrastrando(null); setDestino(null); return; }
    const n = [...escenas];
    const [e] = n.splice(arrastrando, 1);
    n.splice(i > arrastrando ? i - 1 : i, 0, e);
    onEscenas(n);
    setArrastrando(null);
    setDestino(null);
  }

  // marcas de tiempo cada 5/10/30 s según el zoom
  const paso = pxSeg >= 20 ? 5 : pxSeg >= 8 ? 10 : 30;
  const marcas = Array.from({ length: Math.floor(total / paso) + 1 }, (_, k) => k * paso);

  const inicios: number[] = [];
  escenas.forEach((e, i) => inicios.push(i ? inicios[i - 1] + duracionEscena(escenas[i - 1]) : 0));
  return (
    <div style={{ ...panel, padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <p style={etiqueta}>Línea de tiempo · {escenas.length} escenas · {fmtDur(total)}</p>
        <div style={{ flex: 1 }} />
        <button type="button" style={btn} onClick={() => onNuevaDiapositiva(idxSel >= 0 ? idxSel : escenas.length - 1)}>+ Diapositiva</button>
        <button type="button" style={btn} onClick={() => videoRef.current?.click()} title="Grabación de pantalla o clip de vídeo">+ Vídeo</button>
        <input ref={videoRef} type="file" accept="video/*" style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onNuevoVideo(f, idxSel >= 0 ? idxSel : escenas.length - 1); e.target.value = ""; }} />
        {seleccion && <>
          <button type="button" style={btn} onClick={() => onDuplicar(seleccion)}>⧉ Duplicar</button>
          <button type="button" style={btnPeligro} onClick={() => onBorrar(seleccion)}>🗑 Borrar</button>
        </>}
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--muted)" }}>
          🔍 <input type="range" min={3} max={40} value={pxSeg} onChange={(e) => setPxSeg(Number(e.target.value))} style={{ width: 90, accentColor: "var(--accent)" }} />
        </label>
      </div>

      <div style={{ overflowX: "auto", paddingBottom: 6 }}>
        <div style={{ position: "relative", width: Math.max(total * pxSeg + 40, 300) }}>
          {/* regla */}
          <div style={{ position: "relative", height: 16, fontSize: 10, color: "var(--muted)" }}>
            {marcas.map((t) => (
              <span key={t} style={{ position: "absolute", left: t * pxSeg, borderLeft: "1px solid var(--border)", paddingLeft: 3 }}>{fmtDur(t)}</span>
            ))}
          </div>
          {/* pista de escenas */}
          <div style={{ display: "flex", height: 64 }}>
            {escenas.map((e, i) => {
              const d = duracionEscena(e);
              const inicio = inicios[i];
              const sel = e.id === seleccion;
              const titulo = e.tipo === "video" ? "🎥 Clip de vídeo" :
                `${ICONO_LAYOUT[e.layout] || ""} ${e.contenido.titulo || e.contenido.pregunta || e.contenido.cita || LAYOUTS.find((l) => l.id === e.layout)?.label}`;
              return (
                <div key={e.id}
                  draggable
                  onDragStart={() => setArrastrando(i)}
                  onDragOver={(ev) => { ev.preventDefault(); setDestino(i); }}
                  onDragEnd={() => { setArrastrando(null); setDestino(null); }}
                  onDrop={() => soltar(i)}
                  onClick={() => onSeleccionar(e.id)}
                  title={`${titulo} · ${d.toFixed(1)} s · empieza en ${fmtDur(inicio)}`}
                  style={{
                    width: Math.max(d * pxSeg, 26), flexShrink: 0, boxSizing: "border-box", cursor: "grab",
                    borderRadius: 8, marginRight: 2, padding: "6px 7px", overflow: "hidden",
                    background: e.tipo === "video" ? "rgba(56,189,248,0.16)" : sel ? "rgba(155,89,247,0.3)" : "var(--surface2)",
                    // propiedades de borde separadas: mezclar `border` con `borderLeft` hace que React
                    // avise (y deje estilos viejos) al cambiar el indicador de dónde se suelta
                    borderStyle: "solid",
                    borderColor: sel ? "var(--accent)" : "var(--border)",
                    borderWidth: 1,
                    borderLeftWidth: destino === i && arrastrando !== null && arrastrando !== i ? 3 : 1,
                    borderLeftColor: destino === i && arrastrando !== null && arrastrando !== i ? "var(--accent)" : (sel ? "var(--accent)" : "var(--border)"),
                    opacity: arrastrando === i ? 0.4 : 1,
                  }}>
                  <div style={{ fontSize: 11, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{i + 1}. {titulo}</div>
                  <div style={{ fontSize: 10, color: "var(--muted)" }}>{d.toFixed(1)} s{e.transicion === "fundido" ? " · fundido" : ""}</div>
                </div>
              );
            })}
            <div onDragOver={(ev) => { ev.preventDefault(); setDestino(escenas.length); }} onDrop={() => soltar(escenas.length)}
              style={{ width: 40, flexShrink: 0, borderLeft: destino === escenas.length ? "3px solid var(--accent)" : undefined }} />
          </div>
          {/* pista de voz */}
          <div style={{ display: "flex", height: 16, marginTop: 4 }}>
            {escenas.map((e) => {
              const d = duracionEscena(e);
              const voz = e.audio?.duracion ?? 0;
              return (
                <div key={e.id} style={{ width: Math.max(d * pxSeg, 26), flexShrink: 0, marginRight: 2, position: "relative" }}>
                  {e.narracion.trim() && (
                    <div title={e.audio ? `voz ${voz.toFixed(1)} s` : "voz sin generar"}
                      style={{
                        height: "100%", borderRadius: 4,
                        width: e.audio ? `${Math.min(100, (voz / d) * 100)}%` : "100%",
                        background: e.audio ? "rgba(74,222,128,0.35)" : "repeating-linear-gradient(45deg, rgba(122,116,144,0.25) 0 6px, transparent 6px 12px)",
                      }} />
                  )}
                </div>
              );
            })}
          </div>
          {tiempoActual !== null && (
            <div style={{ position: "absolute", top: 0, bottom: 0, left: tiempoActual * pxSeg, width: 2, background: "#f43f5e", pointerEvents: "none" }} />
          )}
        </div>
      </div>
      <p style={{ fontSize: 10.5, color: "var(--muted)", margin: 0 }}>
        Arrastra los bloques para reordenar · verde = voz generada, rayado = pendiente (se genera al reproducir o renderizar)
      </p>
    </div>
  );
}
