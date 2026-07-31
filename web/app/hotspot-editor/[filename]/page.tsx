"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import HotspotEditor from "../../components/HotspotEditor";

export default function HotspotEditorPage() {
  const { filename } = useParams<{ filename: string }>();
  const decoded = decodeURIComponent(filename);

  return (
    <main className="min-h-screen px-4 py-8">
      <div className="max-w-5xl mx-auto">
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
          <Link href="/" style={{ color: "var(--muted)", fontSize: 13 }}>← Inicio</Link>
          <h1 style={{ color: "var(--text)", fontSize: 18, fontWeight: 700, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            Hotspots — {decoded.replace(/_reel\.mp4$/, "").replace(/_/g, " ")}
          </h1>
        </div>
        <HotspotEditor filename={decoded} />
      </div>
    </main>
  );
}
