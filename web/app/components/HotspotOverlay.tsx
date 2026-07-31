"use client";

import { useEffect, useRef, useState, useCallback } from "react";

interface Region {
  x: number; y: number; width: number; height: number;
}

interface Hotspot {
  id: string;
  type: "text" | "qr";
  time_start: number;
  time_end: number;
  region: Region;
  destination: string;
  label: string;
  hold_ms: number | null;
}

interface HotspotData {
  video: string;
  hold_ms_default: number;
  hotspots: Hotspot[];
}

interface Props {
  filename: string;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  /** Si true, intenta decodificar QR en vivo desde el frame. Si false, usa destination del JSON. */
  decodeQrLive?: boolean;
}

// Calcula el rect renderizado real del video respetando object-fit: contain
function getVideoRect(video: HTMLVideoElement): { left: number; top: number; width: number; height: number } {
  const { videoWidth, videoHeight } = video;
  const box = video.getBoundingClientRect();
  if (!videoWidth || !videoHeight) return { left: 0, top: 0, width: box.width, height: box.height };

  const boxRatio = box.width / box.height;
  const vidRatio = videoWidth / videoHeight;

  let w: number, h: number, left: number, top: number;
  if (vidRatio > boxRatio) {
    w = box.width;
    h = box.width / vidRatio;
    left = 0;
    top = (box.height - h) / 2;
  } else {
    h = box.height;
    w = box.height * vidRatio;
    top = 0;
    left = (box.width - w) / 2;
  }
  return { left, top, width: w, height: h };
}

