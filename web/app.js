const conversation = document.querySelector("#conversation");
const sidebar = document.querySelector("#sidebar");
const sidebarToggle = document.querySelector("#sidebar-toggle");
const sidebarClose = document.querySelector("#sidebar-close");
const sidebarBackdrop = document.querySelector("#sidebar-backdrop");
const sidebarResizer = document.querySelector("#sidebar-resizer");
const sidebarClockTime = document.querySelector("#sidebar-clock-time");
const sidebarClockDate = document.querySelector("#sidebar-clock-date");
const sidebarWeather = document.querySelector("#sidebar-weather");
const sidebarWeatherTemperature = document.querySelector("#sidebar-weather-temperature");
const sidebarWeatherDetail = document.querySelector("#sidebar-weather-detail");
const mobileSidebarQuery = window.matchMedia("(max-width: 820px)");
const tabletWindowQuery = window.matchMedia("(max-width: 1366px) and (any-pointer: coarse)");
const welcome = document.querySelector("#welcome");
const chatForm = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const settingsOverlay = document.querySelector("#settings-overlay");
const settingsForm = document.querySelector("#settings-form");
const settingsError = document.querySelector("#settings-error");
const settingsSave = document.querySelector("#settings-save");
const settingsTabs = [...document.querySelectorAll("[data-settings-tab]")];
const settingsPanels = document.querySelector(".settings-panels");
const telegramStatus = document.querySelector("#telegram-status");
const telegramTokenInput = document.querySelector("#telegram-token");
const telegramConnectButton = document.querySelector("#telegram-connect");
const telegramPairButton = document.querySelector("#telegram-pair");
const telegramDisconnectButton = document.querySelector("#telegram-disconnect");
const telegramPairCode = document.querySelector("#telegram-pair-code");
const telegramReminderEnabled = document.querySelector("#telegram-reminder-enabled");
const telegramReminderTime = document.querySelector("#telegram-reminder-time");
const telegramReminderSave = document.querySelector("#telegram-reminder-save");
const googleCalendarStatus = document.querySelector("#google-calendar-status");
const googleClientIdInput = document.querySelector("#google-client-id");
const googleClientSecretInput = document.querySelector("#google-client-secret");
const googleCalendarIdInput = document.querySelector("#google-calendar-id");
const googleCalendarSaveButton = document.querySelector("#google-calendar-save");
const googleCalendarConnectButton = document.querySelector("#google-calendar-connect");
const googleCalendarDisconnectButton = document.querySelector("#google-calendar-disconnect");
const googleCalendarRedirectHelp = document.querySelector("#google-redirect-help");
const providerSelect = document.querySelector("#provider");
const modelInput = document.querySelector("#model");
const modelHelp = document.querySelector("#model-help");
const systemPromptInput = document.querySelector("#system-prompt");
const apiKeyHelp = document.querySelector("#api-key-help");
const apiKeyInput = document.querySelector("#api-key");
const baseUrlInput = document.querySelector("#base-url");
const baseUrlLabel = document.querySelector("#base-url-label");
const baseUrlHelp = document.querySelector("#base-url-help");
const terminalEnabledInput = document.querySelector("#terminal-enabled");
const approvalModeSelect = document.querySelector("#approval-mode");
const workspaceInput = document.querySelector("#workspace");
const pageTitle = document.querySelector("#page-title");
const connectionLabel = document.querySelector("#connection-label");
const newChatButton = document.querySelector("#new-chat");
const workflowsToggle = document.querySelector("#workflows-toggle");
const workflowPanel = document.querySelector("#workflow-panel");
const workflowList = document.querySelector("#workflow-list");
const workflowEmpty = document.querySelector("#workflow-empty");
const workflowOverlay = document.querySelector("#workflow-overlay");
const workflowForm = document.querySelector("#workflow-form");
const workflowNameInput = document.querySelector("#workflow-name");
const workflowPromptInput = document.querySelector("#workflow-prompt");
const workflowError = document.querySelector("#workflow-error");
const workflowSave = document.querySelector("#workflow-save");
const workflowTitle = document.querySelector("#workflow-form-title");
const workflowScheduleEnabled = document.querySelector("#workflow-schedule-enabled");
const workflowScheduleTime = document.querySelector("#workflow-schedule-time");
const workflowDayInputs = [...document.querySelectorAll(".workflow-day input")];
const wakePhraseInput = document.querySelector("#wake-phrase");
const ttsAutoPlayInput = document.querySelector("#tts-auto-play");
const notificationsInput = document.querySelector("#notifications-enabled");
const alertsEnabledInput = document.querySelector("#alerts-enabled");
const alertsDiskInput = document.querySelector("#alerts-disk-percent");
const alertsMemoryInput = document.querySelector("#alerts-memory-percent");
const weatherEnabledInput = document.querySelector("#weather-enabled");
const weatherCityInput = document.querySelector("#weather-city");
const exportDataButton = document.querySelector("#export-data");
const themeToggle = document.querySelector("#theme-toggle");
const launcherOverlay = document.querySelector("#launcher-overlay");
const launcherInput = document.querySelector("#launcher-input");
const launcherResults = document.querySelector("#launcher-results");
const desktopWorkspace = document.querySelector("#desktop-workspace");
const appWindows = document.querySelector("#app-windows");
const windowDock = document.querySelector("#window-dock");
const fileInput = document.querySelector("#file-input");
const attachButton = document.querySelector("#attach-button");
const attachmentList = document.querySelector("#attachment-list");
const voiceStatus = document.querySelector("#voice-status");
const micToggle = document.querySelector("#mic-toggle");
const wakeToggle = document.querySelector("#wake-toggle");
const SpeechRecognitionAPI = window.SpeechRecognition
  || window.webkitSpeechRecognition
  || null;
const messages = [];
let configured = false;
let sending = false;
let workflows = [];
let editingWorkflowId = null;
let voiceRecognition = null;
let voiceMode = null;
let wakeListeningRequested = false;
let wakeTriggered = false;
let wakeRestartTimer = null;
let wakeRetryCount = 0;
let pendingAttachments = [];
let planner = { events: [], tasks: [] };
let taskFilter = "open";
let taskQuery = "";
let telegramAuthorizedChatCount = 0;
let telegramStatusTimer = null;
let launcherSelection = 0;
let visibleLauncherItems = [];
let windowZIndex = 5;
let calendarMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
let selectedCalendarDate = dateKey(new Date());
const openWindows = new Map();

function setSidebarOpen(open) {
  const isOpen = Boolean(open) && mobileSidebarQuery.matches;
  document.body.classList.toggle("sidebar-open", isOpen);
  sidebarToggle.setAttribute("aria-expanded", String(isOpen));
  sidebarBackdrop.hidden = !isOpen;
}

const SIDEBAR_WIDTH_KEY = "nokk-sidebar-width";
const SIDEBAR_MIN_WIDTH = 220;
const SIDEBAR_MAX_WIDTH = 460;
const SIDEBAR_DEFAULT_WIDTH = 252;

function sidebarWidth(value) {
  const width = Number(value);
  if (!Number.isFinite(width)) return SIDEBAR_DEFAULT_WIDTH;
  return Math.round(Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, width)));
}

function applySidebarWidth(value, persist = false) {
  const width = sidebarWidth(value);
  sidebar.style.setProperty("--sidebar-width", `${width}px`);
  sidebarResizer.setAttribute("aria-valuenow", String(width));
  if (persist) {
    try {
      localStorage.setItem(SIDEBAR_WIDTH_KEY, String(width));
    } catch (error) {
      console.warn("Preferenza larghezza menu non disponibile:", error);
    }
  }
  return width;
}

try {
  const savedSidebarWidth = localStorage.getItem(SIDEBAR_WIDTH_KEY);
  if (savedSidebarWidth !== null) applySidebarWidth(savedSidebarWidth);
} catch (error) {
  console.warn("Preferenza larghezza menu non disponibile:", error);
}

let sidebarDragging = false;

sidebarResizer.addEventListener("pointerdown", (event) => {
  if (mobileSidebarQuery.matches || event.button !== 0) return;
  event.preventDefault();
  const startX = event.clientX;
  const startWidth = sidebar.getBoundingClientRect().width;
  sidebarDragging = true;
  document.body.classList.add("sidebar-resizing");

  const move = (moveEvent) => {
    if (!sidebarDragging) return;
    applySidebarWidth(startWidth + moveEvent.clientX - startX);
  };
  const stop = () => {
    if (!sidebarDragging) return;
    sidebarDragging = false;
    document.body.classList.remove("sidebar-resizing");
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", stop);
    window.removeEventListener("pointercancel", stop);
    applySidebarWidth(sidebar.getBoundingClientRect().width, true);
  };

  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", stop);
  window.addEventListener("pointercancel", stop);
});

sidebarResizer.addEventListener("keydown", (event) => {
  if (mobileSidebarQuery.matches) return;
  const current = sidebar.getBoundingClientRect().width;
  let next = null;
  if (event.key === "ArrowLeft") next = current - 16;
  else if (event.key === "ArrowRight") next = current + 16;
  else if (event.key === "Home") next = SIDEBAR_MIN_WIDTH;
  else if (event.key === "End") next = SIDEBAR_MAX_WIDTH;
  if (next === null) return;
  event.preventDefault();
  applySidebarWidth(next, true);
});

sidebarResizer.addEventListener("dblclick", () => {
  if (!mobileSidebarQuery.matches) {
    applySidebarWidth(SIDEBAR_DEFAULT_WIDTH, true);
  }
});

const sidebarClockFormatter = new Intl.DateTimeFormat("it-IT", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

function updateSidebarClock() {
  const now = new Date();
  sidebarClockTime.textContent = now.toLocaleTimeString("it-IT", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  sidebarClockTime.dateTime = now.toISOString();
  sidebarClockDate.textContent = sidebarClockFormatter.format(now);
}

updateSidebarClock();
window.setInterval(updateSidebarClock, 1000);

const textFileExtensions = new Set([
  ".txt", ".md", ".csv", ".json", ".log", ".py", ".js", ".ts",
  ".html", ".css", ".xml", ".yaml", ".yml", ".toml", ".ini", ".sql",
  ".sh",
]);
const imageMimeTypes = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
};
const maxUploadBytes = 4 * 1024 * 1024;
const maxAttachmentsPerMessage = 5;

const providerDefaults = {
  openai: "gpt-4o-mini",
  anthropic: "claude-3-5-haiku-latest",
  google: "gemini-2.0-flash",
  mistral: "mistral-small-latest",
  groq: "llama-3.3-70b-versatile",
  deepseek: "deepseek-chat",
  xai: "grok-2-latest",
  openrouter: "openrouter/free",
  custom: "",
};

const providerLabels = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  google: "Google Gemini",
  mistral: "Mistral AI",
  groq: "Groq",
  deepseek: "DeepSeek",
  xai: "xAI (Grok)",
  openrouter: "OpenRouter gratuito",
  custom: "API compatibile OpenAI",
};

let configuredProviders = new Set();
let savedModels = {};

function apiKeyPlaceholder(provider) {
  return configuredProviders.has(provider)
    ? "Chiave salvata per questo provider · lascia vuoto per mantenerla"
    : "Incolla la chiave API";
}

function modelForProvider(provider) {
  if (provider === "openrouter") return providerDefaults.openrouter;
  return savedModels[provider] || providerDefaults[provider] || "";
}

function updateProviderFields() {
  const provider = providerSelect.value;
  const isOpenRouter = provider === "openrouter";
  const isCustom = provider === "custom";
  modelInput.value = modelForProvider(provider);
  modelInput.readOnly = isOpenRouter;
  baseUrlLabel.hidden = !isCustom;
  baseUrlInput.hidden = !isCustom;
  baseUrlHelp.hidden = !isCustom;
  baseUrlInput.required = isCustom;
  if (isOpenRouter) {
    modelHelp.textContent = "OpenRouter sceglie automaticamente un modello gratuito disponibile. Non usa modelli a pagamento.";
  } else if (isCustom) {
    modelHelp.textContent = "Scrivi il nome del modello accettato dall'endpoint personalizzato.";
  } else {
    modelHelp.textContent = "Il nome deve corrispondere a un modello disponibile nel tuo account.";
  }
  if (isOpenRouter) {
    apiKeyHelp.textContent = "Crea una chiave su openrouter.ai/keys. Non inserirla in una chat. La chiave resta salvata per ogni provider.";
  } else if (isCustom) {
    apiKeyHelp.textContent = "La chiave del servizio compatibile OpenAI. Resta salvata per ogni provider e non viene mai mostrata.";
  } else {
    apiKeyHelp.textContent = "Non inserire la chiave in una chat. Le chiamate al provider partono dal backend. La chiave resta salvata per ogni provider.";
  }
  apiKeyInput.placeholder = apiKeyPlaceholder(provider);
}

