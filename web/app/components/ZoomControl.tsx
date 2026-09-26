"use client";

// Tamaño de la interfaz (A− / A+), recordado por navegador. Usa `zoom` en <html>
// porque casi todos los tamaños de la app están en px dentro de estilos en línea:
// así crece todo por igual (textos, botones, vídeos, márgenes).

import { useEffect, useState } from "react";

const PASOS = [1, 1.1, 1.2, 1.3, 1.4, 1.5];
const DEFECTO = 1.2;
const CLAVE = "ui_zoom";

function aplicar(z: number) {
  document.documentElement.style.setProperty("zoom", String(z));
}

export default function ZoomControl() {
  const [zoom, setZoom] = useState(DEFECTO);

  useEffect(() => {
    let z = DEFECTO;
    try {
      const guardado = parseFloat(localStorage.getItem(CLAVE) || "");
      if (PASOS.includes(guardado)) z = guardado;
    } catch {}
    aplicar(z);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setZoom(z);
  }, []);

  function cambiar(dir: 1 | -1) {
    const i = Math.max(0, Math.min(PASOS.length - 1, PASOS.indexOf(zoom) + dir));
    const z = PASOS[i];
    setZoom(z);
    aplicar(z);
    try { localStorage.setItem(CLAVE, String(z)); } catch {}
  }

  const btn: React.CSSProperties = {
    background: "var(--surface2)", color: "var(--text)", border: "1px solid var(--border)",
    borderRadius: 7, padding: "3px 9px", cursor: "pointer", fontSize: 13, fontWeight: 700,
  };
  return (
    <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }} title="Tamaño de la interfaz">
      <button style={btn} onClick={() => cambiar(-1)} aria-label="Reducir tamaño">A−</button>
      <span style={{ fontSize: 12, color: "var(--muted)", minWidth: 38, textAlign: "center" }}>
        {Math.round(zoom * 100)}%
      </span>
      <button style={btn} onClick={() => cambiar(1)} aria-label="Aumentar tamaño">A+</button>
    </div>
  );
}
