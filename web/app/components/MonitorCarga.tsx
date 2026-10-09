"use client";

// Monitor de carga de la barra superior: CPU, RAM, GPU, VRAM y temperatura.
// Estilo del medidor de AI Studio / Estudio IA (chips .top-chip: monoespaciada,
// píldora #262230 con borde #332e3d; medidor .pnl-meter con esquinas redondas)
// y colores de saturación de su tira de estado: verde #4bd08b, ámbar #f5a524,
// rojo #d8695f. Datos: GET /api/monitor-carga (ruta de Next, ver app/api/monitor-carga).

import { useEffect, useState } from "react";

interface Metricas {
  cpu: { pct: number; nucleos?: number; origen: string } | null;
  ram: { pct: number; usado_mb: number; total_mb: number; origen: string } | null;
  gpu: {
    nombre: string; util: number | null; vram_usada_mb: number; vram_total_mb: number;
    vram_pct: number; temp_c: number | null; origen: string;
  } | null;
}

const C = {
  chip: "#262230", borde: "#332e3d", texto: "#a79fb0", pista: "#1c1920",
  ok: "#4bd08b", medio: "#f5a524", alto: "#d8695f",
  mono: 'ui-monospace, "Cascadia Code", Consolas, monospace',
};

function colorPct(p: number) { return p >= 85 ? C.alto : p >= 60 ? C.medio : C.ok; }
function colorTemp(t: number) { return t >= 83 ? C.alto : t >= 70 ? C.medio : C.ok; }
const gb = (mb: number) => (mb / 1024).toFixed(1);

function Chip({ etiqueta, valor, pct, color, title, sufijo }: {
  etiqueta: string; valor: string; pct: number | null; color: string; title: string; sufijo?: string;
}) {
  return (
    <span title={title} style={{
      display: "inline-flex", alignItems: "center", gap: 6, fontFamily: C.mono, fontSize: 11,
      padding: "3px 9px", borderRadius: 20, background: C.chip, border: `1px solid ${C.borde}`,
      color: C.texto, flexShrink: 0, lineHeight: 1.2,
    }}>
      <span>{etiqueta}{sufijo && <span style={{ fontSize: 9, opacity: 0.7 }}>·{sufijo}</span>}</span>
      {pct !== null && (
        <span style={{ width: 34, height: 6, borderRadius: 3, background: C.pista, overflow: "hidden", display: "inline-block" }}>
          <i style={{ display: "block", height: "100%", width: `${Math.max(2, Math.min(100, pct))}%`, background: color, transition: "width 0.5s" }} />
        </span>
      )}
      <b style={{ color, fontWeight: 700, minWidth: 30, textAlign: "right" }}>{valor}</b>
    </span>
  );
}

export default function MonitorCarga({ intervaloMs = 2500 }: { intervaloMs?: number }) {
  const [m, setM] = useState<Metricas | null>(null);
  const [fallos, setFallos] = useState(0);

  useEffect(() => {
    let vivo = true;
    const tick = async () => {
      if (document.hidden) return; // pestaña oculta: no sondear
      try {
        const r = await fetch("/api/monitor-carga", { cache: "no-store" });
        if (!r.ok) throw new Error(String(r.status));
        const d = await r.json();
        if (vivo) { setM(d); setFallos(0); }
      } catch {
        if (vivo) setFallos((f) => f + 1);
      }
    };
    tick();
    const iv = setInterval(tick, intervaloMs);
    return () => { vivo = false; clearInterval(iv); };
  }, [intervaloMs]);

  if (!m || fallos >= 3) return null; // sin datos: se oculta sin molestar
  const { cpu, ram, gpu } = m;
  const docker = (o?: string) => (o === "docker" ? "docker" : undefined);
  const notaDocker = "\nMedido dentro de Docker (VM de WSL2, donde corren backend y ffmpeg). " +
    "ComfyUI y el resto del PC no cuentan aquí; para la carga real del PC arranca el monitor de host (:8095).";

  return (
    <div style={{ marginLeft: 16, display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }} aria-label="Monitor de carga">
      {cpu && (
        <Chip etiqueta="CPU" sufijo={docker(cpu.origen)} valor={`${cpu.pct}%`} pct={cpu.pct} color={colorPct(cpu.pct)}
          title={`CPU ${cpu.pct}%${cpu.nucleos ? ` · ${cpu.nucleos} hilos` : ""}${cpu.origen === "docker" ? notaDocker : ""}`} />
      )}
      {ram && (
        <Chip etiqueta="RAM" sufijo={docker(ram.origen)} valor={`${ram.pct}%`} pct={ram.pct} color={colorPct(ram.pct)}
          title={`RAM ${gb(ram.usado_mb)} / ${gb(ram.total_mb)} GB (${ram.pct}%)${ram.origen === "docker" ? notaDocker : ""}`} />
      )}
      {gpu && gpu.util !== null && (
        <Chip etiqueta="GPU" valor={`${gpu.util}%`} pct={gpu.util} color={colorPct(gpu.util)}
          title={`${gpu.nombre} · uso ${gpu.util}%`} />
      )}
      {gpu && (
        <Chip etiqueta="VRAM" valor={`${gpu.vram_pct}%`} pct={gpu.vram_pct} color={colorPct(gpu.vram_pct)}
          title={`VRAM ${gpu.vram_usada_mb} / ${gpu.vram_total_mb} MB (${gpu.vram_pct}%) · ${gpu.nombre}`} />
      )}
      {gpu && gpu.temp_c !== null && (
        <Chip etiqueta="TEMP" valor={`${gpu.temp_c}°C`} pct={null} color={colorTemp(gpu.temp_c)}
          title={`Temperatura de la GPU: ${gpu.temp_c} °C`} />
      )}
    </div>
  );
}
