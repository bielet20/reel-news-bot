"use client";

import { useEffect, useRef, useState } from "react";

export interface VoiceConfig {
  servicio: "auto" | "elevenlabs" | "edge-tts";
  voz: string | null;
}

interface TtsStatus {
  edge_tts: boolean;
  elevenlabs: boolean;
}

interface Voice {
  id: string;
  name: string;
  labels?: Record<string, string>;
}

interface Props {
  value: VoiceConfig;
  onChange: (v: VoiceConfig) => void;
}

const TEXTO_PREVIEW_DEFAULT = "Hola, esta es una prueba de voz para el reel. ¿Qué te parece cómo suena?";

export default function VoicePicker({ value, onChange }: Props) {
  const [status, setStatus] = useState<TtsStatus | null>(null);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [loadingVoices, setLoadingVoices] = useState(false);
  const [previewText, setPreviewText] = useState(TEXTO_PREVIEW_DEFAULT);
  const [previewState, setPreviewState] = useState<"idle" | "loading" | "playing">("idle");
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    fetch("/api/tts/status")
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => {});
  }, []);

  const servicioActivo =
    value.servicio === "auto"
      ? status?.elevenlabs ? "elevenlabs" : "edge-tts"
      : value.servicio;

  useEffect(() => {
    setLoadingVoices(true);
    setVoices([]);
    fetch(`/api/tts/voices?servicio=${servicioActivo}`)
      .then((r) => r.json())
      .then((d) => setVoices(d.voices ?? []))
      .catch(() => {})
      .finally(() => setLoadingVoices(false));
  }, [servicioActivo]);

  function handleServicioChange(s: VoiceConfig["servicio"]) {
    stopPreview();
    onChange({ servicio: s, voz: null });
  }

  function stopPreview() {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
    setPreviewState("idle");
  }

  async function handlePreview() {
    if (previewState === "playing") {
      stopPreview();
      return;
    }

    setPreviewState("loading");
    try {
      const res = await fetch("/api/tts/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servicio: value.servicio,
          voz: value.voz ?? null,
          texto: previewText || TEXTO_PREVIEW_DEFAULT,
        }),
      });
      if (!res.ok) throw new Error(await res.text());

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;

      audio.onended = () => {
        URL.revokeObjectURL(url);
        setPreviewState("idle");
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        setPreviewState("idle");
      };

      await audio.play();
      setPreviewState("playing");
    } catch (err) {
      console.error("Preview error:", err);
      setPreviewState("idle");
    }
  }

  // Stop audio if voice changes
  useEffect(() => {
    stopPreview();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.voz, value.servicio]);

  const elevenLabsOk = status?.elevenlabs ?? false;

  return (
    <div className="space-y-3">
      {/* Servicio */}
      <div className="flex gap-2 flex-wrap">
        {(["auto", "edge-tts", "elevenlabs"] as const).map((s) => {
          const labels: Record<string, string> = {
            "auto":       "Auto",
            "edge-tts":   "Edge TTS (gratis)",
            "elevenlabs": "ElevenLabs",
          };
          const disabled = s === "elevenlabs" && !elevenLabsOk;
          const active = value.servicio === s;
          return (
            <button
              key={s}
              type="button"
              disabled={disabled}
              onClick={() => handleServicioChange(s)}
              title={disabled ? "Añade ELEVENLABS_API_KEY al .env para activar" : undefined}
              className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
              style={{
                background: active ? "var(--accent)" : "var(--surface2)",
                color: active ? "#fff" : disabled ? "#555" : "var(--muted)",
                border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                cursor: disabled ? "not-allowed" : "pointer",
                opacity: disabled ? 0.5 : 1,
              }}
            >
              {s === "elevenlabs" ? "⭐ " : ""}{labels[s]}
            </button>
          );
        })}
      </div>

      {/* ElevenLabs sin key */}
      {value.servicio === "elevenlabs" && !elevenLabsOk && (
        <div className="rounded-lg p-3 text-xs"
          style={{ background: "#1a1208", border: "1px solid #4a3010", color: "#c8a060" }}>
          <p className="font-medium mb-1">ElevenLabs no configurado</p>
          <p>Añade <code>ELEVENLABS_API_KEY=tu_key</code> al <code>.env</code> y reinicia el servidor.</p>
        </div>
      )}

      {/* Selector de voz */}
      {voices.length > 0 && (
        <div>
          <label className="text-xs mb-1 block" style={{ color: "var(--muted)" }}>
            {servicioActivo === "elevenlabs" ? "Voz ElevenLabs" : "Voz edge-tts"}
          </label>
          <select
            value={value.voz ?? ""}
            onChange={(e) => onChange({ ...value, voz: e.target.value || null })}
            className="w-full rounded-lg px-3 py-2 text-sm"
            style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)" }}
          >
            <option value="">
              {servicioActivo === "elevenlabs" ? "Adam (predeterminado)" : "Álvaro ES (predeterminado)"}
            </option>
            {voices.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
                {v.labels?.language ? ` — ${v.labels.language}` : ""}
                {v.labels?.gender ? ` (${v.labels.gender})` : ""}
              </option>
            ))}
          </select>
        </div>
      )}

      {loadingVoices && (
        <p className="text-xs" style={{ color: "var(--muted)" }}>Cargando voces…</p>
      )}

      {/* Preview */}
      <div className="space-y-2">
        <label className="text-xs block" style={{ color: "var(--muted)" }}>
          Texto de prueba
        </label>
        <textarea
          value={previewText}
          onChange={(e) => setPreviewText(e.target.value)}
          rows={2}
          className="w-full rounded-lg px-3 py-2 text-sm resize-none"
          style={{
            background: "var(--bg)",
            border: "1px solid var(--border)",
            color: "var(--text)",
            outline: "none",
          }}
        />
        <button
          type="button"
          onClick={handlePreview}
          disabled={previewState === "loading"}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
          style={{
            background: previewState === "playing" ? "#1a2a1a" : "var(--surface2)",
            color: previewState === "playing" ? "var(--success)" : "var(--text)",
            border: `1px solid ${previewState === "playing" ? "var(--success)" : "var(--border)"}`,
            cursor: previewState === "loading" ? "not-allowed" : "pointer",
            opacity: previewState === "loading" ? 0.6 : 1,
          }}
        >
          {previewState === "loading" && <span className="animate-spin">⟳</span>}
          {previewState === "playing" && <span>■</span>}
          {previewState === "idle" && <span>▶</span>}
          {previewState === "loading"
            ? "Generando audio…"
            : previewState === "playing"
            ? "Detener"
            : "Escuchar voz"}
        </button>
      </div>

      {/* Info */}
      <p className="text-xs" style={{ color: "var(--muted)" }}>
        {value.servicio === "auto"
          ? elevenLabsOk
            ? "Auto: usando ElevenLabs (API key detectada)"
            : "Auto: usando edge-tts. Añade ELEVENLABS_API_KEY para voces premium."
          : value.servicio === "elevenlabs" && elevenLabsOk
          ? "Esta voz se usa también para el lip sync del avatar."
          : "Esta voz se usa también para el lip sync del avatar."}
      </p>
    </div>
  );
}
