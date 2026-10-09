"use client";

// Settings → Estado del sistema: todas las piezas, qué sección las usa, cómo
// arreglarlas y el informe del último arranque del backend.

import { arrancarServicio, refrescarEstado, useEstadoSistema } from "./estadoSistema";

export default function PanelEstadoSistema() {
  const { datos, error, arrancando, mensaje } = useEstadoSistema();
  if (error && !datos) return <p style={{ color: "#f87171" }}>El backend (:8000) no responde. Arranca con <code>docker compose up -d</code>.</p>;
  if (!datos) return <p style={{ color: "var(--muted)" }}>Comprobando…</p>;

  const ccOk = !!datos.componentes.find((c) => c.id === "control_center")?.ok;
  const usadoPor = (id: string) => Object.values(datos.secciones)
    .filter((s) => s.faltan.includes(id) || s.opcionales.includes(id) || false)
    .map((s) => s.nombre);

  return (
    <div id="estado" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <p style={{ margin: 0, fontSize: 12, color: "var(--muted)" }}>
          Comprobado a las {datos.comprobado} · backend arrancado {datos.arranque.inicio || "—"}
        </p>
        <button type="button" onClick={() => refrescarEstado(true)}
          style={{ fontSize: 12, padding: "5px 11px", borderRadius: 7, border: "1px solid var(--border)", background: "var(--surface2)", color: "var(--text)", cursor: "pointer" }}>
          ↻ Comprobar ahora
        </button>
      </div>
      {datos.componentes.map((c) => {
        const afecta = usadoPor(c.id);
        return (
          <div key={c.id} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", padding: "9px 12px", borderRadius: 10,
            background: "var(--surface2)", border: `1px solid ${c.ok ? "var(--border)" : c.grave ? "#5a2020" : "#5a4410"}` }}>
            <span style={{ width: 9, height: 9, borderRadius: "50%", flexShrink: 0, background: c.ok ? "#22c55e" : c.grave ? "#ef4444" : "#f59e0b" }} />
            <div style={{ flex: "1 1 260px", minWidth: 0 }}>
              <b style={{ fontSize: 13 }}>{c.nombre}</b> <span style={{ fontSize: 12, color: "var(--muted)" }}>— {c.detalle}</span>
              {!c.ok && c.arreglo && <div style={{ fontSize: 11.5, color: "var(--muted)" }}>{c.arreglo}</div>}
              {!c.ok && afecta.length > 0 && <div style={{ fontSize: 11.5, color: "#fca5a5" }}>Afecta a: {afecta.join(", ")}</div>}
            </div>
            {!c.ok && c.accion && !(c.accion === "arrancar_comfyui" && !ccOk) && (
              <button type="button" disabled={!!arrancando}
                onClick={() => arrancarServicio(c.accion === "despertar_llm" ? "llm" : "comfyui")}
                style={{ fontSize: 12, padding: "4px 11px", borderRadius: 7, border: "1px solid var(--accent)", background: "transparent", color: "var(--accent)", cursor: "pointer" }}>
                {arrancando ? "Arrancando…" : c.accion === "despertar_llm" ? "Despertar el Mac" : "Arrancar ComfyUI"}
              </button>
            )}
          </div>
        );
      })}
      {mensaje && <p style={{ fontSize: 12, color: "#f87171", margin: 0 }}>{mensaje}</p>}
      {(datos.arranque.instaladas.length > 0 || datos.arranque.errores.length > 0 || datos.arranque.carpetas_creadas.length > 0) && (
        <div style={{ fontSize: 12, color: "var(--muted)", padding: "8px 12px", borderRadius: 10, border: "1px dashed var(--border)" }}>
          <b>Último arranque del backend:</b>
          {datos.arranque.carpetas_creadas.length > 0 && <div>Carpetas creadas: {datos.arranque.carpetas_creadas.join(", ")}</div>}
          {datos.arranque.instaladas.length > 0 && <div>Librerías que faltaban y se instalaron solas: {datos.arranque.instaladas.join(", ")}</div>}
          {datos.arranque.errores.map((e, i) => <div key={i} style={{ color: "#f87171" }}>{e}</div>)}
        </div>
      )}
    </div>
  );
}
