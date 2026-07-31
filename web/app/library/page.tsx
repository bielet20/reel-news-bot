"use client";

import { useEffect, useRef, useState } from "react";

interface LibraryItem {
  id: string;
  name: string;
  type: "image" | "qr";
  filename: string;
  destination?: string;
  created_at: string;
}

export default function LibraryPage() {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [qrUrl, setQrUrl] = useState("");
  const [qrName, setQrName] = useState("");
  const [savingQr, setSavingQr] = useState(false);
  const [msg, setMsg] = useState("");
  const [tab, setTab] = useState<"all" | "image" | "qr">("all");
  const fileRef = useRef<HTMLInputElement>(null);

  const reload = () => {
    fetch("/api/library")
      .then((r) => r.json())
      .then(setItems)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { reload(); }, []);

  const uploadFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setMsg("");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("name", file.name.replace(/\.[^.]+$/, ""));
    try {
      const r = await fetch("/api/library/upload", { method: "POST", body: fd });
      if (!r.ok) throw new Error((await r.json()).detail || "Error al subir");
      setMsg("Imagen guardada en la biblioteca");
      reload();
    } catch (err) { setMsg(`Error: ${err}`); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const saveQr = async () => {
    if (!qrUrl.trim()) return;
    setSavingQr(true); setMsg("");
    try {
      const r = await fetch("/api/library/qr", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ destination: qrUrl.trim(), name: qrName.trim() || qrUrl.trim() }),
      });
      if (!r.ok) throw new Error((await r.json()).detail || "Error");
      setMsg("QR guardado en la biblioteca");
      setQrUrl(""); setQrName("");
      reload();
    } catch (err) { setMsg(`Error: ${err}`); }
    finally { setSavingQr(false); }
  };

  const deleteItem = async (id: string) => {
    await fetch(`/api/library/${id}`, { method: "DELETE" });
    setItems((prev) => prev.filter((i) => i.id !== id));
  };

  const filtered = tab === "all" ? items : items.filter((i) => i.type === tab);

  const sx = {
    bg: { background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 8, padding: "7px 10px", fontSize: 13 } as const,
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "24px 20px", maxWidth: 900, margin: "0 auto" }}>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <a href="/" style={{ color: "var(--muted)", textDecoration: "none", fontSize: 13 }}>← Volver</a>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Biblioteca de imágenes</h1>
      </div>

      {/* Acciones */}
      <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>

        {/* Subir imagen */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: 16, flex: "1 1 220px" }}>
          <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 10 }}>Subir imagen</p>
          <input ref={fileRef} type="file" accept="image/*" onChange={uploadFile} style={{ display: "none" }} />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            style={{ width: "100%", background: uploading ? "var(--surface2)" : "var(--accent)", color: uploading ? "var(--muted)" : "#fff", border: "none", borderRadius: 8, padding: "8px 0", fontSize: 13, cursor: uploading ? "not-allowed" : "pointer", fontWeight: 600 }}
          >
            {uploading ? "Subiendo..." : "Elegir archivo"}
          </button>
          <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 6 }}>PNG, JPG, WebP, GIF</p>
        </div>

        {/* Generar QR */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: 16, flex: "1 1 280px" }}>
          <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 10 }}>Generar y guardar QR</p>
          <input
            type="text"
            placeholder="URL o texto para el QR"
            value={qrUrl}
            onChange={(e) => setQrUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && saveQr()}
            style={{ ...sx.bg, width: "100%", marginBottom: 6, boxSizing: "border-box" }}
          />
          <input
            type="text"
            placeholder="Nombre (opcional)"
            value={qrName}
            onChange={(e) => setQrName(e.target.value)}
            style={{ ...sx.bg, width: "100%", marginBottom: 8, boxSizing: "border-box" }}
          />
          <button
            onClick={saveQr}
            disabled={savingQr || !qrUrl.trim()}
            style={{ width: "100%", background: savingQr || !qrUrl.trim() ? "var(--surface2)" : "#7c3aed", color: savingQr || !qrUrl.trim() ? "var(--muted)" : "#fff", border: "none", borderRadius: 8, padding: "8px 0", fontSize: 13, cursor: savingQr || !qrUrl.trim() ? "not-allowed" : "pointer", fontWeight: 600 }}
          >
            {savingQr ? "Generando..." : "Guardar QR"}
          </button>
        </div>
      </div>

      {msg && (
        <p style={{ fontSize: 12, color: msg.startsWith("Error") ? "var(--error)" : "var(--success)", marginBottom: 16 }}>{msg}</p>
      )}

      {/* Filtros */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {(["all", "image", "qr"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{ background: tab === t ? "var(--accent)" : "var(--surface)", color: tab === t ? "#fff" : "var(--muted)", border: "1px solid var(--border)", borderRadius: 20, padding: "4px 14px", fontSize: 12, cursor: "pointer" }}
          >
            {t === "all" ? `Todo (${items.length})` : t === "image" ? `Imágenes (${items.filter(i => i.type === "image").length})` : `QR (${items.filter(i => i.type === "qr").length})`}
          </button>
        ))}
      </div>

      {/* Grid */}
      {loading ? (
        <p style={{ color: "var(--muted)", fontSize: 13 }}>Cargando...</p>
      ) : filtered.length === 0 ? (
        <p style={{ color: "var(--muted)", fontSize: 13, textAlign: "center", paddingTop: 40 }}>
          No hay {tab === "all" ? "elementos" : tab === "image" ? "imágenes" : "QRs"} en la biblioteca todavía.
        </p>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 12 }}>
          {filtered.map((item) => (
            <div
              key={item.id}
              style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", position: "relative" }}
            >
              <div style={{ width: "100%", aspectRatio: "1", background: "var(--surface2)", display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
                <img
                  src={`/library-files/${item.filename}`}
                  alt={item.name}
                  style={{ width: "100%", height: "100%", objectFit: "contain" }}
                />
              </div>
              <div style={{ padding: "6px 8px" }}>
                <p style={{ fontSize: 11, color: "var(--text)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={item.name}>
                  {item.name}
                </p>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
                  <span style={{ fontSize: 10, color: item.type === "qr" ? "#fb923c" : "#60a5fa", background: "var(--surface2)", padding: "1px 5px", borderRadius: 4 }}>
                    {item.type === "qr" ? "QR" : "IMG"}
                  </span>
                  <button
                    onClick={() => deleteItem(item.id)}
                    style={{ background: "none", border: "none", color: "var(--error)", cursor: "pointer", fontSize: 14, padding: 0, lineHeight: 1 }}
                    title="Eliminar"
                  >
                    ✕
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