function activateSettingsTab(name = "", { focus = false } = {}) {
  const target = settingsTabs.find((tab) => tab.dataset.settingsTab === name)
    || settingsTabs.find((tab) => tab.textContent.includes(name))
    || settingsTabs.find((tab) => tab.getAttribute("aria-selected") === "true")
    || settingsTabs[0];
  if (!target) return;
  for (const tab of settingsTabs) {
    const selected = tab === target;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    const panel = document.getElementById(tab.getAttribute("aria-controls"));
    if (panel) panel.hidden = !selected;
  }
  if (settingsPanels) settingsPanels.scrollTop = 0;
  if (focus) {
    const panel = document.getElementById(target.getAttribute("aria-controls"));
    const firstField = panel?.querySelector("input:not([type=hidden]), select, textarea");
    (firstField || target).focus();
  }
}

function openSettings(sectionName = "") {
  settingsError.hidden = true;
  settingsOverlay.hidden = false;
  activateSettingsTab(sectionName, { focus: true });
}

function closeSettings() {
  settingsOverlay.hidden = true;
}

function openWorkflowEditor(workflow = null) {
  editingWorkflowId = workflow?.id || null;
  workflowTitle.textContent = workflow ? "Modifica procedura" : "Nuova procedura";
  workflowNameInput.value = workflow?.name || "";
  workflowPromptInput.value = workflow?.prompt || "";
  workflowScheduleEnabled.checked = Boolean(workflow?.schedule_enabled);
  workflowScheduleTime.value = workflow?.schedule_time || "07:00";
  const scheduleDays = new Set(
    workflow ? (workflow.schedule_days || []) : [0, 1, 2, 3, 4]
  );
  workflowDayInputs.forEach((dayInput) => {
    dayInput.checked = scheduleDays.has(Number(dayInput.value));
  });
  workflowError.hidden = true;
  workflowOverlay.hidden = false;
  workflowNameInput.focus();
}

function closeWorkflowEditor() {
  workflowOverlay.hidden = true;
  editingWorkflowId = null;
}

function setWorkflowPanelVisible(visible) {
  if (visible) openApplicationWindow("workflows");
  else closeApplicationWindow("workflows");
  workflowsToggle.setAttribute("aria-expanded", String(visible));
}

function makeElement(tag, className = "", text = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}

function iconElement(name, className = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", `icon${className ? ` ${className}` : ""}`);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

function setIcon(element, name) {
  const use = element?.querySelector("use");
  if (use) use.setAttribute("href", `#i-${name}`);
}

function focusApplicationWindow(windowElement) {
  if (tabletWindowQuery.matches) {
    for (const other of openWindows.values()) {
      if (other !== windowElement) other.classList.add("is-minimized");
    }
  }
  windowZIndex += 1;
  windowElement.style.zIndex = String(windowZIndex);
  windowElement.classList.remove("is-minimized");
  renderWindowDock();
}

function renderWindowDock() {
  windowDock.replaceChildren();
  for (const [appId, windowElement] of openWindows) {
    if (!windowElement.classList.contains("is-minimized")) continue;
    const restore = makeElement("button", "window-dock-item", windowElement.dataset.title);
    restore.type = "button";
    restore.setAttribute("aria-label", `Ripristina ${windowElement.dataset.title}`);
    restore.addEventListener("click", () => focusApplicationWindow(windowElement));
    windowDock.append(restore);
  }
}

function closeApplicationWindow(appId) {
  const windowElement = openWindows.get(appId);
  if (!windowElement) return;
  if (appId === "workflows") {
    workflowPanel.hidden = true;
    workflowPanel.classList.remove("inside-window");
    document.querySelector(".main").append(workflowPanel);
    workflowsToggle.setAttribute("aria-expanded", "false");
  }
  windowElement.remove();
  openWindows.delete(appId);
  renderWindowDock();
}

function toggleMaximized(windowElement) {
  windowElement.classList.toggle("is-maximized");
  const maximize = windowElement.querySelector('[data-window-action="maximize"]');
  const isMaximized = windowElement.classList.contains("is-maximized");
  setIcon(maximize, isMaximized ? "restore" : "maximize");
  maximize.setAttribute("aria-label", isMaximized ? "Riduci finestra" : "Ingrandisci finestra");
}

function enableWindowDragging(windowElement, titlebar) {
  if (tabletWindowQuery.matches) return;
  titlebar.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target.closest("button")) return;
    if (windowElement.classList.contains("is-maximized")) return;
    const windowRect = windowElement.getBoundingClientRect();
    const workspaceRect = desktopWorkspace.getBoundingClientRect();
    const startX = event.clientX;
    const startY = event.clientY;
    const startLeft = windowRect.left - workspaceRect.left;
    const startTop = windowRect.top - workspaceRect.top;
    titlebar.setPointerCapture(event.pointerId);
    function move(moveEvent) {
      if (moveEvent.pointerId !== event.pointerId) return;
      const maxLeft = Math.max(0, workspaceRect.width - windowElement.offsetWidth);
      const maxTop = Math.max(0, workspaceRect.height - windowElement.offsetHeight);
      windowElement.style.left = `${Math.max(0, Math.min(maxLeft, startLeft + moveEvent.clientX - startX))}px`;
      windowElement.style.top = `${Math.max(0, Math.min(maxTop, startTop + moveEvent.clientY - startY))}px`;
    }
    function stop(stopEvent) {
      if (stopEvent.pointerId !== event.pointerId) return;
      titlebar.removeEventListener("pointermove", move);
      titlebar.removeEventListener("pointerup", stop);
      titlebar.removeEventListener("pointercancel", stop);
    }
    titlebar.addEventListener("pointermove", move);
    titlebar.addEventListener("pointerup", stop);
    titlebar.addEventListener("pointercancel", stop);
  });
}

function createApplicationWindow(appId, title) {
  const windowElement = makeElement("section", "app-window");
  windowElement.dataset.app = appId;
  windowElement.dataset.title = title;
  windowElement.setAttribute("role", "dialog");
  windowElement.setAttribute("aria-label", title);
  const titlebar = makeElement("header", "app-window-titlebar");
  const heading = makeElement("h2", "", title);
  const controls = makeElement("div", "app-window-controls");
  for (const [action, icon, label] of [
    ["minimize", "minus", "Riduci a icona"],
    ["maximize", "maximize", "Ingrandisci finestra"],
    ["close", "close", "Chiudi finestra"],
  ]) {
    const control = makeElement("button", `window-control window-${action}`);
    control.append(iconElement(icon));
    control.type = "button";
    control.dataset.windowAction = action;
    control.setAttribute("aria-label", label);
    control.addEventListener("click", () => {
      if (action === "close") closeApplicationWindow(appId);
      if (action === "maximize") toggleMaximized(windowElement);
      if (action === "minimize") {
        windowElement.classList.add("is-minimized");
        renderWindowDock();
      }
    });
    controls.append(control);
  }
  titlebar.append(heading, controls);
  const content = makeElement("div", "app-window-content");
  windowElement.append(titlebar, content);
  const workspaceRect = desktopWorkspace.getBoundingClientRect();
  const width = Math.min(850, workspaceRect.width - 32);
  const height = Math.min(650, workspaceRect.height - 32);
  windowElement.style.width = `${Math.max(280, width)}px`;
  windowElement.style.height = `${Math.max(250, height)}px`;
  windowElement.style.left = `${Math.max(16, (workspaceRect.width - width) / 2 + openWindows.size * 24)}px`;
  windowElement.style.top = `${Math.max(16, (workspaceRect.height - height) / 2 + openWindows.size * 22)}px`;
  windowElement.addEventListener("pointerdown", () => focusApplicationWindow(windowElement));
  enableWindowDragging(windowElement, titlebar);
  appWindows.append(windowElement);
  focusApplicationWindow(windowElement);
  openWindows.set(appId, windowElement);
  return content;
}

function openApplicationWindow(appId) {
  launcherOverlay.hidden = true;
  if (appId === "settings") {
    openSettings();
    return;
  }
  if (appId === "chat") {
    for (const windowElement of openWindows.values()) {
      windowElement.classList.add("is-minimized");
    }
    renderWindowDock();
    input.focus();
    return;
  }
  if (openWindows.has(appId)) {
    focusApplicationWindow(openWindows.get(appId));
    return;
  }
  const titles = {
    functions: "Funzioni",
    calendar: "Calendario",
    tasks: "Attività",
    workflows: "Procedure",
    machine: "Stato della macchina",
  };
  const content = createApplicationWindow(appId, titles[appId]);
  if (appId === "workflows") {
    workflowPanel.hidden = false;
    workflowPanel.classList.add("inside-window");
    content.append(workflowPanel);
    workflowsToggle.setAttribute("aria-expanded", "true");
    return;
  }
  if (appId === "functions") {
    renderFunctionsWindow(content);
    return;
  }
  if (appId === "calendar" || appId === "tasks") {
    content.append(makeElement("p", "planner-loading", "Caricamento…"));
    loadPlanner().then(() => renderPlannerWindows()).catch((error) => {
      renderWindowError(content, error.message);
    });
    return;
  }
  if (appId === "machine") loadMachineWindow(content);
}

function renderWindowError(container, message) {
  container.replaceChildren(makeElement("p", "window-error", message));
}

function renderFunctionsWindow(container) {
  const heading = makeElement("div", "planner-app-heading");
  heading.append(
    makeElement("div", "", ""),
  );
  heading.firstChild.append(
    makeElement("p", "eyebrow", "APPLICAZIONI E STRUMENTI"),
    makeElement("h3", "", "Funzioni"),
  );
  const grid = makeElement("div", "function-grid");
  const functions = [
    ["Chat", "Conversazione, voce e allegati", "chat", "chat"],
    ["Calendario", "Appuntamenti e date", "calendar", "calendar"],
    ["Attività", "Elenco cose da fare", "tasks", "tasks"],
    ["Procedure", "Istruzioni riutilizzabili", "workflows", "workflows"],
    ["Stato macchina", "Memoria e risorse locali", "machine", "machine"],
    ["Impostazioni", "Connessione e preferenze", "settings", "settings"],
  ];
  for (const [title, description, appId, icon] of functions) {
    const launch = makeElement("button", "function-card");
    launch.type = "button";
    const cardIcon = makeElement("span", "function-card-icon");
    cardIcon.append(iconElement(icon));
    launch.append(
      cardIcon,
      makeElement("strong", "", title),
      makeElement("small", "", description),
    );
    launch.addEventListener("click", () => openApplicationWindow(appId));
    grid.append(launch);
  }
  const voice = makeElement("button", "function-card");
  voice.type = "button";
  const voiceIcon = makeElement("span", "function-card-icon");
  voiceIcon.append(iconElement("wake"));
  voice.append(
    voiceIcon,
    makeElement("strong", "", "Voce"),
    makeElement("small", "", "Wake word e sintesi vocale"),
  );
  voice.addEventListener("click", () => openSettings("Voce"));
  grid.append(voice);
  const attachments = makeElement("button", "function-card");
  attachments.type = "button";
  const attachIcon = makeElement("span", "function-card-icon");
  attachIcon.append(iconElement("plus"));
  attachments.append(
    attachIcon,
    makeElement("strong", "", "Allega file"),
    makeElement("small", "", "Aggiungi documenti e immagini"),
  );
  attachments.addEventListener("click", () => {
    if (attachButton.disabled) openSettings();
    else attachButton.click();
  });
  grid.append(attachments);
  container.replaceChildren(heading, grid);
}

function dateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function openLauncher() {
  launcherOverlay.hidden = false;
  launcherInput.value = "";
  launcherSelection = 0;
  renderLauncherResults();
  launcherInput.focus();
}

function closeLauncher() {
  launcherOverlay.hidden = true;
  launcherInput.value = "";
}

const appIconNames = {
  chat: "chat",
  calendar: "calendar",
  tasks: "tasks",
  workflows: "workflows",
  machine: "machine",
  settings: "settings",
  functions: "sparkle",
};

