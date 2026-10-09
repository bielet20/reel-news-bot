"use client";

// Barra de progreso de producción de un reel.
// Estilo copiado de la barra de progreso de Estudio IA (E:\AI-Studio\tools\EstudioIA,
// static/index.html: .progress-bar / .progress-fill / .progress-label):
//   pista 8 px, esquinas 4 px, fondo #262230 con borde #332e3d, relleno ámbar
//   #c98a2c con transición de 0.4 s, y etiqueta monoespaciada "Fase · 42%".
//
// Solo frontend: el % y la fase se deducen del log que ya devuelve
// GET /api/jobs/{id} (campo "logs", leído del _job_<id>.log mientras corre).

import { useEffect, useRef, useState } from "react";

export const ESTILO_BARRA = {
  pista: "#262230",
  borde: "#332e3d",
  relleno: "#c98a2c",
  rellenoOk: "#1e7e34",
  rellenoError: "#d8695f",
  etiqueta: "#a79fb0",
  mono: 'ui-monospace, "Cascadia Code", Consolas, monospace',
};

export interface Progreso {
  pct: number;          // 0-100
  fase: string;         // texto en español para la etiqueta
  clave: string;        // id estable de la fase (para medir cuánto lleva en ella)
  titulo: string | null;
  esperandoGpu: boolean;
  // Fases sin sub-pasos en el log (montaje): el % avanza solo con el tiempo
  // desde que se detecta la fase, hasta `techo`, sin llegar nunca a él.
  avanceTiempo?: { techo: number; tau: number };
}

// ── Pesos (todo el recorrido = 100 %) ─────────────────────────────────────────
// Con vídeo IA (Flux + Wan en ComfyUI, la ruta habitual):
//   0-10   guion + voz + imágenes del artículo
//   10-11  plan de escenas
//   11-35  imágenes Flux        11 + 24 * N/total
//   35-85  clips de vídeo       35 + 50 * N/total
//   86-95  montaje vertical     (avanza con el tiempo, tau 120 s)
//   96-100 portada/miniatura, atribución y "Listo"
// Sin vídeo IA (reel con imágenes fijas, ~2-3 min en total):
//   0-12 igual que arriba, montaje 12-90 (tau 60 s), 90-100 finalizar.
export function calcularProgreso(logs: string | null | undefined, status?: string): Progreso {
  const p: Progreso = { pct: 1, fase: "Preparando", clave: "inicio", titulo: null, esperandoGpu: false };
  if (status === "pending") { p.fase = "En espera"; p.pct = 0; }
  let videoIA = false;
  const lineas = (logs || "").split(/\r?\n/);
  for (const raw of lineas) {
    const l = raw.trim();
    if (!l) continue;
    let m: RegExpMatchArray | null;
    if ((m = l.match(/^=== Procesando: (.+?) ===$/))) {
      p.titulo = m[1]; set(p, 2, "Leyendo la noticia", "leer");
    } else if (/^-> (Descargando y leyendo|Obteniendo metadatos|Descargando transcripci)/.test(l)) {
      set(p, 2, "Leyendo la fuente", "leer");
    } else if (/^-> Generando guion/.test(l)) {
      set(p, 4, "Guion y voz", "guion");
    } else if (/^-> Generando audio narrado/.test(l)) {
      set(p, 7, "Guion y voz", "voz");
    } else if (/^-> (Extrayendo im|Buscando \d+ imagen|Generando imagen IA)/.test(l)) {
      set(p, 9, "Buscando imágenes", "imgart");
    } else if (/^-> Generando fondos de v/.test(l)) {
      videoIA = true; set(p, 10, "Preparando escenas", "escenas");
    } else if ((m = l.match(/^\[video-ia\] (\d+) escenas/))) {
      set(p, 11, `Escenas listas (${m[1]})`, "escenas");
    } else if (/^\[video-ia\] GPU ocupada.*\(v[ií]deo IA\)/.test(l)) {
      p.esperandoGpu = true; p.fase = "Esperando la GPU"; p.clave = "gpu-video";
    } else if (/^\[video-ia\] turno conseguido/.test(l)) {
      p.esperandoGpu = false; p.fase = p.clave === "gpu-portada" ? "Finalizando" : "Imágenes";
    } else if ((m = l.match(/^\[video-ia\] imagen (\d+)\/(\d+)/))) {
      const n = +m[1], t = +m[2] || 1;
      set(p, 11 + 24 * n / t, `Imágenes ${n}/${t}`, `img${n}`);
    } else if ((m = l.match(/^\[video-ia\] clip (\d+)\/(\d+)/))) {
      const n = +m[1], t = +m[2] || 1;
      set(p, 35 + 50 * n / t, `Clips ${n}/${t}`, `clip${n}`);
    } else if (/^\[video-ia\] fondos listos/.test(l)) {
      set(p, 85, "Clips listos", "fondos");
    } else if (/^-> Generando video vertical/.test(l)) {
      set(p, videoIA ? 86 : 12, "Montaje", "montaje");
      p.avanceTiempo = videoIA ? { techo: 95, tau: 120 } : { techo: 90, tau: 60 };
    } else if (/^Video generado:/.test(l)) {
      set(p, videoIA ? 95 : 90, "Finalizando", "final");
    } else if (/^\[video-ia\] GPU ocupada.*\(portada\)/.test(l)) {
      p.esperandoGpu = true; p.fase = "Finalizando · esperando GPU"; p.clave = "gpu-portada";
    } else if (/^(\[miniatura\]|-> Miniatura)/.test(l)) {
      if (p.clave !== "gpu-portada") set(p, 96, "Finalizando · miniatura", "miniatura");
    } else if (/^(Portada y miniatura|Miniatura r[aá]pida generada)/.test(l)) {
      set(p, 98, "Finalizando", "portada");
    } else if (/^Atribuci[oó]n guardada/.test(l)) {
      set(p, 99, "Finalizando", "atribucion");
    } else if (/^=== Listo ===/.test(l)) {
      set(p, 100, "Listo", "listo");
    }
  }
  if (status === "completed") { p.pct = 100; p.fase = "Listo"; p.clave = "listo"; p.avanceTiempo = undefined; p.esperandoGpu = false; }
  if (status === "failed") { p.fase = "Error"; p.clave = "error"; p.avanceTiempo = undefined; p.esperandoGpu = false; }
  return p;
}

