"use strict";

const STORAGE_KEY = "nokk-hub-settings-v1";
const ROTATION_KEY = "nokk-hub-rotation";
const ROTATIONS = [0, 90, 180, 270];
const LAYOUT_WIDE_MIN_WIDTH = 861;
const LAYOUT_COMPACT_MIN_WIDTH = 700;
const LAYOUT_COMPACT_MAX_HEIGHT = 560;
const WEATHER_REFRESH_MS = 15 * 60 * 1000;
const PLANNER_REFRESH_MS = 60 * 1000;
const JOB_POLL_MS = 800;
const JOB_TIMEOUT_MS = 120 * 1000;

const WIDGETS = [
  { id: "clock", label: "Orologio" },
  { id: "weather", label: "Meteo" },
  { id: "reminders", label: "Promemoria" },
  { id: "tasks", label: "Attività" },
  { id: "media", label: "In riproduzione" },
];

const DEFAULT_LAYOUT = [
  { id: "clock", side: "left", enabled: true },
  { id: "weather", side: "left", enabled: true },
  { id: "reminders", side: "right", enabled: true },
  { id: "tasks", side: "right", enabled: true },
  { id: "media", side: "right", enabled: true },
];

const ICONS = {
  play: '<path d="M8 5l11 7-11 7z"/>',
  pause: '<path d="M9 5v14M15 5v14"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
};

