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
  authTimeoutMs: 120000,
  puppeteer: {
    headless: "shell",
    protocolTimeout: 120000,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--no-first-run",
      "--disable-extensions",
      "--disable-background-timer-throttling",
      "--disable-renderer-backgrounding",
    ],
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
  // Reinicializar tras 5s para reconectar automáticamente. Hay que cerrar el
  // navegador anterior: si no, queda vivo, sigue emitiendo "qr" (cada QR sale
  // duplicado en el log) y pone ready=false aunque la sesión nueva ya esté lista.
  setTimeout(async () => {
    console.log("[wa-service] Reinicializando cliente...");
    try {
      await client.destroy();
    } catch (err) {
      console.error("[wa-service] Error cerrando el cliente anterior:", err.message || err);
    }
    client.initialize().catch((err) => {
      console.error("[wa-service] Error al reinicializar:", err.message || err);
    });
  }, 5000);
});

client.initialize().catch((err) => {
  console.error("[wa-service] Error inicializando cliente:", err.message || err);
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
    const warnings = [];

    try {
      await client.setStatus(caption || "");
    } catch (e) {
      warnings.push(`setStatus: ${e.message}`);
    }

    try {
      await client.sendMessage("status@broadcast", media, { caption });
    } catch (e) {
      // WhatsApp Web cambia APIs internas; loguear pero no fallar
      console.warn("[wa-service] sendMessage status@broadcast falló:", e.message?.slice(0, 200));
      warnings.push(`broadcast: ${e.message}`);
    }

    if (warnings.length === 2) {
      // Ambos fallaron — reportar error real
      return res.status(500).json({ error: warnings.join(" | ") });
    }
    res.json({ ok: true, warnings: warnings.length ? warnings : undefined });
  } catch (err) {
    console.error("[wa-service] Error enviando status:", err);
    res.status(500).json({ error: err.message || String(err) });
  }
});

app.post("/send-message", async (req, res) => {
  const { texto, chat_id } = req.body;
  if (!texto) return res.status(400).json({ error: "texto es requerido" });
  if (!state.ready) return res.status(503).json({ error: "Cliente WhatsApp no está listo. Escanea el QR primero." });

  const target = chat_id || process.env.WA_DEFAULT_CHAT_ID;
  if (!target) return res.status(400).json({ error: "chat_id no configurado. Define WA_DEFAULT_CHAT_ID en el entorno." });

  try {
    await client.sendMessage(target, texto);
    res.json({ ok: true });
  } catch (err) {
    console.error("[wa-service] Error enviando mensaje:", err);
    res.status(500).json({ error: err.message || String(err) });
  }
});

// ── Canal de WhatsApp (Newsletter) ────────────────────────────────────────────

async function _getNewsletters() {
  return client.pupPage.evaluate(() => {
    const results = [];
    const seen = new Set();

    function addModel(m) {
      try {
        const jid = m?.id?._serialized || m?.id?.toString?.() || "";
        if (!jid.endsWith("@newsletter") || seen.has(jid)) return;
        seen.add(jid);
        results.push({ jid, name: m.name || m.formattedTitle || m.id?.user || jid });
      } catch {}
    }

    // WAWebNewsletterCollection._models — funciona en versiones recientes de WA Web
    try {
      const col = (window.requireInterop || window.require)("WAWebNewsletterCollection");
      const models = col?._models;
      if (models) {
        const arr = models instanceof Map ? [...models.values()]
          : Array.isArray(models) ? models : Object.values(models);
        arr.forEach(addModel);
      }
    } catch {}

    return results;
  });
}