function set(p: Progreso, pct: number, fase: string, clave: string) {
  p.pct = Math.max(p.pct, pct);
  p.fase = fase;
  p.clave = clave;
  p.esperandoGpu = false;
  p.avanceTiempo = undefined;
}

// Aplica el avance por tiempo (montaje) y evita que la barra retroceda entre sondeos.
export function useProgreso(jobId: string | null | undefined, logs: string | null | undefined, status?: string) {
  const base = calcularProgreso(logs, status);
  const desde = useRef<{ clave: string; t: number } | null>(null);
  const maximo = useRef<{ id: string; pct: number }>({ id: "", pct: 0 });
  const [, setTick] = useState(0);

  if (!desde.current || desde.current.clave !== `${jobId}:${base.clave}`) {
    desde.current = { clave: `${jobId}:${base.clave}`, t: Date.now() };
  }
  // Re-render cada 2 s mientras haya avance por tiempo, para que se mueva suave.
  useEffect(() => {
    if (!base.avanceTiempo) return;
    const iv = setInterval(() => setTick((x) => x + 1), 2000);
    return () => clearInterval(iv);
  }, [base.avanceTiempo?.techo]); // eslint-disable-line react-hooks/exhaustive-deps

  let pct = base.pct;
  if (base.avanceTiempo) {
    const seg = (Date.now() - desde.current.t) / 1000;
    const { techo, tau } = base.avanceTiempo;
    pct = base.pct + (techo - base.pct) * (1 - Math.exp(-seg / tau));
  }
  if (maximo.current.id !== (jobId || "")) maximo.current = { id: jobId || "", pct: 0 };
  if (status !== "failed") { pct = Math.max(pct, maximo.current.pct); maximo.current.pct = pct; }
  return { ...base, pct: Math.min(100, pct) };
}

