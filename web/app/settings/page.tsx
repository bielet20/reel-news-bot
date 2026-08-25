"use client";

import { useEffect, useState } from "react";

type DestType = "local" | "drive" | "smb";

interface Destination {
  name: string;
  type: DestType;
  path?: string;
  rclone_remote?: string;
  enabled: boolean;
}

interface StorageConfig {
  destinations: Destination[];
}

const TYPE_LABELS: Record<DestType, string> = {
  local: "Local",
  drive: "Google Drive (rclone)",
  smb: "Red SMB (rclone)",
};

const TYPE_PLACEHOLDERS: Record<DestType, string> = {
  local: "/Users/tu/Descargas/Reels",
  drive: "gdrive:Reels",
  smb: "nas:Videos/Reels",
};

const EMPTY_DEST: Destination = {
  name: "",
  type: "local",
  path: "",
  rclone_remote: "",
  enabled: true,
};

export default function SettingsPage() {
  const [config, setConfig] = useState<StorageConfig>({ destinations: [] });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<Destination>({ ...EMPTY_DEST });
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "error" } | null>(null);

  const showToast = (msg: string, type: "ok" | "error") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  async function fetchConfig() {
    try {
      const res = await fetch("/api/storage/config");
      if (res.ok) setConfig(await res.json());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchConfig();
  }, []);

  async function saveConfig(cfg: StorageConfig) {
    setSaving(true);
    try {
      const res = await fetch("/api/storage/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cfg),
      });
      if (!res.ok) throw new Error("Error al guardar");
      showToast("Configuración guardada", "ok");
    } catch {
      showToast("Error al guardar la configuración", "error");
    } finally {
      setSaving(false);
    }
  }

  function handleAddDestination() {
    if (!form.name.trim()) {
      showToast("El nombre del destino es requerido", "error");
      return;
    }
    const dest: Destination = {
      name: form.name.trim(),
      type: form.type,
      enabled: form.enabled,
    };
    if (form.type === "local") {
      dest.path = form.path?.trim() || "";
    } else {
      dest.rclone_remote = form.rclone_remote?.trim() || "";
    }
    const updated = { destinations: [...config.destinations, dest] };
    setConfig(updated);
    saveConfig(updated);
    setShowModal(false);
    setForm({ ...EMPTY_DEST });
  }

  function handleToggle(index: number) {
    const updated = {
      destinations: config.destinations.map((d, i) =>
        i === index ? { ...d, enabled: !d.enabled } : d
      ),
    };
    setConfig(updated);
    saveConfig(updated);
  }

  function handleDelete(index: number) {
    const updated = {
      destinations: config.destinations.filter((_, i) => i !== index),
    };
    setConfig(updated);
    saveConfig(updated);
  }

  const fieldLabel = form.type === "local" ? "Ruta" : "Remote rclone";
  const fieldValue = form.type === "local" ? form.path || "" : form.rclone_remote || "";
  const fieldKey = form.type === "local" ? "path" : "rclone_remote";

  return (
    <main className="min-h-screen px-4 py-10">
      <div className="max-w-2xl mx-auto">
        {/* Toast */}
        {toast && (
          <div style={{
            position: "fixed", top: 60, right: 20, zIndex: 9999,
            background: toast.type === "ok" ? "#0a2a1a" : "#2a0a0a",
            border: `1px solid ${toast.type === "ok" ? "var(--success)" : "var(--error)"}`,
            color: toast.type === "ok" ? "var(--success)" : "var(--error)",
            borderRadius: 10, padding: "10px 16px", fontSize: 13, fontWeight: 600,
            maxWidth: 380, boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
          }}>
            {toast.msg}
          </div>
        )}

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 28 }}>
          <div>
            <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--text)" }}>Settings</h1>
            <p style={{ color: "var(--muted)", fontSize: 14 }}>
              Destinos de almacenamiento — copia automática de cada video generado.
            </p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            style={{
              padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 700,
              background: "var(--accent)", border: "none",
              color: "#fff", cursor: "pointer",
            }}
          >
            + Añadir destino
          </button>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: 40, color: "var(--muted)" }}>Cargando…</div>
        ) : config.destinations.length === 0 ? (
          <div style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 16,
            padding: "40px 20px",
            textAlign: "center",
            color: "var(--muted)",
            fontSize: 14,
          }}>
            Sin destinos configurados. Pulsa &ldquo;+ Añadir destino&rdquo; para empezar.
          </div>
        ) : (
          <div className="space-y-3">
            {config.destinations.map((dest, i) => (
              <div key={i} style={{
                background: "var(--surface)",
                border: `1px solid ${dest.enabled ? "var(--border)" : "var(--border)"}`,
                borderRadius: 14,
                padding: "14px 18px",
                display: "flex",
                alignItems: "center",
                gap: 14,
                opacity: dest.enabled ? 1 : 0.55,
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontWeight: 600, fontSize: 14, margin: 0, color: "var(--text)" }}>
                    {dest.name}
                  </p>
                  <p style={{ fontSize: 11, color: "var(--muted)", margin: "3px 0 0" }}>
                    {TYPE_LABELS[dest.type]} &mdash;{" "}
                    <code style={{ fontSize: 10, background: "var(--bg)", borderRadius: 3, padding: "1px 4px" }}>
                      {dest.type === "local" ? dest.path : dest.rclone_remote}
                    </code>
                  </p>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
                  {/* Toggle */}
                  <button
                    onClick={() => handleToggle(i)}
                    title={dest.enabled ? "Desactivar" : "Activar"}
                    style={{
                      width: 36, height: 20, borderRadius: 10,
                      background: dest.enabled ? "var(--success)" : "var(--border)",
                      border: "none", cursor: "pointer",
                      position: "relative", transition: "background 0.2s",
                    }}
                  >
                    <span style={{
                      position: "absolute", top: 3,
                      left: dest.enabled ? 18 : 3,
                      width: 14, height: 14, borderRadius: "50%",
                      background: "#fff", transition: "left 0.2s",
                    }} />
                  </button>
                  {/* Delete */}
                  <button
                    onClick={() => handleDelete(i)}
                    style={{
                      padding: "5px 10px", borderRadius: 7, fontSize: 12,
                      background: "#2a0a0a", border: "1px solid var(--error)40",
                      color: "var(--error)", cursor: "pointer",
                    }}
                  >
                    Eliminar
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Info box */}
        <div style={{
          marginTop: 24,
          background: "var(--surface2)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          padding: "14px 18px",
        }}>
          <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>
            <strong style={{ color: "var(--text)" }}>Drive / SMB</strong> requieren{" "}
            <code style={{ fontSize: 11, background: "var(--bg)", borderRadius: 4, padding: "1px 5px" }}>rclone</code>{" "}
            instalado y configurado. Usa{" "}
            <code style={{ fontSize: 11, background: "var(--bg)", borderRadius: 4, padding: "1px 5px" }}>rclone config</code>{" "}
            para añadir tus remotos antes de activar estos destinos.
          </p>
        </div>

        {saving && (
          <p style={{ fontSize: 12, color: "var(--muted)", textAlign: "center", marginTop: 12 }}>
            Guardando…
          </p>
        )}
      </div>

      {/* Modal */}
      {showModal && (
        <div
          onClick={(e) => { if (e.target === e.currentTarget) setShowModal(false); }}
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
            zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center",
            padding: 16,
          }}
        >
          <div style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 16,
            padding: 24,
            width: "100%",
            maxWidth: 440,
          }}>
            <h2 style={{ fontSize: 17, fontWeight: 700, color: "var(--text)", margin: "0 0 18px" }}>
              Nuevo destino
            </h2>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 4 }}>
                  Nombre
                </label>
                <input
                  type="text"
                  placeholder="Mi NAS, Descargas, Drive principal…"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  style={{
                    width: "100%", padding: "8px 12px", borderRadius: 8, fontSize: 13,
                    background: "var(--bg)", border: "1px solid var(--border)",
                    color: "var(--text)", outline: "none", boxSizing: "border-box",
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 4 }}>
                  Tipo
                </label>
                <select
                  value={form.type}
                  onChange={(e) => setForm({ ...form, type: e.target.value as DestType, path: "", rclone_remote: "" })}
                  style={{
                    width: "100%", padding: "8px 12px", borderRadius: 8, fontSize: 13,
                    background: "var(--bg)", border: "1px solid var(--border)",
                    color: "var(--text)", outline: "none", boxSizing: "border-box",
                  }}
                >
                  {(Object.entries(TYPE_LABELS) as [DestType, string][]).map(([val, label]) => (
                    <option key={val} value={val}>{label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 4 }}>
                  {fieldLabel}
                </label>
                <input
                  type="text"
                  placeholder={TYPE_PLACEHOLDERS[form.type]}
                  value={fieldValue}
                  onChange={(e) => setForm({ ...form, [fieldKey]: e.target.value })}
                  style={{
                    width: "100%", padding: "8px 12px", borderRadius: 8, fontSize: 13,
                    background: "var(--bg)", border: "1px solid var(--border)",
                    color: "var(--text)", outline: "none", boxSizing: "border-box",
                  }}
                />
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <button
                  onClick={() => setForm({ ...form, enabled: !form.enabled })}
                  style={{
                    width: 36, height: 20, borderRadius: 10,
                    background: form.enabled ? "var(--success)" : "var(--border)",
                    border: "none", cursor: "pointer",
                    position: "relative", flexShrink: 0,
                  }}
                >
                  <span style={{
                    position: "absolute", top: 3,
                    left: form.enabled ? 18 : 3,
                    width: 14, height: 14, borderRadius: "50%",
                    background: "#fff", transition: "left 0.2s",
                  }} />
                </button>
                <span style={{ fontSize: 13, color: "var(--text)" }}>
                  {form.enabled ? "Activo" : "Inactivo"}
                </span>
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 20, justifyContent: "flex-end" }}>
              <button
                onClick={() => { setShowModal(false); setForm({ ...EMPTY_DEST }); }}
                style={{
                  padding: "8px 16px", borderRadius: 8, fontSize: 13,
                  background: "var(--surface2)", border: "1px solid var(--border)",
                  color: "var(--muted)", cursor: "pointer",
                }}
              >
                Cancelar
              </button>
              <button
                onClick={handleAddDestination}
                style={{
                  padding: "8px 18px", borderRadius: 8, fontSize: 13, fontWeight: 700,
                  background: "var(--accent)", border: "none",
                  color: "#fff", cursor: "pointer",
                }}
              >
                Añadir
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
