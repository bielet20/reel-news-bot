/**
 * wa_service/server.js
 * Sidecar Express que gestiona la sesión de WhatsApp Web y expone endpoints
 * para que el backend Python pueda subir videos como WhatsApp Status.
 *
 * Uso: cd wa_service && npm install && npm start
 */

const express = require("express");
const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const qrcode = require("qrcode");
const path = require("path");

const PORT = 3001;

const app = express();
app.use(express.json());

// ── Estado en memoria ─────────────────────────────────────────────────────────

let state = {
  connected: false,
  ready: false,
  qrBase64: null,
};

// ── Cliente WhatsApp ──────────────────────────────────────────────────────────

const client = new Client({
  authStrategy: new LocalAuth({
    dataPath: path.join(__dirname, ".wwebjs_auth"),
  }),
  puppeteer: {
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  },
});

client.on("qr", async (qr) => {
  try {
    state.qrBase64 = await qrcode.toDataURL(qr);
    state.connected = false;
    state.ready = false;
    console.log("[wa-service] QR generado — escanea desde la app /canales");
  } catch (err) {
    console.error("[wa-service] Error generando QR:", err);
  }
});

client.on("ready", () => {
  state.connected = true;
  state.ready = true;
  state.qrBase64 = null;
  console.log("[wa-service] Cliente listo");
});

client.on("authenticated", () => {
  state.connected = true;
  console.log("[wa-service] Autenticado");
});

client.on("auth_failure", (msg) => {
  state.connected = false;
  state.ready = false;
  console.error("[wa-service] Auth fallida:", msg);
});

client.on("disconnected", (reason) => {
  state.connected = false;
  state.ready = false;
  console.log("[wa-service] Desconectado:", reason);
});

client.initialize().catch((err) => {
  console.error("[wa-service] Error inicializando cliente:", err);
});

// ── Endpoints ─────────────────────────────────────────────────────────────────

app.get("/status", (_req, res) => {
  res.json({ connected: state.connected, ready: state.ready });
});

app.get("/qr", (_req, res) => {
  if (!state.qrBase64) {
    return res.status(404).json({ error: "QR no disponible — puede que ya esté autenticado o aún no se haya generado" });
  }
  res.json({ qr: state.qrBase64 });
});

app.post("/send-status", async (req, res) => {
  const { video_path, caption = "" } = req.body;

  if (!video_path) {
    return res.status(400).json({ error: "video_path es requerido" });
  }
  if (!state.ready) {
    return res.status(503).json({ error: "Cliente WhatsApp no está listo. Escanea el QR primero." });
  }

  try {
    const media = MessageMedia.fromFilePath(video_path);

    // Publicar como estado/story de WhatsApp
    await client.setStatus(caption || "");
    await client.sendMessage("status@broadcast", media, { caption });

    res.json({ ok: true });
  } catch (err) {
    console.error("[wa-service] Error enviando status:", err);
    res.status(500).json({ error: err.message || String(err) });
  }
});

// ── Arranque ──────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`[wa-service] Escuchando en http://localhost:${PORT}`);
});