function launcherCatalog() {
  const entries = [
    { title: "Funzioni", hint: "Esplora applicazioni e strumenti", keywords: "applicazioni apps strumenti", app: "functions" },
    { title: "Chat", hint: "Torna alla conversazione", keywords: "messaggi assistente NOKK", app: "chat" },
    { title: "Calendario", hint: "Apri eventi e appuntamenti", keywords: "agenda appuntamento data", app: "calendar" },
    { title: "Nuovo evento", hint: "Aggiungi un appuntamento", keywords: "calendario crea aggiungi", app: "calendar", focus: "#event-title" },
    { title: "Attività", hint: "Apri la lista delle cose da fare", keywords: "todo task tasks checklist", app: "tasks" },
    { title: "Nuova attività", hint: "Aggiungi una cosa da fare", keywords: "todo task crea aggiungi", app: "tasks", focus: "#task-title" },
    { title: "Procedure", hint: "Apri le istruzioni salvate", keywords: "workflow workflows", app: "workflows" },
    { title: "Nuova procedura", hint: "Crea istruzioni riutilizzabili", keywords: "workflow crea", run: () => {
      openApplicationWindow("workflows");
      openWorkflowEditor();
    } },
    { title: "Stato della macchina", hint: "Memoria, spazio disco e sistema", keywords: "computer sistema risorse cpu ram disco hardware", app: "machine" },
    { title: "Impostazioni", hint: "Configura NOKK", keywords: "preferenze configurazione settings settaggi", app: "settings" },
    { title: "Connessione AI", hint: "Provider, modello e chiave", keywords: "impostazioni api provider modello", app: "settings", section: "Connessione AI" },
    { title: "Personalità", hint: "Istruzioni permanenti", keywords: "impostazioni prompt personalità", app: "settings", section: "Personalità" },
    { title: "Voce", hint: "Wake word e sintesi vocale", keywords: "impostazioni microfono wake word voce", app: "settings", section: "Voce" },
    { title: "Strumenti", hint: "Terminale e cartella di lavoro", keywords: "impostazioni terminale workspace", app: "settings", section: "Strumenti" },
    { title: "Telegram", hint: "Bot, promemoria e comandi", keywords: "telegram bot promemoria orario chat notifiche collegamento", app: "settings", section: "Telegram", icon: "chat" },
    { title: "Dati e notifiche", hint: "Meteo, avvisi macchina e notifiche", keywords: "dati notifiche meteo città avvisi disco memoria soglie", app: "settings", section: "Dati e notifiche", icon: "weather" },
    { title: "Google Calendar", hint: "Collega gli appuntamenti", keywords: "google calendar agenda sincronizza appuntamenti", app: "settings", section: "Google Calendar", icon: "calendar" },
    { title: "Promemoria", hint: "Orario di materie e scadenze su Telegram", keywords: "promemoria orario materie scadenze anticipo telegram", app: "settings", section: "Telegram", icon: "calendar" },
    { title: "Meteo in sidebar", hint: "Attiva il meteo e scegli la città", keywords: "meteo temperatura città previsioni sidebar orologio", app: "settings", section: "Dati e notifiche", icon: "weather" },
    { title: "Avvisi macchina", hint: "Soglie di disco e memoria su Telegram", keywords: "avvisi macchina disco memoria soglie telegram notifiche", app: "settings", section: "Dati e notifiche", icon: "machine" },
    { title: "Profilo e memoria", hint: "Le informazioni che NOKK ricorda", keywords: "memoria profilo per nokk ricordi informazioni personali contesto", icon: "memory", run: () => window.nokkOpenMemory?.() },
    { title: "Tema", hint: "Alterna tema chiaro e scuro", keywords: "aspetto colori scuro chiaro", run: () => themeToggle.click() },
    { title: "Nuova chat", hint: "Azzera la conversazione corrente", keywords: "nuova chat azzera pulisci reset", run: () => newChatButton.click() },
    { title: "Esporta backup", hint: "Scarica tutti i dati in JSON", keywords: "backup esporta dati salva json", run: () => exportData().catch((error) => window.alert(error.message)) },
    { title: "Esporta calendario", hint: "Scarica il file .ics", keywords: "calendario ics esporta agenda", run: () => { window.location.href = "/api/calendar.ics"; } },
    { title: "Aggiorna meteo", hint: "Ricarica la temperatura in sidebar", keywords: "meteo temperatura aggiorna", run: () => refreshWeather() },
  ];
  for (const workflow of workflows) {
    entries.push({
      title: `Procedura: ${workflow.name}`,
      hint: "Inserisci le istruzioni nella chat",
      keywords: workflow.prompt,
      run: () => {
        input.value = workflow.prompt;
        resizeComposer();
        welcome.hidden = true;
        openApplicationWindow("chat");
      },
    });
  }
  return entries;
}

function launcherMatches(item, terms) {
  const words = `${item.title} ${item.hint} ${item.keywords}`
    .toLocaleLowerCase("it")
    .split(/[^a-zà-ÿ0-9]+/)
    .filter(Boolean);
  return terms.every((term) => words.some((word) => word.startsWith(term)));
}

function launcherScore(item, terms) {
  const title = item.title.toLocaleLowerCase("it");
  return terms.filter((term) => !title.includes(term)).length;
}

function renderLauncherResults() {
  const query = launcherInput.value.trim().toLocaleLowerCase("it");
  const terms = query.split(/\s+/).filter(Boolean);
  visibleLauncherItems = launcherCatalog()
    .filter((item) => launcherMatches(item, terms))
    .sort((left, right) => launcherScore(left, terms) - launcherScore(right, terms))
    .slice(0, 12);
  launcherSelection = Math.min(launcherSelection, Math.max(0, visibleLauncherItems.length - 1));
  launcherResults.replaceChildren();
  visibleLauncherItems.forEach((item, index) => {
    const result = makeElement("button", "launcher-result");
    result.type = "button";
    result.setAttribute("role", "option");
    result.setAttribute("aria-selected", String(index === launcherSelection));
    const text = makeElement("span", "launcher-result-copy");
    text.append(makeElement("strong", "", item.title), makeElement("small", "", item.hint));
    const entryIcon = makeElement("span", "launcher-result-icon");
    entryIcon.append(iconElement(item.icon || appIconNames[item.app] || (item.run ? "sparkle" : "arrow-right")));
    result.append(entryIcon, text);
    result.addEventListener("click", () => runLauncherItem(item));
    result.addEventListener("pointermove", () => {
      launcherSelection = index;
      updateLauncherSelection();
    });
    launcherResults.append(result);
  });
  if (visibleLauncherItems.length === 0) {
    launcherResults.append(makeElement("p", "launcher-empty", "Nessun risultato."));
  }
}

function updateLauncherSelection() {
  for (const [index, result] of [...launcherResults.querySelectorAll(".launcher-result")].entries()) {
    result.setAttribute("aria-selected", String(index === launcherSelection));
  }
}

function runLauncherItem(item) {
  closeLauncher();
  if (item.run) {
    item.run();
    return;
  }
  if (item.app === "settings") {
    openSettings(item.section);
    return;
  }
  openApplicationWindow(item.app);
  if (item.focus) {
    window.setTimeout(() => document.querySelector(item.focus)?.focus(), 0);
  }
}

function handleLauncherKeys(event) {
  if (event.key === "Escape") {
    closeLauncher();
    return;
  }
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    if (visibleLauncherItems.length === 0) return;
    event.preventDefault();
    const step = event.key === "ArrowDown" ? 1 : -1;
    launcherSelection = (launcherSelection + step + visibleLauncherItems.length) % visibleLauncherItems.length;
    updateLauncherSelection();
  } else if (event.key === "Enter" && visibleLauncherItems[launcherSelection]) {
    event.preventDefault();
    runLauncherItem(visibleLauncherItems[launcherSelection]);
  }
}

async function loadPlanner() {
  const response = await fetch("/api/planner");
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Calendario e attività non disponibili.");
  planner = result;
  checkPlannerNotifications();
}

async function refreshNokkData() {
  await loadPlanner();
  renderPlannerWindows();
  const response = await fetch("/api/config");
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Sezioni NOKK non aggiornate.");
  workflows = result.workflows || [];
  renderWorkflows();
  if (openWindows.has("machine")) {
    await loadMachineWindow(openWindows.get("machine").lastElementChild);
  }
}

async function savePlannerItem(kind, item) {
  const response = await fetch("/api/planner", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "save", kind, ...item }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Salvataggio non riuscito.");
  planner = result;
  renderPlannerWindows();
}

async function deletePlannerItem(kind, id) {
  const response = await fetch("/api/planner", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "delete", kind, id }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Eliminazione non riuscita.");
  planner = result;
  renderPlannerWindows();
}

function renderPlannerWindows() {
  for (const appId of ["calendar", "tasks"]) {
    const windowElement = openWindows.get(appId);
    if (!windowElement) continue;
    const content = windowElement.querySelector(".app-window-content");
    if (appId === "calendar") renderCalendarApp(content);
    else renderTasksApp(content);
  }
}

function renderCalendarApp(container) {
  container.replaceChildren();
  const toolbar = makeElement("div", "calendar-toolbar");
  const previous = makeElement("button", "calendar-nav", "‹");
  previous.type = "button";
  previous.setAttribute("aria-label", "Mese precedente");
  previous.addEventListener("click", () => {
    calendarMonth = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() - 1, 1);
    selectedCalendarDate = dateKey(calendarMonth);
    renderCalendarWindows();
  });
  const monthTitle = makeElement(
    "h3",
    "",
    calendarMonth.toLocaleDateString("it-IT", { month: "long", year: "numeric" }),
  );
  const next = makeElement("button", "calendar-nav", "›");
  next.type = "button";
  next.setAttribute("aria-label", "Mese successivo");
  next.addEventListener("click", () => {
    calendarMonth = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() + 1, 1);
    selectedCalendarDate = dateKey(calendarMonth);
    renderCalendarWindows();
  });
  const today = makeElement("button", "calendar-today", "Oggi");
  today.type = "button";
  today.addEventListener("click", () => {
    calendarMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
    selectedCalendarDate = dateKey(new Date());
    renderCalendarWindows();
  });
  const exportIcs = makeElement("a", "calendar-export", "Esporta .ics");
  exportIcs.href = "/api/calendar.ics";
  exportIcs.download = "nokk-calendario.ics";
  toolbar.append(previous, monthTitle, next, today, exportIcs);

  const calendar = makeElement("div", "calendar-grid");
  calendar.setAttribute("role", "grid");
  for (const day of ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]) {
    calendar.append(makeElement("span", "calendar-weekday", day));
  }
  const firstDay = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth(), 1);
  const start = new Date(firstDay.getFullYear(), firstDay.getMonth(), 1 - ((firstDay.getDay() + 6) % 7));
  const eventDates = new Set(planner.events.map((event) => event.starts_at.slice(0, 10)));
  for (let offset = 0; offset < 42; offset += 1) {
    const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + offset);
    const key = dateKey(date);
    const dayButton = makeElement("button", "calendar-day", String(date.getDate()));
    dayButton.type = "button";
    dayButton.setAttribute("role", "gridcell");
    dayButton.setAttribute("aria-label", date.toLocaleDateString("it-IT", {
      weekday: "long", day: "numeric", month: "long", year: "numeric",
    }));
    if (date.getMonth() !== calendarMonth.getMonth()) dayButton.classList.add("outside-month");
    if (key === selectedCalendarDate) dayButton.classList.add("selected");
    if (key === dateKey(new Date())) dayButton.classList.add("today");
    if (eventDates.has(key)) dayButton.classList.add("has-event");
    dayButton.addEventListener("click", () => {
      selectedCalendarDate = key;
      renderCalendarWindows();
    });
    calendar.append(dayButton);
  }

  const selectedDate = makeElement(
    "h4",
    "planner-section-title",
    new Date(
      Number(selectedCalendarDate.slice(0, 4)),
      Number(selectedCalendarDate.slice(5, 7)) - 1,
      Number(selectedCalendarDate.slice(8, 10)),
    ).toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" }),
  );
  const eventList = makeElement("div", "planner-list");
  const dayEvents = planner.events
    .filter((event) => event.starts_at.startsWith(selectedCalendarDate))
    .sort((left, right) => left.starts_at.localeCompare(right.starts_at));
  if (dayEvents.length === 0) eventList.append(makeElement("p", "planner-empty", "Nessun appuntamento in questa data."));
  for (const event of dayEvents) {
    const row = makeElement("article", "planner-item");
    const eventTime = makeElement("time", "planner-item-time", event.starts_at.slice(11, 16));
    const details = makeElement("div", "planner-item-details");
    details.append(makeElement("strong", "", event.title));
    if (event.description) details.append(makeElement("p", "", event.description));
    const remove = makeElement("button", "planner-delete", "Elimina");
    remove.type = "button";
    remove.addEventListener("click", async () => {
      try {
        await deletePlannerItem("event", event.id);
      } catch (error) {
        window.alert(error.message);
      }
    });
    row.append(eventTime, details, remove);
    eventList.append(row);
  }

  const form = makeElement("form", "planner-form calendar-event-form");
  form.append(makeElement("h4", "planner-section-title", "Nuovo appuntamento"));
  const titleLabel = makeElement("label", "", "Titolo");
  const title = makeElement("input");
  title.id = "event-title";
  title.name = "title";
  title.maxLength = 160;
  title.required = true;
  title.placeholder = "Es. Riunione";
  titleLabel.append(title);
  const datetimeLabel = makeElement("label", "", "Data e ora");
  const startsAt = makeElement("input");
  startsAt.type = "datetime-local";
  startsAt.name = "starts_at";
  startsAt.value = `${selectedCalendarDate}T09:00`;
  startsAt.required = true;
  datetimeLabel.append(startsAt);
  const descriptionLabel = makeElement("label", "", "Note");
  const description = makeElement("textarea");
  description.name = "description";
  description.maxLength = 2000;
  description.rows = 2;
  description.placeholder = "Dettagli facoltativi";
  descriptionLabel.append(description);
  const error = makeElement("p", "planner-error");
  error.hidden = true;
  const submit = makeElement("button", "planner-submit", "Aggiungi al calendario");
  submit.type = "submit";
  form.append(titleLabel, datetimeLabel, descriptionLabel, error, submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    error.hidden = true;
    try {
      selectedCalendarDate = startsAt.value.slice(0, 10);
      calendarMonth = new Date(
        Number(selectedCalendarDate.slice(0, 4)),
        Number(selectedCalendarDate.slice(5, 7)) - 1,
        1,
      );
      await savePlannerItem("event", {
        title: title.value,
        starts_at: startsAt.value,
        description: description.value,
      });
    } catch (saveError) {
      error.textContent = saveError.message;
      error.hidden = false;
      submit.disabled = false;
    }
  });
  container.append(toolbar, calendar, selectedDate, eventList, form);
}