const els = {
  railLeft: document.getElementById("rail-left"),
  railRight: document.getElementById("rail-right"),
  ptt: document.getElementById("ptt"),
  pttHint: document.getElementById("ptt-hint"),
  transcript: document.getElementById("transcript"),
  reply: document.getElementById("reply"),
  connection: document.getElementById("connection"),
  rotateButton: document.getElementById("rotate-button"),
  fullscreenButton: document.getElementById("fullscreen-button"),
  settingsButton: document.getElementById("settings-button"),
  settings: document.getElementById("settings"),
  settingsClose: document.getElementById("settings-close"),
  widgetList: document.getElementById("widget-list"),
  streamUrl: document.getElementById("stream-url"),
  streamName: document.getElementById("stream-name"),
  speakReplies: document.getElementById("speak-replies"),
  themeSelect: document.getElementById("theme-select"),
  audio: document.getElementById("player"),
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function icon(name) {
  const wrapper = document.createElement("span");
  wrapper.className = "hub-inline-icon";
  wrapper.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`;
  return wrapper;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function vibrate(ms) {
  if (navigator.vibrate) navigator.vibrate(ms);
}

/* Settings */

function defaultSettings() {
  return {
    layout: DEFAULT_LAYOUT.map((item) => ({ ...item })),
    streamUrl: "",
    streamName: "",
    volume: 0.7,
    speakReplies: true,
  };
}

function normalizeStreamUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const url = new URL(raw, window.location.origin);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
  } catch {
    return "";
  }
}

function sanitizeSettings(raw) {
  const clean = defaultSettings();
  if (!raw || typeof raw !== "object") return clean;
  const stored = new Map();
  if (Array.isArray(raw.layout)) {
    for (const item of raw.layout) {
      if (item && WIDGETS.some((widget) => widget.id === item.id)) stored.set(item.id, item);
    }
  }
  clean.layout = DEFAULT_LAYOUT.map((base) => {
    const item = stored.get(base.id);
    if (!item) return { ...base };
    return {
      id: base.id,
      side: item.side === "left" || item.side === "right" ? item.side : base.side,
      enabled: typeof item.enabled === "boolean" ? item.enabled : base.enabled,
    };
  });
  clean.streamUrl = normalizeStreamUrl(raw.streamUrl);
  clean.streamName = typeof raw.streamName === "string" ? raw.streamName.slice(0, 60) : "";
  clean.volume = typeof raw.volume === "number" && raw.volume >= 0 && raw.volume <= 1
    ? raw.volume
    : clean.volume;
  clean.speakReplies = typeof raw.speakReplies === "boolean" ? raw.speakReplies : clean.speakReplies;
  return clean;
}

function currentRotation() {
  const saved = Number(document.documentElement.dataset.rotation);
  return ROTATIONS.includes(saved) ? saved : 0;
}

function storedRotation() {
  try {
    const stored = Number(localStorage.getItem(ROTATION_KEY));
    return ROTATIONS.includes(stored) ? stored : 0;
  } catch {
    return 0;
  }
}

/* The manual rotation swaps the viewport on screen, so pick the layout from the
   size the page really renders at instead of relying on the device media queries. */
function effectiveViewport() {
  const turned = currentRotation() === 90 || currentRotation() === 270;
  return {
    width: turned ? window.innerHeight : window.innerWidth,
    height: turned ? window.innerWidth : window.innerHeight,
  };
}

function updateHubLayout() {
  const { width, height } = effectiveViewport();
  let layout = "stack";
  if (width >= LAYOUT_COMPACT_MIN_WIDTH && height <= LAYOUT_COMPACT_MAX_HEIGHT) layout = "compact";
  else if (width >= LAYOUT_WIDE_MIN_WIDTH) layout = "wide";
  document.documentElement.dataset.hubLayout = layout;
}

function applyRotation(degrees) {
  const rotation = ROTATIONS.includes(degrees) ? degrees : 0;
  if (rotation === 0) delete document.documentElement.dataset.rotation;
  else document.documentElement.dataset.rotation = String(rotation);
  updateHubLayout();
  els.rotateButton.setAttribute("aria-label", `Ruota la schermata (attuale ${rotation}°)`);
  els.rotateButton.title = `Ruota la schermata (attuale ${rotation}°)`;
  try {
    localStorage.setItem(ROTATION_KEY, String(rotation));
  } catch {
    /* private mode: the rotation lasts for the session only */
  }
}

function loadSettings() {
  try {
    return sanitizeSettings(JSON.parse(localStorage.getItem(STORAGE_KEY) || "null"));
  } catch {
    return defaultSettings();
  }
}

function saveSettings() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    /* private mode: settings last for the session only */
  }
}

let settings = loadSettings();
let controllers = new Map();

/* Widgets */

function renderRails() {
  for (const controller of controllers.values()) controller.destroy?.();
  controllers = new Map();
  els.railLeft.replaceChildren();
  els.railRight.replaceChildren();
  for (const item of settings.layout) {
    if (!item.enabled) continue;
    const definition = WIDGETS.find((widget) => widget.id === item.id);
    if (!definition) continue;
    const box = element("section", "hub-widget");
    box.dataset.widget = item.id;
    const body = element("div", "widget-body");
    box.append(element("h2", "widget-title", definition.label), body);
    (item.side === "left" ? els.railLeft : els.railRight).append(box);
    controllers.set(item.id, mountWidget(item.id, body) || {});
  }
}

function mountWidget(id, body) {
  if (id === "clock") return mountClock(body);
  if (id === "weather") return mountWeather(body);
  if (id === "reminders") return mountReminders(body);
  if (id === "tasks") return mountTasks(body);
  if (id === "media") return mountMedia(body);
  return null;
}

function mountClock(body) {
  const time = element("p", "clock-time", "--:--");
  const date = element("p", "clock-date", "");
  body.append(time, date);
  const refresh = () => {
    const now = new Date();
    time.textContent = now.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
    date.textContent = now.toLocaleDateString("it-IT", {
      weekday: "long", day: "numeric", month: "long",
    });
  };
  refresh();
  const timer = setInterval(refresh, 1000);
  return { refresh, destroy: () => clearInterval(timer) };
}

function mountWeather(body) {
  const temperature = element("p", "weather-temp", "—");
  const description = element("p", "weather-desc", "Carico il meteo…");
  const range = element("p", "weather-range", "");
  body.append(temperature, description, range);
  let active = true;

  const refresh = async () => {
    try {
      const response = await fetch("/api/weather", { cache: "no-store" });
      const data = await response.json();
      if (!active) return;
      if (!data.configured) {
        temperature.textContent = "—";
        description.textContent = "Imposta città e meteo nelle impostazioni di NOKK";
        range.textContent = "";
        return;
      }
      if (!response.ok || data.error) {
        temperature.textContent = "—";
        description.textContent = data.error || "Meteo non disponibile";
        range.textContent = data.city || "";
        return;
      }
      temperature.textContent = Number.isFinite(data.temperature) ? `${data.temperature}°` : "—";
      description.textContent = data.description || "condizioni variabili";
      range.textContent = [
        data.city,
        Number.isFinite(data.minimum) ? `min ${data.minimum}°` : "",
        Number.isFinite(data.maximum) ? `max ${data.maximum}°` : "",
      ].filter(Boolean).join(" · ");
    } catch {
      if (active) description.textContent = "Meteo non raggiungibile";
    }
  };

  refresh();
  const timer = setInterval(refresh, WEATHER_REFRESH_MS);
  return { refresh, destroy: () => { active = false; clearInterval(timer); } };
}

let planner = { events: [], tasks: [] };
const plannerListeners = new Set();
let plannerRequest = null;

async function loadPlanner() {
  if (plannerRequest) return plannerRequest;
  plannerRequest = (async () => {
    try {
      const response = await fetch("/api/planner", { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json();
      planner = {
        events: Array.isArray(data.events) ? data.events : [],
        tasks: Array.isArray(data.tasks) ? data.tasks : [],
      };
    } catch {
      /* keep the previous snapshot */
    } finally {
      plannerRequest = null;
      for (const listener of plannerListeners) listener();
    }
  })();
  return plannerRequest;
}

function upcomingItems() {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const items = [];
  for (const event of planner.events) {
    const when = event.starts_at;
    if (when && Date.parse(when) >= startOfToday.getTime()) {
      items.push({ title: event.title, when });
    }
  }
  for (const task of planner.tasks) {
    if (task.completed) continue;
    const when = task.starts_at || (task.due_date ? `${task.due_date}T09:00:00` : "");
    if (when && Date.parse(when) >= startOfToday.getTime()) {
      items.push({ title: task.title, when });
    }
  }
  return items
    .filter((item) => !Number.isNaN(Date.parse(item.when)))
    .sort((left, right) => Date.parse(left.when) - Date.parse(right.when))
    .slice(0, 4);
}

function formatWhen(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const day = new Date(date);
  day.setHours(0, 0, 0, 0);
  const difference = Math.round((day.getTime() - today.getTime()) / 86400000);
  const hasTime = String(value).includes("T") && !/T00:00:00$/.test(String(value));
  const time = hasTime
    ? date.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })
    : "";
  if (difference === 0) return time ? `Oggi ${time}` : "Oggi";
  if (difference === 1) return time ? `Domani ${time}` : "Domani";
  const label = date.toLocaleDateString("it-IT", { day: "numeric", month: "short" });
  return time ? `${label} ${time}` : label;
}

function renderPlannerList(body, emptyText, items) {
  body.replaceChildren();
  if (!items.length) {
    body.append(element("p", "widget-empty", emptyText));
    return;
  }
  const list = element("ul", "list");
  for (const item of items) {
    const row = element("li", "list-item");
    row.append(element("span", "list-title", item.title || "Senza titolo"));
    if (item.when) row.append(element("span", "list-when", formatWhen(item.when)));
    list.append(row);
  }
  body.append(list);
}

function mountReminders(body) {
  const render = () => renderPlannerList(
    body, "Nessun promemoria in arrivo.", upcomingItems(),
  );
  plannerListeners.add(render);
  render();
  return { refresh: loadPlanner, destroy: () => plannerListeners.delete(render) };
}

function mountTasks(body) {
  const render = () => {
    const tasks = planner.tasks
      .filter((task) => !task.completed && !task.starts_at && !task.due_date)
      .slice(0, 5)
      .map((task) => ({ title: task.title }));
    renderPlannerList(body, "Nessuna attività aperta.", tasks);
  };
  plannerListeners.add(render);
  render();
  return { refresh: loadPlanner, destroy: () => plannerListeners.delete(render) };
}

let mediaTitle = null;
let mediaSubtitle = null;
let mediaToggle = null;
let audioListeners = [];

function resetPlayer() {
  els.audio.pause();
  els.audio.removeAttribute("src");
  els.audio.load();
}

function updateMediaSession() {
  if (!("mediaSession" in navigator) || typeof MediaMetadata === "undefined") return;
  try {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: settings.streamName || "NOKK Hub",
      artist: "NOKK",
    });
  } catch {
    /* older browsers */
  }
}

function playStream() {
  if (!settings.streamUrl) return;
  if (els.audio.src !== settings.streamUrl) els.audio.src = settings.streamUrl;
  els.audio.volume = settings.volume;
  updateMediaSession();
  els.audio.play().catch(() => {
    if (mediaSubtitle) mediaSubtitle.textContent = "Impossibile riprodurre il flusso";
  });
}

function mountMedia(body) {
  const title = element("p", "media-title");
  const subtitle = element("p", "media-sub");
  const controls = element("div", "media-controls");
  const toggle = element("button", "media-toggle");
  toggle.type = "button";
  const volume = document.createElement("input");
  volume.type = "range";
  volume.className = "media-volume";
  volume.min = "0";
  volume.max = "100";
  volume.value = String(Math.round(settings.volume * 100));
  volume.setAttribute("aria-label", "Volume");
  controls.append(toggle, volume);
  body.append(title, subtitle, controls);
  mediaTitle = title;
  mediaSubtitle = subtitle;
  mediaToggle = toggle;

  const sync = () => {
    const playing = !els.audio.paused && Boolean(settings.streamUrl);
    toggle.replaceChildren(icon(playing ? "pause" : "play"));
    toggle.setAttribute("aria-label", playing ? "Pausa" : "Riproduci");
    if (!settings.streamUrl) {
      title.textContent = "Nessun flusso audio";
      subtitle.textContent = "Impostalo dalle impostazioni dell'hub";
      return;
    }
    title.textContent = settings.streamName || "Flusso audio";
    subtitle.textContent = playing ? "In riproduzione" : (els.audio.error ? "Flusso non raggiungibile" : "Pronto");
    if (playing && "mediaSession" in navigator) {
      try { navigator.mediaSession.playbackState = "playing"; } catch { /* ignore */ }
    }
  };

  toggle.addEventListener("click", () => {
    if (!settings.streamUrl) {
      openSettings();
      els.streamUrl.focus();
      return;
    }
    if (els.audio.paused) playStream();
    else els.audio.pause();
  });

  volume.addEventListener("input", () => {
    settings.volume = Number(volume.value) / 100;
    els.audio.volume = settings.volume;
    saveSettings();
  });

  const onPlay = () => sync();
  const onPause = () => sync();
  const onError = () => sync();
  audioListeners.push(["play", onPlay], ["pause", onPause], ["error", onError], ["ended", onPause]);
  for (const [event, handler] of audioListeners) els.audio.addEventListener(event, handler);

  sync();
  return {
    refresh: sync,
    destroy: () => {
      for (const [event, handler] of audioListeners) els.audio.removeEventListener(event, handler);
      audioListeners = [];
      mediaTitle = null;
      mediaSubtitle = null;
      mediaToggle = null;
    },
  };
}

/* Push to talk */

const recorderState = {
  held: false,
  busy: false,
  recorder: null,
  stream: null,
  chunks: [],
  startedAt: 0,
};

function setPttState(state, hint) {
  els.ptt.dataset.state = state;
  els.ptt.disabled = state === "thinking";
  if (hint) els.pttHint.textContent = hint;
}

function stopStream() {
  if (recorderState.stream) {
    for (const track of recorderState.stream.getTracks()) track.stop();
  }
  recorderState.stream = null;
}

function recorderOptions() {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  if (typeof MediaRecorder.isTypeSupported !== "function") return undefined;
  const type = candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate));
  return type ? { mimeType: type } : undefined;
}

function microphoneError(error) {
  if (!error || !error.name) return "Microfono non disponibile.";
  if (error.name === "NotAllowedError" || error.name === "SecurityError") {
    return "Microfono bloccato: consenti l'accesso al microfono per questa pagina.";
  }
  if (error.name === "NotFoundError") return "Nessun microfono collegato.";
  if (error.name === "NotReadableError") return "Il microfono è occupato da un'altra app.";
  return "Microfono non disponibile: controlla i permessi del browser.";
}

async function startRecording() {
  if (recorderState.busy || recorderState.recorder) return;
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    showError("Questo browser non permette la registrazione audio.");
    return;
  }
  stopSpeaking();
  setPttState("recording", "Rilascia per inviare");
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    recorderState.stream = stream;
    if (!recorderState.held) {
      stopStream();
      setPttState("idle", "Tieni premuto e parla");
      return;
    }
    const recorder = new MediaRecorder(stream, recorderOptions());
    recorderState.recorder = recorder;
    recorderState.chunks = [];
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data && event.data.size) recorderState.chunks.push(event.data);
    });
    recorder.addEventListener("stop", () => {
      const blob = new Blob(recorderState.chunks, {
        type: recorder.mimeType || "audio/webm",
      });
      const duration = Date.now() - recorderState.startedAt;
      recorderState.recorder = null;
      recorderState.chunks = [];
      stopStream();
      if (duration < 450 || blob.size < 800) {
        setPttState("idle", "Tieni premuto un attimo più a lungo");
        return;
      }
      transcribeAndAsk(blob);
    });
    recorderState.startedAt = Date.now();
    recorder.start();
    vibrate(15);
  } catch (error) {
    stopStream();
    recorderState.recorder = null;
    showError(microphoneError(error));
    setPttState("idle", "Tieni premuto e parla");
  }
}

function stopRecording() {
  recorderState.held = false;
  const recorder = recorderState.recorder;
  if (recorder && recorder.state !== "inactive") recorder.stop();
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Impossibile leggere la registrazione."));
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(blob);
  });
}

async function transcribeAndAsk(blob) {
  recorderState.busy = true;
  setPttState("transcribing", "Trascrivo…");
  try {
    const audio = await blobToBase64(blob);
    const response = await fetch("/api/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mime_type: (blob.type || "audio/webm").split(";")[0],
        audio,
      }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || "Trascrizione non riuscita.");
    const text = String(result.text || "").trim();
    if (!text) {
      setPttState("idle", "Non ho capito: riprova");
      return;
    }
    els.transcript.textContent = `Tu: ${text}`;
    await askAssistant(text);
  } catch (error) {
    showError(error.message);
    setPttState("idle", "Tieni premuto e parla");
  } finally {
    recorderState.busy = false;
  }
}

async function askAssistant(text) {
  setPttState("thinking", "Ci penso…");
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: [{ role: "user", content: text }] }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || "Richiesta non riuscita.");
  if (!result.job_id) throw new Error("Il server non ha avviato la richiesta.");
  const job = await waitForJob(result.job_id);
  showJob(job);
}

async function waitForJob(jobId) {
  const deadline = Date.now() + JOB_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const response = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
    const job = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(job.error || "Attività non trovata.");
    if (["complete", "failed", "awaiting_approval"].includes(job.status)) return job;
    await delay(JOB_POLL_MS);
  }
  throw new Error("Nessuna risposta entro due minuti.");
}

function showJob(job) {
  if (job.status === "failed") {
    showError(job.error || "Non sono riuscito a rispondere.");
  } else if (job.status === "awaiting_approval") {
    showReply("Questa richiesta ha bisogno di un'approvazione: aprila nella pagina principale di NOKK.", []);
  } else {
    showReply(job.reply || "", Array.isArray(job.artifacts) ? job.artifacts : []);
    speak(job.reply || "");
  }
  setPttState("idle", "Tieni premuto e parla");
}

function showReply(text, artifacts) {
  els.reply.classList.remove("is-error");
  els.reply.replaceChildren();
  if (text) els.reply.append(document.createTextNode(text));
  if (artifacts.length) {
    const group = element("div", "reply-attachments");
    for (const artifact of artifacts) {
      const link = document.createElement("a");
      link.className = "reply-attachment";
      link.href = artifact.url;
      link.download = artifact.filename || "";
      link.append(icon("file"), document.createTextNode(artifact.filename || "File"));
      group.append(link);
    }
    els.reply.append(group);
  }
  els.reply.scrollTop = 0;
}

function showError(message) {
  els.reply.classList.add("is-error");
  els.reply.replaceChildren(document.createTextNode(message));
}

function speak(text) {
  if (!settings.speakReplies || !("speechSynthesis" in window)) return;
  const clean = String(text || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[*_`#>]/g, "")
    .trim();
  if (!clean) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(clean.slice(0, 600));
  utterance.lang = "it-IT";
  utterance.rate = 1;
  const voice = window.speechSynthesis.getVoices().find((item) => /^it/i.test(item.lang));
  if (voice) utterance.voice = voice;
  window.speechSynthesis.speak(utterance);
}

function stopSpeaking() {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  if (els.audio && !els.audio.paused) {
    /* speaking starts from a press: pause the stream so the mic is clean */
    els.audio.pause();
  }
}

/* Settings panel */

function openSettings() {
  renderSettings();
  els.settings.hidden = false;
  els.settingsButton.setAttribute("aria-expanded", "true");
}

function closeSettings() {
  els.settings.hidden = true;
  els.settingsButton.setAttribute("aria-expanded", "false");
}

function applySettings({ rebuildPanel = false } = {}) {
  saveSettings();
  renderRails();
  if (rebuildPanel) renderSettings();
}

function renderSettings() {
  els.widgetList.replaceChildren();
  settings.layout.forEach((item, index) => {
    const row = element("div", "hub-widget-row");
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = item.enabled;
    checkbox.addEventListener("change", () => {
      item.enabled = checkbox.checked;
      applySettings();
    });
    label.append(checkbox, document.createTextNode(WIDGETS.find((widget) => widget.id === item.id)?.label || item.id));

    const side = document.createElement("select");
    side.setAttribute("aria-label", "Lato del widget");
    for (const [value, text] of [["left", "Sin."], ["right", "Des."]]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = text;
      option.selected = item.side === value;
      side.append(option);
    }
    side.addEventListener("change", () => {
      item.side = side.value;
      applySettings();
    });

    const up = element("button", "row-move", "↑");
    up.type = "button";
    up.setAttribute("aria-label", "Sposta su");
    up.disabled = index === 0;
    up.addEventListener("click", () => moveWidget(index, -1));

    const down = element("button", "row-move", "↓");
    down.type = "button";
    down.setAttribute("aria-label", "Sposta giù");
    down.disabled = index === settings.layout.length - 1;
    down.addEventListener("click", () => moveWidget(index, 1));

    row.append(label, side, up, down);
    els.widgetList.append(row);
  });
  els.streamUrl.value = settings.streamUrl;
  els.streamName.value = settings.streamName;
  els.speakReplies.checked = settings.speakReplies;
  els.themeSelect.value = currentTheme();
}

function moveWidget(index, delta) {
  const target = index + delta;
  if (target < 0 || target >= settings.layout.length) return;
  const layout = settings.layout;
  [layout[index], layout[target]] = [layout[target], layout[index]];
  applySettings({ rebuildPanel: true });
}

els.rotateButton.addEventListener("click", () => {
  const next = ROTATIONS[(ROTATIONS.indexOf(currentRotation()) + 1) % ROTATIONS.length];
  applyRotation(next);
  els.connection.textContent = next === 0 ? "pronto" : `schermo ruotato di ${next}°`;
});
applyRotation(storedRotation());
window.addEventListener("resize", updateHubLayout);
window.addEventListener("orientationchange", updateHubLayout);

els.settingsButton.addEventListener("click", openSettings);
els.settingsClose.addEventListener("click", closeSettings);
els.settings.addEventListener("click", (event) => {
  if (event.target === els.settings) closeSettings();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !els.settings.hidden) closeSettings();
});

