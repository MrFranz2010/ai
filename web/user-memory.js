(() => {
  const sidebar = document.querySelector(".sidebar");
  const openButton = document.createElement("button");
  openButton.type = "button";
  openButton.className = "user-memory-trigger";
  openButton.textContent = "Profilo per NOKK";
  openButton.setAttribute("aria-label", "Gestisci le informazioni ricordate da NOKK");
  const appMenu = sidebar.querySelector(".app-menu");
  appMenu.after(openButton);

  const overlay = document.createElement("section");
  overlay.className = "user-memory-overlay";
  overlay.hidden = true;
  overlay.innerHTML = `
    <div class="user-memory-card" role="dialog" aria-modal="true" aria-labelledby="user-memory-title">
      <div class="user-memory-heading">
        <div><p class="eyebrow">MEMORIA PERSONALE</p><h2 id="user-memory-title">Informazioni su di te</h2></div>
        <button class="user-memory-close" type="button" aria-label="Chiudi">×</button>
      </div>
      <p class="user-memory-description">Aggiungi un’informazione per riga, ad esempio preferenze o obiettivi. Puoi anche caricare un file di testo o un PDF, come l’orario scolastico: le sue righe vengono aggiunte alla memoria. NOKK userà tutto come contesto aggiuntivo nelle chat. Non inserire password, chiavi o dati molto sensibili. Queste informazioni vengono inviate al provider AI configurato quando chatti.</p>
      <label for="user-memory-input">Informazioni da ricordare</label>
      <textarea id="user-memory-input" rows="9" maxlength="15000" placeholder="Preferisco risposte in italiano e concise.&#10;Sto imparando Python."></textarea>
      <input class="user-memory-file" type="file" accept=".txt,.md,.csv,.json,.log,.pdf,.docx" hidden>
      <p class="user-memory-status" role="status" aria-live="polite"></p>
      <div class="user-memory-actions">
        <div class="user-memory-left">
          <button class="user-memory-upload" type="button">Carica file</button>
          <button class="user-memory-clear" type="button">Dimentica tutto</button>
        </div>
        <button class="user-memory-save" type="button">Salva</button>
      </div>
    </div>`;
  document.body.append(overlay);

  const css = document.createElement("style");
  css.textContent = `
    .user-memory-trigger { min-height: 38px; margin: 10px 0 3px; padding: 0 11px; color: var(--text); background: transparent; border: 1px solid var(--border); border-radius: 5px; text-align: left; font-size: 11px; cursor: pointer; }
    .user-memory-trigger:hover { background: var(--panel-hover); }
    .user-memory-overlay { position: fixed; inset: 0; z-index: 20; display: grid; place-items: center; padding: 18px; background: #000a; }
    .user-memory-overlay[hidden] { display: none; }
    .user-memory-card { width: min(100%, 520px); max-height: 90dvh; overflow-y: auto; padding: 22px; color: var(--text); background: var(--sidebar); border: 1px solid var(--border); border-radius: 10px; }
    .user-memory-heading { display: flex; justify-content: space-between; gap: 12px; }
    .user-memory-heading h2 { margin: 0; font-size: 20px; }
    .user-memory-close { width: 32px; height: 32px; color: var(--text); background: transparent; border: 0; font-size: 24px; cursor: pointer; }
    .user-memory-description { color: var(--muted); font-size: 12px; line-height: 1.6; }
    .user-memory-card label { display: block; margin: 14px 0 6px; font-size: 12px; }
    .user-memory-card textarea { width: 100%; padding: 10px; color: var(--text); background: var(--page); border: 1px solid var(--border); border-radius: 6px; font: inherit; resize: vertical; }
    .user-memory-status { min-height: 18px; color: var(--muted); font-size: 11px; }
    .user-memory-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .user-memory-left { display: flex; flex-wrap: wrap; gap: 8px; }
    .user-memory-actions button { min-height: 36px; padding: 0 12px; color: var(--text); background: var(--panel); border: 1px solid var(--border); border-radius: 5px; cursor: pointer; }
    .user-memory-actions button:disabled { opacity: .55; cursor: wait; }
    .user-memory-actions .user-memory-save { color: white; background: #9e343b; }
    @media (max-width: 820px) { .user-memory-trigger { width: 100%; min-height: 38px; padding: 0 11px; overflow: visible; font-size: 11px; text-align: left; } .user-memory-trigger::after { content: none; } }
    @media (max-width: 680px) { .user-memory-overlay { padding: 0; } .user-memory-card { width: 100%; height: 100dvh; max-height: 100dvh; border-radius: 0; padding: 20px 16px calc(20px + env(safe-area-inset-bottom)); } }
  `;
  document.head.append(css);

  const textarea = overlay.querySelector("#user-memory-input");
  const status = overlay.querySelector(".user-memory-status");
  const saveButton = overlay.querySelector(".user-memory-save");
  const clearButton = overlay.querySelector(".user-memory-clear");
  const uploadButton = overlay.querySelector(".user-memory-upload");
  const fileInput = overlay.querySelector(".user-memory-file");
  const textFileExtensions = new Set([".txt", ".md", ".csv", ".json", ".log"]);
  const maxFileBytes = 4 * 1024 * 1024;
  let memoryLoaded = false;

  function fileExtension(name) {
    const index = name.lastIndexOf(".");
    return index === -1 ? "" : name.slice(index).toLowerCase();
  }

  function base64FromBuffer(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let index = 0; index < bytes.length; index += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    }
    return btoa(binary);
  }

  async function extractFileText(file) {
    if (file.size > maxFileBytes) {
      throw new Error("Il file deve essere più piccolo di 4 MB.");
    }
    const extension = fileExtension(file.name);
    if (textFileExtensions.has(extension)) {
      const content = (await file.text()).replace(/^\uFEFF/, "");
      if (!content.trim()) throw new Error("Il file è vuoto.");
      return content;
    }
    if (extension === ".pdf" || extension === ".docx") {
      const data = base64FromBuffer(await file.arrayBuffer());
      const response = await fetch("/api/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: file.name, data }),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || "Estrazione del documento non riuscita.");
      }
      return result.text;
    }
    throw new Error("Formato non supportato. Usa TXT, MD, CSV, JSON, LOG, PDF o DOCX.");
  }

  async function loadMemory() {
    status.textContent = "Caricamento…";
    try {
      const response = await fetch("/api/memory");
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Memoria non disponibile.");
      textarea.value = (result.memories || []).join("\n");
      memoryLoaded = true;
      status.textContent = "";
    } catch (error) {
      memoryLoaded = false;
      status.textContent = error.message;
    }
  }

  async function saveMemory(memories) {
    saveButton.disabled = true;
    clearButton.disabled = true;
    status.textContent = "Salvataggio…";
    try {
      const response = await fetch("/api/memory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "save", memories }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Salvataggio non riuscito.");
      textarea.value = (result.memories || []).join("\n");
      memoryLoaded = true;
      status.textContent = "Memoria aggiornata.";
    } catch (error) { status.textContent = error.message; }
    finally { saveButton.disabled = false; clearButton.disabled = false; }
  }

  async function uploadMemoryFile(file) {
    saveButton.disabled = true;
    clearButton.disabled = true;
    uploadButton.disabled = true;
    status.textContent = `Lettura di ${file.name}…`;
    try {
      const text = await extractFileText(file);
      const memories = textarea.value
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean);
      status.textContent = "Salvataggio del file nella memoria…";
      const payload = { action: "append_file", name: file.name, text };
      if (memoryLoaded) payload.memories = memories;
      const response = await fetch("/api/memory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Caricamento non riuscito.");
      textarea.value = (result.memories || []).join("\n");
      status.textContent = `File aggiunto alla memoria: ${file.name}.`;
    } catch (error) {
      status.textContent = error.message;
    } finally {
      saveButton.disabled = false;
      clearButton.disabled = false;
      uploadButton.disabled = false;
      fileInput.value = "";
    }
  }

  openButton.addEventListener("click", () => {
    overlay.hidden = false;
    void loadMemory();
    textarea.focus();
  });
  overlay.querySelector(".user-memory-close").addEventListener("click", () => { overlay.hidden = true; });
  overlay.addEventListener("click", (event) => { if (event.target === overlay) overlay.hidden = true; });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !overlay.hidden) overlay.hidden = true;
  });
  saveButton.addEventListener("click", () => {
    const memories = textarea.value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
    void saveMemory(memories);
  });
  clearButton.addEventListener("click", () => {
    if (confirm("Vuoi cancellare tutte le informazioni che NOKK ricorda su di te?")) {
      textarea.value = "";
      void saveMemory([]);
    }
  });
  uploadButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (file) void uploadMemoryFile(file);
  });
})();
