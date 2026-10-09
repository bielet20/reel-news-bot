"use client";

// Zona «Cursos y formaciones»: lista de cursos + alta de uno nuevo. Al crear
// se entra en el editor, que empieza por la documentación.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AvisoServicios from "../components/AvisoServicios";

interface CursoResumen {
  id: string; titulo: string; descripcion: string; actualizado: string;
  n_modulos: number; n_lecciones: number; n_renderizadas: number; n_documentos: number;
}

const input: React.CSSProperties = {
  width: "100%", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8,
  padding: "9px 12px", color: "var(--text)", fontSize: 14, outline: "none", boxSizing: "border-box",
};

export default function CursosPage() {
  const router = useRouter();
  const [cursos, setCursos] = useState<CursoResumen[] | null>(null);
  const [titulo, setTitulo] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [publico, setPublico] = useState("");
  const [minutos, setMinutos] = useState(5);
  const [creando, setCreando] = useState(false);
  const [error, setError] = useState("");

  async function cargar() {
    try {
      const r = await fetch("/api/cursos");
      setCursos(r.ok ? await r.json() : []);
    } catch { setCursos([]); }
  }
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    cargar();
  }, []);

  async function crear(e: React.FormEvent) {
    e.preventDefault();
    if (!titulo.trim()) return;
    setCreando(true);
    setError("");
    try {
      const r = await fetch("/api/cursos", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ titulo, descripcion, publico }),
      });
      if (!r.ok) throw new Error(await r.text());
      const c = await r.json();
      await fetch(`/api/cursos/${c.id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duracion_leccion_min: minutos }),
      });
      router.push(`/cursos/${c.id}`);
    } catch (err) {
      setError(String(err));
      setCreando(false);
    }
  }

  async function borrar(c: CursoResumen) {
    if (!window.confirm(`¿Borrar el curso «${c.titulo}» con su documentación y vídeos? No se puede deshacer.`)) return;
    await fetch(`/api/cursos/${c.id}`, { method: "DELETE" });
    cargar();
  }

  return (
    <main className="page-wrap" style={{ paddingTop: 28, paddingBottom: 60 }}>
      <AvisoServicios seccion="cursos" />
      <h1 style={{ fontSize: 26, fontWeight: 800, margin: 0 }}>🎓 Cursos y formaciones</h1>
      <p style={{ color: "var(--muted)", fontSize: 14, margin: "6px 0 24px" }}>
        Sube tu documentación (PDF, Word, PowerPoint, Markdown o webs) y la app hace el resto sola: temario,
        diapositivas, imágenes, narración y el vídeo de cada lección, más el curso completo unido. Si quieres,
        luego lo retocas como en un editor de vídeo y vuelves a renderizar.
      </p>

      <div style={{ display: "grid", gap: 20, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", alignItems: "start" }}>
        <form onSubmit={crear} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 16, padding: 20, display: "flex", flexDirection: "column", gap: 12 }}>
          <p style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: 0 }}>Nuevo curso</p>
          <label style={{ fontSize: 12, color: "var(--muted)" }}>Título
            <input style={input} value={titulo} onChange={(e) => setTitulo(e.target.value)} placeholder="ej: Git desde cero" required />
          </label>
          <label style={{ fontSize: 12, color: "var(--muted)" }}>Descripción (opcional)
            <textarea style={{ ...input, resize: "vertical" }} rows={2} value={descripcion} onChange={(e) => setDescripcion(e.target.value)}
              placeholder="Qué aprenderá el alumno" />
          </label>
          <label style={{ fontSize: 12, color: "var(--muted)" }}>Público (opcional)
            <input style={input} value={publico} onChange={(e) => setPublico(e.target.value)} placeholder="ej: principiantes, equipo de soporte, clientes" />
          </label>
          <label style={{ fontSize: 12, color: "var(--muted)" }}>Duración de cada lección: <b style={{ color: "var(--text)" }}>{minutos} min</b>
            <input type="range" min={1} max={20} value={minutos} onChange={(e) => setMinutos(Number(e.target.value))} style={{ width: "100%", accentColor: "var(--accent)" }} />
          </label>
          {error && <p style={{ color: "var(--error)", fontSize: 12, margin: 0 }}>{error}</p>}
          <button type="submit" disabled={creando || !titulo.trim()}
            style={{ background: "var(--accent)", color: "#fff", border: "none", borderRadius: 10, padding: "11px 0", fontWeight: 700, cursor: "pointer", opacity: creando ? 0.6 : 1 }}>
            {creando ? "Creando…" : "Crear y subir la documentación →"}
          </button>
        </form>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--muted)", margin: 0 }}>
            Tus cursos {cursos ? `(${cursos.length})` : ""}
          </p>
          {cursos === null ? <p style={{ color: "var(--muted)" }}>Cargando…</p> : cursos.length === 0 ? (
            <p style={{ color: "var(--muted)", fontSize: 14 }}>Aún no hay cursos. Crea el primero.</p>
          ) : cursos.map((c) => (
            <div key={c.id} onClick={() => router.push(`/cursos/${c.id}`)}
              style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, padding: "14px 16px", cursor: "pointer", display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <div style={{ flex: "1 1 220px", minWidth: 0 }}>
                <p style={{ margin: 0, fontWeight: 700, fontSize: 15 }}>{c.titulo}</p>
                <p style={{ margin: "3px 0 0", fontSize: 12, color: "var(--muted)" }}>
                  {c.n_documentos} documento{c.n_documentos === 1 ? "" : "s"} · {c.n_modulos} módulos · {c.n_lecciones} lecciones
                  {c.n_lecciones > 0 && ` · ${c.n_renderizadas}/${c.n_lecciones} en vídeo`}
                </p>
              </div>
              <button type="button" onClick={(e) => { e.stopPropagation(); borrar(c); }}
                style={{ background: "var(--surface2)", border: "1px solid var(--border)", color: "#f87171", borderRadius: 8, padding: "5px 10px", fontSize: 12, cursor: "pointer" }}>
                🗑 Borrar
              </button>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
