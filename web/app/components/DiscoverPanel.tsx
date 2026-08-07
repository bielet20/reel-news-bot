"use client";

import { useState, useEffect } from "react";

interface Recencia {
  horas: number | null;
  label: string;
  muy_reciente: boolean;
}

interface NoticiaProuesta {
  titulo: string;
  titulo_original: string;
  fuente: string;
  link: string;
  resumen: string;
  score: number;
  categoria: string;
  gancho: string;
  audiencia: string;
  fecha?: string;
  recencia?: Recencia;
  fuente_verificada?: boolean;
}

interface Props {
  onUsar: (noticia: NoticiaProuesta) => void;
}

interface BatchItem {
  article: NoticiaProuesta;
  status: "pending" | "running" | "done" | "error";
  jobId?: string;
  errorMsg?: string;
}


// Solo afecta el idioma/edición de Google News para búsquedas por tema
// Las fuentes RSS verificadas son siempre globales (Reuters, BBC, AP, DW, Al Jazeera…)
const PAISES = [
  { value: "ES", label: "🌐 Español (España)" },
  { value: "MX", label: "🌐 Español (México)" },
  { value: "AR", label: "🌐 Español (Argentina)" },
  { value: "US", label: "🌐 English (Global)" },
];

const CATEGORIAS: Record<string, string> = {
  tecnologia: "💻",
  economia: "💰",
  mundo: "🌍",
  politica: "🏛️",
  ciencia: "🔬",
  salud: "🏥",
  deportes: "⚽",
  entretenimiento: "🎬",
  cripto: "₿",
  general: "📰",
};

function recenciaLabel(recencia?: Recencia): { label: string; color: string; bg: string; icon: string } | null {
  if (!recencia?.label) return null;
  const horas = recencia.horas ?? 9999;
  if (horas < 1)  return { icon: "⚡", label: recencia.label, color: "#f43f5e", bg: "#2a0a12" };
  if (horas < 3)  return { icon: "🔴", label: recencia.label, color: "#fb923c", bg: "#2a1200" };
  if (horas < 12) return { icon: "🟠", label: recencia.label, color: "#fbbf24", bg: "#231a00" };
  if (horas < 24) return { icon: "🟡", label: "Hoy",          color: "#a3e635", bg: "#162008" };
  return null;
}

function scoreLabel(score: number): { emoji: string; label: string; color: string; bg: string } {
  if (score >= 9)   return { emoji: "🔥🔥🔥", label: "Viral",   color: "#f97316", bg: "#2a1000" };
  if (score >= 7.5) return { emoji: "🔥🔥",   label: "Alto",    color: "#fb923c", bg: "#231208" };
  if (score >= 6)   return { emoji: "🔥",     label: "Bueno",   color: "#fbbf24", bg: "#231a08" };
  return                   { emoji: "📰",     label: "Normal",  color: "#94a3b8", bg: "#141820" };
}

const STORAGE_KEY = "reel-news-saved";

function cargarGuardadas(): NoticiaProuesta[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as NoticiaProuesta[]) : [];
  } catch {
    return [];
  }
}

function persistirGuardadas(lista: NoticiaProuesta[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(lista));
  } catch {}
}

