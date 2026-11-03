(() => {
  const sidebar = document.querySelector(".sidebar");
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

  const styles = document.createElement("style");
  styles.textContent = `
    .chat-history-panel { min-height: 0; max-height: 35vh; margin: 15px 0 8px; overflow-y: auto; }
    .chat-history-heading { padding: 0 8px 7px; color: var(--muted); font-size: 9px; letter-spacing: 1.5px; }
    .chat-history-list { display: grid; gap: 3px; }
    .chat-history-row { display: flex; align-items: center; gap: 3px; min-width: 0; }
    .chat-history-open { flex: 1; min-width: 0; overflow: hidden; padding: 8px; color: var(--text); background: transparent; border: 1px solid transparent; border-radius: 5px; text-align: left; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; cursor: pointer; }
    .chat-history-open:hover, .chat-history-open.active { background: var(--panel-hover); border-color: var(--border); }
    .chat-history-delete { flex: 0 0 27px; width: 27px; height: 27px; color: var(--muted); background: transparent; border: 0; border-radius: 5px; cursor: pointer; }
    .chat-history-delete:hover { color: var(--text); background: var(--panel-hover); }
    .chat-history-empty { margin: 5px 8px; color: var(--muted); font-size: 10px; }
    @media (max-width: 680px) {
      .chat-history-panel { width: 100%; max-height: 30vh; }
      .chat-history-heading, .chat-history-open, .chat-history-delete { display: none; }
      .chat-history-panel.has-chats { display: none; }
    }
  `;
  document.head.append(styles);

  let chats = [];
  let activeChatId = null;
  let saveTimer = null;
  let isLoadingChat = false;

  function state() {
    return {
      conversation, welcome, input, pageTitle,
      messages, sending, configured, addMessage, resizeComposer,
    };
  }

  function makeChat() {
    return {
      id: crypto.randomUUID().replaceAll("-", ""),
      title: "Nuova chat",
      updated_at: Date.now(),
      messages: [],
    };
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

  function syncActiveMessages() {
    const current = chats.find((chat) => chat.id === activeChatId);
    if (!current) return;
    current.messages = state().messages
      .filter((message) => ["user", "assistant"].includes(message.role))
      .map((message) => ({ role: message.role, content: message.content }));
    current.updated_at = Date.now();
    const firstUserMessage = current.messages.find((message) => message.role === "user");
    if (firstUserMessage && (!current.title || current.title === "Nuova chat")) {
      current.title = firstUserMessage.content.trim().replace(/\s+/g, " ").slice(0, 48)
        || "Nuova chat";
    }
    renderChats();
  }

  async function persistChat(chat = chats.find((item) => item.id === activeChatId)) {
    if (!chat) return;
    const response = await fetch("/api/chats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "save", chat }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Salvataggio chat non riuscito.");
    chats = result.chats || chats;
    renderChats();
  }

  function scheduleSave() {
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(async () => {
      if (isLoadingChat) return;
      syncActiveMessages();
      try { await persistChat(); }
      catch (error) { console.error("Impossibile salvare la conversazione:", error); }
    }, 350);
  }

  function renderActiveChat(chat) {
    isLoadingChat = true;
    const current = state();
    current.messages.splice(0, current.messages.length, ...chat.messages.map((item) => ({
      role: item.role, content: item.content,
    })));
    current.conversation.replaceChildren(current.welcome);
    for (const message of current.messages) current.addMessage(message.role, message.content);
    current.welcome.hidden = current.messages.length > 0;
    current.input.value = "";
    current.resizeComposer();
    current.pageTitle.textContent = chat.messages.length
      ? (chat.title || "Conversazione")
      : "Una nuova conversazione";
    activeChatId = chat.id;
    isLoadingChat = false;
    renderChats();
  }

  function openChat(chatId) {
    if (state().sending || chatId === activeChatId) return;
    syncActiveMessages();
    const chat = chats.find((item) => item.id === chatId);
    if (chat) renderActiveChat(chat);
  }

  async function createChat() {
    if (state().sending) return;
    syncActiveMessages();
    const chat = makeChat();
    chats.unshift(chat);
    renderActiveChat(chat);
    try { await persistChat(chat); }
    catch (error) { console.error("Impossibile creare la conversazione:", error); }
  }

  async function deleteChat(chatId) {
    if (state().sending) return;
    const chat = chats.find((item) => item.id === chatId);
    if (!chat || !window.confirm(`Eliminare la chat “${chat.title || "Nuova chat"}”?`)) return;
    try {
      const response = await fetch("/api/chats", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "delete", id: chatId }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Eliminazione chat non riuscita.");
      chats = result.chats || [];
      if (activeChatId === chatId) {
        if (!chats.length) chats.push(makeChat());
        renderActiveChat(chats[0]);
        await persistChat(chats[0]);
      } else renderChats();
    } catch (error) { window.alert(error.message); }
  }

  async function initializeChats() {
    try {
      const response = await fetch("/api/chats");
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Cronologia chat non disponibile.");
      chats = result.chats || [];
      if (!chats.length) chats = [makeChat()];
      chats.sort((left, right) => right.updated_at - left.updated_at);
      renderActiveChat(chats[0]);
      if (!result.chats?.length) await persistChat(chats[0]);
    } catch (error) {
      const empty = document.createElement("p");
      empty.className = "chat-history-empty";
      empty.textContent = "Cronologia non disponibile";
      historyList.replaceChildren(empty);
      console.error("Impossibile caricare le conversazioni:", error);
    }
  }

  function removeChromeEmoji(root = document) {
    const replacements = [
      ["#mic-toggle", "Microfono"],
      ["#theme-toggle span:first-child", "◐"],
      ["#settings-toggle span:first-child", "·"],
      ['[data-open-app="tasks"] span:first-child', "□"],
      [".privacy-note span", "Nota"],
    ];
    for (const [selector, text] of replacements) {
      root.querySelectorAll?.(selector).forEach((element) => { element.textContent = text; });
    }
    root.querySelectorAll?.(".message-role").forEach((element) => {
      if (element.textContent.trim() === "✳") element.textContent = "N";
    });
    root.querySelectorAll?.(".speak-message").forEach((element) => { element.textContent = "Leggi"; });
    root.querySelectorAll?.(".function-card-icon").forEach((element) => {
      if (["☑", "⚙"].includes(element.textContent.trim())) {
        element.textContent = element.textContent.trim() === "☑" ? "□" : "·";
      }
    });
  }

  newChatButton.addEventListener("click", () => {
    window.setTimeout(() => { void createChat(); }, 0);
  });
  document.querySelector("#chat-form").addEventListener("submit", () => {
    if (isLoadingChat) return;
    window.setTimeout(() => {
      syncActiveMessages();
      scheduleSave();
      const waitForReply = async () => {
        while (state().sending) await new Promise((resolve) => setTimeout(resolve, 200));
        syncActiveMessages();
        try { await persistChat(); }
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
      } catch (error) {
        console.warn("Non è stato possibile limitare il contesto chat:", error);
      }
    }
    return originalFetch(resource, options);
  };

  const observer = new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType === Node.ELEMENT_NODE) removeChromeEmoji(node);
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
  removeChromeEmoji();
  void initializeChats();
})();