app.get("/debug-stores", async (_req, res) => {
  if (!state.ready) return res.status(503).json({ error: "no listo" });
  try {
    const info = await client.pupPage.evaluate(() => {
      const reqFn = window.requireInterop || window.require;
      const results = {};

      // Buscar módulos que exponen isRegularUser
      const candidates = [
        "WAWebUserPref", "WAWebUser", "WAWebMeUser", "WAWebMe",
        "WAWebConn", "WAWebConnModel", "WAWebConnection",
        "WAWebAccountInfo", "WAWebUserInfo", "WAWebSubscription",
        "WAWebBusinessProfile", "WAWebDeviceCapabilities",
        "WAWebContactModel", "WAWebContact",
      ];
      for (const name of candidates) {
        try {
          const m = reqFn(name);
          if (!m) continue;
          const keys = Object.keys(m);
          if (keys.some(k => k.toLowerCase().includes("regular") || k.toLowerCase().includes("user"))) {
            results[name] = keys.filter(k => k.toLowerCase().includes("regular") || k.toLowerCase().includes("user") || k.toLowerCase().includes("business")).slice(0, 10);
          }
          // Also check for isRegularUser directly
          if (typeof m.isRegularUser !== "undefined") {
            results[`${name}.isRegularUser`] = m.isRegularUser;
          }
        } catch {}
      }

      // Buscar la función P dentro del módulo WAWebNewsletterSendMsgAction
      // Para eso necesito ver el source del módulo completo via webpackChunkbuild
      let pFnSrc = "no encontrado";
      try {
        const chunk = window.webpackChunkbuild;
        if (Array.isArray(chunk)) {
          outer: for (const entry of chunk) {
            if (!entry?.[1]) continue;
            for (const [id, fn] of Object.entries(entry[1])) {
              if (typeof fn !== "function") continue;
              const src = fn.toString();
              if (src.includes("sendNewsletterMediaMsg") && src.includes("sendNewsletterTextMsg")) {
                // Este es el módulo. Buscar isRegularUser en él
                const iruIdx = src.indexOf("isRegularUser");
                if (iruIdx >= 0) {
                  pFnSrc = src.slice(Math.max(0, iruIdx - 200), iruIdx + 200);
                }
                results.moduleSrc = src.slice(0, 1000);
                break outer;
              }
            }
          }
        }
      } catch(e) { pFnSrc = e.message; }
      results.pFnSrc = pFnSrc;

      return results;
    });
    res.json(info);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get("/channels", async (req, res) => {
  if (!state.ready) return res.status(503).json({ error: "Cliente no listo. Escanea el QR primero." });
  try {
    const channels = await _getNewsletters();
    res.json(channels);
  } catch (err) {
    console.error("[wa-service] Error listando canales:", err);
    res.status(500).json({ error: err.message || String(err) });
  }
});

app.post("/find-channel", async (req, res) => {
  if (!state.ready) return res.status(503).json({ error: "Cliente no listo. Escanea el QR primero." });
  const { url } = req.body;
  const inviteCode = url ? url.split("/channel/").pop().split("?")[0].trim() : null;
  if (!inviteCode) {
    // Sin código de invitación: devolver todos los canales del usuario para selección manual
    try {
      const all = await _getNewsletters();
      return res.json(all.map((c) => ({ ...c, exact: false })));
    } catch { return res.json([]); }
  }

  // Intento 1: buscar en WAWebNewsletterCollection por invite code
  try {
    const found = await client.pupPage.evaluate((invCode) => {
      try {
        const col = (window.requireInterop || window.require)("WAWebNewsletterCollection");
        const models = col?._models;
        if (!models) return null;
        const arr = models instanceof Map ? [...models.values()]
          : Array.isArray(models) ? models : Object.values(models);
        const norm = invCode.toLowerCase();
        const match = arr.find(m => {
          const inviteCode = m?.metadata?.inviteCode || m?.inviteCode || "";
          return inviteCode.toLowerCase() === norm;
        });
        if (!match) return null;
        const jid = match.id?._serialized || match.id?.toString?.() || null;
        if (!jid) return null;
        return { jid, name: match.name || match.formattedTitle || match.id?.user || jid };
      } catch { return null; }
    }, inviteCode);

    if (found) {
      return res.json([{ jid: found.jid, name: found.name, invite_link: url, exact: true }]);
    }
  } catch (e) {
    console.warn("[wa] find-channel intento1:", e.message);
  }

  // Intento 2: buscar en los canales ya cargados por código o nombre
  try {
    const all = await _getNewsletters();
    const norm = inviteCode.toLowerCase();
    const match = all.find((c) =>
      (c.invite_link || "").toLowerCase().includes(norm) ||
      (c.jid || "").toLowerCase().includes(norm)
    );
    if (match) return res.json([{ ...match, invite_link: url, exact: true }]);
    // Devolver todos los canales del usuario para selección manual
    if (all.length > 0) return res.json(all.map((c) => ({ ...c, invite_link: url, exact: false })));
  } catch (e) {
    console.warn("[wa] find-channel all-channels fallback:", e.message);
  }

  res.json([]);
});

app.post("/send-channel", async (req, res) => {
  const { caption = "", channel_jid } = req.body;
  const targetJid = channel_jid || process.env.WA_CHANNEL_JID;

  if (!targetJid) return res.status(400).json({ error: "channel_jid no configurado." });
  if (!state.ready) return res.status(503).json({ error: "Cliente no listo. Escanea el QR primero." });

  try {
    await client.pupPage.evaluate(async (jid, text) => {
      const reqFn = window.requireInterop || window.require;
      const NS    = reqFn("WAWebNewsletterSendMsgAction");
      if (!NS?.sendNewsletterTextMsg) throw new Error("sendNewsletterTextMsg no disponible");

      const col  = reqFn("WAWebNewsletterCollection");
      const mods = col?._models;
      const arr  = mods instanceof Map ? [...mods.values()] : Array.isArray(mods) ? mods : Object.values(mods || {});
      const chat = arr.find(m => { try { return (m?.id?._serialized || "") === jid; } catch { return false; } });
      if (!chat) throw new Error(`Newsletter no encontrado: ${jid}`);

      await NS.sendNewsletterTextMsg(chat, text, {});
    }, targetJid, caption || "📢 Nuevo reel publicado");

    res.json({ ok: true, channel_jid: targetJid });
  } catch (err) {
    console.error("[wa-service] Error enviando a canal:", err.message?.slice(0, 300));
    res.status(500).json({ error: err.message || String(err) });
  }
});

// ── Arranque ──────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`[wa-service] Escuchando en http://localhost:${PORT}`);
});
