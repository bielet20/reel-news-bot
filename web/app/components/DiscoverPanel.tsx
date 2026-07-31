"use client";

import { useState } from "react";

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
}

interface Props {
  onUsar: (noticia: NoticiaProuesta) => void;
}


const PAISES = [
  { value: "ES", label: "🇪🇸 España" },
  { value: "AR", label: "🇦🇷 Argentina" },
  { value: "MX", label: "🇲🇽 México" },
  { value: "CO", label: "🇨🇴 Colombia" },
  { value: "US", label: "🇺🇸 EE.UU." },
  { value: "CL", label: "🇨🇱 Chile" },
  { value: "PE", label: "🇵🇪 Perú" },
  { value: "VE", label: "🇻🇪 Venezuela" },
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

function scoreLabel(score: number): { emoji: string; label: string; color: string; bg: string } {
  if (score >= 9)   return { emoji: "🔥🔥🔥", label: "Viral",   color: "#f97316", bg: "#2a1000" };
  if (score >= 7.5) return { emoji: "🔥🔥",   label: "Alto",    color: "#fb923c", bg: "#231208" };
  if (score >= 6)   return { emoji: "🔥",     label: "Bueno",   color: "#fbbf24", bg: "#231a08" };
  return                   { emoji: "📰",     label: "Normal",  color: "#94a3b8", bg: "#141820" };
}

export default function DiscoverPanel({ onUsar }: Props) {
  const [pais, setPais] = useState("ES");
  const [tema, setTema] = useState("");
  const [variado, setVariado] = useState(true);
  const [loading, setLoading] = useState(false);
  const [noticias, setNoticias] = useState<NoticiaProuesta[]>([]);
  const [error, setError] = useState("");
  const [buscado, setBuscado] = useState(false);

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
          {/* País */}
          <div className="flex-1 min-w-[140px]">
            <label className="text-xs block mb-1" style={{ color: "var(--muted)" }}>País / Región</label>
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

      {noticias.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs" style={{ color: "var(--muted)" }}>
            {noticias.length} propuestas ordenadas por potencial viral — haz clic en &quot;Usar&quot; para generar el reel
          </p>
          {noticias.map((n, i) => {
            const sl = scoreLabel(n.score);
            const cat = CATEGORIAS[n.categoria] ?? "📰";
            return (
              <div
                key={i}
                className="rounded-xl p-4 space-y-2"
                style={{ background: "var(--surface)", border: `1px solid ${sl.color}30` }}
              >
                {/* Header */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                      style={{ background: sl.bg, color: sl.color, border: `1px solid ${sl.color}40` }}>
                      {sl.emoji} {n.score} — {sl.label}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full"
                      style={{ background: "var(--surface2)", color: "var(--muted)" }}>
                      {cat} {n.categoria}
                    </span>
                    {n.fuente && (
                      <span className="text-xs" style={{ color: "var(--muted)" }}>{n.fuente}</span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => onUsar(n)}
                    className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                    style={{ background: "var(--accent)", color: "#fff" }}
                  >
                    Usar →
                  </button>
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
