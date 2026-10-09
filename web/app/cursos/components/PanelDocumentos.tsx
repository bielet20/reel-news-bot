"use client";

// Documentación del curso: subir archivos / URLs, importar un PowerPoint tal
// cual y pedir a la IA el temario.

import { useRef, useState } from "react";
import type { Curso } from "../tipos";
import { btn, btnPeligro, btnPrimario, etiqueta, input, panel } from "./ui";

const ICONO: Record<string, string> = { pdf: "📕", docx: "📘", pptx: "📙", texto: "📄", url: "🌐" };

export default function PanelDocumentos({
  curso, ocupado, onCambio, onTarea,
}: {
  curso: Curso;
  ocupado: boolean;
  onCambio: () => void;
  onTarea: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [url, setUrl] = useState("");
  const [nModulos, setNModulos] = useState(0);
  const [mensajes, setMensajes] = useState<string[]>([]);
  const [auto, setAuto] = useState(true);

  async function subir(files: FileList | null) {
    if (!files?.length) return;
    setSubiendo(true);
    setMensajes([]);
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("archivos", f));
    fd.append("auto", String(auto));
    let tarea = false;
    try {
      const r = await fetch(`/api/cursos/${curso.id}/documentos`, { method: "POST", body: fd });
      const d = await r.json();
      setMensajes(d.errores || []);
      tarea = !!d.tarea;
    } catch (e) { setMensajes([String(e)]); }
    setSubiendo(false);
    if (fileRef.current) fileRef.current.value = "";
    if (tarea) onTarea(); else onCambio();
  }

  async function subirUrl() {
    if (!url.trim()) return;
    setSubiendo(true);
    setMensajes([]);
    const r = await fetch(`/api/cursos/${curso.id}/documentos/url`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url, auto }),
    });
    let tarea = false;
    if (!r.ok) setMensajes([(await r.json().catch(() => ({}))).detail || "No se pudo leer la URL"]);
    else { setUrl(""); tarea = !!(await r.json()).tarea; }
    setSubiendo(false);
    if (tarea) onTarea(); else onCambio();
  }

  async function borrar(id: string) {
    await fetch(`/api/cursos/${curso.id}/documentos/${id}`, { method: "DELETE" });
    onCambio();
  }

  async function importar(id: string) {
    await fetch(`/api/cursos/${curso.id}/documentos/${id}/importar`, { method: "POST" });
    onTarea();
  }

  async function temario() {
    if (curso.modulos.length && !window.confirm("Ya hay un temario. ¿Sustituirlo por uno nuevo? Se perderán las lecciones actuales.")) return;
    await fetch(`/api/cursos/${curso.id}/temario`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ n_modulos: nModulos }),
    });
    onTarea();
  }

  async function todo() {
    await fetch(`/api/cursos/${curso.id}/automatico`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ n_modulos: nModulos }),
    });
    onTarea();
  }

  return (
    <div style={{ ...panel, padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
      <p style={etiqueta}>1 · Documentación ({curso.documentos.length})</p>

      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); subir(e.dataTransfer.files); }}
        onClick={() => fileRef.current?.click()}
        style={{ border: "1px dashed var(--border)", borderRadius: 10, padding: "18px 12px", textAlign: "center", cursor: "pointer", background: "var(--bg)" }}
      >
        <div style={{ fontSize: 22 }}>📥</div>
        <div style={{ fontSize: 13 }}>{subiendo ? "Leyendo documentos…" : "Arrastra aquí o haz clic para subir"}</div>
        <div style={{ fontSize: 11, color: "var(--muted)" }}>PDF · Word (.docx) · PowerPoint (.pptx) · Markdown · texto</div>
        <input ref={fileRef} type="file" multiple accept=".pdf,.docx,.pptx,.md,.markdown,.txt,.rst"
          style={{ display: "none" }} onChange={(e) => subir(e.target.files)} />
      </div>

      <div style={{ display: "flex", gap: 6 }}>
        <input style={input} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://documentación online…"
          onKeyDown={(e) => e.key === "Enter" && subirUrl()} />
        <button type="button" style={btn} onClick={subirUrl} disabled={subiendo}>Añadir</button>
      </div>

      <label style={{ fontSize: 12, display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
        <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} style={{ accentColor: "var(--accent)" }} />
        Al subir, generar el curso completo solo (temario, lecciones, imágenes y vídeos)
      </label>

      {mensajes.map((m, i) => <p key={i} style={{ fontSize: 12, color: "var(--error)", margin: 0 }}>⚠ {m}</p>)}

      {curso.documentos.map((d) => (
        <div key={d.id} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", background: "var(--surface2)", borderRadius: 10, padding: "8px 10px" }}>
          <span style={{ fontSize: 18 }}>{ICONO[d.tipo] || "📄"}</span>
          <div style={{ flex: "1 1 160px", minWidth: 0 }}>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.titulo}</p>
            <p style={{ margin: 0, fontSize: 11, color: "var(--muted)" }}>
              {d.palabras} palabras · {d.n_imagenes} imágenes{d.n_diapositivas ? ` · ${d.n_diapositivas} diapositivas` : ""}
            </p>
          </div>
          {d.tipo === "pptx" && (
            <button type="button" style={btn} onClick={() => importar(d.id)} disabled={ocupado}
              title="Crea un módulo con estas diapositivas tal cual; las notas del orador serán la narración">
              Importar diapositivas
            </button>
          )}
          <button type="button" style={btnPeligro} onClick={() => borrar(d.id)}>✕</button>
        </div>
      ))}

      <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        <p style={etiqueta}>2 · Temario</p>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <select value={nModulos} onChange={(e) => setNModulos(Number(e.target.value))} style={{ ...input, width: "auto" }}>
            <option value={0}>Módulos: automático</option>
            {[1, 2, 3, 4, 5, 6, 8].map((n) => <option key={n} value={n}>{n} módulos</option>)}
          </select>
          <button type="button" style={btnPrimario} onClick={temario} disabled={ocupado || !curso.documentos.length}>
            ✨ {curso.modulos.length ? "Rehacer temario" : "Solo el temario"}
          </button>
          <button type="button" style={btnPrimario} onClick={todo} disabled={ocupado || !curso.documentos.length}
            title="Lo que falte: temario, lecciones con imágenes, vídeo de cada lección y el curso completo unido">
            🚀 Generar todo
          </button>
        </div>
        <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>
          La IA lee la documentación y propone módulos y lecciones. Luego puedes renombrar, reordenar o añadir lecciones en el árbol.
        </p>
      </div>
    </div>
  );
}
