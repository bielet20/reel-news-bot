"use client";

// Ajustes del curso: datos, tema visual de las diapositivas, voz, música de
// fondo, subtítulos y duración objetivo de cada lección.

import { useEffect, useState } from "react";
import type { Curso, Tema } from "../tipos";
import { TEMA_DEFECTO } from "../tipos";
import { btn, btnPrimario, etiqueta, input, panel } from "./ui";

const TEMAS: { nombre: string; tema: Tema }[] = [
  { nombre: "Noche", tema: TEMA_DEFECTO },
  { nombre: "Claro", tema: { fondo: "#f8fafc", texto: "#0f172a", acento: "#2563eb", fuente: "Inter" } },
  { nombre: "Grafito", tema: { fondo: "#18181b", texto: "#fafafa", acento: "#f59e0b", fuente: "Inter" } },
  { nombre: "Bosque", tema: { fondo: "#052e2b", texto: "#ecfdf5", acento: "#34d399", fuente: "Inter" } },
  { nombre: "Corporativo", tema: { fondo: "#ffffff", texto: "#1e293b", acento: "#dc2626", fuente: "Inter" } },
];

export default function AjustesCurso({
  curso, onCerrar, onGuardado,
}: {
  curso: Curso;
  onCerrar: () => void;
  onGuardado: (c: Curso) => void;
}) {
  const [c, setC] = useState({
    titulo: curso.titulo, descripcion: curso.descripcion, publico: curso.publico,
    tema: { ...TEMA_DEFECTO, ...curso.tema }, voz: { ...curso.voz }, musica: curso.musica || "",
    volumen_musica: curso.volumen_musica, subtitulos: curso.subtitulos, duracion_leccion_min: curso.duracion_leccion_min,
  });
  const [voces, setVoces] = useState<{ id: string; name: string }[]>([]);
  const [musicas, setMusicas] = useState<{ filename: string; name: string }[]>([]);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    fetch(`/api/tts/voices?servicio=${c.voz.servicio}`).then((r) => r.json()).then((d) => setVoces(d.voices || [])).catch(() => {});
  }, [c.voz.servicio]);
  useEffect(() => {
    fetch("/api/music").then((r) => r.json()).then((d) => setMusicas(Array.isArray(d) ? d : [])).catch(() => {});
  }, []);

  async function guardar() {
    setGuardando(true);
    const r = await fetch(`/api/cursos/${curso.id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(c),
    });
    setGuardando(false);
    if (r.ok) onGuardado(await r.json());
  }

  const campo = (label: string, el: React.ReactNode) => (
    <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, color: "var(--muted)" }}>{label}{el}</label>
  );

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 2000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ ...panel, width: "100%", maxWidth: 560, maxHeight: "calc(88vh / var(--zoom, 1))", overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p style={{ fontWeight: 800, fontSize: 16, margin: 0 }}>Ajustes del curso</p>
          <button type="button" style={btn} onClick={onCerrar}>✕</button>
        </div>
        {campo("Título", <input style={input} value={c.titulo} onChange={(e) => setC({ ...c, titulo: e.target.value })} />)}
        {campo("Descripción", <textarea style={{ ...input, resize: "vertical" }} rows={2} value={c.descripcion} onChange={(e) => setC({ ...c, descripcion: e.target.value })} />)}
        {campo("Público", <input style={input} value={c.publico} onChange={(e) => setC({ ...c, publico: e.target.value })} />)}
        {campo(`Duración objetivo de cada lección: ${c.duracion_leccion_min} min (para las que genere la IA)`,
          <input type="range" min={1} max={20} value={c.duracion_leccion_min} onChange={(e) => setC({ ...c, duracion_leccion_min: Number(e.target.value) })} style={{ accentColor: "var(--accent)" }} />)}

        <p style={{ ...etiqueta, marginTop: 6 }}>Diseño de las diapositivas</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {TEMAS.map((t) => (
            <button key={t.nombre} type="button" onClick={() => setC({ ...c, tema: { ...t.tema } })}
              style={{ ...btn, background: t.tema.fondo, color: t.tema.texto, border: `2px solid ${c.tema.fondo === t.tema.fondo && c.tema.acento === t.tema.acento ? "var(--accent)" : t.tema.acento}` }}>
              <span style={{ color: t.tema.acento }}>■</span> {t.nombre}
            </button>
          ))}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
          {(["fondo", "texto", "acento"] as const).map((k) => campo(k[0].toUpperCase() + k.slice(1),
            <input type="color" value={c.tema[k]} onChange={(e) => setC({ ...c, tema: { ...c.tema, [k]: e.target.value } })}
              style={{ width: "100%", height: 32, background: "none", border: "1px solid var(--border)", borderRadius: 6 }} />))}
        </div>

        <p style={{ ...etiqueta, marginTop: 6 }}>Voz y sonido</p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {campo("Servicio", <select style={input} value={c.voz.servicio} onChange={(e) => setC({ ...c, voz: { servicio: e.target.value, voz: "" } })}>
            <option value="edge-tts">Edge TTS (gratis)</option>
            <option value="elevenlabs">ElevenLabs</option>
          </select>)}
          {campo("Voz", <select style={input} value={c.voz.voz} onChange={(e) => setC({ ...c, voz: { ...c.voz, voz: e.target.value } })}>
            {!c.voz.voz && <option value="">(por defecto)</option>}
            {voces.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>)}
        </div>
        {campo("Música de fondo", <select style={input} value={c.musica} onChange={(e) => setC({ ...c, musica: e.target.value })}>
          <option value="">Sin música</option>
          {musicas.map((m) => <option key={m.filename} value={m.filename}>{m.name}</option>)}
        </select>)}
        {c.musica && campo(`Volumen de la música: ${Math.round(c.volumen_musica * 100)}% (baja sola cuando habla la voz)`,
          <input type="range" min={0} max={0.5} step={0.01} value={c.volumen_musica} onChange={(e) => setC({ ...c, volumen_musica: Number(e.target.value) })} style={{ accentColor: "var(--accent)" }} />)}
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
          <input type="checkbox" checked={c.subtitulos} onChange={(e) => setC({ ...c, subtitulos: e.target.checked })} style={{ accentColor: "var(--accent)" }} />
          Subtítulos grabados en el vídeo (el .srt se genera siempre)
        </label>
        <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>Cambiar la voz obliga a regenerar las narraciones al renderizar.</p>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button type="button" style={btn} onClick={onCerrar}>Cancelar</button>
          <button type="button" style={btnPrimario} onClick={guardar} disabled={guardando}>{guardando ? "Guardando…" : "Guardar"}</button>
        </div>
      </div>
    </div>
  );
}
