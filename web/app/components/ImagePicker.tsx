"use client";

import { useRef, useState } from "react";

export interface ImageConfig {
  mode: "none" | "article" | "upload" | "ai";
  uploadedPaths: string[];
  generateAi: boolean;
  servicioAi: string;
}

interface Props {
  value: ImageConfig;
  onChange: (v: ImageConfig) => void;
  hasArticleUrl: boolean;
  tituloParaAi?: string;
}

const MODES = [
  { id: "none",    label: "Automático",       icon: "✨" },
  { id: "article", label: "Del artículo",     icon: "🌐" },
  { id: "upload",  label: "Subir imágenes",   icon: "📁" },
  { id: "ai",      label: "Generar con IA",   icon: "🤖" },
] as const;

export default function ImagePicker({ value, onChange, hasArticleUrl, tituloParaAi }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [previewAi, setPreviewAi] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [uploadedNames, setUploadedNames] = useState<string[]>([]);

  function setMode(mode: ImageConfig["mode"]) {
    onChange({ ...value, mode, generateAi: mode === "ai" });
  }

  async function handleFileUpload(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      const form = new FormData();
      Array.from(files).forEach((f) => form.append("files", f));
      const res = await fetch("/api/upload", { method: "POST", body: form });
      const data = await res.json();
      const names = Array.from(files).map((f) => f.name);
      setUploadedNames(names);
      onChange({ ...value, mode: "upload", uploadedPaths: data.rutas, generateAi: false });
    } catch {
      alert("Error subiendo imágenes");
    } finally {
      setUploading(false);
    }
  }

  async function handlePreviewAi() {
    if (!tituloParaAi) return;
    setLoadingPreview(true);
    try {
      const res = await fetch(`/api/preview-image?prompt=${encodeURIComponent(tituloParaAi)}&seed=42`);
      const data = await res.json();
      setPreviewAi(data.url);
    } catch {
      /* ignore */
    } finally {
      setLoadingPreview(false);
    }
  }

  return (
    <div className="space-y-3">
      {/* Mode tabs */}
      <div className="flex gap-2 flex-wrap">
        {MODES.map((m) => {
          const disabled = m.id === "article" && !hasArticleUrl;
          return (
            <button
              key={m.id}
              type="button"
              disabled={disabled}
              onClick={() => setMode(m.id as ImageConfig["mode"])}
              className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
              style={{
                background: value.mode === m.id ? "var(--accent)" : "var(--surface2)",
                color: value.mode === m.id ? "#fff" : disabled ? "#444" : "var(--muted)",
                border: `1px solid ${value.mode === m.id ? "var(--accent)" : "var(--border)"}`,
                cursor: disabled ? "not-allowed" : "pointer",
                opacity: disabled ? 0.4 : 1,
              }}
            >
              {m.icon} {m.label}
            </button>
          );
        })}
      </div>

      {/* Upload */}
      {value.mode === "upload" && (
        <div>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => handleFileUpload(e.target.files)}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="w-full py-2 rounded-lg text-sm border-2 border-dashed transition-all"
            style={{
              borderColor: "var(--border)",
              color: "var(--muted)",
              background: "var(--bg)",
            }}
          >
            {uploading ? "Subiendo..." : "Haz clic para seleccionar imágenes"}
          </button>
          {uploadedNames.length > 0 && (
            <div className="mt-2 space-y-1">
              {uploadedNames.map((n, i) => (
                <p key={i} className="text-xs" style={{ color: "var(--success)" }}>
                  ✓ {n}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* AI generation */}
      {value.mode === "ai" && (
        <div className="space-y-2">
          <div className="flex gap-2 items-center">
            <select
              value={value.servicioAi}
              onChange={(e) => onChange({ ...value, servicioAi: e.target.value })}
              className="flex-1 rounded-lg px-3 py-2 text-sm"
              style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)" }}
            >
              <option value="pollinations">Pollinations.ai — IA generativa (gratis)</option>
              <option value="pexels">Pexels — fotos reales (PEXELS_API_KEY)</option>
              <option value="unsplash">Unsplash — fotos reales (UNSPLASH_ACCESS_KEY)</option>
              <option value="pixabay">Pixabay — fotos reales (PIXABAY_API_KEY)</option>
            </select>
            <button
              type="button"
              onClick={handlePreviewAi}
              disabled={loadingPreview || !tituloParaAi}
              className="px-3 py-2 rounded-lg text-xs whitespace-nowrap"
              style={{
                background: "var(--surface2)",
                color: "var(--muted)",
                border: "1px solid var(--border)",
                opacity: !tituloParaAi ? 0.5 : 1,
              }}
            >
              {loadingPreview ? "..." : "Ver preview"}
            </button>
          </div>

          {previewAi && (
            <div className="rounded-xl overflow-hidden" style={{ maxHeight: 200 }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={previewAi}
                alt="Preview IA"
                className="w-full object-cover"
                style={{ maxHeight: 200, objectPosition: "center top" }}
              />
              <p className="text-xs px-2 py-1" style={{ color: "var(--muted)", background: "var(--surface2)" }}>
                Preview de imagen generada. En el video se generarán 3 imágenes similares.
              </p>
            </div>
          )}

          <p className="text-xs" style={{ color: "var(--muted)" }}>
            Se generarán 3 imágenes con keywords extraídas del artículo.
            En modo Pollinations no se necesita API key.
          </p>
        </div>
      )}

      {value.mode === "none" && (
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          Busca fotos reales (Pexels/Unsplash/Pixabay si hay API key) o genera con Pollinations.ai
          usando keywords del artículo. Sin configuración adicional.
        </p>
      )}

      {value.mode === "article" && (
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          Extrae las imágenes del artículo. Si no hay suficientes, busca fotos relacionadas automáticamente.
        </p>
      )}
    </div>
  );
}
