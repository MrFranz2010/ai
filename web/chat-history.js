(() => {
  const newChatButton = document.querySelector("#new-chat");
  const historyPanel = document.createElement("section");
  historyPanel.className = "chat-history-panel";
  historyPanel.setAttribute("aria-label", "Conversazioni salvate");
  const historyHeading = document.createElement("div");
  historyHeading.className = "chat-history-heading";
  historyHeading.textContent = "CONVERSAZIONI";
  const historyExport = document.createElement("button");
  historyExport.type = "button";
  historyExport.className = "chat-history-export";
  historyExport.textContent = "Esporta";
  historyExport.title = "Esporta tutte le chat in Markdown";
  historyHeading.append(historyExport);
  const historySearch = document.createElement("input");
  historySearch.type = "search";
  historySearch.className = "chat-history-search";
  historySearch.placeholder = "Cerca nelle chat…";
  historySearch.setAttribute("aria-label", "Cerca nelle conversazioni");
  const historyList = document.createElement("div");
  historyList.className = "chat-history-list";
  historyPanel.append(historyHeading, historySearch, historyList);
  newChatButton.after(historyPanel);

  let chats = [];
  let activeChatId = null;
  let isLoadingChat = false;
  let saveTimer = null;
  let chatQuery = "";

  function state() {
    return { conversation, welcome, input, pageTitle, messages, sending, addMessage, resizeComposer };
  }

  function newChatRecord() {
    return { id: crypto.randomUUID().replaceAll("-", ""), title: "Nuova chat", updated_at: Date.now(), messages: [] };
  }

  function renderChats() {
    historyList.replaceChildren();
    historyPanel.classList.toggle("has-chats", chats.length > 0);
    const query = chatQuery.trim().toLocaleLowerCase("it");
    const visible = query
      ? chats.filter((chat) => {
          if ((chat.title || "").toLocaleLowerCase("it").includes(query)) return true;
          return (chat.messages || []).some((message) =>
            (message.content || "").toLocaleLowerCase("it").includes(query)
          );
        })
      : chats;
    if (!visible.length) {
      const empty = document.createElement("p");
      empty.className = "chat-history-empty";
      empty.textContent = query ? "Nessuna chat corrisponde alla ricerca" : "Nessuna chat salvata";
      historyList.append(empty);
      return;
    }
    for (const chat of visible) {
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
      if (query) {
        const message = (chat.messages || []).find((item) =>
          (item.content || "").toLocaleLowerCase("it").includes(query)
        );
        if (message) {
          const at = (message.content || "").toLocaleLowerCase("it").indexOf(query);
          const start = Math.max(0, at - 35);
          const snippet = document.createElement("p");
          snippet.className = "chat-history-snippet";
          snippet.textContent = `${start > 0 ? "…" : ""}${message.content.slice(start, start + 90)}${message.content.length > start + 90 ? "…" : ""}`;
          historyList.append(snippet);
        }
      }
    }
  }

  function downloadText(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function exportChats() {
    const lines = [];
    for (const chat of chats) {
      lines.push(`# ${chat.title || "Nuova chat"}`, "");
      for (const message of chat.messages || []) {
        lines.push(`**${message.role === "user" ? "Utente" : "NOKK"}:** ${message.content}`, "");
      }
      lines.push("---", "");
    }
    downloadText("nokk-chat.md", lines.join("\n"), "text/markdown;charset=utf-8");
  }

  historySearch.addEventListener("input", () => {
    chatQuery = historySearch.value;
    renderChats();
  });
  historyExport.addEventListener("click", exportChats);

  function syncActive() {
    const chat = chats.find((item) => item.id === activeChatId);
    if (!chat) return;
    chat.messages = state().messages
      .filter((message) => ["user", "assistant"].includes(message.role))
      .map((message) => ({ role: message.role, content: message.content }));
    chat.updated_at = Date.now();
    const firstUser = chat.messages.find((message) => message.role === "user");
    const firstReply = chat.messages.find((message) => message.role === "assistant");
    if (
      firstUser
      && (!chat.title || chat.title === "Nuova chat" || isGenericChatTitle(chat.title))
    ) {
      chat.title = summarizeChatTitle(
        firstUser.content,
        firstReply ? firstReply.content : "",
      );
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

  void initialize();
})();