export default function HotspotOverlay({ filename, videoRef, decodeQrLive = false }: Props) {
  const [data, setData] = useState<HotspotData | null>(null);
  const [activeIds, setActiveIds] = useState<Set<string>>(new Set());
  const [modal, setModal] = useState<{ title: string; content: string; url: string | null } | null>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Cargar hotspots
  useEffect(() => {
    if (!filename) return;
    fetch(`/api/hotspots/${encodeURIComponent(filename)}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setData(d))
      .catch(() => {});
  }, [filename]);

  // Actualizar hotspots activos en timeupdate
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !data) return;
    const onTime = () => {
      const t = video.currentTime;
      setActiveIds(new Set(
        data.hotspots
          .filter((h) => t >= h.time_start && t <= h.time_end)
          .map((h) => h.id)
      ));
    };
    video.addEventListener("timeupdate", onTime);
    return () => video.removeEventListener("timeupdate", onTime);
  }, [videoRef, data]);

  const clearTimer = (id: string) => {
    const t = timersRef.current.get(id);
    if (t) { clearTimeout(t); timersRef.current.delete(id); }
  };

  const captureQrContent = useCallback(async (hotspot: Hotspot): Promise<string> => {
    const video = videoRef.current;
    if (!video || !decodeQrLive) return hotspot.destination;
    try {
      const canvas = canvasRef.current!;
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(video, 0, 0);
      const { x, y, width, height } = hotspot.region;
      const px = Math.round(x * video.videoWidth);
      const py = Math.round(y * video.videoHeight);
      const pw = Math.round(width * video.videoWidth);
      const ph = Math.round(height * video.videoHeight);
      const imgData = ctx.getImageData(px, py, pw, ph);
      const jsQR = (await import("jsqr")).default;
      const result = jsQR(imgData.data, pw, ph);
      return result ? result.data : hotspot.destination;
    } catch {
      return hotspot.destination;
    }
  }, [videoRef, decodeQrLive]);

  const handleLongPress = useCallback(async (hotspot: Hotspot) => {
    videoRef.current?.pause();
    const content = hotspot.type === "qr"
      ? await captureQrContent(hotspot)
      : hotspot.destination;
    const isUrl = content.startsWith("http://") || content.startsWith("https://");
    setModal({
      title: hotspot.label || (hotspot.type === "qr" ? "Código QR" : "Enlace"),
      content,
      url: isUrl ? content : null,
    });
  }, [videoRef, captureQrContent]);

  const onPointerDown = useCallback((e: React.PointerEvent, hotspot: Hotspot) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    const holdMs = hotspot.hold_ms ?? data?.hold_ms_default ?? 800;
    const timer = setTimeout(() => handleLongPress(hotspot), holdMs);
    timersRef.current.set(hotspot.id, timer);
  }, [data, handleLongPress]);

  const onPointerUp = useCallback((e: React.PointerEvent, hotspot: Hotspot) => {
    e.currentTarget.releasePointerCapture(e.pointerId);
    clearTimer(hotspot.id);
  }, []);

  const onPointerCancel = useCallback((_e: React.PointerEvent, hotspot: Hotspot) => {
    clearTimer(hotspot.id);
  }, []);

  if (!data || data.hotspots.length === 0) return null;

  return (
    <>
      {/* canvas oculto para capturar frames QR */}
      <canvas ref={canvasRef} style={{ display: "none" }} />

      {/* overlay contenedor */}
      <div
        ref={overlayRef}
        style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
      >
        {data.hotspots
          .filter((h) => activeIds.has(h.id))
          .map((hotspot) => {
            const video = videoRef.current;
            if (!video) return null;
            const vr = getVideoRect(video);
            const { x, y, width, height } = hotspot.region;
            return (
              <div
                key={hotspot.id}
                onPointerDown={(e) => onPointerDown(e, hotspot)}
                onPointerUp={(e) => onPointerUp(e, hotspot)}
                onPointerCancel={(e) => onPointerCancel(e, hotspot)}
                style={{
                  position: "absolute",
                  left: vr.left + x * vr.width,
                  top: vr.top + y * vr.height,
                  width: width * vr.width,
                  height: height * vr.height,
                  pointerEvents: "all",
                  cursor: "pointer",
                  // borde sutil para indicar zona interactiva
                  border: "2px solid rgba(255,255,255,0.35)",
                  borderRadius: 6,
                  background: "rgba(255,255,255,0.04)",
                  boxSizing: "border-box",
                  userSelect: "none",
                  WebkitUserSelect: "none",
                }}
                title={`Mantén pulsado para ver: ${hotspot.label || hotspot.destination}`}
              >
                {/* indicador visual pequeño en esquina */}
                <span style={{
                  position: "absolute", bottom: 4, right: 6,
                  fontSize: 10, color: "rgba(255,255,255,0.6)",
                  pointerEvents: "none",
                }}>
                  {hotspot.type === "qr" ? "QR" : "↗"}
                </span>
              </div>
            );
          })}
      </div>

      {/* modal */}
      {modal && (
        <div
          onClick={() => setModal(null)}
          style={{
            position: "fixed", inset: 0, zIndex: 1000,
            background: "rgba(0,0,0,0.7)",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: 24,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "#1a1a2e", border: "1px solid #333",
              borderRadius: 16, padding: 28, maxWidth: 420, width: "100%",
            }}
          >
            <p style={{ color: "#a78bfa", fontSize: 12, marginBottom: 8 }}>
              {modal.title}
            </p>
            <p style={{
              color: "#e2e8f0", fontSize: 14, wordBreak: "break-all",
              marginBottom: 20, lineHeight: 1.6,
            }}>
              {modal.content}
            </p>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              {modal.url && (
                <a
                  href={modal.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    background: "#7c3aed", color: "#fff", padding: "8px 18px",
                    borderRadius: 8, fontSize: 13, textDecoration: "none",
                  }}
                >
                  Abrir enlace →
                </a>
              )}
              <button
                onClick={() => setModal(null)}
                style={{
                  background: "#2d2d4e", color: "#94a3b8",
                  border: "1px solid #444", padding: "8px 18px",
                  borderRadius: 8, fontSize: 13, cursor: "pointer",
                }}
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
