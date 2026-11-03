(() => {
  const newChatButton = document.querySelector("#new-chat");
  const historyPanel = document.createElement("section");
  historyPanel.className = "chat-history-panel";
  historyPanel.setAttribute("aria-label", "Conversazioni salvate");
  const historyHeading = document.createElement("div");
  historyHeading.className = "chat-history-heading";
  historyHeading.textContent = "CONVERSAZIONI";
  const historyList = document.createElement("div");
  historyList.className = "chat-history-list";
  historyPanel.append(historyHeading, historyList);
  newChatButton.after(historyPanel);

  let chats = [];
  let activeChatId = null;
  let isLoadingChat = false;
  let saveTimer = null;

  function state() {
    return { conversation, welcome, input, pageTitle, messages, sending, addMessage, resizeComposer };
  }

  function newChatRecord() {
    return { id: crypto.randomUUID().replaceAll("-", ""), title: "Nuova chat", updated_at: Date.now(), messages: [] };
  }

  function renderChats() {
    historyList.replaceChildren();
    historyPanel.classList.toggle("has-chats", chats.length > 0);
    if (!chats.length) {
      const empty = document.createElement("p");
      empty.className = "chat-history-empty";
      empty.textContent = "Nessuna chat salvata";
      historyList.append(empty);
      return;
    }
    for (const chat of chats) {
      const row = document.createElement("div");
      row.className = "chat-history-row";
      const open = document.createElement("button");
      open.type = "button";
      open.className = "chat-history-open";
      open.classList.toggle("active", chat.id === activeChatId);
      open.textContent = chat.title || "Nuova chat";
      open.title = open.textContent;
      open.disabled = state().sending;
      open.addEventListener("click", () => openChat(chat.id));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "chat-history-delete";
      remove.textContent = "×";
      remove.title = `Elimina ${chat.title || "Nuova chat"}`;
      remove.setAttribute("aria-label", remove.title);
      remove.disabled = state().sending;
      remove.addEventListener("click", () => deleteChat(chat.id));
      row.append(open, remove);
      historyList.append(row);
    }
  }

  function syncActive() {
    const chat = chats.find((item) => item.id === activeChatId);
    if (!chat) return;
    chat.messages = state().messages
      .filter((message) => ["user", "assistant"].includes(message.role))
      .map((message) => ({ role: message.role, content: message.content }));
    chat.updated_at = Date.now();
    const firstUser = chat.messages.find((message) => message.role === "user");
    if (firstUser && (!chat.title || chat.title === "Nuova chat")) {
      chat.title = firstUser.content.trim().replace(/\s+/g, " ").slice(0, 48) || "Nuova chat";
    }
    renderChats();
  }

  async function saveChat(chat = chats.find((item) => item.id === activeChatId)) {
    if (!chat) return;
    const response = await fetch("/api/chats", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "save", chat }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Salvataggio chat non riuscito.");
    chats = result.chats || chats;
    renderChats();
  }

  function saveSoon() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
      if (isLoadingChat) return;
      syncActive();
      try { await saveChat(); }
      catch (error) { console.error("Impossibile salvare la conversazione:", error); }
    }, 350);
  }

  function showChat(chat) {
    isLoadingChat = true;
    const current = state();
    current.messages.splice(0, current.messages.length, ...chat.messages.map((item) => ({ role: item.role, content: item.content })));
    current.conversation.replaceChildren(current.welcome);
    for (const message of current.messages) current.addMessage(message.role, message.content);
    current.welcome.hidden = current.messages.length > 0;
    current.input.value = "";
    current.resizeComposer();
    current.pageTitle.textContent = chat.messages.length ? (chat.title || "Conversazione") : "Una nuova conversazione";
    activeChatId = chat.id;
    isLoadingChat = false;
    renderChats();
  }

  function openChat(id) {
    if (state().sending || id === activeChatId) return;
    syncActive();
    const chat = chats.find((item) => item.id === id);
    if (chat) showChat(chat);
  }

  async function createChat() {
    if (state().sending) return;
    syncActive();
    const chat = newChatRecord();
    chats.unshift(chat);
    showChat(chat);
    try { await saveChat(chat); }
    catch (error) { console.error("Impossibile creare la chat:", error); }
  }

  async function deleteChat(id) {
    if (state().sending) return;
    const chat = chats.find((item) => item.id === id);
    if (!chat || !confirm(`Eliminare la chat “${chat.title || "Nuova chat"}”?`)) return;
    try {
      const response = await fetch("/api/chats", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "delete", id }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Eliminazione chat non riuscita.");
      chats = result.chats || [];
      if (activeChatId === id) {
        if (!chats.length) chats.push(newChatRecord());
        showChat(chats[0]);
        await saveChat(chats[0]);
      } else renderChats();
    } catch (error) { alert(error.message); }
  }

  async function initialize() {
    try {
      const response = await fetch("/api/chats");
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Cronologia chat non disponibile.");
      chats = result.chats || [];
      if (!chats.length) chats = [newChatRecord()];
      chats.sort((a, b) => b.updated_at - a.updated_at);
      showChat(chats[0]);
      if (!result.chats?.length) await saveChat(chats[0]);
    } catch (error) {
      historyList.textContent = "Cronologia chat non disponibile";
      console.error("Impossibile caricare le conversazioni:", error);
    }
  }

  function removeEmoji(root = document) {
    for (const [selector, text] of [
      ["#mic-toggle", "Microfono"], ["#theme-toggle span:first-child", "◐"],
      ["#settings-toggle span:first-child", "·"],
      ['[data-open-app="tasks"] span:first-child', "□"], [".privacy-note span", "Nota"],
    ]) root.querySelectorAll?.(selector).forEach((el) => { el.textContent = text; });
    root.querySelectorAll?.(".message-role").forEach((el) => { if (el.textContent.trim() === "✳") el.textContent = "N"; });
    root.querySelectorAll?.(".speak-message").forEach((el) => { el.textContent = "Leggi"; });
    root.querySelectorAll?.(".function-card-icon").forEach((el) => {
      if (["☑", "⚙"].includes(el.textContent.trim())) el.textContent = el.textContent.trim() === "☑" ? "□" : "·";
    });
  }

  // Capture before the default new-chat handler clears the current messages.
  newChatButton.addEventListener("click", (event) => {
    event.stopImmediatePropagation();
    void createChat();
  }, true);
  document.querySelector("#chat-form").addEventListener("submit", () => {
    if (isLoadingChat) return;
    setTimeout(() => {
      syncActive();
      saveSoon();
      const waitForReply = async () => {
        while (state().sending) await new Promise((resolve) => setTimeout(resolve, 200));
        syncActive();
        try { await saveChat(); }
        catch (error) { console.error("Impossibile salvare la risposta:", error); }
      };
      void waitForReply();
    }, 0);
  });

  const originalFetch = window.fetch.bind(window);
  window.fetch = (resource, options = {}) => {
    if (String(resource).split("?")[0] === "/api/chat" && options.body) {
      try {
        const body = JSON.parse(options.body);
        if (Array.isArray(body.messages) && body.messages.length > 40) {
          body.messages = body.messages.slice(-40);
          options = { ...options, body: JSON.stringify(body) };
        }
      } catch (error) { console.warn("Contesto chat non limitato:", error); }
    }
    return originalFetch(resource, options);
  };

  const observer = new MutationObserver((records) => {
    for (const record of records) for (const node of record.addedNodes) {
      if (node.nodeType === Node.ELEMENT_NODE) removeEmoji(node);
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
  removeEmoji();
  void initialize();
})();
