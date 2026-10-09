// GET /api/monitor-carga — métricas de carga para el monitor de la barra superior.
//
// Vive en el servidor de Next (contenedor frontend), así que NO toca el backend
// FastAPI (uvicorn --reload) ni corta trabajos. Las rutas de app/ tienen prioridad
// sobre el rewrite "/api/:path*" -> backend de next.config.ts.
//
// Fuentes, por orden:
//   1) Monitor de host opcional (MONITOR_HOST_URL, por defecto
//      http://host.docker.internal:8095/metrics): CPU/RAM reales del PC + GPU,
//      VRAM y temperatura (nvidia-smi). Ver _staging/monitor-carga-2026-10-06/.
//   2) Si no está: GPU/VRAM del Centro de Control de AI Studio (:8090/api/status,
//      el mismo dato que usa el medidor de VRAM de Estudio IA) y CPU/RAM leídas de
//      /proc dentro de Docker (= la VM de WSL2 donde corren backend y ffmpeg).

import { readFile } from "node:fs/promises";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HOST_URL = process.env.MONITOR_HOST_URL || "http://host.docker.internal:8095/metrics";
const CC_URL = (process.env.AISTUDIO_CONTROL_CENTER_URL || "http://host.docker.internal:8090") + "/api/status";

type Origen = "host" | "docker" | "control-center";
interface Metricas {
  cpu: { pct: number; nucleos?: number; origen: Origen } | null;
  ram: { pct: number; usado_mb: number; total_mb: number; origen: Origen } | null;
  gpu: {
    nombre: string; util: number | null; vram_usada_mb: number; vram_total_mb: number;
    vram_pct: number; temp_c: number | null; origen: Origen;
  } | null;
  t: number;
}

async function getJson(url: string, ms: number): Promise<any | null> {
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(ms), cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

// ── 1) monitor de host (si no responde, no se reintenta en 60 s) ─────────────
let hostCaidoHasta = 0;
async function desdeHost(): Promise<Metricas | null> {
  if (Date.now() < hostCaidoHasta) return null;
  const d = await getJson(HOST_URL, 700);
  if (!d || !d.cpu) { hostCaidoHasta = Date.now() + 60_000; return null; }
  return {
    cpu: { pct: d.cpu.pct, nucleos: d.cpu.nucleos, origen: "host" },
    ram: d.ram ? { ...d.ram, origen: "host" } : null,
    gpu: d.gpu ? { ...d.gpu, origen: "host" } : null,
    t: Date.now(),
  };
}

// ── 2a) GPU desde el Centro de Control (tarda ~2 s: caché de 5 s) ─────────────
let gpuCache: { t: number; v: Metricas["gpu"] } = { t: 0, v: null };
let gpuEnCurso: Promise<Metricas["gpu"]> | null = null;
async function gpuDesdeCC(): Promise<Metricas["gpu"]> {
  if (Date.now() - gpuCache.t < 5000) return gpuCache.v;
  if (!gpuEnCurso) {
    gpuEnCurso = getJson(CC_URL, 6000).then((d) => {
      const g = d?.gpu;
      const v = g && g.total ? {
        nombre: String(g.name || "GPU"), util: g.util ?? null,
        vram_usada_mb: g.used, vram_total_mb: g.total,
        vram_pct: Math.round((g.used / g.total) * 100), temp_c: null, origen: "control-center" as Origen,
      } : null;
      gpuCache = { t: Date.now(), v };
      return v;
    }).finally(() => { gpuEnCurso = null; });
  }
  // Si hay un dato reciente (<15 s) no esperamos a la petición lenta.
  if (gpuCache.v && Date.now() - gpuCache.t < 15000) return gpuCache.v;
  return gpuEnCurso;
}

// ── 2b) CPU/RAM de /proc (VM de Docker/WSL2) ─────────────────────────────────
let cpuPrev: { idle: number; total: number } | null = null;
async function muestraCpu() {
  const txt = await readFile("/proc/stat", "utf8");
  const n = txt.split("\n")[0].trim().split(/\s+/).slice(1).map(Number);
  const idle = n[3] + (n[4] || 0);
  const total = n.reduce((a, b) => a + b, 0);
  const nucleos = (txt.match(/^cpu\d+/gm) || []).length;
  return { idle, total, nucleos };
}
async function cpuDocker(): Promise<Metricas["cpu"]> {
  try {
    let s = await muestraCpu();
    if (!cpuPrev) {
      cpuPrev = s;
      await new Promise((r) => setTimeout(r, 300));
      s = await muestraCpu();
    }
    const dT = s.total - cpuPrev.total, dI = s.idle - cpuPrev.idle;
    cpuPrev = s;
    const pct = dT > 0 ? Math.round((1 - dI / dT) * 100) : 0;
    return { pct: Math.max(0, Math.min(100, pct)), nucleos: s.nucleos, origen: "docker" };
  } catch {
    return null;
  }
}
async function ramDocker(): Promise<Metricas["ram"]> {
  try {
    const txt = await readFile("/proc/meminfo", "utf8");
    const kb = (k: string) => Number((txt.match(new RegExp(`^${k}:\\s+(\\d+)`, "m")) || [])[1] || 0);
    const total = kb("MemTotal"), libre = kb("MemAvailable");
    if (!total) return null;
    const usado = total - libre;
    return { pct: Math.round((usado / total) * 100), usado_mb: Math.round(usado / 1024), total_mb: Math.round(total / 1024), origen: "docker" };
  } catch {
    return null;
  }
}

export async function GET() {
  const host = await desdeHost();
  if (host) return Response.json(host, { headers: { "Cache-Control": "no-store" } });
  const [cpu, ram, gpu] = await Promise.all([cpuDocker(), ramDocker(), gpuDesdeCC()]);
  const m: Metricas = { cpu, ram, gpu, t: Date.now() };
  return Response.json(m, { headers: { "Cache-Control": "no-store" } });
}
