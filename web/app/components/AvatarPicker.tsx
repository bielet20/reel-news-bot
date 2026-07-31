"use client";

import { useEffect, useRef, useState } from "react";

export interface AvatarConfig {
  enabled: boolean;
  imagePath: string | null;
  previewUrl: string | null;
  servicio: "auto" | "sadtalker" | "did";
}

interface AvatarStatus {
  sadtalker: boolean;
  did: boolean;
}

interface Props {
  value: AvatarConfig;
  onChange: (v: AvatarConfig) => void;
}

export default function AvatarPicker({ value, onChange }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState<AvatarStatus | null>(null);

  useEffect(() => {
    fetch("/api/avatar/status")
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => {});
  }, []);

  async function handleFile(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("files", files[0]);
      const res = await fetch("/api/upload", { method: "POST", body: form });
      const data = await res.json();
      const ruta = data.rutas?.[0] ?? null;
      const preview = ruta ? URL.createObjectURL(files[0]) : null;
      onChange({ ...value, enabled: true, imagePath: ruta, previewUrl: preview });
    } catch {
      alert("Error subiendo imagen");
    } finally {
      setUploading(false);
    }
  }

  const sadtalkerOk = status?.sadtalker ?? false;
  const didOk = status?.did ?? false;
  const ningunServicio = !sadtalkerOk && !didOk;

  return (
    <div className="space-y-3">
      {/* Toggle */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onChange({ ...value, enabled: !value.enabled })}
          className="relative w-10 h-5 rounded-full transition-colors"
          style={{ background: value.enabled ? "var(--accent)" : "var(--border)" }}
        >
          <span
            className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all"
            style={{ left: value.enabled ? "calc(100% - 18px)" : "2px" }}
          />
        </button>
        <span className="text-sm" style={{ color: "var(--text)" }}>
          Avatar hablando (lip sync)
        </span>
      </div>

      {value.enabled && (
        <div className="space-y-3 pl-1">
          {/* Status chips */}
          <div className="flex gap-2 flex-wrap">
            <span className="text-xs px-2 py-1 rounded-full" style={{
              background: sadtalkerOk ? "#0a2a1a" : "#1a1010",
              color: sadtalkerOk ? "var(--success)" : "#666",
              border: `1px solid ${sadtalkerOk ? "var(--success)" : "#333"}`,
            }}>
              {sadtalkerOk ? "✓" : "✗"} SadTalker (local)
            </span>
            <span className="text-xs px-2 py-1 rounded-full" style={{
              background: didOk ? "#0a2a1a" : "#1a1010",
              color: didOk ? "var(--success)" : "#666",
              border: `1px solid ${didOk ? "var(--success)" : "#333"}`,
            }}>
              {didOk ? "✓" : "✗"} D-ID (cloud)
            </span>
          </div>

          {ningunServicio && (
            <div className="rounded-lg p-3 text-xs space-y-1"
              style={{ background: "#1a1208", border: "1px solid #4a3010", color: "#c8a060" }}>
              <p className="font-medium">Ningún servicio de avatar configurado</p>
              <p>• <strong>SadTalker</strong> (local, gratis): <code>bash setup_sadtalker.sh</code></p>
              <p>• <strong>D-ID</strong> (cloud, plan gratis): añade <code>DID_API_KEY=tu_key</code> al .env</p>
            </div>
          )}

          {/* Servicio selector */}
          {(sadtalkerOk || didOk) && (
            <div>
              <label className="text-xs mb-1 block" style={{ color: "var(--muted)" }}>Servicio</label>
              <select
                value={value.servicio}
                onChange={(e) => onChange({ ...value, servicio: e.target.value as AvatarConfig["servicio"] })}
                className="w-full rounded-lg px-3 py-2 text-sm"
                style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)" }}
              >
                <option value="auto">Auto (D-ID si hay key, si no SadTalker)</option>
                {sadtalkerOk && <option value="sadtalker">SadTalker — local, gratis</option>}
                {didOk && <option value="did">D-ID — cloud, más rápido</option>}
              </select>
            </div>
          )}

          {/* Imagen del avatar */}
          <div>
            <label className="text-xs mb-1 block" style={{ color: "var(--muted)" }}>
              Foto del avatar (cara frontal)
            </label>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => handleFile(e.target.files)}
            />
            <div className="flex gap-3 items-start">
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                className="flex-1 py-2 rounded-lg text-sm border-2 border-dashed"
                style={{ borderColor: "var(--border)", color: "var(--muted)", background: "var(--bg)" }}
              >
                {uploading ? "Subiendo..." : value.imagePath ? "Cambiar foto" : "📷 Subir foto del avatar"}
              </button>
              {value.previewUrl && (
                <div className="w-16 h-16 rounded-full overflow-hidden shrink-0"
                  style={{ border: "2px solid var(--accent)" }}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={value.previewUrl} alt="Avatar preview"
                    className="w-full h-full object-cover" />
                </div>
              )}
            </div>
          </div>

          {value.imagePath && !sadtalkerOk && !didOk && (
            <p className="text-xs" style={{ color: "var(--error)" }}>
              Foto cargada pero no hay servicio disponible para generar el lip sync.
            </p>
          )}

          {value.imagePath && (sadtalkerOk || didOk) && (
            <p className="text-xs" style={{ color: "var(--success)" }}>
              ✓ Listo. El avatar aparecerá en la parte inferior del reel hablando sincronizado.
              {value.servicio === "sadtalker" || (value.servicio === "auto" && !didOk)
                ? " SadTalker puede tardar 5-10 min en CPU."
                : " D-ID suele tardar ~1 min."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
