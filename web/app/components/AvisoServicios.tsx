"use client";

// Aviso de cada sección: qué le falta para funcionar y cómo arrancarlo.
//   - rojo: falta algo obligatorio (la sección no funcionará)
//   - ámbar: falta algo opcional (solo algunas opciones no estarán)
//   - verde discreto: todo listo
// Uso: <AvisoServicios seccion="montaje" />  (ids en api/sistema.py SECCIONES)

import type { Componente } from "./estadoSistema";
import { arrancarServicio, refrescarEstado, useEstadoSistema } from "./estadoSistema";

const ETIQUETA_ACCION: Record<string, string> = {
  despertar_llm: "Despertar el Mac",
  arrancar_comfyui: "Arrancar ComfyUI",
};

function BotonAccion({ c, arrancando, ccOk }: { c: Componente; arrancando: string | null; ccOk: boolean }) {
  if (!c.accion) return null;
  const servicio = c.accion === "despertar_llm" ? "llm" : "comfyui";
  // ComfyUI se arranca a través del Centro de Control del PC: si está cerrado, no hay botón posible
  if (servicio === "comfyui" && !ccOk) {
    return <span style={{ fontSize: 11.5, opacity: 0.9 }}>Primero abre <code>E:\AI-Studio\Centro-Control.bat</code></span>;
  }
  const activo = arrancando === servicio;
  return (
    <button type="button" disabled={!!arrancando} onClick={() => arrancarServicio(servicio)}
      style={{ fontSize: 12, padding: "4px 11px", borderRadius: 7, border: "1px solid currentColor", background: "transparent",
        color: "inherit", cursor: arrancando ? "wait" : "pointer", fontWeight: 600, whiteSpace: "nowrap" }}>
      {activo ? "Arrancando… (hasta 1-3 min)" : ETIQUETA_ACCION[c.accion]}
    </button>
  );
}

export default function AvisoServicios({ seccion, compacto }: { seccion: string; compacto?: boolean }) {
  const { datos, error, arrancando, mensaje } = useEstadoSistema();

  if (error && !datos) {
    return (
      <div style={{ ...caja, background: "#2a1515", border: "1px solid #5a2020", color: "#f87171" }}>
        ⚠ No se puede contactar con el backend (puerto 8000). Arranca la app con <code>docker compose up -d</code>.
      </div>
    );
  }
  if (!datos) return null;
  const s = datos.secciones[seccion];
  if (!s) return null;
  const por = Object.fromEntries(datos.componentes.map((c) => [c.id, c]));
  const faltan = s.faltan.map((id) => por[id]).filter(Boolean);
  const opcionales = s.opcionales.map((id) => por[id]).filter(Boolean);
  const instalando = datos.arranque.instalando;

  if (!faltan.length && !opcionales.length) {
    if (compacto) return null;
    return (
      <p style={{ fontSize: 11.5, color: "var(--muted)", margin: "0 0 12px", display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />
        Todo listo para {s.nombre} · comprobado {datos.comprobado}
      </p>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
      {faltan.length > 0 && (
        <div style={{ ...caja, background: "#2a1515", border: "1px solid #5a2020", color: "#fca5a5" }}>
          <p style={{ margin: "0 0 6px", fontWeight: 700, color: "#f87171" }}>
            ⚠ {s.nombre} necesita {faltan.length === 1 ? "que arranques esto" : "que arranques estas piezas"} para funcionar:
          </p>
          {faltan.map((c) => (
            <div key={c.id} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", padding: "4px 0" }}>
              <div style={{ flex: "1 1 260px", minWidth: 0 }}>
                <b>{c.nombre}</b> <span style={{ opacity: 0.8 }}>— {c.detalle}</span>
                {c.arreglo && <div style={{ fontSize: 11.5, opacity: 0.85 }}>{c.arreglo}</div>}
              </div>
              <BotonAccion c={c} arrancando={arrancando} ccOk={!!por.control_center?.ok} />
            </div>
          ))}
        </div>
      )}
      {opcionales.length > 0 && (
        <div style={{ ...caja, background: "#231a08", border: "1px solid #5a4410", color: "#fcd34d" }}>
          {opcionales.map((c) => (
            <div key={c.id} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ flex: "1 1 260px" }}>
                <b>{c.nombre}</b> apagado: no estará disponible <i>{s.opcionales_para[c.id]}</i>.
              </span>
              <BotonAccion c={c} arrancando={arrancando} ccOk={!!por.control_center?.ok} />
            </div>
          ))}
        </div>
      )}
      {(mensaje || instalando.length > 0) && (
        <p style={{ fontSize: 12, margin: 0, color: mensaje ? "#f87171" : "var(--muted)" }}>
          {mensaje || `Instalando librerías que faltaban: ${instalando.join(", ")}…`}
        </p>
      )}
      <button type="button" onClick={() => refrescarEstado(true)}
        style={{ alignSelf: "flex-start", fontSize: 11, background: "none", border: "none", color: "var(--muted)", cursor: "pointer", padding: 0, textDecoration: "underline" }}>
        Volver a comprobar
      </button>
    </div>
  );
}

const caja: React.CSSProperties = { borderRadius: 10, padding: "10px 14px", fontSize: 13, lineHeight: 1.45 };