function renderCalendarWindows() {
  const windowElement = openWindows.get("calendar");
  if (windowElement) renderCalendarApp(windowElement.querySelector(".app-window-content"));
}

function renderTasksApp(container) {
  container.replaceChildren();
  const openCount = planner.tasks.filter((task) => !task.completed).length;
  const completedCount = planner.tasks.length - openCount;
  const overdueCount = planner.tasks.filter((task) => (
    !task.completed && task.due_date && task.due_date < dateKey(new Date())
  )).length;
  const heading = makeElement("div", "task-app-heading");
  const titleGroup = makeElement("div", "task-app-title");
  titleGroup.append(
    makeElement("p", "eyebrow", "ELENCO PERSONALE"),
    makeElement("h3", "", "Attività"),
    makeElement("p", "task-count", `${openCount} da fare · ${completedCount} completate`),
  );
  heading.append(titleGroup);

  const addButton = makeElement("button", "task-add-trigger", "＋ Nuova attività");
  addButton.type = "button";
  heading.append(addButton);

  const form = makeElement("form", "task-quick-add");
  const title = makeElement("input");
  title.id = "task-title";
  title.name = "title";
  title.maxLength = 160;
  title.required = true;
  title.placeholder = "Aggiungi un’attività…";
  const dueDate = makeElement("input");
  dueDate.type = "date";
  dueDate.name = "due_date";
  dueDate.setAttribute("aria-label", "Scadenza facoltativa");
  const error = makeElement("p", "planner-error");
  error.hidden = true;
  const submit = makeElement("button", "planner-submit", "Aggiungi");
  submit.type = "submit";
  const cancel = makeElement("button", "task-add-cancel", "Annulla");
  cancel.type = "button";
  form.append(title, dueDate, submit, cancel, error);
  form.hidden = true;
  addButton.addEventListener("click", () => {
    form.hidden = false;
    title.focus();
  });
  cancel.addEventListener("click", () => {
    form.reset();
    form.hidden = true;
    error.hidden = true;
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    error.hidden = true;
    try {
      await savePlannerItem("task", {
        title: title.value,
        due_date: dueDate.value || null,
        completed: false,
      });
    } catch (saveError) {
      error.textContent = saveError.message;
      error.hidden = false;
      submit.disabled = false;
    }
  });

  const search = makeElement("input", "task-search");
  search.type = "search";
  search.placeholder = "Filtra per nome…";
  search.value = taskQuery;
  search.setAttribute("aria-label", "Cerca attività");
  search.addEventListener("input", () => {
    taskQuery = search.value;
    renderTasksApp(container);
    const updatedSearch = container.querySelector(".task-search");
    updatedSearch.focus();
    updatedSearch.setSelectionRange(taskQuery.length, taskQuery.length);
  });

  const filters = makeElement("nav", "task-filters");
  filters.setAttribute("aria-label", "Filtra attività");
  const filterOptions = [
    ["open", "Da fare", openCount],
    ["overdue", "Scadute", overdueCount],
    ["completed", "Completate", completedCount],
    ["all", "Tutte", planner.tasks.length],
  ];
  for (const [filter, label, count] of filterOptions) {
    const button = makeElement("button", "task-filter", label);
    button.type = "button";
    button.classList.toggle("active", taskFilter === filter);
    button.setAttribute("aria-pressed", String(taskFilter === filter));
    const badge = makeElement("span", "task-filter-count", String(count));
    button.append(badge);
    button.addEventListener("click", () => {
      taskFilter = filter;
      renderTasksApp(container);
    });
    filters.append(button);
  }

  const taskList = makeElement("div", "task-list");
  const query = taskQuery.trim().toLocaleLowerCase("it");
  const tasks = [...planner.tasks]
    .filter((task) => {
      if (taskFilter === "open" && task.completed) return false;
      if (taskFilter === "completed" && !task.completed) return false;
      if (taskFilter === "overdue" && (
        task.completed || !task.due_date || task.due_date >= dateKey(new Date())
      )) return false;
      return !query || task.title.toLocaleLowerCase("it").includes(query);
    })
    .sort((left, right) => {
    if (left.completed !== right.completed) return Number(left.completed) - Number(right.completed);
    return (left.due_date || "9999-12-31").localeCompare(right.due_date || "9999-12-31");
  });
  if (tasks.length === 0) {
    const empty = taskFilter === "completed"
      ? "Non ci sono ancora attività completate."
      : taskFilter === "overdue"
        ? "Nessuna attività scaduta. Ottimo!"
        : taskQuery
          ? "Nessuna attività corrisponde alla ricerca."
          : "La lista è vuota. Aggiungi un’attività per iniziare.";
    taskList.append(makeElement("p", "planner-empty task-empty", empty));
  }
  for (const task of tasks) {
    const row = makeElement("article", `planner-item task-item${task.completed ? " completed" : ""}`);
    const checkbox = makeElement("input");
    checkbox.className = "task-checkbox";
    checkbox.type = "checkbox";
    checkbox.checked = task.completed;
    checkbox.setAttribute("aria-label", `Segna ${task.title} come completata`);
    checkbox.addEventListener("change", async () => {
      checkbox.disabled = true;
      try {
        await savePlannerItem("task", { ...task, completed: checkbox.checked });
      } catch (saveError) {
        checkbox.checked = task.completed;
        checkbox.disabled = false;
        window.alert(saveError.message);
      }
    });
    const details = makeElement("div", "planner-item-details");
    details.append(makeElement("strong", "", task.title));
    if (task.due_date) {
      const dueDateValue = new Date(
        Number(task.due_date.slice(0, 4)),
        Number(task.due_date.slice(5, 7)) - 1,
        Number(task.due_date.slice(8, 10)),
      );
      const dueLabel = dueDateValue.toLocaleDateString("it-IT", {
        day: "numeric", month: "short", year: "numeric",
      });
      const due = makeElement("time", "task-due", dueLabel);
      due.dateTime = task.due_date;
      if (!task.completed && task.due_date < dateKey(new Date())) due.classList.add("overdue");
      details.append(due);
    }
    const remove = makeElement("button", "planner-delete", "Elimina");
    remove.type = "button";
    remove.addEventListener("click", async () => {
      try {
        await deletePlannerItem("task", task.id);
      } catch (deleteError) {
        window.alert(deleteError.message);
      }
    });
    row.append(checkbox, details, remove);
    taskList.append(row);
  }
  container.append(heading, form, search, filters, taskList);
}

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return "Non disponibile";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${new Intl.NumberFormat("it-IT", { maximumFractionDigits: 1 }).format(value)} ${units[unitIndex]}`;
}

function formatUptime(seconds) {
  if (seconds === null || seconds === undefined) return "Non disponibile";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return [days && `${days} g`, hours && `${hours} h`, `${minutes} min`]
    .filter(Boolean)
    .join(" ");
}

async function loadMachineWindow(container) {
  container.replaceChildren(makeElement("p", "planner-loading", "Lettura delle informazioni…"));
  try {
    const response = await fetch("/api/system");
    const status = await response.json();
    if (!response.ok) throw new Error(status.error || "Stato della macchina non disponibile.");
    const heading = makeElement("div", "planner-app-heading");
    heading.append(
      makeElement("div", "", ""),
    );
    heading.firstChild.append(
      makeElement("p", "eyebrow", "INFORMAZIONI LOCALI"),
      makeElement("h3", "", "Stato della macchina"),
    );
    const refresh = makeElement("button", "calendar-today", "Aggiorna");
    refresh.type = "button";
    refresh.addEventListener("click", () => loadMachineWindow(container));
    heading.append(refresh);
    const details = makeElement("dl", "system-details");
    const rows = [
      ["Sistema operativo", status.operating_system],
      ["Versione Python", status.python_version],
      ["Processori disponibili", status.processor_count ?? "Non disponibile"],
      ["Memoria", `${formatBytes(status.memory_available)} disponibili / ${formatBytes(status.memory_total)}`],
      ["Spazio disco", `${formatBytes(status.disk_free)} liberi / ${formatBytes(status.disk_total)}`],
      ["Tempo dall'avvio", formatUptime(status.uptime_seconds)],
    ];
    for (const [label, value] of rows) {
      details.append(makeElement("dt", "", label), makeElement("dd", "", String(value)));
    }
    container.replaceChildren(heading, details);
  } catch (error) {
    renderWindowError(container, error.message);
  }
}

function setVoiceStatus(text) {
  voiceStatus.textContent = text;
}

function setTheme(theme) {
  const isDark = theme !== "light";
  document.documentElement.dataset.theme = isDark ? "dark" : "light";
  themeToggle.querySelector("span:last-child").textContent = isDark ? "Tema scuro" : "Tema chiaro";
  setIcon(themeToggle.querySelector("span:first-child"), isDark ? "moon" : "sun");
  themeToggle.setAttribute("aria-label", isDark ? "Attiva tema chiaro" : "Attiva tema scuro");
  themeToggle.title = isDark ? "Attiva tema chiaro" : "Attiva tema scuro";
  document.querySelector('meta[name="theme-color"]').content = isDark ? "#191817" : "#f4f8fa";
  try {
    localStorage.setItem("nokk-theme", isDark ? "dark" : "light");
  } catch (error) {
    console.warn("Preferenza tema non salvata:", error);
  }
}

function base64FromBuffer(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return window.btoa(binary);
}

function fileExtension(name) {
  return name.slice(name.lastIndexOf(".")).toLowerCase();
}

function renderPendingAttachments() {
  attachmentList.replaceChildren();
  attachmentList.hidden = pendingAttachments.length === 0;
  for (const [index, attachment] of pendingAttachments.entries()) {
    const chip = document.createElement("div");
    chip.className = "attachment-chip";
    const icon = document.createElement("span");
    icon.className = "attachment-icon";
    icon.append(iconElement(attachment.kind === "image" ? "image" : "file"));
    const name = document.createElement("span");
    name.className = "attachment-name";
    name.textContent = attachment.name;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-attachment";
    remove.append(iconElement("close"));
    remove.setAttribute("aria-label", `Rimuovi ${attachment.name}`);
    remove.addEventListener("click", () => {
      pendingAttachments.splice(index, 1);
      renderPendingAttachments();
    });
    chip.append(icon, name, remove);
    attachmentList.append(chip);
  }
}

async function loadAttachment(file) {
  if (file.size > maxUploadBytes) {
    throw new Error("Ogni file deve essere più piccolo di 4 MB.");
  }
  const extension = fileExtension(file.name);
  if (textFileExtensions.has(extension)) {
    const content = (await file.text()).replace(/^\uFEFF/, "");
    if (!content.trim() || content.length > 150000) {
      throw new Error("Il file è vuoto o contiene troppo testo (limite 150.000 caratteri).");
    }
    return { kind: "text", name: file.name, content, size: file.size };
  }
  if (extension === ".pdf" || extension === ".docx") {
    const data = base64FromBuffer(await file.arrayBuffer());
    const response = await fetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: file.name, data }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Estrazione del documento non riuscita.");
    return { kind: "text", name: file.name, content: result.text, size: file.size };
  }
  const mimeType = imageMimeTypes[extension];
  if (mimeType) {
    const data = base64FromBuffer(await file.arrayBuffer());
    return { kind: "image", name: file.name, mime_type: mimeType, data, size: file.size };
  }
  throw new Error("Formato non supportato. Usa testo, PDF, DOCX o immagini PNG/JPG/WEBP/GIF.");
}

async function addFiles(fileList) {
  const files = [...fileList];
  for (const file of files) {
    if (pendingAttachments.length >= maxAttachmentsPerMessage) {
      setVoiceStatus(`Puoi allegare al massimo ${maxAttachmentsPerMessage} file per messaggio.`);
      break;
    }
    if (pendingAttachments.some((item) => item.name === file.name)) continue;
    try {
      const attachment = await loadAttachment(file);
      const existingBytes = pendingAttachments.reduce((total, item) => total + item.size, 0);
      if (existingBytes + attachment.size > 8 * 1024 * 1024) {
        throw new Error("Gli allegati del messaggio superano il limite di 8 MB.");
      }
      pendingAttachments.push(attachment);
      renderPendingAttachments();
      setVoiceStatus(`${pendingAttachments.length} file pronti · verranno inviati al provider al tuo invio`);
    } catch (error) {
      setVoiceStatus(`${file.name}: ${error.message}`);
    }
  }
  fileInput.value = "";
}

function updateVoiceButtons() {
  micToggle.disabled = !configured || !SpeechRecognitionAPI;
  attachButton.disabled = !configured;
  micToggle.classList.toggle("voice-active", voiceMode === "dictation");
  wakeToggle.classList.toggle("voice-active", wakeListeningRequested);
  wakeToggle.setAttribute("aria-pressed", String(wakeListeningRequested));
  wakeToggle.setAttribute(
    "aria-label",
    wakeListeningRequested
      ? "Disattiva wake word"
      : `Attiva wake word ${wakePhraseInput.value.trim() || "Nok"}`,
  );
  wakeToggle.title = wakeListeningRequested
    ? "Disattiva wake word"
    : `Attiva wake word ${wakePhraseInput.value.trim() || "Nok"}`;
  if (!SpeechRecognitionAPI) {
    micToggle.title = "Riconoscimento vocale non supportato da questo browser";
    wakeToggle.title = "Riconoscimento vocale non supportato da questo browser";
    micToggle.disabled = true;
    wakeToggle.disabled = true;
  } else {
    wakeToggle.disabled = !configured;
    micToggle.title = voiceMode === "dictation"
      ? "Interrompi dettatura"
      : "Detta un messaggio";
  }
}

function appendTranscript(text) {
  const transcript = text.trim();
  if (!transcript) return;
  const separator = input.value && !/\s$/.test(input.value) ? " " : "";
  input.value += `${separator}${transcript}`;
  resizeComposer();
  input.focus();
}

function scheduleWakeRestart() {
  if (
    !wakeListeningRequested
    || voiceRecognition
  ) return;
  window.clearTimeout(wakeRestartTimer);
  const delay = Math.min(300 * (2 ** wakeRetryCount), 2000);
  wakeRetryCount = Math.min(wakeRetryCount + 1, 5);
  setVoiceStatus(`Riattivo l’ascolto tra ${delay / 1000} s…`);
  wakeRestartTimer = window.setTimeout(() => {
    wakeRestartTimer = null;
    if (wakeListeningRequested && !voiceRecognition) startRecognition("wake");
  }, delay);
}

function startRecognition(mode) {
  if (!SpeechRecognitionAPI) {
    setVoiceStatus("Riconoscimento vocale non supportato da questo browser.");
    updateVoiceButtons();
    return;
  }
  const recognition = new SpeechRecognitionAPI();
  recognition.lang = "it-IT";
  recognition.continuous = mode === "wake";
  recognition.interimResults = mode === "wake";
  recognition.maxAlternatives = 1;
  voiceRecognition = recognition;
  voiceMode = mode;
  updateVoiceButtons();

  recognition.onstart = () => {
    if (voiceRecognition !== recognition) return;
    if (mode === "wake") {
      wakeRetryCount = 0;
      setVoiceStatus(`In ascolto di “${wakePhraseInput.value.trim()}”…`);
    } else {
      setVoiceStatus("Sto ascoltando…");
    }
  };
  recognition.onresult = (event) => {
    if (voiceRecognition !== recognition) return;
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      if (!result.isFinal) continue;
      const transcript = result[0].transcript.trim();
      if (mode === "dictation") {
        appendTranscript(transcript);
        wakeListeningRequested = false;
        recognition.stop();
        return;
      }

      if (!wakeTriggered) {
        const phrase = wakePhraseInput.value.trim() || "Nok";
        const escapedPhrase = phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const wakePattern = new RegExp(
          `(^|[^\\p{L}\\p{N}])(${escapedPhrase})(?=$|[^\\p{L}\\p{N}])`,
          "iu",
        );
        const match = wakePattern.exec(transcript);
        if (!match) continue;
        wakeTriggered = true;
        const command = transcript
          .slice(match.index + match[0].length)
          .replace(/^[\s,.:;!?-]+/, "")
          .trim();
        if (command) {
          appendTranscript(command);
          wakeTriggered = false;
          setVoiceStatus(
            `Testo acquisito. Wake word “${phrase}” ancora attiva; premi Invio per inviare.`,
          );
          continue;
        }
        setVoiceStatus("Wake word riconosciuta. Parla ora.");
        continue;
      }

      appendTranscript(transcript);
      wakeTriggered = false;
      setVoiceStatus(
        `Testo acquisito. Wake word “${wakePhraseInput.value.trim()}” ancora attiva; premi Invio per inviare.`,
      );
    }
  };
  recognition.onerror = (event) => {
    if (voiceRecognition !== recognition) return;
    const messagesByError = {
      "not-allowed": "Accesso al microfono negato. Controlla i permessi del browser.",
      "service-not-allowed": "Il browser non consente il servizio di riconoscimento vocale.",
      "audio-capture": "Microfono non disponibile. Controlla il dispositivo audio.",
      "language-not-supported": "Il riconoscimento vocale non supporta la lingua italiana.",
      network: "Servizio vocale non raggiungibile. Controlla la connessione.",
    };
    setVoiceStatus(
      messagesByError[event.error]
      || (event.error === "no-speech" ? "Non ho sentito la voce." : `Errore vocale: ${event.error}.`),
    );
    if ([
      "not-allowed",
      "service-not-allowed",
      "audio-capture",
      "language-not-supported",
    ].includes(event.error)) {
      wakeListeningRequested = false;
      wakeTriggered = false;
      window.clearTimeout(wakeRestartTimer);
    }
    updateVoiceButtons();
  };
  recognition.onend = () => {
    if (voiceRecognition !== recognition) return;
    const endedMode = voiceMode;
    voiceRecognition = null;
    voiceMode = null;
    updateVoiceButtons();
    if (wakeListeningRequested) {
      scheduleWakeRestart();
    } else if (!wakeListeningRequested && endedMode === "dictation") {
      setVoiceStatus("Dettatura terminata. Rivedi il testo prima di inviarlo.");
    } else if (!wakeListeningRequested && endedMode === "wake") {
      setVoiceStatus("Wake word disattivata.");
    }
  };
  try {
    recognition.start();
  } catch (error) {
    voiceRecognition = null;
    voiceMode = null;
    updateVoiceButtons();
    if (mode === "wake" && wakeListeningRequested) {
      setVoiceStatus(`Microfono non disponibile: ${error.message}`);
      scheduleWakeRestart();
    } else {
      setVoiceStatus(`Impossibile avviare il microfono: ${error.message}`);
    }
  }
}

function stopRecognition({ keepWakeRequested = false } = {}) {
  if (!keepWakeRequested) wakeListeningRequested = false;
  window.clearTimeout(wakeRestartTimer);
  if (voiceRecognition) voiceRecognition.stop();
  updateVoiceButtons();
}

function startDictation() {
  if (!configured || !SpeechRecognitionAPI) return;
  if (voiceMode === "dictation") {
    stopRecognition();
    return;
  }
  if (voiceRecognition) {
    stopRecognition();
    window.setTimeout(() => startRecognition("dictation"), 250);
    return;
  }
  startRecognition("dictation");
}

function toggleWakeWord() {
  if (!SpeechRecognitionAPI) {
    setVoiceStatus("Riconoscimento vocale non supportato da questo browser.");
    return;
  }
  if (wakeListeningRequested) {
    stopRecognition();
    wakeTriggered = false;
    wakeRetryCount = 0;
    setVoiceStatus("Wake word disattivata.");
    return;
  }
  wakeListeningRequested = true;
  wakeTriggered = false;
  wakeRetryCount = 0;
  if (voiceRecognition) {
    voiceRecognition.stop();
    window.setTimeout(() => {
      if (wakeListeningRequested && !voiceRecognition) startRecognition("wake");
    }, 250);
  } else {
    startRecognition("wake");
  }
}

function speakText(text) {
  if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
    setVoiceStatus("Sintesi vocale non supportata da questo browser.");
    return;
  }
  const rendered = document.createElement("div");
  renderMarkdown(rendered, text);
  const blockTags = new Set([
    "BLOCKQUOTE", "DIV", "H1", "H2", "H3", "H4", "H5", "H6",
    "LI", "P", "PRE", "TR",
  ]);
  function collectSpeechText(node) {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent;
    if (node.nodeName === "BR") return "\n";
    const content = [...node.childNodes].map(collectSpeechText).join("");
    return blockTags.has(node.nodeName) ? `${content}\n` : content;
  }
  const speechText = collectSpeechText(rendered)
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  const utterance = new SpeechSynthesisUtterance(speechText || text);
  utterance.lang = "it-IT";
  utterance.onstart = () => setVoiceStatus("Lettura vocale in corso…");
  utterance.onend = () => setVoiceStatus("Lettura vocale terminata.");
  utterance.onerror = (event) => {
    if (event.error === "canceled" || event.error === "interrupted") return;
    setVoiceStatus(`Lettura vocale non riuscita: ${event.error}.`);
  };
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

function renderWorkflows() {
  workflowList.replaceChildren();
  workflowEmpty.hidden = workflows.length > 0;
  for (const workflow of workflows) {
    const card = document.createElement("article");
    card.className = "workflow-card-item";
    const title = document.createElement("h3");
    title.textContent = workflow.name;
    const description = document.createElement("p");
    description.textContent = workflow.prompt;
    const actions = document.createElement("div");
    actions.className = "workflow-card-actions";
    const useButton = document.createElement("button");
    useButton.type = "button";
    useButton.className = "workflow-use";
    useButton.textContent = "Rivedi nella chat";
    useButton.disabled = !configured;
    useButton.addEventListener("click", () => {
      input.value = workflow.prompt;
      resizeComposer();
      welcome.hidden = true;
      setWorkflowPanelVisible(false);
      input.focus();
    });
    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.className = "workflow-edit";
    editButton.textContent = "Modifica";
    editButton.addEventListener("click", () => openWorkflowEditor(workflow));
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "workflow-delete";
    deleteButton.textContent = "Elimina";
    deleteButton.addEventListener("click", () => deleteWorkflow(workflow));
    actions.append(useButton, editButton, deleteButton);
    card.append(title, description);
    if (workflow.schedule_enabled) {
      const dayNames = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];
      const days = (workflow.schedule_days || [])
        .map((day) => dayNames[day])
        .filter(Boolean);
      const schedule = document.createElement("p");
      schedule.className = "workflow-schedule";
      schedule.textContent = `Programmata: ${days.join(", ") || "nessun giorno"} alle ${workflow.schedule_time || "07:00"}`;
      card.append(schedule);
    }
    if (workflow.last_run) {
      let when = workflow.last_run;
      try { when = new Date(workflow.last_run).toLocaleString("it-IT"); } catch {}
      const lastRun = document.createElement("p");
      lastRun.className = "workflow-last-run";
      lastRun.textContent = `Ultima esecuzione: ${when} · ${workflow.last_status === "ok" ? "completata" : "errore"}`;
      card.append(lastRun);
      if (workflow.last_result) {
        const details = document.createElement("details");
        details.className = "workflow-last-result";
        const summary = document.createElement("summary");
        summary.textContent = "Risultato";
        const body = document.createElement("p");
        body.textContent = workflow.last_result;
        details.append(summary, body);
        card.append(details);
      }
    }
    card.append(actions);
    workflowList.append(card);
  }
}

async function loadTelegramStatus() {
  const response = await fetch("/api/telegram");
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Stato Telegram non disponibile.");
  if (result.configured) {
    const username = result.bot_username ? ` @${result.bot_username}` : "";
    telegramStatus.textContent = `Bot collegato${username} · ${result.authorized_chats} chat autorizzate`;
  } else {
    telegramStatus.textContent = "Bot non collegato";
  }
  telegramAuthorizedChatCount = result.authorized_chats;
  telegramPairButton.disabled = !result.configured;
  telegramDisconnectButton.hidden = !result.configured;
  telegramReminderEnabled.checked = result.reminder_enabled !== false;
  telegramReminderTime.value = result.reminder_time || "07:00";
  return result;
}

async function sendTelegramAction(payload) {
  const response = await fetch("/api/telegram", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Operazione Telegram non riuscita.");
  return result;
}

async function loadGoogleCalendarStatus() {
  const response = await fetch("/api/google-calendar");
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || "Stato Google Calendar non disponibile.");
  }
  if (result.connected) {
    googleCalendarStatus.textContent = result.account
      ? `Google Calendar collegato · ${result.account}`
      : `Google Calendar collegato · calendario ${result.calendar_id}`;
  } else if (result.configured) {
    googleCalendarStatus.textContent = "Credenziali salvate · calendario non collegato";
  } else {
    googleCalendarStatus.textContent = "Google Calendar non collegato";
  }
  if (result.client_id && !googleClientIdInput.value) {
    googleClientIdInput.value = result.client_id;
  }
  if (result.calendar_id) googleCalendarIdInput.value = result.calendar_id;
  if (result.redirect_uri) {
    googleCalendarRedirectHelp.textContent =
      `Registra questo URI di reindirizzamento nel client OAuth Google: ${result.redirect_uri}`;
  }
  googleCalendarConnectButton.disabled = !result.configured;
  googleCalendarDisconnectButton.hidden = !result.connected;
  return result;
}

async function sendGoogleCalendarAction(payload) {
  const response = await fetch("/api/google-calendar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || "Operazione Google Calendar non riuscita.");
  }
  return result;
}

async function handleGoogleCalendarReturn() {
  const params = new URLSearchParams(window.location.search);
  const outcome = params.get("google_calendar");
  if (!outcome) return;
  window.history.replaceState(null, "", window.location.pathname);
  openSettings("Google Calendar");
  try {
    await loadGoogleCalendarStatus();
  } catch (error) {
    googleCalendarStatus.textContent = error.message;
    return;
  }
  if (outcome === "connected") {
    googleCalendarStatus.textContent = "Google Calendar collegato.";
  } else if (outcome === "denied") {
    googleCalendarStatus.textContent =
      "Collegamento annullato: nessun permesso concesso.";
  } else {
    googleCalendarStatus.textContent =
      "Collegamento non riuscito. Controlla client ID, client secret e URI di reindirizzamento.";
  }
}

async function deleteWorkflow(workflow) {
  if (!window.confirm(`Eliminare la procedura "${workflow.name}"?`)) return;
  try {
    const response = await fetch("/api/workflows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "delete", id: workflow.id }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Eliminazione non riuscita.");
    workflows = result.workflows;
    renderWorkflows();
  } catch (error) {
    window.alert(error.message);
  }
}

function setConfigured(isConfigured, provider, model) {
  configured = isConfigured;
  input.disabled = !configured;
  sendButton.disabled = !configured || sending;
  input.placeholder = configured ? "Scrivi un messaggio..." : "Configura un provider per iniziare...";
  const providerName = providerLabels[provider] || provider;
  connectionLabel.textContent = configured ? `${providerName} · ${model}` : "Configura un provider";
  document.querySelector(".status-dot").classList.toggle("connected", configured);
  updateVoiceButtons();
}

function appendInlineMarkdown(parent, text, depth = 0) {
  if (depth > 8) {
    parent.append(document.createTextNode(text));
    return;
  }

  let cursor = 0;
  while (cursor < text.length) {
    let match = null;
    let element = null;
    let content = "";
    let nextCursor = cursor;

    if (text[cursor] === "`") {
      const end = text.indexOf("`", cursor + 1);
      if (end > cursor + 1) {
        element = document.createElement("code");
        content = text.slice(cursor + 1, end);
        nextCursor = end + 1;
      }
    } else if (text[cursor] === "[") {
      match = text.slice(cursor).match(/^\[([^\]]+)\]\(([^)\s]+)(?:\s+["']([^"']*)["'])?\)/);
      if (match) {
        try {
          const url = new URL(match[2], window.location.href);
          if (["http:", "https:", "mailto:"].includes(url.protocol)) {
            element = document.createElement("a");
            element.href = url.href;
            element.rel = "noopener noreferrer";
            if (url.protocol !== "mailto:") element.target = "_blank";
            content = match[1];
            nextCursor = cursor + match[0].length;
          }
        } catch {
          // Leave malformed or unsafe links as plain text.
        }
      }
    } else {
      const delimiter = text.startsWith("**", cursor) ? "**"
        : text.startsWith("__", cursor) ? "__"
          : text.startsWith("~~", cursor) ? "~~"
            : text[cursor] === "*" || text[cursor] === "_" ? text[cursor] : "";
      if (delimiter) {
        const end = text.indexOf(delimiter, cursor + delimiter.length);
        const contentStart = cursor + delimiter.length;
        const before = text[cursor - 1] || "";
        const after = end === -1 ? "" : text[end + delimiter.length] || "";
        const underscoreBoundaries = delimiter !== "_"
          || (!before || /[\s([{>]/.test(before))
            && (!after || /[\s.,!?;:)\]}>]/.test(after));
        if (
          end > contentStart
          && !/\s/.test(text[contentStart])
          && underscoreBoundaries
        ) {
          element = document.createElement(
            delimiter.length === 2 && delimiter !== "~~" ? "strong"
              : delimiter === "~~" ? "del" : "em",
          );
          content = text.slice(cursor + delimiter.length, end);
          nextCursor = end + delimiter.length;
        }
      }
    }

    if (element) {
      if (element.tagName === "CODE") element.textContent = content;
      else appendInlineMarkdown(element, content, depth + 1);
      parent.append(element);
      cursor = nextCursor;
      continue;
    }

    const nextSpecial = text.slice(cursor + 1).search(/[`[*_~]/);
    const textEnd = nextSpecial === -1 ? text.length : cursor + 1 + nextSpecial;
    parent.append(document.createTextNode(text.slice(cursor, textEnd)));
    cursor = textEnd;
  }
}

function renderMarkdown(parent, source) {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  let index = 0;

  function isTableSeparator(line) {
    return /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(line) && line.includes("-");
  }

  function isListItem(line) {
    return /^\s{0,3}(?:[-+*]|\d+[.)])\s+/.test(line);
  }

  function isBlockStart(line, nextLine = "") {
    return /^\s{0,3}(?:#{1,6}\s|```|~~~|>|(?:[-*_]\s*){3,}$)/.test(line)
      || isListItem(line)
      || (line.includes("|") && isTableSeparator(nextLine));
  }

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.match(/^\s{0,3}(`{3,}|~{3,})\s*([A-Za-z0-9_+-]*)?.*$/);
    if (fence) {
      const marker = fence[1][0];
      const codeLines = [];
      index += 1;
      while (index < lines.length && !new RegExp(`^\\s{0,3}${marker}{${fence[1].length},}\\s*$`).test(lines[index])) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      if (fence[2]) code.className = `language-${fence[2]}`;
      code.textContent = codeLines.join("\n");
      pre.append(code);
      parent.append(pre);
      continue;
    }

    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      const element = document.createElement(`h${heading[1].length}`);
      appendInlineMarkdown(element, heading[2]);
      parent.append(element);
      index += 1;
      continue;
    }

    if (/^\s{0,3}(?:(\*\s*){3,}|(-\s*){3,}|(_\s*){3,})$/.test(line)) {
      parent.append(document.createElement("hr"));
      index += 1;
      continue;
    }

    if (line.includes("|") && isTableSeparator(lines[index + 1] || "")) {
      const table = document.createElement("table");
      const header = document.createElement("thead");
      const headerRow = document.createElement("tr");
      const cells = (value) => value.trim().replace(/^\||\|$/g, "").split("|");
      for (const cellText of cells(line)) {
        const cell = document.createElement("th");
        appendInlineMarkdown(cell, cellText.trim());
        headerRow.append(cell);
      }
      header.append(headerRow);
      table.append(header);
      index += 2;
      const rows = document.createElement("tbody");
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        const row = document.createElement("tr");
        for (const cellText of cells(lines[index])) {
          const cell = document.createElement("td");
          appendInlineMarkdown(cell, cellText.trim());
          row.append(cell);
        }
        rows.append(row);
        index += 1;
      }
      table.append(rows);
      parent.append(table);
      continue;
    }

    if (/^\s{0,3}>/.test(line)) {
      const quoteLines = [];
      while (index < lines.length && /^\s{0,3}>/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^\s{0,3}>\s?/, ""));
        index += 1;
      }
      const quote = document.createElement("blockquote");
      renderMarkdown(quote, quoteLines.join("\n"));
      parent.append(quote);
      continue;
    }

    if (isListItem(line)) {
      const ordered = /^\s{0,3}\d+[.)]\s+/.test(line);
      const list = document.createElement(ordered ? "ol" : "ul");
      while (index < lines.length && isListItem(lines[index])) {
        const itemText = lines[index].replace(/^\s{0,3}(?:[-+*]|\d+[.)])\s+/, "");
        const item = document.createElement("li");
        appendInlineMarkdown(item, itemText);
        list.append(item);
        index += 1;
      }
      parent.append(list);
      continue;
    }

    const paragraphLines = [line.trim()];
    index += 1;
    while (
      index < lines.length
      && lines[index].trim()
      && !isBlockStart(lines[index], lines[index + 1] || "")
    ) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    const paragraph = document.createElement("p");
    appendInlineMarkdown(paragraph, paragraphLines.join(" "));
    parent.append(paragraph);
  }
}

function appendAttachmentPreviews(parent, attachments) {
  if (!attachments?.length) return;
  const group = document.createElement("div");
  group.className = "message-attachments";
  for (const attachment of attachments) {
    const item = document.createElement("div");
    item.className = "message-attachment";
    if (attachment.kind === "image") {
      const image = document.createElement("img");
      image.src = `data:${attachment.mime_type};base64,${attachment.data}`;
      image.alt = attachment.name;
      item.append(image);
    } else {
      const icon = document.createElement("span");
      icon.append(iconElement("file"));
      item.append(icon);
    }
    const name = document.createElement("span");
    name.textContent = attachment.name;
    item.append(name);
    group.append(item);
  }
  parent.append(group);
}

function addMessage(role, text, extraClass = "", attachments = []) {
  const row = document.createElement("article");
  row.className = `message ${role} ${extraClass}`.trim();
  const roleIcon = document.createElement("span");
  roleIcon.className = "message-role";
  if (role === "user") roleIcon.textContent = "Tu";
  else roleIcon.append(iconElement("sparkle"));
  const body = document.createElement("div");
  body.className = "message-body";
  if (role === "user") appendAttachmentPreviews(body, attachments);
  if (role === "assistant") {
    renderMarkdown(body, text);
    const speakButton = document.createElement("button");
    speakButton.type = "button";
    speakButton.className = "speak-message";
    speakButton.setAttribute("aria-label", "Leggi questa risposta");
    speakButton.title = "Leggi questa risposta";
    speakButton.append(iconElement("volume"));
    speakButton.addEventListener("click", () => speakText(text));
    body.append(speakButton);
  } else {
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    body.append(paragraph);
  }
  row.append(roleIcon, body);
  conversation.append(row);
  conversation.scrollTo({ top: conversation.scrollHeight, behavior: "smooth" });
  return row;
}

function addToolEvent(event) {
  const row = document.createElement("article");
  row.className = "message tool-event";
  const roleIcon = document.createElement("span");
  roleIcon.className = "message-role";
  roleIcon.append(iconElement("terminal"));
  const body = document.createElement("div");
  body.className = "message-body";
  const label = document.createElement("p");
  label.textContent = event.tool
    ? `${event.executed ? "Strumento NOKK eseguito" : "Strumento NOKK non riuscito"}:`
    : !event.executed
      ? "Comando non eseguito:"
      : `${event.automatic ? "Eseguito in automatico" : "Comando approvato"}:`;
  const command = document.createElement("pre");
  const commandCode = document.createElement("code");
  commandCode.textContent = event.command;
  command.append(commandCode);
  const output = document.createElement("pre");
  const outputCode = document.createElement("code");
  outputCode.textContent = `${event.output}\n\nCodice di uscita: ${event.exit_code}`;
  output.append(outputCode);
  body.append(label, command, output);
  row.append(roleIcon, body);
  conversation.append(row);
  conversation.scrollTo({ top: conversation.scrollHeight, behavior: "smooth" });
}

function showApproval(jobId, action) {
  let card = document.querySelector(`[data-action-id="${action.id}"]`);
  if (card) return;

  card = document.createElement("article");
  card.className = "approval-card";
  card.dataset.actionId = action.id;
  card.dataset.jobId = jobId;
  const heading = document.createElement("h3");
  heading.textContent = "L’assistente chiede di eseguire un comando";
  const directory = document.createElement("p");
  directory.textContent = `Cartella di lavoro: ${action.workspace}`;
  const command = document.createElement("pre");
  const code = document.createElement("code");
  code.textContent = action.command;
  command.append(code);
  const warning = document.createElement("p");
  warning.className = "approval-warning";
  warning.textContent = "Controlla il comando. Verrà eseguito sul tuo computer con i tuoi permessi.";
  const controls = document.createElement("div");
  controls.className = "approval-actions";
  const deny = document.createElement("button");
  deny.type = "button";
  deny.className = "cancel-button";
  deny.textContent = "Rifiuta";
  const approve = document.createElement("button");
  approve.type = "button";
  approve.className = "approve-command";
  approve.textContent = "Approva ed esegui";
  controls.append(deny, approve);
  card.append(heading, directory, command, warning, controls);
  conversation.append(card);
  conversation.scrollTo({ top: conversation.scrollHeight, behavior: "smooth" });

  async function respond(approved) {
    approve.disabled = true;
    deny.disabled = true;
    try {
      const response = await fetch(`/api/jobs/${jobId}/approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_id: action.id, approved }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Risposta di approvazione non riuscita.");
      card.dataset.approved = String(approved);
      warning.textContent = approved
        ? "Approvato. Il comando è in esecuzione…"
        : "Rifiutato. Il comando non è stato eseguito.";
    } catch (error) {
      warning.textContent = error.message;
      approve.disabled = false;
      deny.disabled = false;
    }
  }

  approve.addEventListener("click", () => respond(true));
  deny.addEventListener("click", () => respond(false));
}

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function resizeComposer() {
  input.rows = 1;
  const lineHeight = Number.parseFloat(getComputedStyle(input).lineHeight) || 22;
  input.rows = Math.min(7, Math.max(1, Math.ceil(input.scrollHeight / lineHeight)));
}