export default function DiscoverPanel({ onUsar }: Props) {
  const [pais, setPais] = useState("ES");
  const [tema, setTema] = useState("");
  const [variado, setVariado] = useState(true);
  const [loading, setLoading] = useState(false);
  const [noticias, setNoticias] = useState<NoticiaProuesta[]>([]);
  const [error, setError] = useState("");
  const [buscado, setBuscado] = useState(false);
  const [savedNews, setSavedNews] = useState<NoticiaProuesta[]>([]);
  const [showSaved, setShowSaved] = useState(false);

  // Carga localStorage solo en el cliente (después de la hidratación)
  useEffect(() => {
    setSavedNews(cargarGuardadas());
  }, []);
  const [selectedLinks, setSelectedLinks] = useState<Set<string>>(new Set());
  const [batchQueue, setBatchQueue] = useState<BatchItem[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);

  // ── Selección para lote ────────────────────────────────────────────────

  function toggleSelect(link: string) {
    setSelectedLinks((prev) => {
      const next = new Set(prev);
      next.has(link) ? next.delete(link) : next.add(link);
      return next;
    });
  }

  function selectAll() {
    setSelectedLinks(new Set(savedNews.map((n) => n.link)));
  }

  function clearSelect() {
    setSelectedLinks(new Set());
  }

  // ── Descarga de descripciones ──────────────────────────────────────────

  function buildDesc(n: NoticiaProuesta, idx: number): string {
    const encabezado = "🔴 ÚLTIMA HORA:";
    const hashtags = ["#noticias", "#ultimahora", `#${n.categoria || "informacion"}`,
      "#verificado", "#shorts"].join(" ");
    return [
      `══════════════════════════════════════════════`,
      `VIDEO ${idx + 1}: ${n.titulo}`,
      `══════════════════════════════════════════════`,
      ``,
      `${encabezado} ${n.titulo.toUpperCase()}`,
      ``,
      n.resumen ? n.resumen.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim() : n.titulo_original,
      ``,
      `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`,
      ``,
      `📰 FUENTE ORIGINAL`,
      n.fuente || "Fuente verificada",
      n.link ? `🔗 ${n.link}` : "",
      ``,
      `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`,
      ``,
      `⚠️ Contenido basado en fuentes verificadas. Consulta el enlace original para más detalles.`,
      ``,
      `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`,
      ``,
      `🔔 SUSCRÍBETE para no perderte las últimas noticias verificadas`,
      `💬 ¿Qué opinas? Comenta abajo 👇`,
      `👍 Dale LIKE y COMPARTE si te fue útil`,
      ``,
      hashtags,
    ].filter(Boolean).join("\n");
  }

  function downloadDescriptions(articles: NoticiaProuesta[]) {
    const text = articles.map((n, i) => buildDesc(n, i)).join("\n\n\n");
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `descripciones_youtube_${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ── Generación en lote ────────────────────────────────────────────────

  async function pollJobHastaFin(jobId: string, idx: number) {
    while (true) {
      await new Promise((r) => setTimeout(r, 4000));
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) continue;
        const job = await res.json();
        if (job.status === "completed") {
          setBatchQueue((prev) =>
            prev.map((it, i) => (i === idx ? { ...it, status: "done", jobId } : it))
          );
          return;
        }
        if (job.status === "failed") {
          // Extraer la última línea de error significativa de los logs
          const logs: string = job.logs || job.error || "";
          const errorMsg = _extraerError(logs);
          setBatchQueue((prev) =>
            prev.map((it, i) => (i === idx ? { ...it, status: "error", jobId, errorMsg } : it))
          );
          return;
        }
      } catch { /* sigue esperando */ }
    }
  }

  function _extraerError(logs: string): string {
    if (!logs) return "Error desconocido";
    const lineas = logs.split("\n").map((l) => l.trim()).filter(Boolean);
    // Prioridad 1: línea de excepción Python (e.g. "ValueError: ...")
    for (let i = lineas.length - 1; i >= 0; i--) {
      if (/^\w+Error:\s|^\w+Exception:\s/i.test(lineas[i])) {
        const l = lineas[i];
        return l.length > 120 ? l.slice(0, 117) + "…" : l;
      }
    }
    // Prioridad 2: cualquier línea con "error", "failed", etc.
    for (let i = lineas.length - 1; i >= 0; i--) {
      const l = lineas[i];
      if (/error|exception|raise|failed|no se pudo/i.test(l)) {
        return l.length > 120 ? l.slice(0, 117) + "…" : l;
      }
    }
    // Fallback: última línea no vacía
    const ultima = lineas[lineas.length - 1] ?? "Error en el proceso";
    return ultima.length > 120 ? ultima.slice(0, 117) + "…" : ultima;
  }

  async function _lanzarJob(art: NoticiaProuesta): Promise<string> {
    const textoLimpio = (art.resumen || art.titulo_original)
      .replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: "texto",
        titulo: art.titulo,
        fuente: art.fuente || "",
        texto: textoLimpio,
        url_fuente: art.link || "",
        tipo_contenido: "noticia",
        mostrar_titulo: true,
        servicio_voz: "auto",
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const { job_id } = await res.json();
    return job_id;
  }

  async function reintentarItem(idx: number) {
    setBatchQueue((prev) =>
      prev.map((it, i) => (i === idx ? { ...it, status: "running", errorMsg: undefined } : it))
    );
    try {
      const art = batchQueue[idx].article;
      const jobId = await _lanzarJob(art);
      await pollJobHastaFin(jobId, idx);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setBatchQueue((prev) =>
        prev.map((it, i) => (i === idx ? { ...it, status: "error", errorMsg: msg } : it))
      );
    }
  }

  async function iniciarBatch() {
    const selected = savedNews.filter((n) => selectedLinks.has(n.link));
    if (!selected.length) return;

    const queue: BatchItem[] = selected.map((a) => ({ article: a, status: "pending" }));
    setBatchQueue(queue);
    setBatchRunning(true);
    setShowSaved(true);

    for (let i = 0; i < queue.length; i++) {
      setBatchQueue((prev) =>
        prev.map((it, idx) => (idx === i ? { ...it, status: "running", errorMsg: undefined } : it))
      );
      try {
        const jobId = await _lanzarJob(queue[i].article);
        await pollJobHastaFin(jobId, i);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setBatchQueue((prev) =>
          prev.map((it, idx) => (idx === i ? { ...it, status: "error", errorMsg: msg } : it))
        );
      }
    }

    setBatchRunning(false);
  }

  function isGuardada(link: string) {
    return savedNews.some((n) => n.link === link);
  }

  function toggleGuardar(noticia: NoticiaProuesta) {
    setSavedNews((prev) => {
      const ya = prev.some((n) => n.link === noticia.link);
      const next = ya ? prev.filter((n) => n.link !== noticia.link) : [...prev, noticia];
      persistirGuardadas(next);
      return next;
    });
  }

  function eliminarGuardada(link: string) {
    setSavedNews((prev) => {
      const next = prev.filter((n) => n.link !== link);
      persistirGuardadas(next);
      return next;
    });
  }

  async function handleBuscar() {
    setLoading(true);
    setError("");
    setNoticias([]);
    setBuscado(false);
    try {
      const res = await fetch("/api/news/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pais, tema: tema || null, variado, n_retornar: 8 }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setNoticias(data.noticias ?? []);
      setBuscado(true);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      {/* Filtros */}
      <div className="rounded-xl p-4 space-y-3"
        style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}>
        <div className="flex gap-3 flex-wrap">
          {/* Idioma Google News */}
          <div className="flex-1 min-w-[140px]">
            <label className="text-xs block mb-1" style={{ color: "var(--muted)" }}>Idioma búsqueda</label>
            <select
              value={pais}
              onChange={(e) => setPais(e.target.value)}
              className="w-full rounded-lg px-3 py-2 text-sm"
              style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)" }}
            >
              {PAISES.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>

          {/* Tema */}
          <div className="flex-1 min-w-[160px]">
            <label className="text-xs block mb-1" style={{ color: "var(--muted)" }}>
              Tema (opcional)
            </label>
            <input
              type="text"
              value={tema}
              onChange={(e) => { setTema(e.target.value); if (e.target.value) setVariado(false); }}
              placeholder="cripto, IA, política…"
              className="w-full rounded-lg px-3 py-2 text-sm"
              style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", outline: "none" }}
            />
          </div>
        </div>

        {/* Variado toggle */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setVariado((v) => !v)}
            className="relative w-9 h-5 rounded-full transition-colors shrink-0"
            style={{ background: variado ? "var(--accent)" : "var(--border)" }}
          >
            <span
              className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all"
              style={{ left: variado ? "calc(100% - 18px)" : "2px" }}
            />
          </button>
          <span className="text-xs" style={{ color: "var(--muted)" }}>
            Variado (mezcla tecnología, mundo, economía, ciencia…)
          </span>
        </div>

        <button
          type="button"
          onClick={handleBuscar}
          disabled={loading}
          className="w-full py-2.5 rounded-xl text-sm font-semibold text-white transition-all"
          style={{
            background: loading ? "var(--surface2)" : "var(--accent)",
            border: loading ? "1px solid var(--border)" : "none",
            color: loading ? "var(--muted)" : "#fff",
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading
            ? <span className="flex items-center justify-center gap-2">
                <span className="animate-spin">⟳</span>
                Buscando y analizando noticias…
              </span>
            : "🔭 Buscar noticias con potencial viral"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <p className="text-xs px-3 py-2 rounded-lg"
          style={{ background: "#2a1515", color: "var(--error)", border: "1px solid #5a2020" }}>
          {error}
        </p>
      )}

      {/* Resultados */}
      {buscado && noticias.length === 0 && (
        <p className="text-sm text-center py-6" style={{ color: "var(--muted)" }}>
          No se encontraron noticias. Intenta con otro tema o país.
        </p>
      )}

      {/* ── Noticias guardadas ──────────────────────────────────────────── */}
      {savedNews.length > 0 && (
        <div className="rounded-xl overflow-hidden"
          style={{ border: "1px solid #4ade8030", background: "var(--surface)" }}>

          {/* Header colapsable */}
          <button
            type="button"
            onClick={() => setShowSaved((v) => !v)}
            className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold"
            style={{ color: "#4ade80", background: "#0a1f0f" }}
          >
            <span>📋 Guardadas ({savedNews.length})</span>
            <span style={{ fontSize: "0.7rem", opacity: 0.7 }}>
              {showSaved ? "▲ ocultar" : "▼ ver todas"}
            </span>
          </button>

          {showSaved && (
            <>
              {/* Barra de selección */}
              <div className="flex items-center justify-between px-4 py-2 gap-2 flex-wrap"
                style={{ background: "#111827", borderBottom: "1px solid var(--border)" }}>
                <div className="flex items-center gap-2">
                  <button type="button" onClick={selectAll}
                    className="text-xs px-2 py-1 rounded"
                    style={{ color: "#4ade80", background: "#14532d30" }}>
                    ☑ Todas
                  </button>
                  <button type="button" onClick={clearSelect}
                    className="text-xs px-2 py-1 rounded"
                    style={{ color: "var(--muted)", background: "var(--surface2)" }}>
                    ☐ Ninguna
                  </button>
                  {selectedLinks.size > 0 && (
                    <span className="text-xs" style={{ color: "var(--muted)" }}>
                      {selectedLinks.size} seleccionada{selectedLinks.size > 1 ? "s" : ""}
                    </span>
                  )}
                </div>
                {/* Acciones de lote */}
                {selectedLinks.size > 0 && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => downloadDescriptions(savedNews.filter((n) => selectedLinks.has(n.link)))}
                      className="text-xs px-3 py-1.5 rounded-lg font-semibold"
                      style={{ background: "#1e3a5f", color: "#60a5fa", border: "1px solid #1d4ed840" }}
                    >
                      📄 Descargar descripciones ({selectedLinks.size})
                    </button>
                    <button
                      type="button"
                      onClick={iniciarBatch}
                      disabled={batchRunning}
                      className="text-xs px-3 py-1.5 rounded-lg font-semibold"
                      style={{
                        background: batchRunning ? "var(--surface2)" : "#7c3aed",
                        color: batchRunning ? "var(--muted)" : "#fff",
                        cursor: batchRunning ? "not-allowed" : "pointer",
                      }}
                    >
                      {batchRunning ? "⟳ Generando…" : `🎬 Generar ${selectedLinks.size} video${selectedLinks.size > 1 ? "s" : ""}`}
                    </button>
                  </div>
                )}
              </div>

              {/* Cola de progreso */}
              {batchQueue.length > 0 && (
                <div className="px-4 py-3 space-y-2"
                  style={{ background: "#0d1117", borderBottom: "1px solid var(--border)" }}>
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold" style={{ color: "#a78bfa" }}>
                      🎬 Progreso del lote
                    </p>
                    <p className="text-xs" style={{ color: "var(--muted)" }}>
                      {batchQueue.filter((i) => i.status === "done").length} / {batchQueue.length} completados
                    </p>
                  </div>
                  {/* Barra de progreso */}
                  <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: "var(--border)" }}>
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${(batchQueue.filter((i) => i.status === "done").length / batchQueue.length) * 100}%`,
                        background: "#7c3aed",
                      }}
                    />
                  </div>
                  {/* Filas de estado */}
                  {batchQueue.map((item, i) => {
                    const icon = { pending: "⏳", running: "🔄", done: "✅", error: "❌" }[item.status];
                    const color = { pending: "var(--muted)", running: "#a78bfa", done: "#4ade80", error: "#f87171" }[item.status];
                    const label = { pending: "En cola", running: "Generando…", done: "Completado", error: "Error" }[item.status];
                    return (
                      <div key={i} className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className={item.status === "running" ? "animate-spin inline-block" : ""}>{icon}</span>
                          <span className="flex-1 text-xs truncate" style={{ color: "var(--text)" }}>
                            {item.article.titulo}
                          </span>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <span className="text-xs" style={{ color }}>{label}</span>
                            {item.status === "error" && !batchRunning && (
                              <button
                                type="button"
                                onClick={() => reintentarItem(i)}
                                className="text-xs px-2 py-0.5 rounded"
                                style={{ background: "#7c3aed30", color: "#a78bfa", border: "1px solid #7c3aed40" }}
                              >
                                ↺ Reintentar
                              </button>
                            )}
                          </div>
                        </div>
                        {/* Mensaje de error */}
                        {item.status === "error" && item.errorMsg && (
                          <p className="text-xs pl-6 leading-snug" style={{ color: "#fca5a5" }}>
                            {item.errorMsg}
                          </p>
                        )}
                      </div>
                    );
                  })}
                  {/* Al terminar: descargar todas las descripciones */}
                  {!batchRunning && batchQueue.length > 0 && (
                    <button
                      type="button"
                      onClick={() => downloadDescriptions(batchQueue.map((i) => i.article))}
                      className="w-full mt-1 py-2 rounded-lg text-xs font-semibold"
                      style={{ background: "#1e3a5f", color: "#60a5fa", border: "1px solid #1d4ed840" }}
                    >
                      📄 Descargar todas las descripciones para YouTube Studio
                    </button>
                  )}
                </div>
              )}

              {/* Lista de artículos guardados */}
              <div className="divide-y" style={{ borderColor: "var(--border)" }}>
                {savedNews.map((n, i) => {
                  const sl = scoreLabel(n.score);
                  const rec = recenciaLabel(n.recencia);
                  const cat = CATEGORIAS[n.categoria] ?? "📰";
                  const selected = selectedLinks.has(n.link);
                  return (
                    <div key={i} className="px-4 py-3 flex items-start gap-3"
                      style={{ background: selected ? "#1a1040" : "transparent" }}>
                      {/* Checkbox */}
                      <button
                        type="button"
                        onClick={() => toggleSelect(n.link)}
                        className="mt-0.5 shrink-0 w-4 h-4 rounded flex items-center justify-center text-xs font-bold"
                        style={{
                          background: selected ? "#7c3aed" : "var(--surface2)",
                          border: `1px solid ${selected ? "#7c3aed" : "var(--border)"}`,
                          color: "#fff",
                        }}
                      >
                        {selected ? "✓" : ""}
                      </button>
                      {/* Info */}
                      <div className="flex-1 min-w-0 space-y-1">
                        <p className="text-xs font-medium leading-snug truncate" style={{ color: "var(--text)" }}>
                          {n.titulo}
                        </p>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs px-1.5 py-0.5 rounded-full"
                            style={{ background: sl.bg, color: sl.color }}>
                            {sl.emoji} {n.score}
                          </span>
                          {rec && (
                            <span className="text-xs px-1.5 py-0.5 rounded-full"
                              style={{ background: rec.bg, color: rec.color }}>
                              {rec.icon} {rec.label}
                            </span>
                          )}
                          <span className="text-xs" style={{ color: "var(--muted)" }}>
                            {cat} {n.fuente && `· ${n.fuente}`}
                          </span>
                        </div>
                      </div>
                      {/* Acciones */}
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => onUsar(n)}
                          className="px-2.5 py-1 rounded-lg text-xs font-semibold"
                          style={{ background: "var(--accent)", color: "#fff" }}
                        >
                          Usar →
                        </button>
                        <button
                          type="button"
                          onClick={() => eliminarGuardada(n.link)}
                          title="Eliminar de guardadas"
                          className="px-2 py-1 rounded-lg text-xs"
                          style={{ background: "var(--surface2)", color: "var(--muted)", border: "1px solid var(--border)" }}
                        >
                          🗑️
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      )}

      {noticias.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs" style={{ color: "var(--muted)" }}>
            {noticias.length} propuestas ordenadas por potencial viral — haz clic en &quot;Usar&quot; o &quot;💾&quot; para guardar
          </p>
          {noticias.map((n, i) => {
            const sl = scoreLabel(n.score);
            const cat = CATEGORIAS[n.categoria] ?? "📰";
            const rec = recenciaLabel(n.recencia);
            return (
              <div
                key={i}
                className="rounded-xl p-4 space-y-2"
                style={{ background: "var(--surface)", border: `1px solid ${n.recencia?.muy_reciente && rec ? rec.color : sl.color}30` }}
              >
                {/* Header */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                      style={{ background: sl.bg, color: sl.color, border: `1px solid ${sl.color}40` }}>
                      {sl.emoji} {n.score} — {sl.label}
                    </span>
                    {rec && (
                      <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
                        style={{ background: rec.bg, color: rec.color, border: `1px solid ${rec.color}50` }}>
                        {rec.icon} {rec.label}
                      </span>
                    )}
                    <span className="text-xs px-2 py-0.5 rounded-full"
                      style={{ background: "var(--surface2)", color: "var(--muted)" }}>
                      {cat} {n.categoria}
                    </span>
                    {n.fuente && (
                      <span className="text-xs flex items-center gap-1" style={{ color: "var(--muted)" }}>
                        {n.fuente_verificada && <span style={{ color: "#4ade80" }}>✓</span>}
                        {n.fuente}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => toggleGuardar(n)}
                      title={isGuardada(n.link) ? "Quitar de guardadas" : "Guardar para más tarde"}
                      className="px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all"
                      style={{
                        background: isGuardada(n.link) ? "#14532d" : "var(--surface2)",
                        color: isGuardada(n.link) ? "#4ade80" : "var(--muted)",
                        border: `1px solid ${isGuardada(n.link) ? "#4ade8040" : "var(--border)"}`,
                      }}
                    >
                      {isGuardada(n.link) ? "✓ Guardada" : "💾"}
                    </button>
                    <button
                      type="button"
                      onClick={() => onUsar(n)}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                      style={{ background: "var(--accent)", color: "#fff" }}
                    >
                      Usar →
                    </button>
                  </div>
                </div>

                {/* Título */}
                <p className="text-sm font-medium leading-snug" style={{ color: "var(--text)" }}>
                  {n.titulo}
                </p>

                {/* Gancho + audiencia */}
                {n.gancho && (
                  <p className="text-xs" style={{ color: "#a78bfa" }}>
                    💡 {n.gancho}
                  </p>
                )}
                {n.audiencia && (
                  <p className="text-xs" style={{ color: "var(--muted)" }}>
                    👥 {n.audiencia}
                  </p>
                )}

                {/* Resumen colapsable si hay */}
                {n.resumen && (
                  <p className="text-xs line-clamp-2" style={{ color: "var(--muted)" }}>
                    {n.resumen}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