els.streamUrl.addEventListener("change", () => {
  settings.streamUrl = normalizeStreamUrl(els.streamUrl.value);
  els.streamUrl.value = settings.streamUrl;
  resetPlayer();
  saveSettings();
  renderRails();
});
els.streamName.addEventListener("change", () => {
  settings.streamName = els.streamName.value.trim().slice(0, 60);
  els.streamName.value = settings.streamName;
  saveSettings();
  renderRails();
});
els.speakReplies.addEventListener("change", () => {
  settings.speakReplies = els.speakReplies.checked;
  saveSettings();
  if (!settings.speakReplies) stopSpeaking();
});

function currentTheme() {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function applyTheme(value) {
  const theme = value === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = theme === "light" ? "#f4f8fa" : "#191817";
}

els.themeSelect.addEventListener("change", () => {
  applyTheme(els.themeSelect.value);
  try {
    localStorage.setItem("nokk-theme", currentTheme());
  } catch {
    /* private mode */
  }
});

/* Buttons, wake lock and connectivity */

els.ptt.addEventListener("pointerdown", (event) => {
  if (event.pointerType === "mouse" && event.button !== 0) return;
  event.preventDefault();
  try { els.ptt.setPointerCapture(event.pointerId); } catch { /* ignore */ }
  recorderState.held = true;
  startRecording();
});
for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) {
  els.ptt.addEventListener(type, stopRecording);
}
els.ptt.addEventListener("contextmenu", (event) => event.preventDefault());

