"use client";

// Fuentes y verificación:
//  - Noticias analizadas: viralidad (IA), fiabilidad (0-100, con sus razones),
//    medios que la publican, cómo se expande y si se publicaría sola.
//  - Fuentes: las ~150 integradas + las añadidas, con su nivel; añadir, probar,
//    cambiar nivel, desactivar.
//  - Reglas automáticas: lo que debe cumplir una noticia para generarse y
//    publicarse sola.

import { useCallback, useEffect, useMemo, useState } from "react";

interface Punto { t: string; n: number }
interface Noticia {
  titulo: string;
  titulo_original?: string;
  link?: string;
  fuente?: string;
  org_fuente?: string;
  nivel_fuente?: number;
  score?: number;
  viralidad_estimada?: boolean;
  gancho?: string;
  categoria?: string;
  fiabilidad?: number;
  fiabilidad_label?: string;
  fiabilidad_color?: string;
  fiabilidad_razones?: string[];
  n_medios?: number;
  medios?: string[];
  expansion?: Punto[];
  tendencia?: string;
  apta_auto?: boolean;
  motivos_no_apta?: string[];
  recencia?: { label?: string };
}
interface Analisis {
  fecha: string | null;
  tema?: string | null;
  noticias: Noticia[];
  analizando: boolean;
  error: string | null;
}
interface Fuente {
  nombre: string; url: string; dominio: string; categoria: string;
  nivel: number; nivel_base: number; activa: boolean; tipo: "integrada" | "añadida";
}
interface Evaluacion {
  feed: string; dominio: string; puntuacion: number; nivel_sugerido: number; nivel_actual: number | null;
  medias_por_nivel: Record<string, number>; razones: string[]; calibrado: boolean;
  corroboracion: number; corroboracion_fuerte: number; sensacionalismo: number; por_dia: number | null;
  muestra: { titular: string; confirman: string[]; nivel_1_2: boolean }[];
  parecidas?: { nombre: string; nivel: number; puntuacion: number }[];
}
interface Reglas {
  score_min: number; fiabilidad_min: number; min_medios: number; excluir_nivel4: boolean;
  auto_generate: boolean; auto_publish: boolean; enabled: boolean; interval_min: number;
  [k: string]: unknown;
}

const NIVEL_COLOR: Record<number, string> = { 1: "#22c55e", 2: "#60a5fa", 3: "#fbbf24", 4: "#f87171" };
const NIVEL_TXT: Record<number, string> = { 1: "Agencia / ciencia", 2: "Prensa de referencia", 3: "Especialista", 4: "Alerta / PR" };
const TENDENCIA: Record<string, string> = { creciendo: "📈 Creciendo", estable: "➖ Estable", bajando: "📉 Bajando", nueva: "🆕 Nueva" };

