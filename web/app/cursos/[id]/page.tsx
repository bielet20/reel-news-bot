"use client";

// Editor de un curso: documentación + temario (izquierda), diapositiva
// editable (centro), propiedades de la escena (derecha) y línea de tiempo de
// la lección (abajo). Guarda solo (autoguardado); las tareas largas (IA,
// render) van a la cola del backend y se siguen por polling.

import { use, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { Curso, Escena, Leccion, Modulo, Tarea } from "../tipos";
import { duracionEscena, escenaVacia, fmtDur, nuevoId, urlArchivo } from "../tipos";
import SlideRender, { SLIDE_H, SLIDE_W } from "../components/SlideRender";
import PanelDocumentos from "../components/PanelDocumentos";
import ArbolCurso from "../components/ArbolCurso";
import SceneInspector from "../components/SceneInspector";
import Timeline from "../components/Timeline";
import AjustesCurso from "../components/AjustesCurso";
import SubirYoutube from "../components/SubirYoutube";
import { btn, btnPrimario, etiqueta, panel } from "../components/ui";
import AvisoServicios from "../../components/AvisoServicios";

/** Espera `seg` segundos llamando a onTick(segundos pasados) en cada frame. */
function esperar(seg: number, cancelado: () => boolean, onTick: (pasado: number) => void): Promise<void> {
  const t0 = performance.now();
  return new Promise((res) => {
    const tick = () => {
      const pasado = (performance.now() - t0) / 1000;
      if (cancelado() || pasado >= seg) { res(); return; }
      onTick(pasado);
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

function buscarLeccion(modulos: Modulo[], id: string | null): Leccion | null {
  for (const m of modulos) for (const l of m.lecciones) if (l.id === id) return l;
  return null;
}

/** Lienzo 16:9 que escala la diapositiva de 1920×1080 al ancho disponible. */
function Lienzo({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [escala, setEscala] = useState(0.4);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setEscala(e.contentRect.width / SLIDE_W));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={ref} style={{ width: "100%", height: SLIDE_H * escala, position: "relative", borderRadius: 10, overflow: "hidden", boxShadow: "0 8px 30px rgba(0,0,0,0.45)" }}>
      <div style={{ transform: `scale(${escala})`, transformOrigin: "0 0", width: SLIDE_W, height: SLIDE_H, position: "absolute", top: 0, left: 0 }}>
        {children}
      </div>
    </div>
  );
}

export default function EditorCurso({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [curso, setCurso] = useState<Curso | null>(null);
  const [error, setError] = useState("");
  const [leccionId, setLeccionId] = useState<string | null>(null);
  const [escenaId, setEscenaId] = useState<string | null>(null);
  const [tareas, setTareas] = useState<Tarea[]>([]);
  const [fallidas, setFallidas] = useState<Tarea[]>([]);
  const [guardado, setGuardado] = useState<"ok" | "pendiente" | "guardando">("ok");
  const [verDocs, setVerDocs] = useState(true);
  const [verAjustes, setVerAjustes] = useState(false);
  const [verSubir, setVerSubir] = useState(false);
  const [preview, setPreview] = useState<{ idx: number; t: number; preparando?: string } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cursoRef = useRef<Curso | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const parar = useRef(false);
  const sucio = useRef(false); // hay cambios del editor sin mandar al servidor

  const cargar = useCallback(async () => {
    const r = await fetch(`/api/cursos/${id}`);
    if (!r.ok) { setError("Curso no encontrado"); return; }
    const c: Curso = await r.json();
    const primeraCarga = !cursoRef.current;
    sucio.current = false;
    cursoRef.current = c;
    setCurso(c);
    setLeccionId((prev) => (prev && buscarLeccion(c.modulos, prev) ? prev
      : c.modulos.flatMap((m) => m.lecciones).find((l) => l.escenas.length)?.id ?? c.modulos[0]?.lecciones[0]?.id ?? null));
    if (primeraCarga && c.modulos.length) setVerDocs(false);
  }, [id]);

  // ── Guardado ─────────────────────────────────────────────────────────────
  const guardarYa = useCallback(async () => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    const c = cursoRef.current;
    // sin cambios del usuario no se manda nada: mandar la copia vieja pisaría
    // lo que haya hecho una tarea (p. ej. borraba el temario recién generado)
    if (!c || !sucio.current) return;
    sucio.current = false;
    setGuardado("guardando");
    const r = await fetch(`/api/cursos/${id}/estructura`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ modulos: c.modulos, rev_modulos: c.rev_modulos ?? 0 }),
    });
    if (r.status === 409) cursoRef.current = null; // el temario cambió en el servidor: manda el servidor
    setGuardado("ok");
  }, [id]);

  function cambiarModulos(modulos: Modulo[]) {
    if (!cursoRef.current) return;
    const c = { ...cursoRef.current, modulos };
    cursoRef.current = c;
    setCurso(c);
    sucio.current = true;
    setGuardado("pendiente");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(guardarYa, 900);
  }

  // ── Tareas en segundo plano ──────────────────────────────────────────────
  const hayTareas = tareas.length > 0;
  const nTareasPrevias = useRef(0);
  const revisarTareas = useCallback(async () => {
    const r = await fetch(`/api/cursos/${id}/tareas`);
    const todas: Tarea[] = r.ok ? await r.json() : [];
    const activas = todas.filter((t) => t.estado === "en_cola" || t.estado === "en_curso");
    if (nTareasPrevias.current && activas.length < nTareasPrevias.current) {
      // alguna terminó: guardar lo pendiente y recargar lo que haya hecho
      await guardarYa();
      await cargar();
    }
    nTareasPrevias.current = activas.length;
    setTareas(activas);
    setFallidas(todas.filter((t) => t.estado === "error"));
  }, [id, cargar, guardarYa]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    cargar();
    revisarTareas();
  }, [cargar, revisarTareas]);

  useEffect(() => {
    if (!hayTareas) return;
    const t = setInterval(revisarTareas, 2500);
    return () => clearInterval(t);
  }, [hayTareas, revisarTareas]);

  function tareaLanzada() {
    guardarYa().then(() => { revisarTareas(); cargar(); });
  }

  if (error) return <main className="page-wrap" style={{ paddingTop: 30 }}><p>{error}</p><Link href="/cursos">← Cursos</Link></main>;
  if (!curso) return <main className="page-wrap" style={{ paddingTop: 30 }}><p style={{ color: "var(--muted)" }}>Cargando…</p></main>;

  const leccion = buscarLeccion(curso.modulos, leccionId);
  const escenas = leccion?.escenas ?? [];
  const escena = escenas.find((e) => e.id === escenaId) ?? escenas[0] ?? null;
  const tareaLeccion = tareas.find((t) => t.objetivo === leccion?.id);

  function cambiarLeccion(l: Leccion) {
    cambiarModulos(curso!.modulos.map((m) => ({ ...m, lecciones: m.lecciones.map((x) => (x.id === l.id ? l : x)) })));
  }
  function cambiarEscenas(nuevas: Escena[]) {
    if (leccion) cambiarLeccion({ ...leccion, escenas: nuevas, render: leccion.render });
  }
  function cambiarEscena(e: Escena) {
    const previa = escenas.find((x) => x.id === e.id);
    // texto de la voz cambiado → el audio anterior ya no vale
    if (previa && previa.narracion !== e.narracion) e = { ...e, audio: null };
    cambiarEscenas(escenas.map((x) => (x.id === e.id ? e : x)));
  }

  async function narrar(e: Escena, reproducir: boolean): Promise<Escena["audio"]> {
    await guardarYa();
    const r = await fetch(`/api/cursos/${id}/escenas/${e.id}/narrar`, { method: "POST" });
    if (!r.ok) { alert((await r.json().catch(() => ({}))).detail || "No se pudo generar la voz"); return null; }
    const { audio } = await r.json();
    const c = cursoRef.current!;
    const modulos = c.modulos.map((m) => ({ ...m, lecciones: m.lecciones.map((l) => ({ ...l, escenas: l.escenas.map((x) => (x.id === e.id ? { ...x, audio } : x)) })) }));
    cursoRef.current = { ...c, modulos };
    setCurso(cursoRef.current);
    if (reproducir && audio) new Audio(urlArchivo(id, audio.archivo) + `?v=${audio.hash}`).play();
    return audio;
  }

  async function lanzar(url: string) {
    await guardarYa();
    await fetch(url, { method: "POST" });
    tareaLanzada();
  }

  async function nuevoVideo(f: File, despuesDe: number) {
    const fd = new FormData();
    fd.append("archivo", f);
    const r = await fetch(`/api/cursos/${id}/assets`, { method: "POST", body: fd });
    if (!r.ok) { alert("No se pudo subir el vídeo"); return; }
    const d = await r.json();
    const e: Escena = { ...escenaVacia(), tipo: "video", contenido: { titulo: f.name },
      video: { archivo: d.ruta, inicio: 0, fin: d.duracion || 10, duracion_total: d.duracion } };
    const n = [...escenas];
    n.splice(despuesDe + 1, 0, e);
    cambiarEscenas(n);
    setEscenaId(e.id);
  }

  // ── Vista previa en el navegador ─────────────────────────────────────────
  async function reproducir() {
    if (!leccion || !escenas.length) return;
    parar.current = false;
    const lista = [...escenas];
    for (let i = 0; i < lista.length; i++) {
      if (parar.current) { setPreview(null); return; }
      if (lista[i].narracion.trim() && !lista[i].audio) {
        setPreview({ idx: i, t: 0, preparando: `Generando voces ${i + 1}/${lista.length}…` });
        const audio = await narrar(lista[i], false);
        lista[i] = { ...lista[i], audio };
      }
    }
    let inicio = 0;
    for (let i = 0; i < lista.length; i++) {
      if (parar.current) break;
      const e = lista[i];
      const d = duracionEscena(e);
      setEscenaId(e.id);
      setPreview({ idx: i, t: inicio });
      if (e.audio) {
        const a = new Audio(urlArchivo(id, e.audio.archivo) + `?v=${e.audio.hash}`);
        audioRef.current = a;
        a.play().catch(() => {});
      }
      const ini = inicio;
      await esperar(d, () => parar.current, (pasado) => setPreview({ idx: i, t: ini + pasado }));
      audioRef.current?.pause();
      inicio += d;
    }
    setPreview(null);
  }
  function detener() {
    parar.current = true;
    audioRef.current?.pause();
    videoRef.current?.pause();
    setPreview(null);
  }

  const ocupado = tareas.length > 0;
  const enPreview = preview && !preview.preparando;
  const escenaVista = enPreview ? escenas[preview.idx] : escena;
  const numero = escenaVista ? `${escenas.indexOf(escenaVista) + 1} / ${escenas.length}` : "";
  const durLeccion = escenas.reduce((s, e) => s + duracionEscena(e), 0);

  return (
    <main className="page-wrap" style={{ paddingTop: 16, paddingBottom: 40 }}>
      <AvisoServicios seccion="cursos" />
      {/* misma fuente que la página de render: lo que ves es lo que sale */}
      {/* eslint-disable-next-line @next/next/no-page-custom-font */}
      <link rel="stylesheet" precedence="default"
        href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=JetBrains+Mono&display=swap" />
      <style>{`.slide-editable:hover{outline:2px dashed rgba(155,89,247,.55)!important;outline-offset:6px}
        .slide-editable:focus{outline:3px solid rgba(155,89,247,.9)!important;outline-offset:6px}
        .slide-editable:empty:before{content:attr(data-placeholder);opacity:.35}`}</style>
      {/* Cabecera */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
        <Link href="/cursos" style={{ color: "var(--muted)", fontSize: 13, textDecoration: "none" }}>← Cursos</Link>
        <h1 style={{ fontSize: 20, fontWeight: 800, margin: 0, flex: "1 1 240px" }}>🎓 {curso.titulo}</h1>
        <span style={{ fontSize: 11, color: guardado === "ok" ? "var(--muted)" : "#fbbf24" }}>
          {guardado === "ok" ? "✓ Guardado" : guardado === "guardando" ? "Guardando…" : "Cambios sin guardar"}
        </span>
        <button type="button" style={btn} onClick={() => setVerDocs((v) => !v)}>📚 Documentación ({curso.documentos.length})</button>
        <button type="button" style={btn} onClick={() => setVerAjustes(true)}>⚙ Ajustes</button>
        <button type="button" style={btnPrimario} disabled={ocupado} onClick={() => lanzar(`/api/cursos/${id}/render`)}
          title="Renderiza las lecciones que falten y las une en un solo vídeo con capítulos">
          🎬 Renderizar curso
        </button>
        <button type="button" style={btn} onClick={async () => { await guardarYa(); setVerSubir(true); }}
          title="Elige qué lecciones subir (o todas) y si van públicas, ocultas o privadas">
          ⬆ Subir a YouTube
        </button>
      </div>

      {curso.render?.archivo && (
        <div style={{ ...panel, padding: "8px 12px", marginBottom: 12, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 12 }}>
          <span>🎬 Curso completo: {fmtDur(curso.render.duracion)}</span>
          <a href={urlArchivo(id, curso.render.archivo)} download style={{ color: "var(--accent)" }}>↓ MP4</a>
          <a href={urlArchivo(id, curso.render.capitulos)} target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>Capítulos para YouTube</a>
        </div>
      )}

      {fallidas.map((t) => (
        <div key={t.id} style={{ ...panel, padding: "8px 12px", marginBottom: 8, fontSize: 12, color: "#f87171", border: "1px solid #5a2020" }}>
          ⚠ <b>{t.etiqueta}</b> falló: {t.error}
        </div>
      ))}

      {tareas.length > 0 && (
        <div style={{ ...panel, padding: "8px 12px", marginBottom: 12, display: "flex", flexDirection: "column", gap: 4 }}>
          {tareas.map((t) => (
            <div key={t.id} style={{ fontSize: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <span className={t.estado === "en_curso" ? "animate-spin" : ""} style={{ display: "inline-block" }}>⟳</span>
              <b>{t.etiqueta}</b>
              <span style={{ color: "var(--muted)" }}>{t.estado === "en_cola" ? "en cola" : t.log[t.log.length - 1] || "empezando…"}</span>
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-4 items-start xl:grid-cols-[300px_minmax(0,1fr)_340px]">
        {/* Izquierda */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
          {(verDocs || !curso.modulos.length) && (
            <PanelDocumentos curso={curso} ocupado={ocupado} onCambio={cargar} onTarea={tareaLanzada} />
          )}
          <ArbolCurso
            modulos={curso.modulos}
            leccionActiva={leccionId}
            onSeleccionar={(lid) => { setLeccionId(lid); setEscenaId(null); }}
            onModulos={cambiarModulos}
            onGenerar={(lid) => lanzar(`/api/cursos/${id}/lecciones/${lid}/generar`)}
            onGenerarPendientes={() => lanzar(`/api/cursos/${id}/generar-pendientes`)}
            ocupado={ocupado}
          />
        </div>

        {/* Centro */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
          {!leccion ? (
            <div style={{ ...panel, padding: 30, textAlign: "center", color: "var(--muted)" }}>
              Sube la documentación y pide el temario para empezar.
            </div>
          ) : !escenas.length ? (
            <div style={{ ...panel, padding: 30, textAlign: "center", display: "flex", flexDirection: "column", gap: 12, alignItems: "center" }}>
              <p style={{ margin: 0, fontWeight: 700 }}>{leccion.titulo}</p>
              {leccion.objetivos.length > 0 && (
                <ul style={{ margin: 0, color: "var(--muted)", fontSize: 13, textAlign: "left" }}>
                  {leccion.objetivos.map((o, i) => <li key={i}>{o}</li>)}
                </ul>
              )}
              {tareaLeccion ? <p style={{ color: "#60a5fa", margin: 0 }}>⟳ {tareaLeccion.estado === "en_cola" ? "En cola…" : "Generando la lección con la IA…"}</p> : (
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
                  <button type="button" style={btnPrimario} onClick={() => lanzar(`/api/cursos/${id}/lecciones/${leccion.id}/generar`)}>
                    ✨ Generar lección con IA
                  </button>
                  <button type="button" style={btn} onClick={() => { const e = { ...escenaVacia("portada"), contenido: { titulo: leccion.titulo } }; cambiarEscenas([e]); setEscenaId(e.id); }}>
                    Empezar en blanco
                  </button>
                </div>
              )}
            </div>
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <p style={{ ...etiqueta, flex: 1 }}>{leccion.titulo} · {fmtDur(durLeccion)}</p>
                {preview ? (
                  <>
                    {preview.preparando && <span style={{ fontSize: 12, color: "var(--muted)" }}>{preview.preparando}</span>}
                    <button type="button" style={btn} onClick={detener}>⏹ Detener</button>
                  </>
                ) : (
                  <button type="button" style={btn} onClick={reproducir}>▶ Vista previa</button>
                )}
                <button type="button" style={btnPrimario} disabled={ocupado} onClick={() => lanzar(`/api/cursos/${id}/lecciones/${leccion.id}/render`)}>
                  🎬 Renderizar lección
                </button>
              </div>
              {escenaVista && (
                escenaVista.tipo === "video" && escenaVista.video ? (
                  <video
                    key={escenaVista.id + (enPreview ? "-p" : "")}
                    ref={videoRef}
                    src={`${urlArchivo(id, escenaVista.video.archivo)}#t=${escenaVista.video.inicio},${escenaVista.video.fin}`}
                    controls={!enPreview} autoPlay={!!enPreview} muted={!!(enPreview && escenaVista.audio)}
                    style={{ width: "100%", aspectRatio: "16 / 9", background: "#000", borderRadius: 10 }} />
                ) : (
                  <Lienzo>
                    <SlideRender escena={escenaVista} tema={curso.tema} cursoId={id} cursoTitulo={curso.titulo} numero={numero}
                      editar={enPreview ? undefined : (c) => cambiarEscena({ ...escenaVista, contenido: c })} />
                  </Lienzo>
                )
              )}
              {!enPreview && <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>Haz clic en cualquier texto de la diapositiva para editarlo.</p>}
              {leccion.render?.archivo && (
                <div style={{ ...panel, padding: 10, display: "flex", flexDirection: "column", gap: 6 }}>
                  <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 12 }}>
                    <b>🎬 Vídeo de la lección ({fmtDur(leccion.render.duracion)})</b>
                    <a href={urlArchivo(id, leccion.render.archivo)} download style={{ color: "var(--accent)" }}>↓ MP4</a>
                    <a href={urlArchivo(id, leccion.render.srt)} download style={{ color: "var(--accent)" }}>↓ Subtítulos .srt</a>
                  </div>
                  <video src={urlArchivo(id, leccion.render.archivo) + `?v=${leccion.render.fecha}`} controls
                    style={{ width: "100%", maxHeight: "calc(40vh / var(--zoom, 1))", background: "#000", borderRadius: 8 }} />
                </div>
              )}
            </>
          )}
        </div>

        {/* Derecha */}
        <div style={{ minWidth: 0 }}>
          {escena && !enPreview && (
            <SceneInspector key={escena.id} cursoId={id} escena={escena} onCambio={cambiarEscena}
              onNarrar={async (e, rep) => { await narrar(e, rep); }} />
          )}
        </div>
      </div>

      {leccion && escenas.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <Timeline
            escenas={escenas}
            seleccion={escena?.id ?? null}
            tiempoActual={preview && !preview.preparando ? preview.t : null}
            onSeleccionar={setEscenaId}
            onEscenas={cambiarEscenas}
            onNuevaDiapositiva={(pos) => { const e = escenaVacia(); const n = [...escenas]; n.splice(pos + 1, 0, e); cambiarEscenas(n); setEscenaId(e.id); }}
            onNuevoVideo={nuevoVideo}
            onDuplicar={(eid) => {
              const i = escenas.findIndex((x) => x.id === eid);
              const copia = { ...structuredClone(escenas[i]), id: nuevoId(), audio: null };
              const n = [...escenas]; n.splice(i + 1, 0, copia); cambiarEscenas(n); setEscenaId(copia.id);
            }}
            onBorrar={(eid) => {
              const i = escenas.findIndex((x) => x.id === eid);
              cambiarEscenas(escenas.filter((x) => x.id !== eid));
              setEscenaId(escenas[i + 1]?.id ?? escenas[i - 1]?.id ?? null);
            }}
          />
        </div>
      )}

      {verSubir && <SubirYoutube cursoId={id} onCerrar={() => setVerSubir(false)} onTarea={revisarTareas} />}

      {verAjustes && (
        <AjustesCurso curso={curso} onCerrar={() => setVerAjustes(false)} onGuardado={(c) => { cursoRef.current = { ...c, modulos: cursoRef.current!.modulos }; setCurso(cursoRef.current); setVerAjustes(false); }} />
      )}
    </main>
  );
}