document.addEventListener("keydown", (event) => {
  if (event.code !== "Space" || event.repeat || !els.settings.hidden) return;
  const tag = event.target?.tagName;
  if (["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(tag)) return;
  event.preventDefault();
  recorderState.held = true;
  startRecording();
});
document.addEventListener("keyup", (event) => {
  if (event.code === "Space") stopRecording();
});

els.fullscreenButton.addEventListener("click", async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  } catch {
    /* iOS and some kiosk browsers do not allow it */
  }
});

let wakeLock = null;

async function keepAwake() {
  if (!("wakeLock" in navigator) || document.visibilityState !== "visible") return;
  try {
    wakeLock = await navigator.wakeLock.request("screen");
  } catch {
    wakeLock = null;
  }
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") {
    stopRecording();
    return;
  }
  keepAwake();
  for (const controller of controllers.values()) controller.refresh?.();
});

function updateConnection() {
  const offline = !navigator.onLine;
  els.connection.textContent = offline ? "offline" : "pronto";
  els.connection.dataset.offline = String(offline);
}

window.addEventListener("online", updateConnection);
window.addEventListener("offline", updateConnection);

/* Boot */

applyTheme(document.documentElement.dataset.theme);
renderRails();
loadPlanner();
keepAwake();
updateConnection();
setInterval(loadPlanner, PLANNER_REFRESH_MS);