// ── Vista ─────────────────────────────────────────────────────────────────────
export function BarraProgreso({ progreso, titulo, compacta = false, status }: {
  progreso: Progreso; titulo?: string | null; compacta?: boolean; status?: string;
}) {
  const pct = Math.round(progreso.pct);
  const color = status === "failed" ? ESTILO_BARRA.rellenoError : pct >= 100 ? ESTILO_BARRA.rellenoOk : ESTILO_BARRA.relleno;
  const tit = titulo || progreso.titulo;
  return (
    <div style={{ margin: compacta ? "0" : "0.6rem 0" }} aria-label={`Progreso ${pct}%`}>
      {tit && !compacta && (
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text, #f0ece4)", marginBottom: 5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {tit}
        </div>
      )}
      <div style={{
        width: "100%", height: 8, borderRadius: 4, background: ESTILO_BARRA.pista,
        overflow: "hidden", border: `1px solid ${ESTILO_BARRA.borde}`,
      }}>
        <div style={{ height: "100%", width: `${Math.max(0, Math.min(100, progreso.pct))}%`, background: color, transition: "width 0.4s ease" }} />
      </div>
      <div style={{ fontFamily: ESTILO_BARRA.mono, fontSize: 12, color: ESTILO_BARRA.etiqueta, marginTop: 4, display: "flex", justifyContent: "space-between", gap: 8 }}>
        <span>
          {progreso.esperandoGpu && <span style={{ color: "#f5a524" }}>⏳ </span>}
          {progreso.fase} · {pct}%
        </span>
      </div>
    </div>
  );
}

// Variante para quien ya sondea el job (JobPanel de la página principal).
export function BarraProgresoLog({ jobId, logs, status, titulo }: {
  jobId: string; logs?: string | null; status?: string; titulo?: string | null;
}) {
  const progreso = useProgreso(jobId, logs, status);
  return <BarraProgreso progreso={progreso} titulo={titulo} status={status} />;
}

// ── Caché compartida de /api/jobs/{id} ────────────────────────────────────────
// Varias barras del mismo job (panel "En producción" + tarjeta de la cola)
// comparten una sola petición por ciclo.
const cache = new Map<string, { t: number; p: Promise<JobInfo | null> }>();
interface JobInfo { id: string; status: string; logs?: string; label?: string }

function pedirJob(jobId: string): Promise<JobInfo | null> {
  const c = cache.get(jobId);
  if (c && Date.now() - c.t < 3000) return c.p;
  const p = fetch(`/api/jobs/${jobId}`, { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  cache.set(jobId, { t: Date.now(), p });
  return p;
}

// Barra autónoma: sondea el job cada 4 s mientras está montada y en curso.
// Si el endpoint no responde, no muestra nada (se oculta sin romper la página).
export function BarraProgresoJob({ jobId, titulo, compacta = false, intervaloMs = 4000 }: {
  jobId: string; titulo?: string | null; compacta?: boolean; intervaloMs?: number;
}) {
  const [job, setJob] = useState<JobInfo | null>(null);
  useEffect(() => {
    let vivo = true;
    let iv: ReturnType<typeof setInterval> | null = null;
    const tick = async () => {
      const d = await pedirJob(jobId);
      if (!vivo) return;
      if (d) setJob(d);
      if (d && (d.status === "completed" || d.status === "failed") && iv) { clearInterval(iv); iv = null; }
    };
    tick();
    iv = setInterval(tick, intervaloMs);
    return () => { vivo = false; if (iv) clearInterval(iv); };
  }, [jobId, intervaloMs]);

  const progreso = useProgreso(jobId, job?.logs, job?.status);
  if (!job) return null;
  return <BarraProgreso progreso={progreso} titulo={titulo} compacta={compacta} status={job.status} />;
}
