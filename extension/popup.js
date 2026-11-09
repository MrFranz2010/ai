const DEFAULTS = { baseUrl: "", apiKey: "", mode: "" };

const settingsToggle = document.querySelector("#settings-toggle");
const settingsForm = document.querySelector("#settings");
const baseUrlInput = document.querySelector("#base-url");
const apiKeyInput = document.querySelector("#api-key");
const settingsStatus = document.querySelector("#settings-status");
const testButton = document.querySelector("#test-connection");

const askForm = document.querySelector("#ask");
const questionInput = document.querySelector("#question");
const modeSelect = document.querySelector("#mode");
const sendButton = document.querySelector("#send");
const askStatus = document.querySelector("#ask-status");

const replyBox = document.querySelector("#reply");
const replyTitle = document.querySelector("#reply-title");
const replyText = document.querySelector("#reply-text");
const copyReply = document.querySelector("#copy-reply");

async function loadSettings() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  baseUrlInput.value = stored.baseUrl;
  apiKeyInput.value = stored.apiKey;
  modeSelect.value = stored.mode;
  return stored;
}

function normalizeBaseUrl(value) {
  return value.trim().replace(/\/+$/, "");
}

async function saveSettings(event) {
  event.preventDefault();
  const baseUrl = normalizeBaseUrl(baseUrlInput.value);
  if (baseUrl && !/^https?:\/\/[^\s]+$/.test(baseUrl)) {
    settingsStatus.textContent = "Scrivi un indirizzo completo, per esempio https://ai-49bx.onrender.com";
    return;
  }
  const apiKey = apiKeyInput.value.trim();
  if (apiKey && !/^nokk_[A-Za-z0-9_-]{32}$/.test(apiKey)) {
    settingsStatus.textContent = "La chiave deve iniziare con nokk_ e avere 32 caratteri dopo.";
    return;
  }
  await chrome.storage.local.set({ baseUrl, apiKey, mode: modeSelect.value });
  settingsStatus.textContent = "Impostazioni salvate.";
}

async function testConnection() {
  testButton.disabled = true;
  settingsStatus.textContent = "Verifica in corso…";
  try {
    const baseUrl = normalizeBaseUrl(baseUrlInput.value);
    const apiKey = apiKeyInput.value.trim();
    if (!baseUrl) throw new Error("Inserisci prima l'indirizzo di NOKK.");
    const health = await fetch(`${baseUrl}/api/v1/health`);
    if (!health.ok) throw new Error(`Il servizio ha risposto ${health.status}.`);
    const response = await fetch(`${baseUrl}/api/v1/planner`, {
      headers: { "X-API-Key": apiKey },
    });
    if (response.status === 401) throw new Error("La chiave non è valida.");
    if (response.status === 403) throw new Error("L'API è disattivata nelle impostazioni di NOKK.");
    if (response.status === 429) throw new Error("Troppe richieste: riprova tra un minuto.");
    if (!response.ok) throw new Error(`NOKK ha risposto ${response.status}.`);
    settingsStatus.textContent = "Connessione riuscita.";
  } catch (error) {
    settingsStatus.textContent = error.message;
  } finally {
    testButton.disabled = false;
  }
}

function showReply(title, text) {
  replyTitle.textContent = title;
  replyText.textContent = text;
  replyBox.hidden = false;
}

async function submitQuestion(event) {
  event.preventDefault();
  const text = questionInput.value.trim();
  if (!text) return;
  sendButton.disabled = true;
  askStatus.textContent = "NOKK sta pensando…";
  try {
    const answer = await chrome.runtime.sendMessage({ type: "ask", text });
    if (!answer || !answer.ok) throw new Error((answer && answer.error) || "Nessuna risposta.");
    showReply("NOKK", answer.reply);
    askStatus.textContent = "";
    questionInput.value = "";
  } catch (error) {
    askStatus.textContent = error.message;
    replyBox.hidden = true;
  } finally {
    sendButton.disabled = false;
  }
}

settingsToggle.addEventListener("click", () => {
  const open = settingsForm.hidden;
  settingsForm.hidden = !open;
  settingsToggle.setAttribute("aria-expanded", String(open));
});

settingsForm.addEventListener("submit", (event) => {
  void saveSettings(event);
});

testButton.addEventListener("click", () => {
  void testConnection();
});

askForm.addEventListener("submit", (event) => {
  void submitQuestion(event);
});

modeSelect.addEventListener("change", async () => {
  await chrome.storage.local.set({ mode: modeSelect.value });
});

copyReply.addEventListener("click", async () => {
  await navigator.clipboard.writeText(replyText.textContent || "");
  copyReply.textContent = "Copiata";
  window.setTimeout(() => {
    copyReply.textContent = "Copia risposta";
  }, 1500);
});

loadSettings()
  .then(async (stored) => {
    if (!stored.baseUrl || !stored.apiKey) {
      settingsForm.hidden = false;
      settingsToggle.setAttribute("aria-expanded", "true");
    }
    const cached = await chrome.storage.local.get("lastReply");
    if (cached.lastReply && cached.lastReply.message) {
      showReply(cached.lastReply.title || "NOKK", cached.lastReply.message);
    }
  })
  .catch((error) => {
    askStatus.textContent = error.message;
  });
