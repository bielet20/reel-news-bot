// Estilos compartidos del editor de cursos (mismo lenguaje visual que el Gestor).


import type { CSSProperties } from "react";
export const panel: CSSProperties = {
  background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14,
};

export const etiqueta: CSSProperties = {
  fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em",
  color: "var(--muted)", margin: 0,
};

export const input: CSSProperties = {
  width: "100%", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8,
  padding: "7px 10px", color: "var(--text)", fontSize: 13, outline: "none", boxSizing: "border-box",
  fontFamily: "inherit",
};

export const btn: CSSProperties = {
  background: "var(--surface2)", border: "1px solid var(--border)", color: "var(--text)",
  borderRadius: 8, padding: "6px 11px", fontSize: 12, cursor: "pointer", whiteSpace: "nowrap",
};

export const btnPrimario: CSSProperties = {
  ...btn, background: "var(--accent)", border: "1px solid var(--accent)", color: "#fff", fontWeight: 700,
};

export const btnPeligro: CSSProperties = { ...btn, color: "#f87171" };