// Safari reports a body that is not JSON as "The string did not match the
// expected pattern.", so keep the real HTTP status and body in the message.
async function readJsonResponse(response, fallbackMessage) {
  const text = await response.text();
  if (!text.trim()) {
    throw new Error(`${fallbackMessage} (risposta vuota, HTTP ${response.status})`);
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    const body = text.replace(/\s+/g, " ").trim();
    // A proxy page adds nothing useful for the reader of the chat.
    const detail = body.startsWith("<") ? "" : body.slice(0, 120);
    throw new Error(`${fallbackMessage} (HTTP ${response.status}${detail ? `: ${detail}` : ""})`);
  }
}

async function waitForChatJob(jobId) {
  let renderedEvents = 0;
  while (true) {
    const response = await fetch(`/api/jobs/${jobId}`);
    const job = await readJsonResponse(response, "Attività non disponibile.");
    if (!response.ok) throw new Error(job.error || "Attività non disponibile.");
    if (job.action && job.status === "awaiting_approval") {
      showApproval(jobId, job.action);
    }
    const toolEvents = job.tool_events || [];
    for (const event of toolEvents.slice(renderedEvents)) {
      addToolEvent(event);
    }
    renderedEvents = toolEvents.length;
    if (job.status === "failed") {
      finishApprovalCards(jobId);
      const details = job.details ? `\n\n${job.details}` : "";
      const hint = job.hint ? `\n\n${job.hint}` : "";
      throw new Error(`${job.error || "La richiesta non è riuscita."}${hint}${details}`);
    }
    if (job.status === "complete") {
      finishApprovalCards(jobId);
      if (toolEvents.length > 0) await refreshNokkData();
      return job.reply;
    }
    await delay(500);
  }
}

