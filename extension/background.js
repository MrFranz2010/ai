/**
 * Lato service worker: crea la voce del menu contestuale e inoltra il testo
 * selezionato a NOKK. La configurazione vive in chrome.storage.local.
 */

const DEFAULTS = { baseUrl: "", apiKey: "", mode: "" };
const CONTEXT_MENU_ID = "nokk-ask-selection";

async function getSettings() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

async function readJson(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    payload = null;
  }
  if (!response.ok) {
    const reason = payload && payload.error ? payload.error : `HTTP ${response.status}`;
    throw new Error(reason);
  }
  return payload;
}

async function apiRequest(path, options = {}) {
  const { baseUrl, apiKey } = await getSettings();
  if (!baseUrl) throw new Error("Configura l'indirizzo di NOKK nelle impostazioni dell'estensione.");
  if (!apiKey) throw new Error("Inserisci la chiave API nelle impostazioni dell'estensione.");
  const response = await fetch(`${baseUrl.replace(/\/+$/, "")}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
      ...(options.headers || {}),
    },
  });
  return readJson(response);
}

async function askNokk(text) {
  const { mode } = await getSettings();
  const payload = { messages: [{ role: "user", content: text }] };
  if (mode) payload.mode = mode;
  const started = await apiRequest("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const jobId = started.job_id;
  for (let attempt = 0; attempt < 120; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    const job = await apiRequest(`/api/v1/jobs/${jobId}`);
    if (job.status === "complete") return job.reply || "NOKK non ha prodotto testo.";
    if (job.status === "failed") throw new Error(job.error || "La richiesta è fallita.");
    if (job.status === "awaiting_approval") {
      return "NOKK ha bisogno di un'approvazione: apri la pagina di NOKK per confermare il comando.";
    }
  }
  throw new Error("NOKK sta impiegando troppo tempo: riprova dalla pagina.");
}

async function showReply(title, message) {
  await chrome.storage.local.set({
    lastReply: { title, message, at: Date.now() },
  });
  await chrome.notifications.create({
    type: "basic",
    iconUrl: "icon-128.png",
    title,
    message: message.slice(0, 900),
  });
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: CONTEXT_MENU_ID,
    title: "Chiedi a NOKK: «%s»",
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener((info) => {
  if (info.menuItemId !== CONTEXT_MENU_ID) return;
  const selection = (info.selectionText || "").trim();
  if (!selection) return;
  askNokk(selection)
    .then((reply) => showReply("NOKK", reply))
    .catch((error) => showReply("NOKK · errore", error.message));
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "ask") {
    askNokk(String(message.text || ""))
      .then((reply) => sendResponse({ ok: true, reply }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  return false;
});