const card: React.CSSProperties = { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, padding: 18 };
const btn: React.CSSProperties = { background: "var(--accent)", color: "#fff", border: 0, borderRadius: 10, padding: "9px 16px", fontWeight: 600, cursor: "pointer" };
const btnGhost: React.CSSProperties = { background: "var(--surface2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 10, padding: "8px 14px", cursor: "pointer" };
const input: React.CSSProperties = { background: "var(--surface2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 10, padding: "9px 12px" };

function Barra({ valor, max, color, texto }: { valor: number; max: number; color: string; texto: string }) {
  return (
    <div style={{ minWidth: 150 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
        <span style={{ color: "var(--muted)" }}>{texto}</span>
        <b style={{ color }}>{max === 10 ? valor.toFixed(1) : Math.round(valor)}{max === 10 ? "/10" : "/100"}</b>
      </div>
      <div style={{ height: 8, background: "var(--surface2)", borderRadius: 4, overflow: "hidden" }}>
        <div style={{ width: `${Math.max(2, Math.min(100, (valor / max) * 100))}%`, height: "100%", background: color }} />
      </div>
    </div>
  );
}

function Expansion({ puntos }: { puntos: Punto[] }) {
  if (!puntos || puntos.length < 2) return null;
  const W = 120, H = 32, max = Math.max(...puntos.map((p) => p.n), 1);
  const xy = puntos.map((p, i) => `${(i / (puntos.length - 1)) * W},${H - (p.n / max) * (H - 4) - 2}`).join(" ");
  return (
    <svg width={W} height={H} style={{ display: "block" }} aria-label="Medios que la publican a lo largo del tiempo">
      <polyline points={xy} fill="none" stroke="var(--accent)" strokeWidth="2" />
    </svg>
  );
}

function InformeCredibilidad({ ev, onUsar }: { ev: Evaluacion; onUsar: (nivel: number) => void }) {
  const medias = ev.medias_por_nivel || {};
  return (
    <div style={{ marginTop: 14, padding: 14, borderRadius: 12, background: "var(--surface2)" }}>
      <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 40, fontWeight: 800, color: NIVEL_COLOR[ev.nivel_sugerido] }}>{ev.puntuacion}</div>
          <div style={{ fontSize: 12, color: "var(--muted)" }}>credibilidad / 100</div>
        </div>
        <div>
          <div style={{ fontSize: 13, color: "var(--muted)" }}>Nivel sugerido</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: NIVEL_COLOR[ev.nivel_sugerido] }}>
            Nivel {ev.nivel_sugerido} · {NIVEL_TXT[ev.nivel_sugerido]}
          </div>
          {ev.nivel_actual && <div style={{ fontSize: 12, color: "var(--muted)" }}>Ya la tienes como nivel {ev.nivel_actual}</div>}
          <button style={{ ...btn, marginTop: 8, padding: "6px 12px" }} onClick={() => onUsar(ev.nivel_sugerido)}>
            Usar nivel sugerido
          </button>
        </div>
        <div style={{ flex: 1, minWidth: 260 }}>
          {ev.parecidas && ev.parecidas.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 4 }}>Puntúa parecido a estas fuentes tuyas:</div>
              {ev.parecidas.map((p) => (
                <div key={p.nombre} style={{ fontSize: 13 }}>
                  <b>{p.nombre}</b> <span style={{ color: NIVEL_COLOR[p.nivel] }}>· nivel {p.nivel}</span>
                  <span style={{ color: "var(--muted)" }}> · {p.puntuacion}/100</span>
                </div>
              ))}
            </div>
          )}
          <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 6 }}>
            {ev.calibrado ? "Media de tus fuentes por nivel" : "Media de tus fuentes por nivel (no ordenada: el nivel sugerido usa umbrales fijos)"}
          </div>
          {[1, 2, 3, 4].map((l) => medias[String(l)] != null && (
            <div key={l} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5, fontSize: 12 }}>
              <span style={{ width: 70, color: NIVEL_COLOR[l] }}>Nivel {l}</span>
              <div style={{ flex: 1, position: "relative", height: 10, background: "var(--bg)", borderRadius: 5 }}>
                <div style={{ width: `${medias[String(l)]}%`, height: "100%", background: NIVEL_COLOR[l], opacity: 0.5, borderRadius: 5 }} />
                <div title="Esta fuente" style={{ position: "absolute", left: `calc(${ev.puntuacion}% - 1px)`, top: -3, width: 3, height: 16, background: "var(--text)" }} />
              </div>
              <span style={{ width: 28, textAlign: "right" }}>{medias[String(l)]}</span>
            </div>
          ))}
          <div style={{ fontSize: 11, color: "var(--muted)" }}>La raya blanca es esta fuente.</div>
        </div>
      </div>
      <ul style={{ margin: "12px 0 8px 18px", listStyle: "disc", fontSize: 13, lineHeight: 1.6 }}>
        {ev.razones.map((r, j) => <li key={j}>{r}</li>)}
      </ul>
      <div style={{ fontSize: 13 }}>
        <b>Sus titulares y quién los confirma:</b>
        {ev.muestra.map((m, j) => (
          <div key={j} style={{ padding: "4px 0", borderTop: j ? "1px solid var(--border)" : "none" }}>
            <span style={{ color: m.confirman.length ? (m.nivel_1_2 ? "#22c55e" : "#fbbf24") : "#f87171" }}>
              {m.confirman.length ? "✓" : "✗"}
            </span>{" "}{m.titular}
            <span style={{ color: "var(--muted)" }}> — {m.confirman.length ? m.confirman.join(", ") : "nadie más lo publica"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function colorViral(s: number) { return s >= 8.5 ? "#f472b6" : s >= 7.5 ? "#a78bfa" : s >= 6 ? "#fbbf24" : "#94a3b8"; }

export default function FuentesPage() {
  const [tab, setTab] = useState<"noticias" | "fuentes" | "reglas">("noticias");
  const [analisis, setAnalisis] = useState<Analisis | null>(null);
  const [tema, setTema] = useState("");
  const [abiertas, setAbiertas] = useState<Record<number, boolean>>({});
  const [enviadas, setEnviadas] = useState<Record<number, string>>({});
  const [fuentes, setFuentes] = useState<Fuente[]>([]);
  const [categorias, setCategorias] = useState<string[]>([]);
  const [filtro, setFiltro] = useState({ texto: "", nivel: 0, categoria: "" });
  const [nueva, setNueva] = useState({ nombre: "", url: "", nivel: 3, categoria: "general" });
  const [prueba, setPrueba] = useState<{ feed?: string; muestra?: string[]; error?: string; cargando?: boolean } | null>(null);
  const [reglas, setReglas] = useState<Reglas | null>(null);
  const [evaluacion, setEvaluacion] = useState<Evaluacion | { error: string } | "cargando" | null>(null);
  const [calib, setCalib] = useState<{ fecha?: string; calibrando?: boolean; niveles?: Record<string, { media: number | null }> } | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const cargarAnalisis = useCallback(() => fetch("/api/fuentes/analisis").then((r) => r.json()).then(setAnalisis).catch(() => {}), []);
  const cargarFuentes = useCallback(() => fetch("/api/fuentes").then((r) => r.json()).then((d) => { setFuentes(d.fuentes); setCategorias(d.categorias); }).catch(() => {}), []);
  const cargarCalib = useCallback(() => fetch("/api/fuentes/calibracion").then((r) => r.json()).then(setCalib).catch(() => {}), []);
  const cargarReglas = useCallback(() => fetch("/api/scanner/status").then((r) => r.json()).then((d) => setReglas(d.config)).catch(() => {}), []);

  useEffect(() => { cargarAnalisis(); cargarFuentes(); cargarReglas(); cargarCalib(); }, [cargarAnalisis, cargarFuentes, cargarReglas, cargarCalib]);
  useEffect(() => {
    if (!calib?.calibrando) return;
    const t = setInterval(cargarCalib, 10000);
    return () => clearInterval(t);
  }, [calib?.calibrando, cargarCalib]);

  async function evaluar() {
    setEvaluacion("cargando");
    const r = await fetch("/api/fuentes/evaluar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: nueva.url }) });
    const d = await r.json();
    setEvaluacion(r.ok ? d : { error: d.detail || "No se pudo evaluar" });
  }

  async function recalibrar() {
    await fetch("/api/fuentes/calibrar", { method: "POST" });
    cargarCalib();
  }
  useEffect(() => {
    if (!analisis?.analizando) return;
    const t = setInterval(cargarAnalisis, 5000);
    return () => clearInterval(t);
  }, [analisis?.analizando, cargarAnalisis]);

  async function analizar() {
    await fetch("/api/fuentes/analizar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tema: tema || null }) });
    cargarAnalisis();
  }

  async function alGestor(n: Noticia, i: number) {
    setEnviadas((e) => ({ ...e, [i]: "enviando" }));
    try {
      const r = await fetch("/api/gestor/items", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tipo: "noticia", contenido: JSON.stringify(n), titulo: n.titulo, score_noticia: n.score ?? null }),
      });
      if (!r.ok) throw new Error(await r.text());
      setEnviadas((e) => ({ ...e, [i]: "ok" }));
    } catch {
      setEnviadas((e) => ({ ...e, [i]: "error" }));
    }
  }

  const noticias = useMemo(() => {
    const ns = [...(analisis?.noticias || [])];
    return ns.sort((a, b) => Number(!!b.apta_auto) - Number(!!a.apta_auto) || (b.score || 0) - (a.score || 0));
  }, [analisis]);

  const fuentesFiltradas = useMemo(() => fuentes.filter((f) =>
    (!filtro.nivel || f.nivel === filtro.nivel) &&
    (!filtro.categoria || f.categoria === filtro.categoria) &&
    (!filtro.texto || `${f.nombre} ${f.dominio}`.toLowerCase().includes(filtro.texto.toLowerCase()))), [fuentes, filtro]);

  async function probar() {
    setPrueba({ cargando: true });
    const r = await fetch("/api/fuentes/probar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: nueva.url }) });
    const d = await r.json();
    setPrueba(r.ok ? d : { error: d.detail || "No se pudo leer" });
  }

  async function agregar() {
    const r = await fetch("/api/fuentes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(nueva) });
    const d = await r.json();
    if (!r.ok) { setAviso(`⚠ ${d.detail}`); return; }
    setAviso(`✓ Fuente «${d.nombre}» añadida con nivel ${d.nivel}`);
    setNueva({ nombre: "", url: "", nivel: 3, categoria: "general" });
    setPrueba(null);
    cargarFuentes();
  }

  async function ajustar(f: Fuente, cambios: { nivel?: number; activa?: boolean }) {
    await fetch(`/api/fuentes/${encodeURIComponent(f.nombre)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cambios) });
    cargarFuentes();
  }

  async function borrar(f: Fuente) {
    if (!confirm(`¿Borrar la fuente «${f.nombre}»?`)) return;
    await fetch(`/api/fuentes/${encodeURIComponent(f.nombre)}`, { method: "DELETE" });
    cargarFuentes();
  }

  async function guardarReglas(r: Reglas) {
    const res = await fetch("/api/scanner/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(r) });
    if (res.ok) { setReglas(await res.json()); setAviso("✓ Reglas guardadas"); } else setAviso("⚠ No se pudieron guardar las reglas");
  }

  const aptas = noticias.filter((n) => n.apta_auto).length;

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "28px 16px 64px" }}>
      <h1 style={{ fontSize: 26, fontWeight: 700, margin: 0 }}>Fuentes y verificación</h1>
      <p style={{ color: "var(--muted)", margin: "6px 0 18px" }}>
        Viralidad y fiabilidad de cada noticia, las fuentes que la confirman y cómo se expande. Solo lo más viral y mejor verificado se genera y publica solo.
      </p>

      {aviso && (
        <div style={{ ...card, padding: 10, marginBottom: 14, display: "flex", justifyContent: "space-between" }}>
          <span>{aviso}</span>
          <button onClick={() => setAviso(null)} style={{ background: "none", border: 0, color: "var(--muted)", cursor: "pointer" }}>✕</button>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
        {([["noticias", "📰 Noticias analizadas"], ["fuentes", `🏛 Fuentes (${fuentes.length})`], ["reglas", "🤖 Reglas automáticas"]] as const).map(([k, t]) => (
          <button key={k} onClick={() => setTab(k)}
            style={{ ...btnGhost, borderColor: tab === k ? "var(--accent)" : "var(--border)", color: tab === k ? "var(--text)" : "var(--muted)", fontWeight: tab === k ? 700 : 400 }}>
            {t}
          </button>
        ))}
      </div>

      {tab === "noticias" && (
        <>
          <div style={{ ...card, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 14 }}>
            <input value={tema} onChange={(e) => setTema(e.target.value)} placeholder="Tema (vacío = variadas)" style={{ ...input, flex: 1, minWidth: 200 }} />
            <button style={{ ...btn, opacity: analisis?.analizando ? 0.6 : 1 }} disabled={analisis?.analizando} onClick={analizar}>
              {analisis?.analizando ? "⏳ Analizando…" : "🔍 Analizar ahora"}
            </button>
            <span style={{ fontSize: 13, color: "var(--muted)" }}>
              {analisis?.fecha ? `Último análisis: ${new Date(analisis.fecha).toLocaleString("es-ES")}` : "Sin análisis todavía"}
              {analisis?.fecha && ` · ${noticias.length} noticias · ${aptas} se publicarían solas`}
            </span>
          </div>
          {analisis?.error && <p style={{ color: "var(--error)" }}>Error: {analisis.error}</p>}

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {noticias.map((n, i) => (
              <div key={i} style={{ ...card, borderColor: n.apta_auto ? "#22c55e" : "var(--border)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
                  <div style={{ flex: 1, minWidth: 280 }}>
                    <div style={{ fontWeight: 700, fontSize: 16 }}>{n.titulo}</div>
                    {n.titulo_original && n.titulo_original !== n.titulo && (
                      <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 2 }}>{n.titulo_original}</div>
                    )}
                    <div style={{ fontSize: 13, marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                      <span style={{ padding: "2px 8px", borderRadius: 6, background: "var(--surface2)", color: NIVEL_COLOR[n.nivel_fuente || 3] }}>
                        {n.org_fuente || n.fuente} · nivel {n.nivel_fuente} ({NIVEL_TXT[n.nivel_fuente || 3]})
                      </span>
                      {n.recencia?.label && <span style={{ color: "var(--muted)" }}>{n.recencia.label}</span>}
                      {n.link && <a href={n.link} target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>ver noticia ↗</a>}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 20, alignItems: "center", flexWrap: "wrap" }}>
                    <Barra valor={n.score || 0} max={10} color={colorViral(n.score || 0)} texto={n.viralidad_estimada ? "Viralidad (estimada)" : "Viralidad"} />
                    <Barra valor={n.fiabilidad || 0} max={100} color={n.fiabilidad_color || "#94a3b8"} texto={`Fiabilidad · ${n.fiabilidad_label || "?"}`} />
                    <div style={{ minWidth: 130 }}>
                      <div style={{ fontSize: 12, color: "var(--muted)" }}>{n.n_medios || 1} medio{(n.n_medios || 1) > 1 ? "s" : ""} · {TENDENCIA[n.tendencia || "nueva"]}</div>
                      <Expansion puntos={n.expansion || []} />
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
                  <div style={{ fontSize: 13 }}>
                    {n.apta_auto
                      ? <span style={{ color: "#22c55e", fontWeight: 700 }}>✅ Cumple las reglas: se generaría y publicaría sola</span>
                      : <span style={{ color: "var(--muted)" }}>✋ No se publicaría sola: {(n.motivos_no_apta || []).join(" · ")}</span>}
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button style={btnGhost} onClick={() => setAbiertas((a) => ({ ...a, [i]: !a[i] }))}>
                      {abiertas[i] ? "Ocultar detalle" : "¿Por qué?"}
                    </button>
                    <button style={btnGhost} disabled={enviadas[i] === "enviando" || enviadas[i] === "ok"} onClick={() => alGestor(n, i)}>
                      {enviadas[i] === "ok" ? "✓ En el Gestor" : enviadas[i] === "error" ? "⚠ Reintentar" : "➕ Al Gestor"}
                    </button>
                  </div>
                </div>

                {abiertas[i] && (
                  <div style={{ marginTop: 12, padding: 12, borderRadius: 10, background: "var(--surface2)", fontSize: 13, lineHeight: 1.6 }}>
                    <b>Fiabilidad {n.fiabilidad}/100:</b>
                    <ul style={{ margin: "4px 0 8px 18px", listStyle: "disc" }}>
                      {(n.fiabilidad_razones || []).map((r, j) => <li key={j}>{r}</li>)}
                    </ul>
                    {n.medios && n.medios.length > 0 && <div><b>Medios que la publican:</b> {n.medios.join(", ")}</div>}
                    {n.gancho && <div><b>Por qué es viral:</b> {n.gancho}</div>}
                  </div>
                )}
              </div>
            ))}
            {analisis?.fecha && noticias.length === 0 && <p style={{ color: "var(--muted)" }}>El análisis no encontró noticias.</p>}
          </div>
        </>
      )}

      {tab === "fuentes" && (
        <>
          <div style={{ ...card, marginBottom: 14 }}>
            <h2 style={{ fontSize: 16, margin: "0 0 12px" }}>Añadir una fuente</h2>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr 1fr 1fr", gap: 10 }}>
              <input style={input} placeholder="Nombre (p. ej. Xataka)" value={nueva.nombre} onChange={(e) => setNueva({ ...nueva, nombre: e.target.value })} />
              <input style={input} placeholder="Web o RSS del medio (https://…)" value={nueva.url} onChange={(e) => { setNueva({ ...nueva, url: e.target.value }); setPrueba(null); }} />
              <select style={input} value={nueva.nivel} onChange={(e) => setNueva({ ...nueva, nivel: Number(e.target.value) })}>
                {[1, 2, 3, 4].map((l) => <option key={l} value={l}>Nivel {l} · {NIVEL_TXT[l]}</option>)}
              </select>
              <select style={input} value={nueva.categoria} onChange={(e) => setNueva({ ...nueva, categoria: e.target.value })}>
                {categorias.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div style={{ display: "flex", gap: 10, marginTop: 10, alignItems: "center" }}>
              <button style={btnGhost} disabled={!nueva.url || prueba?.cargando} onClick={probar}>{prueba?.cargando ? "Probando…" : "🔎 Probar"}</button>
              <button style={btnGhost} disabled={!nueva.url || evaluacion === "cargando"} onClick={evaluar}>
                {evaluacion === "cargando" ? "⏳ Evaluando (~30 s)…" : "🧪 Evaluar credibilidad"}
              </button>
              <button style={{ ...btn, opacity: nueva.nombre && nueva.url ? 1 : 0.5 }} disabled={!nueva.nombre || !nueva.url} onClick={agregar}>➕ Añadir</button>
              <span style={{ fontSize: 12, color: "var(--muted)" }}>Si la web no tiene RSS, se usa Google News filtrado por su dominio.</span>
            </div>
            {prueba?.error && <p style={{ color: "var(--error)", marginBottom: 0 }}>{prueba.error}</p>}
            {evaluacion && evaluacion !== "cargando" && "error" in evaluacion && (
              <p style={{ color: "var(--error)", marginBottom: 0 }}>{evaluacion.error}</p>
            )}
            {evaluacion && evaluacion !== "cargando" && !("error" in evaluacion) && (
              <InformeCredibilidad ev={evaluacion} onUsar={(nv) => setNueva({ ...nueva, nivel: nv })} />
            )}
            {prueba?.muestra && (
              <div style={{ marginTop: 10, fontSize: 13 }}>
                <div style={{ color: "var(--muted)" }}>Feed: {prueba.feed}</div>
                <ul style={{ margin: "4px 0 0 18px", listStyle: "disc" }}>{prueba.muestra.map((m, j) => <li key={j}>{m}</li>)}</ul>
              </div>
            )}
          </div>

          <div style={{ ...card, padding: 12, marginBottom: 14, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", fontSize: 13 }}>
            <span style={{ color: "var(--muted)" }}>
              Referencia de niveles: {calib?.calibrando ? "⏳ midiendo tus fuentes…" : calib?.fecha
                ? `medida el ${new Date(calib.fecha).toLocaleString("es-ES")} — ` + [1, 2, 3, 4].map((l) => `nivel ${l}: ${calib.niveles?.[String(l)]?.media ?? "—"}`).join(" · ")
                : "sin medir todavía"}
            </span>
            <button style={{ ...btnGhost, padding: "6px 12px" }} disabled={calib?.calibrando} onClick={recalibrar}>↻ Recalibrar</button>
          </div>

          <div style={{ display: "flex", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
            <input style={{ ...input, flex: 1, minWidth: 200 }} placeholder="Buscar fuente…" value={filtro.texto} onChange={(e) => setFiltro({ ...filtro, texto: e.target.value })} />
            <select style={input} value={filtro.nivel} onChange={(e) => setFiltro({ ...filtro, nivel: Number(e.target.value) })}>
              <option value={0}>Todos los niveles</option>
              {[1, 2, 3, 4].map((l) => <option key={l} value={l}>Nivel {l} · {NIVEL_TXT[l]}</option>)}
            </select>
            <select style={input} value={filtro.categoria} onChange={(e) => setFiltro({ ...filtro, categoria: e.target.value })}>
              <option value="">Todas las categorías</option>
              {categorias.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          <div style={{ ...card, padding: 0, overflow: "hidden" }}>
            {fuentesFiltradas.map((f) => (
              <div key={f.nombre} style={{ display: "grid", gridTemplateColumns: "2fr 1.4fr 1fr 1.6fr auto", gap: 10, alignItems: "center", padding: "10px 16px", borderBottom: "1px solid var(--border)", opacity: f.activa ? 1 : 0.45 }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{f.nombre} {f.tipo === "añadida" && <span style={{ fontSize: 11, color: "var(--accent)" }}>· añadida</span>}</div>
                  <div style={{ fontSize: 12, color: "var(--muted)" }}>{f.dominio}</div>
                </div>
                <span style={{ fontSize: 13, color: "var(--muted)" }}>{f.categoria}</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: NIVEL_COLOR[f.nivel] }}>● Nivel {f.nivel}{f.nivel !== f.nivel_base && <span style={{ color: "var(--muted)", fontWeight: 400 }}> (era {f.nivel_base})</span>}</span>
                <select style={{ ...input, padding: "6px 8px" }} value={f.nivel} onChange={(e) => ajustar(f, { nivel: Number(e.target.value) })}>
                  {[1, 2, 3, 4].map((l) => <option key={l} value={l}>{l} · {NIVEL_TXT[l]}</option>)}
                </select>
                <div style={{ display: "flex", gap: 6 }}>
                  <button style={{ ...btnGhost, padding: "6px 10px" }} onClick={() => ajustar(f, { activa: !f.activa })}>{f.activa ? "Desactivar" : "Activar"}</button>
                  {f.tipo === "añadida" && <button style={{ ...btnGhost, padding: "6px 10px", color: "#f87171" }} onClick={() => borrar(f)}>🗑</button>}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === "reglas" && reglas && (
        <div style={{ ...card, maxWidth: 720 }}>
          <h2 style={{ fontSize: 16, margin: "0 0 4px" }}>Qué debe cumplir una noticia para generarse y publicarse sola</h2>
          <p style={{ fontSize: 13, color: "var(--muted)", marginTop: 0 }}>Tienen que cumplirse TODAS. Las demás siguen apareciendo aquí y en los avisos para hacerlas a mano.</p>
          {([
            ["score_min", "Viralidad mínima (0-10, calculada por la IA)", 0.5, 10],
            ["fiabilidad_min", "Fiabilidad mínima (0-100)", 5, 100],
            ["min_medios", "Medios independientes mínimos", 1, 10],
          ] as const).map(([k, t, paso, max]) => (
            <label key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
              <span>{t}</span>
              <input type="number" step={paso} min={0} max={max} value={Number(reglas[k])} style={{ ...input, width: 100 }}
                onChange={(e) => setReglas({ ...reglas, [k]: Number(e.target.value) })} />
            </label>
          ))}
          {([
            ["excluir_nivel4", "Nunca si el origen es de nivel 4 (alerta / PR)"],
            ["auto_generate", "Generar solas las noticias que cumplan (escáner)"],
            ["auto_publish", "Publicarlas solas al terminar"],
            ["enabled", "Escáner activado"],
          ] as const).map(([k, t]) => (
            <label key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--border)", cursor: "pointer" }}>
              <span>{t}</span>
              <input type="checkbox" checked={Boolean(reglas[k])} style={{ width: 20, height: 20 }}
                onChange={(e) => setReglas({ ...reglas, [k]: e.target.checked })} />
            </label>
          ))}
          <div style={{ display: "flex", gap: 10, marginTop: 14, alignItems: "center" }}>
            <button style={btn} onClick={() => guardarReglas(reglas)}>Guardar reglas</button>
            <span style={{ fontSize: 13, color: "var(--muted)" }}>
              Las más virales (≥ {process.env.NEXT_PUBLIC_VIDEO_IA_UMBRAL || "7.5"}) salen además con vídeo IA y portada IA.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