function finishApprovalCards(jobId) {
  for (const card of conversation.querySelectorAll(
    `.approval-card[data-job-id="${jobId}"][data-approved="true"]`,
  )) {
    const warning = card.querySelector(".approval-warning");
    warning.textContent = "Comando completato. Verifica l’output qui sotto.";
  }
}

function checkPlannerNotifications() {
  if (
    !notificationsInput?.checked
    || !("Notification" in window)
    || Notification.permission !== "granted"
  ) return;
  const now = Date.now();
  const today = dateKey(new Date());
  let sent = {};
  try {
    sent = JSON.parse(localStorage.getItem("nokk-notified") || "{}") || {};
  } catch (error) {
    sent = {};
  }
  const items = [];
  for (const event of planner.events) {
    const starts = new Date(event.starts_at).getTime();
    if (starts >= now && starts <= now + 24 * 60 * 60 * 1000) {
      items.push({
        key: `event:${event.id}:${today}`,
        title: "Appuntamento",
        body: `${event.starts_at.slice(11, 16)} · ${event.title}`,
      });
    }
  }
  for (const task of planner.tasks) {
    if (!task.completed && task.due_date && task.due_date <= today) {
      items.push({
        key: `task:${task.id}:${today}`,
        title: "Attività",
        body: `${task.title}${task.due_date === today ? " · scade oggi" : " · scaduta"}`,
      });
    }
  }
  for (const item of items.filter((entry) => !sent[entry.key]).slice(0, 3)) {
    try {
      new Notification(`NOKK · ${item.title}`, { body: item.body, tag: item.key });
      sent[item.key] = true;
    } catch (error) {
      console.warn("Notifica non mostrata:", error);
    }
  }
  try {
    localStorage.setItem("nokk-notified", JSON.stringify(sent));
  } catch (error) {
    console.warn("Stato notifiche non salvato:", error);
  }
}

