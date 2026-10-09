"use client";

// Estado del sistema compartido por toda la web (GET /api/sistema/estado).
// Un solo sondeo para todos los componentes que lo usan: cada 20 s, o cada
// 4 s mientras se está arrancando algo.

import { useEffect, useSyncExternalStore } from "react";

export interface Componente {
  id: string;
  nombre: string;
  ok: boolean;
  detalle: string;
  arreglo: string;
  accion: "despertar_llm" | "arrancar_comfyui" | null;
  grave: boolean;
}

export interface EstadoSeccion {
  nombre: string;
  ok: boolean;
  faltan: string[];
  opcionales: string[];
  opcionales_para: Record<string, string>;
}

export interface EstadoSistema {
  componentes: Componente[];
  secciones: Record<string, EstadoSeccion>;
  arranque: { hecho: boolean; instalando: string[]; instaladas: string[]; errores: string[]; carpetas_creadas: string[]; inicio: string | null };
  comprobado: string;
}

type Estado = { datos: EstadoSistema | null; error: boolean; arrancando: string | null; mensaje: string };

let estado: Estado = { datos: null, error: false, arrancando: null, mensaje: "" };
const oyentes = new Set<() => void>();
let timer: ReturnType<typeof setTimeout> | null = null;
let usuarios = 0;

function emitir(parcial: Partial<Estado>) {
  estado = { ...estado, ...parcial };
  oyentes.forEach((f) => f());
}

export async function refrescarEstado(forzar = false) {
  try {
    const r = await fetch(`/api/sistema/estado${forzar ? "?forzar=true" : ""}`);
    if (!r.ok) throw new Error(String(r.status));
    emitir({ datos: await r.json(), error: false });
  } catch {
    emitir({ error: true });
  }
}

function programar() {
  if (timer) clearTimeout(timer);
  if (!usuarios) return;
  const ms = estado.arrancando || estado.datos?.arranque.instalando.length ? 4000 : 20000;
  timer = setTimeout(async () => { await refrescarEstado(); programar(); }, ms);
}

/** Arranca un servicio desde la web: "llm" (despertar el Mac) o "comfyui". */
export async function arrancarServicio(servicio: "llm" | "comfyui") {
  emitir({ arrancando: servicio, mensaje: "" });
  programar();
  try {
    const r = await fetch(`/api/sistema/arrancar/${servicio}`, { method: "POST" });
    const d = await r.json();
    emitir({ mensaje: d.ok ? "" : d.msg || "No se pudo arrancar" });
  } catch {
    emitir({ mensaje: "No se pudo contactar con el servidor" });
  } finally {
    emitir({ arrancando: null });
    await refrescarEstado(true);
    programar();
  }
}

function suscribir(f: () => void) {
  oyentes.add(f);
  return () => { oyentes.delete(f); };
}

export function useEstadoSistema(): Estado {
  useEffect(() => {
    usuarios += 1;
    if (usuarios === 1) { refrescarEstado(); programar(); }
    return () => {
      usuarios -= 1;
      if (!usuarios && timer) { clearTimeout(timer); timer = null; }
    };
  }, []);
  return useSyncExternalStore(suscribir, () => estado, () => estado);
}
