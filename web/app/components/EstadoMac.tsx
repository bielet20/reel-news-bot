"use client";

// Indicador de la barra superior. Prioriza la IA del Mac (sin ella no se
// generan reels ni cursos) con su botón «Despertar»; si la IA está bien pero
// hay otros servicios apagados, lo resume y enlaza al panel completo en
// Settings → Estado del sistema.

import Link from "next/link";
import { arrancarServicio, useEstadoSistema } from "./estadoSistema";

export default function EstadoMac() {
  const { datos, error, arrancando, mensaje } = useEstadoSistema();

  if (error && !datos) {
    return (
      <span style={{ marginLeft: 16, fontSize: 13, color: "#ef4444", fontWeight: 700, flexShrink: 0 }} title="El backend (:8000) no responde">
        ● Backend sin respuesta
      </span>
    );
  }
  if (!datos) return null;

  const llm = datos.componentes.find((c) => c.id === "llm");
  const apagados = datos.componentes.filter((c) => !c.ok && c.grave && c.id !== "llm");
  const llmOk = llm?.ok ?? false;
  const color = !llmOk ? "#ef4444" : apagados.length ? "#f59e0b" : "#22c55e";

  return (
    <div style={{ marginLeft: 16, display: "flex", alignItems: "center", gap: 8, fontSize: 13, flexShrink: 0 }}
      title={mensaje || llm?.detalle || (llmOk ? "La IA responde" : "La IA no responde")}>
      <span style={{ width: 10, height: 10, borderRadius: "50%", background: color, display: "inline-block" }} />
      {!llmOk ? (
        <>
          <span style={{ color, fontWeight: 700 }}>{llm?.nombre || "IA"} sin respuesta</span>
          {llm?.accion === "despertar_llm" && (
            <button onClick={() => arrancarServicio("llm")} disabled={!!arrancando}
              style={{ padding: "4px 10px", borderRadius: 6, border: `1px solid ${color}`, background: "transparent", color, cursor: arrancando ? "wait" : "pointer" }}>
              {arrancando === "llm" ? "Despertando…" : "Despertar"}
            </button>
          )}
        </>
      ) : apagados.length ? (
        <Link href="/settings#estado" style={{ color, fontWeight: 600, textDecoration: "none" }}
          title={apagados.map((c) => `${c.nombre}: ${c.detalle}`).join("\n")}>
          {llm?.nombre === "Grok" ? "Grok listo" : "IA lista"} · {apagados.length} servicio{apagados.length > 1 ? "s" : ""} apagado{apagados.length > 1 ? "s" : ""}
        </Link>
      ) : (
        <Link href="/settings#estado" style={{ color: "var(--muted, #aaa)", textDecoration: "none" }}>
          {llm?.nombre === "Grok" ? "Grok listo" : "Sistema listo"}
        </Link>
      )}
    </div>
  );
}