async function exportData() {
  const response = await fetch("/api/export");
  if (!response.ok) throw new Error("Esportazione non riuscita.");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "nokk-backup.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function refreshWeather() {
  try {
    const response = await fetch("/api/weather");
    const result = await response.json();
    if (result.configured && result.error) {
      sidebarWeatherTemperature.textContent = "--°";
      sidebarWeatherDetail.textContent = result.error || "Meteo non disponibile";
      sidebarWeather.hidden = false;
      return;
    }
    if (!response.ok || !result.configured) {
      sidebarWeather.hidden = true;
      return;
    }
    const temperature = Number.isFinite(result.temperature)
      ? `${Math.round(result.temperature)}°`
      : "--°";
    const range = [];
    if (Number.isFinite(result.maximum)) range.push(`max ${Math.round(result.maximum)}°`);
    if (Number.isFinite(result.minimum)) range.push(`min ${Math.round(result.minimum)}°`);
    sidebarWeatherTemperature.textContent = temperature;
    sidebarWeatherDetail.textContent = [result.description, range.join(" · "), result.city]
      .filter(Boolean)
      .join(" · ");
    sidebarWeather.hidden = false;
  } catch {
    sidebarWeather.hidden = true;
  }
}

window.setInterval(() => {
  if (!document.hidden) refreshWeather();
}, 15 * 60 * 1000);

async function loadConfig() {
  const response = await fetch("/api/config");
  if (!response.ok) throw new Error("Non riesco a leggere la configurazione.");
  const saved = await response.json();
  workflows = saved.workflows || [];
  configuredProviders = new Set(saved.configured_providers || []);
  if (saved.configured && saved.provider) configuredProviders.add(saved.provider);
  wakePhraseInput.value = saved.wake_phrase || "Nok";
  ttsAutoPlayInput.checked = saved.tts_auto_play === true;
  notificationsInput.checked = saved.notifications_enabled === true;
  alertsEnabledInput.checked = saved.alerts_enabled === true;
  alertsDiskInput.value = String(saved.alerts_disk_percent ?? 90);
  alertsMemoryInput.value = String(saved.alerts_memory_percent ?? 92);
  weatherEnabledInput.checked = saved.weather_enabled === true;
  weatherCityInput.value = saved.weather_city || "";
  refreshWeather();
  ttsAutoPlayInput.disabled = !(
    "speechSynthesis" in window
    && "SpeechSynthesisUtterance" in window
  );
  baseUrlInput.value = saved.base_url || "";
  savedModels = { ...(saved.models || {}) };
  if (saved.provider && saved.model) savedModels[saved.provider] = saved.model;
  if (saved.provider) {
    providerSelect.value = saved.provider;
    updateProviderFields();
    if (saved.provider !== "openrouter" && saved.model) modelInput.value = saved.model;
  }
  if (saved.workspace) workspaceInput.value = saved.workspace;
  systemPromptInput.value = saved.system_prompt || "";
  terminalEnabledInput.checked = saved.terminal_enabled === true;
  approvalModeSelect.value = saved.approval_mode || "manual";
  apiKeyInput.placeholder = apiKeyPlaceholder(providerSelect.value);
  setConfigured(saved.configured, saved.provider, saved.model);
  renderWorkflows();
  updateVoiceButtons();
}

document.querySelectorAll("[data-open-app]").forEach((button) => {
  button.addEventListener("click", () => openApplicationWindow(button.dataset.openApp));
});

sidebarToggle.addEventListener("click", () => {
  setSidebarOpen(!document.body.classList.contains("sidebar-open"));
});
sidebarClose.addEventListener("click", () => setSidebarOpen(false));
sidebarBackdrop.addEventListener("click", () => setSidebarOpen(false));
sidebar.addEventListener("click", (event) => {
  if (
    mobileSidebarQuery.matches
    && event.target.closest("button, a")
    && !event.target.closest("#sidebar-close")
  ) {
    window.setTimeout(() => setSidebarOpen(false), 0);
  }
});
const closeSidebarOnResize = () => {
  if (!mobileSidebarQuery.matches) setSidebarOpen(false);
};
if (mobileSidebarQuery.addEventListener) {
  mobileSidebarQuery.addEventListener("change", closeSidebarOnResize);
} else {
  mobileSidebarQuery.addListener(closeSidebarOnResize);
}
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && document.body.classList.contains("sidebar-open")) {
    setSidebarOpen(false);
    sidebarToggle.focus();
  }
});
document.querySelector("#welcome-setup").addEventListener("click", () => openSettings());
document.querySelector("#settings-close").addEventListener("click", closeSettings);
document.querySelector("#settings-cancel").addEventListener("click", closeSettings);
settingsTabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activateSettingsTab(tab.dataset.settingsTab));
  tab.addEventListener("keydown", (event) => {
    const keys = ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "Home", "End"];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    let nextIndex = index;
    if (event.key === "ArrowDown" || event.key === "ArrowRight") nextIndex = (index + 1) % settingsTabs.length;
    if (event.key === "ArrowUp" || event.key === "ArrowLeft") nextIndex = (index - 1 + settingsTabs.length) % settingsTabs.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = settingsTabs.length - 1;
    const nextTab = settingsTabs[nextIndex];
    activateSettingsTab(nextTab.dataset.settingsTab);
    nextTab.focus();
  });
});
document.querySelector("#launcher-open").addEventListener("click", openLauncher);
launcherInput.addEventListener("input", () => {
  launcherSelection = 0;
  renderLauncherResults();
});
launcherInput.addEventListener("keydown", handleLauncherKeys);
launcherOverlay.addEventListener("click", (event) => {
  if (event.target === launcherOverlay) closeLauncher();
});
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    openLauncher();
  } else if (event.key === "Escape" && !launcherOverlay.hidden) {
    closeLauncher();
  }
});
themeToggle.addEventListener("click", () => {
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});
try {
  setTheme(localStorage.getItem("nokk-theme") || "dark");
} catch (error) {
  console.warn("Preferenza tema non disponibile:", error);
  setTheme("dark");
}
attachButton.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => addFiles(fileInput.files));
chatForm.addEventListener("dragover", (event) => {
  if (!event.dataTransfer?.types.includes("Files")) return;
  event.preventDefault();
  chatForm.classList.add("drag-over");
});
chatForm.addEventListener("dragleave", (event) => {
  if (!chatForm.contains(event.relatedTarget)) chatForm.classList.remove("drag-over");
});
chatForm.addEventListener("drop", (event) => {
  if (!event.dataTransfer?.files.length) return;
  event.preventDefault();
  chatForm.classList.remove("drag-over");
  addFiles(event.dataTransfer.files);
});
document.querySelector("#workflow-create").addEventListener("click", () => {
  openWorkflowEditor();
});
document.querySelector("#workflow-close").addEventListener("click", closeWorkflowEditor);
document.querySelector("#workflow-cancel").addEventListener("click", closeWorkflowEditor);
micToggle.addEventListener("click", startDictation);
wakeToggle.addEventListener("click", toggleWakeWord);
wakePhraseInput.addEventListener("input", updateVoiceButtons);
document.addEventListener("visibilitychange", () => {
  if (
    document.visibilityState === "visible"
    && wakeListeningRequested
    && !voiceRecognition
  ) {
    window.clearTimeout(wakeRestartTimer);
    wakeRestartTimer = null;
    startRecognition("wake");
  }
});
newChatButton.addEventListener("click", () => {
  for (const windowElement of openWindows.values()) {
    windowElement.classList.add("is-minimized");
  }
  renderWindowDock();
  messages.length = 0;
  pendingAttachments = [];
  renderPendingAttachments();
  input.value = "";
  resizeComposer();
  conversation.replaceChildren(welcome);
  welcome.hidden = false;
  pageTitle.textContent = "Una nuova conversazione";
});

