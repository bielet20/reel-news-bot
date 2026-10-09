"use client";

// Propiedades de la escena seleccionada: layout, contenido (además de la
// edición directa sobre la diapositiva), imagen, narración + voz, tiempo.

import { useRef, useState } from "react";
import type { Contenido, Escena, Layout } from "../tipos";
import { LAYOUTS, PALABRAS_POR_SEG, duracionEscena, urlArchivo } from "../tipos";
import { btn, btnPrimario, etiqueta, input, panel } from "./ui";

const lineas = (v?: string[]) => (v || []).join("\n");
const aLista = (t: string) => t.split("\n").map((x) => x.trim()).filter(Boolean);

function Campo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, color: "var(--muted)" }}>
      {label}{children}
    </label>
  );
}

export default function SceneInspector({
  cursoId, escena, onCambio, onNarrar,
}: {
  cursoId: string;
  escena: Escena;
  onCambio: (e: Escena) => void;
  onNarrar: (e: Escena, reproducir: boolean) => Promise<void>;
}) {
  const [subiendo, setSubiendo] = useState(false);
  const [generandoImg, setGenerandoImg] = useState(false);
  const [narrando, setNarrando] = useState(false);
  const [aviso, setAviso] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const c = escena.contenido;
  const set = (parcial: Partial<Contenido>) => onCambio({ ...escena, contenido: { ...c, ...parcial } });
  const palabras = escena.narracion.trim() ? escena.narracion.trim().split(/\s+/).length : 0;
  const vozDesfasada = !!escena.audio && palabras > 0 && Math.abs(escena.audio.duracion - palabras / PALABRAS_POR_SEG) > 6;

  async function subirImagen(f: File | undefined) {
    if (!f) return;
    setSubiendo(true);
    const fd = new FormData();
    fd.append("archivo", f);
    const r = await fetch(`/api/cursos/${cursoId}/assets`, { method: "POST", body: fd });
    if (r.ok) set({ imagen: (await r.json()).ruta });
    setSubiendo(false);
  }

  async function imagenIA() {
    const prompt = c.imagen_prompt || c.titulo || "";
    if (!prompt) { setAviso("Escribe una descripción de la imagen"); return; }
    setGenerandoImg(true);
    setAviso("");
    const r = await fetch(`/api/cursos/${cursoId}/imagen-ia`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt }),
    });
    if (r.ok) set({ imagen: (await r.json()).ruta });
    else setAviso("No se pudo generar la imagen");
    setGenerandoImg(false);
  }

  async function narrar() {
    setNarrando(true);
    try { await onNarrar(escena, true); } finally { setNarrando(false); }
  }

  const conImagen = escena.layout === "imagen_texto" || escena.layout === "imagen_completa";

  return (
    <div style={{ ...panel, padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
      <p style={etiqueta}>{escena.tipo === "video" ? "Clip de vídeo" : "Diapositiva"}</p>

      {escena.tipo === "diapositiva" && (
        <>
          <Campo label="Diseño">
            <select style={input} value={escena.layout}
              onChange={(e) => onCambio({ ...escena, layout: e.target.value as Layout })}>
              {LAYOUTS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
            </select>
          </Campo>

          {escena.layout !== "cita" && escena.layout !== "cuestionario" && (
            <Campo label="Título">
              <input style={input} value={c.titulo || ""} onChange={(e) => set({ titulo: e.target.value })} />
            </Campo>
          )}
          {escena.layout === "portada" && (
            <Campo label="Subtítulo">
              <input style={input} value={c.subtitulo || ""} onChange={(e) => set({ subtitulo: e.target.value })} />
            </Campo>
          )}
          {(["vinetas", "resumen", "imagen_texto"] as Layout[]).includes(escena.layout) && (
            <Campo label="Viñetas (una por línea)">
              <textarea style={{ ...input, resize: "vertical" }} rows={5} value={lineas(c.vinetas)}
                onChange={(e) => set({ vinetas: e.target.value.split("\n") })}
                onBlur={(e) => set({ vinetas: aLista(e.target.value) })} />
            </Campo>
          )}
          {escena.layout === "pasos" && (
            <Campo label="Pasos (uno por línea)">
              <textarea style={{ ...input, resize: "vertical" }} rows={6} value={lineas(c.pasos)}
                onChange={(e) => set({ pasos: e.target.value.split("\n") })}
                onBlur={(e) => set({ pasos: aLista(e.target.value) })} />
            </Campo>
          )}
          {escena.layout === "codigo" && (
            <>
              <Campo label="Lenguaje">
                <input style={input} value={c.lenguaje || ""} onChange={(e) => set({ lenguaje: e.target.value })} placeholder="bash, python…" />
              </Campo>
              <Campo label="Código">
                <textarea style={{ ...input, fontFamily: "monospace", resize: "vertical" }} rows={8} value={c.codigo || ""}
                  onChange={(e) => set({ codigo: e.target.value })} />
              </Campo>
            </>
          )}
          {escena.layout === "cita" && (
            <>
              <Campo label="Cita"><textarea style={{ ...input, resize: "vertical" }} rows={3} value={c.cita || ""} onChange={(e) => set({ cita: e.target.value })} /></Campo>
              <Campo label="Autor"><input style={input} value={c.autor || ""} onChange={(e) => set({ autor: e.target.value })} /></Campo>
            </>
          )}
          {escena.layout === "comparacion" && [0, 1].map((i) => {
            const cols = c.columnas?.length ? c.columnas : [{ titulo: "", vinetas: [] }, { titulo: "", vinetas: [] }];
            const col = cols[i] || { titulo: "", vinetas: [] };
            const setCol = (p: Partial<typeof col>) => { const n = [...cols]; n[i] = { ...col, ...p }; set({ columnas: n }); };
            return (
              <Campo key={i} label={`Columna ${i + 1}`}>
                <input style={input} value={col.titulo || ""} onChange={(e) => setCol({ titulo: e.target.value })} placeholder="Título" />
                <textarea style={{ ...input, resize: "vertical" }} rows={3} value={lineas(col.vinetas)}
                  onChange={(e) => setCol({ vinetas: e.target.value.split("\n") })}
                  onBlur={(e) => setCol({ vinetas: aLista(e.target.value) })} placeholder="Una viñeta por línea" />
              </Campo>
            );
          })}
          {escena.layout === "cuestionario" && (
            <>
              <Campo label="Pregunta"><input style={input} value={c.pregunta || ""} onChange={(e) => set({ pregunta: e.target.value })} /></Campo>
              <Campo label="Opciones (una por línea)">
                <textarea style={{ ...input, resize: "vertical" }} rows={4} value={lineas(c.opciones)}
                  onChange={(e) => set({ opciones: e.target.value.split("\n") })}
                  onBlur={(e) => set({ opciones: aLista(e.target.value) })} />
              </Campo>
              <Campo label="Respuesta correcta">
                <select style={input} value={c.correcta ?? 0} onChange={(e) => set({ correcta: Number(e.target.value) })}>
                  {(c.opciones || []).map((o, i) => <option key={i} value={i}>{String.fromCharCode(65 + i)}. {o}</option>)}
                </select>
              </Campo>
            </>
          )}

          {conImagen && (
            <Campo label="Imagen">
              {c.imagen && (/* eslint-disable-next-line @next/next/no-img-element */
                <img src={urlArchivo(cursoId, c.imagen)} alt="" style={{ width: "100%", borderRadius: 8, maxHeight: 140, objectFit: "cover" }} />
              )}
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <button type="button" style={btn} onClick={() => fileRef.current?.click()} disabled={subiendo}>
                  {subiendo ? "Subiendo…" : "📁 Subir"}
                </button>
                <button type="button" style={btn} onClick={imagenIA} disabled={generandoImg}>
                  {generandoImg ? "⟳ Generando…" : "✨ Generar con IA"}
                </button>
                {c.imagen && <button type="button" style={btn} onClick={() => set({ imagen: undefined })}>Quitar</button>}
              </div>
              <input style={input} value={c.imagen_prompt || ""} onChange={(e) => set({ imagen_prompt: e.target.value })}
                placeholder="Descripción para la imagen IA (mejor en inglés)" />
              <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }} onChange={(e) => subirImagen(e.target.files?.[0])} />
            </Campo>
          )}
        </>
      )}

      {escena.tipo === "video" && escena.video && (
        <>
          <video src={urlArchivo(cursoId, escena.video.archivo)} controls style={{ width: "100%", borderRadius: 8, background: "#000" }} />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <Campo label="Inicio (s)">
              <input type="number" step={0.1} min={0} style={input} value={escena.video.inicio}
                onChange={(e) => onCambio({ ...escena, video: { ...escena.video!, inicio: Math.max(0, Number(e.target.value)) } })} />
            </Campo>
            <Campo label="Fin (s)">
              <input type="number" step={0.1} min={0} style={input} value={escena.video.fin}
                onChange={(e) => onCambio({ ...escena, video: { ...escena.video!, fin: Number(e.target.value) } })} />
            </Campo>
          </div>
        </>
      )}

      <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        <Campo label={`Narración · ${palabras} palabras · ~${Math.round(palabras / PALABRAS_POR_SEG)} s`}>
          <textarea style={{ ...input, resize: "vertical", lineHeight: 1.5 }} rows={7} value={escena.narracion}
            onChange={(e) => onCambio({ ...escena, narracion: e.target.value })}
            placeholder={escena.tipo === "video" ? "Opcional: voz en off encima del clip" : "Lo que dirá la voz en esta diapositiva"} />
        </Campo>
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <button type="button" style={btnPrimario} onClick={narrar} disabled={narrando || !palabras}>
            {narrando ? "⟳ Generando voz…" : "▶ Escuchar"}
          </button>
          {escena.audio
            ? <span style={{ fontSize: 11, color: vozDesfasada ? "#fbbf24" : "var(--muted)" }}>voz: {escena.audio.duracion.toFixed(1)} s{vozDesfasada ? " (texto cambiado)" : ""}</span>
            : palabras > 0 && <span style={{ fontSize: 11, color: "var(--muted)" }}>voz sin generar</span>}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <Campo label={`Duración (${duracionEscena(escena).toFixed(1)} s)`}>
          <input type="number" min={0} step={0.5} style={input} value={escena.duracion ?? ""} placeholder="auto (voz)"
            onChange={(e) => onCambio({ ...escena, duracion: e.target.value === "" ? null : Math.max(0, Number(e.target.value)) })} />
        </Campo>
        <Campo label="Transición">
          <select style={input} value={escena.transicion} onChange={(e) => onCambio({ ...escena, transicion: e.target.value as Escena["transicion"] })}>
            <option value="fundido">Fundido</option>
            <option value="corte">Corte</option>
          </select>
        </Campo>
      </div>
      <Campo label="Notas (no salen en el vídeo)">
        <textarea style={{ ...input, resize: "vertical" }} rows={2} value={escena.notas} onChange={(e) => onCambio({ ...escena, notas: e.target.value })} />
      </Campo>
      {escena.fuente && <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>📚 Fuente: {escena.fuente}</p>}
      {aviso && <p style={{ fontSize: 11, color: "#f87171", margin: 0 }}>{aviso}</p>}
    </div>
  );
}
