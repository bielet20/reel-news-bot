"use client";

// Fila de noticia con el mismo patrón que las "Alertas virales" del Gestor:
// casilla de selección, título, línea de metadatos (fuente · score · fecha ·
// contrastada por · gancho), procedencia y, a la derecha, la etiqueta
// Viral/Alto encima de las acciones.

export function fmtFecha(iso?: string) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("es-ES", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

export default function NoticiaFila({
  titulo, fuente, score, fecha, verificadores, gancho, documentacion,
  extraMeta, seleccionada, onToggle, atenuada, acciones, pie,
}: {
  titulo: string;
  fuente?: string;
  score: number;
  fecha?: string;
  verificadores?: string[];
  gancho?: string;
  documentacion?: string;
  extraMeta?: React.ReactNode;
  seleccionada?: boolean;
  onToggle?: () => void;
  atenuada?: boolean;
  acciones?: React.ReactNode;
  pie?: React.ReactNode;
}) {
  const sel = !!seleccionada;
  const viral = score >= 8.5;
  return (
    <div style={{
      padding: "11px 14px", borderRadius: 12,
      background: sel ? "rgba(99,102,241,0.12)" : atenuada ? "var(--surface2)" : "rgba(99,102,241,0.07)",
      border: `1px solid ${sel ? "var(--accent)" : atenuada ? "var(--border)" : "var(--accent)"}`,
      opacity: atenuada && !sel ? 0.7 : 1,
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        {onToggle && (
          <button
            type="button"
            onClick={onToggle}
            aria-label={sel ? "Quitar de la selección" : "Seleccionar"}
            style={{ marginTop: 2, width: 16, height: 16, borderRadius: 4, border: `1px solid ${sel ? "var(--accent)" : "var(--border)"}`, background: sel ? "var(--accent)" : "transparent", color: "#fff", fontSize: 10, cursor: "pointer", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            {sel ? "✓" : ""}
          </button>
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontSize: 13, fontWeight: 600, margin: 0, color: "var(--text)", lineHeight: 1.3 }}>
            {titulo}
          </p>
          <p style={{ fontSize: 11, color: "var(--muted)", margin: "3px 0 0" }}>
            {fuente}{fuente ? " · " : ""}score {score.toFixed(1)}
            {fecha ? ` · ${fmtFecha(fecha)}` : ""}
            {verificadores?.length ? ` · contrastada por ${verificadores.join(", ")}` : ""}
            {extraMeta}
            {gancho && <span style={{ color: "var(--accent)", marginLeft: 6 }}>{gancho}</span>}
          </p>
          {documentacion && (
            <p style={{ fontSize: 11, color: "var(--text)", opacity: 0.75, margin: "2px 0 0" }}>{documentacion}</p>
          )}
          {pie}
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 5, flexShrink: 0 }}>
          <span style={{
            fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 5,
            background: viral ? "#0a2010" : "#1a1a2e",
            color: viral ? "#4ade80" : "#c084fc",
          }}>
            {viral ? "Viral" : score >= 7.5 ? "Alto" : score >= 6 ? "Bueno" : "Normal"}
          </span>
          {acciones}
        </div>
      </div>
    </div>
  );
}