providerSelect.addEventListener("change", updateProviderFields);
notificationsInput.addEventListener("change", async () => {
  if (notificationsInput.checked && "Notification" in window && Notification.permission === "default") {
    await Notification.requestPermission();
  }
});
exportDataButton.addEventListener("click", () => {
  exportData().catch((error) => window.alert(error.message));
});

settingsOverlay.addEventListener("click", (event) => {
  if (event.target === settingsOverlay) closeSettings();
});

telegramConnectButton.addEventListener("click", async () => {
  const token = telegramTokenInput.value.trim();
  if (!token) {
    telegramStatus.textContent = "Inserisci il token fornito da BotFather.";
    return;
  }
  telegramConnectButton.disabled = true;
  telegramStatus.textContent = "Verifica e collegamento del bot…";
  try {
    await sendTelegramAction({ action: "connect", token });
    telegramTokenInput.value = "";
    telegramPairCode.hidden = true;
    window.clearInterval(telegramStatusTimer);
    telegramStatusTimer = null;
    await loadTelegramStatus();
  } catch (error) {
    telegramStatus.textContent = error.message;
  } finally {
    telegramConnectButton.disabled = false;
  }
});

telegramReminderSave.addEventListener("click", async () => {
  telegramReminderSave.disabled = true;
  try {
    const time = telegramReminderTime.value;
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(time)) {
      throw new Error("Scegli un orario valido per il promemoria.");
    }
    await sendTelegramAction({
      action: "reminder",
      enabled: telegramReminderEnabled.checked,
      time,
    });
    telegramStatus.textContent = telegramReminderEnabled.checked
      ? `Promemoria materie attivo alle ${time}, ora italiana.`
      : "Promemoria materie disattivato.";
  } catch (error) {
    telegramStatus.textContent = error.message;
  } finally {
    telegramReminderSave.disabled = false;
  }
});

telegramPairButton.addEventListener("click", async () => {
  telegramPairButton.disabled = true;
  telegramStatus.textContent = "Generazione del codice…";
  try {
    const previousCount = telegramAuthorizedChatCount;
    const result = await sendTelegramAction({ action: "pair_code" });
    telegramPairCode.textContent = `/pair ${result.code} · valido 10 minuti`;
    telegramPairCode.hidden = false;
    await loadTelegramStatus();
    window.clearInterval(telegramStatusTimer);
    const expiresAt = Date.now() + result.expires_in * 1000;
    telegramStatusTimer = window.setInterval(async () => {
      try {
        const status = await loadTelegramStatus();
        if (
          status.authorized_chats > previousCount
          || Date.now() >= expiresAt
        ) {
          window.clearInterval(telegramStatusTimer);
          telegramStatusTimer = null;
          telegramPairCode.hidden = true;
        }
      } catch (error) {
        telegramStatus.textContent = error.message;
      }
    }, 3000);
  } catch (error) {
    telegramStatus.textContent = error.message;
  } finally {
    telegramPairButton.disabled = false;
  }
});

googleCalendarSaveButton.addEventListener("click", async () => {
  googleCalendarSaveButton.disabled = true;
  googleCalendarStatus.textContent = "Salvataggio delle credenziali…";
  try {
    await sendGoogleCalendarAction({
      action: "save",
      client_id: googleClientIdInput.value.trim(),
      client_secret: googleClientSecretInput.value,
      calendar_id: googleCalendarIdInput.value.trim() || "primary",
    });
    googleClientSecretInput.value = "";
    await loadGoogleCalendarStatus();
  } catch (error) {
    googleCalendarStatus.textContent = error.message;
  } finally {
    googleCalendarSaveButton.disabled = false;
  }
});

googleCalendarConnectButton.addEventListener("click", async () => {
  googleCalendarConnectButton.disabled = true;
  try {
    await loadGoogleCalendarStatus();
    window.location.href = "/api/google-calendar/start";
  } catch (error) {
    googleCalendarStatus.textContent = error.message;
    googleCalendarConnectButton.disabled = false;
  }
});

googleCalendarDisconnectButton.addEventListener("click", async () => {
  if (!window.confirm("Disconnettere Google Calendar da NOKK?")) return;
  googleCalendarDisconnectButton.disabled = true;
  try {
    await sendGoogleCalendarAction({ action: "disconnect" });
    await loadGoogleCalendarStatus();
  } catch (error) {
    googleCalendarStatus.textContent = error.message;
  } finally {
    googleCalendarDisconnectButton.disabled = false;
  }
});

telegramDisconnectButton.addEventListener("click", async () => {
  if (!window.confirm("Disconnettere il bot Telegram e rimuovere le chat autorizzate?")) return;
  telegramDisconnectButton.disabled = true;
  try {
    await sendTelegramAction({ action: "disconnect" });
    window.clearInterval(telegramStatusTimer);
    telegramStatusTimer = null;
    telegramPairCode.hidden = true;
    await loadTelegramStatus();
  } catch (error) {
    telegramStatus.textContent = error.message;
  } finally {
    telegramDisconnectButton.disabled = false;
  }
});

workflowOverlay.addEventListener("click", (event) => {
  if (event.target === workflowOverlay) closeWorkflowEditor();
});

workflowForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  workflowError.hidden = true;
  workflowSave.disabled = true;
  try {
    const scheduleDays = workflowDayInputs
      .filter((dayInput) => dayInput.checked)
      .map((dayInput) => Number(dayInput.value));
    const scheduleEnabled = workflowScheduleEnabled.checked;
    if (scheduleEnabled && scheduleDays.length === 0) {
      throw new Error("Scegli almeno un giorno per la programmazione.");
    }
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(workflowScheduleTime.value)) {
      throw new Error("Scegli un orario valido per la programmazione.");
    }
    const response = await fetch("/api/workflows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "save",
        id: editingWorkflowId,
        name: workflowNameInput.value.trim(),
        prompt: workflowPromptInput.value.trim(),
        schedule_enabled: scheduleEnabled,
        schedule_time: workflowScheduleTime.value,
        schedule_days: scheduleDays,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Salvataggio non riuscito.");
    workflows = result.workflows;
    renderWorkflows();
    closeWorkflowEditor();
    setWorkflowPanelVisible(true);
  } catch (error) {
    workflowError.textContent = error.message;
    workflowError.hidden = false;
  } finally {
    workflowSave.disabled = false;
  }
});

settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  settingsError.hidden = true;
  settingsSave.disabled = true;
  settingsSave.textContent = "Collegamento...";
  try {
    const requiredFields = [
      { input: modelInput, tab: "connection", message: "Inserisci il nome del modello." },
      { input: wakePhraseInput, tab: "voice", message: "Inserisci una wake word." },
      { input: workspaceInput, tab: "tools", message: "Indica la cartella di lavoro." },
    ];
    const missingField = requiredFields.find(({ input: field }) => !field.value.trim());
    if (missingField) {
      activateSettingsTab(missingField.tab);
      missingField.input.focus();
      throw new Error(missingField.message);
    }
    if (providerSelect.value === "custom" && baseUrlInput.value.trim()) {
      try {
        new URL(baseUrlInput.value.trim());
      } catch {
        activateSettingsTab("connection");
        baseUrlInput.focus();
        throw new Error("Inserisci un indirizzo API valido.");
      }
    }
    const response = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: providerSelect.value,
        model: modelInput.value.trim(),
        base_url: baseUrlInput.value.trim(),
        api_key: apiKeyInput.value,
        terminal_enabled: terminalEnabledInput.checked,
        approval_mode: approvalModeSelect.value,
        workspace: workspaceInput.value.trim(),
        system_prompt: systemPromptInput.value,
        wake_phrase: wakePhraseInput.value.trim(),
        tts_auto_play: ttsAutoPlayInput.checked,
        notifications_enabled: notificationsInput.checked,
        alerts_enabled: alertsEnabledInput.checked,
        alerts_disk_percent: Number.parseInt(alertsDiskInput.value, 10) || 90,
        alerts_memory_percent: Number.parseInt(alertsMemoryInput.value, 10) || 92,
        weather_enabled: weatherEnabledInput.checked,
        weather_city: weatherCityInput.value.trim(),
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Configurazione non riuscita.");
    apiKeyInput.value = "";
    configuredProviders.add(providerSelect.value);
    savedModels[providerSelect.value] = modelInput.value.trim();
    apiKeyInput.placeholder = apiKeyPlaceholder(providerSelect.value);
    setConfigured(
      true,
      providerSelect.value,
      modelInput.value.trim(),
    );
    if (notificationsInput.checked && "Notification" in window && Notification.permission === "default") {
      await Notification.requestPermission();
    }
    closeSettings();
    refreshWeather();
    welcome.hidden = true;
    input.focus();
  } catch (error) {
    settingsError.textContent = error.message;
    settingsError.hidden = false;
  } finally {
    settingsSave.disabled = false;
    settingsSave.textContent = "Salva e collega";
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if ((!text && pendingAttachments.length === 0) || sending || !configured) return;
  const attachments = pendingAttachments;
  const messageText = text || "Analizza i file allegati.";
  welcome.hidden = true;
  if (messages.length === 0) pageTitle.textContent = messageText.slice(0, 50);
  messages.push({ role: "user", content: messageText, attachments });
  addMessage("user", messageText, "", attachments);
  pendingAttachments = [];
  renderPendingAttachments();
  input.value = "";
  resizeComposer();
  sending = true;
  sendButton.disabled = true;
  newChatButton.disabled = true;
  const pending = addMessage("assistant", "Sto pensando...", "pending");
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });
    const result = await readJsonResponse(response, "La richiesta non è riuscita.");
    if (!response.ok) throw new Error(result.error || "La richiesta non è riuscita.");
    const reply = await waitForChatJob(result.job_id);
    pending.remove();
    messages.push({ role: "assistant", content: reply });
    addMessage("assistant", reply);
    if (ttsAutoPlayInput.checked) speakText(reply);
  } catch (error) {
    pending.classList.remove("pending");
    pending.classList.add("error");
    const errorParagraph = document.createElement("p");
    errorParagraph.textContent = error.message;
    pending.querySelector(".message-body").replaceChildren(errorParagraph);
  } finally {
    sending = false;
    sendButton.disabled = !configured;
    newChatButton.disabled = false;
    input.focus();
  }
});

input.addEventListener("input", () => {
  resizeComposer();
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

async function refreshWorkflows() {
  const response = await fetch("/api/workflows");
  const result = await response.json();
  if (!response.ok) return;
  workflows = result.workflows || [];
  renderWorkflows();
}

window.setInterval(() => {
  if (!workflowPanel.hidden) void refreshWorkflows();
}, 30000);

loadConfig().catch((error) => {
  connectionLabel.textContent = error.message;
});
loadTelegramStatus().catch((error) => {
  telegramStatus.textContent = `Errore: ${error.message}`;
});
loadGoogleCalendarStatus().catch((error) => {
  googleCalendarStatus.textContent = `Errore: ${error.message}`;
});
handleGoogleCalendarReturn();
