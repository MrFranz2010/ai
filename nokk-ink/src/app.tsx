import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import fs from "node:fs";
import path from "node:path";
import { Box, Text, useApp, useInput } from "ink";
import { NokkClient, NokkError, type Job, type ToolEvent } from "./client.js";
import {
  DEFAULT_BASE_URL,
  configPath,
  loadConfig,
  normalizeMode,
  saveConfig,
  sessionsPath,
  type Mode,
  type NokkConfig,
} from "./config.js";
import {
  collectFileContext,
  copyText,
  extractRunCommands,
  needsSudo,
  runCapture,
  runLocal,
  type LocalResult,
} from "./local.js";
import { loadSessions, newChat, saveSessions, type ChatSession, type StoredMessage } from "./sessions.js";
import type { ChatState, ViewMessage } from "./types.js";
import { viewFromMessages } from "./types.js";
import {
  Banner,
  COLORS,
  CommandPalette,
  Composer,
  ConfirmPanel,
  Header,
  HelpPanel,
  PasswordPanel,
  SettingsPanel,
  StatusBar,
  Transcript,
  shortPath,
} from "./ui.js";

const MODES: Mode[] = ["codice", "studio", "analista", null];
const COMMAND_NAMES = [
  "/new", "/clear", "/cd", "/pwd", "/run", "/agent", "/mode", "/model",
  "/profile", "/url", "/key", "/settings", "/status", "/sessions", "/resume", "/delete",
  "/rename", "/export", "/copy", "/retry", "/diff", "/git", "/jobs", "/update",
  "/cancel", "/config", "/exit", "/help",
];
const POLL_MS = 500;

type Dialog =
  | { kind: "confirm"; title: string; detail: string; resolve: (value: boolean) => void }
  | { kind: "password"; title: string; detail: string; resolve: (value: string | null) => void }
  | null;

interface ModelOverride {
  provider: string;
  model: string;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function toChat(session: ChatSession): ChatState {
  const messages = session.messages.map((message) => ({ ...message }));
  return {
    title: session.title,
    createdAt: session.createdAt,
    messages,
    view: viewFromMessages(messages),
  };
}

function toStored(chats: ChatState[]): ChatSession[] {
  return chats.map((chat) => ({
    title: chat.title,
    createdAt: chat.createdAt,
    messages: chat.messages,
  }));
}

function formatResult(result: LocalResult): string {
  return [
    "Ho eseguito questo comando sulla macchina locale:",
    `comando: ${result.command}`,
    `exit code: ${result.exitCode}`,
    "output:",
    result.output.trim() || "(nessun output)",
  ].join("\n");
}

function safeConfig(config: NokkConfig): Record<string, unknown> {
  return {
    base_url: config.baseUrl,
    profile: config.profile,
    mode: config.mode,
    agent: config.agent,
    auto_approve: config.autoApprove,
    stream: config.stream,
    save_sessions: config.saveSessions,
    max_rounds: config.maxRounds,
    job_timeout: config.jobTimeout,
    bell_on_finish: config.bellOnFinish,
    api_key_configured: Boolean(config.apiKey),
  };
}

export function App({ initialConfig, configFile = configPath() }: { initialConfig: NokkConfig; configFile?: string }): React.ReactElement {
  const { exit } = useApp();
  const [config, setConfigState] = useState(initialConfig);
  const configRef = useRef(initialConfig);
  const [chats, setChats] = useState<ChatState[]>(() => {
    const loaded = loadSessions(sessionsPath(configFile)).map(toChat);
    return loaded.length ? loaded : [toChat(newChat())];
  });
  const chatsRef = useRef(chats);
  const [active, setActive] = useState(0);
  const activeRef = useRef(0);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [status, setStatus] = useState("pronto");
  const [partial, setPartial] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [startedAt, setStartedAt] = useState(0);
  const [online, setOnline] = useState<boolean | null>(null);
  const [modelLabel, setModelLabel] = useState("");
  const [overlay, setOverlay] = useState<"help" | "settings" | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [modelOverride, setModelOverride] = useState<ModelOverride | null>(null);
  const cancelRef = useRef(false);
  const currentJobRef = useRef<string | null>(null);
  const activeLocalRef = useRef<AbortController | null>(null);
  const initialised = useRef(false);

  const activeChat = chats[active] || chats[0];

  const client = useCallback(
    () => new NokkClient(configRef.current.baseUrl, configRef.current.apiKey),
    [],
  );

  const persist = useCallback((force = false) => {
    if (!force && !configRef.current.saveSessions) return;
    try {
      saveSessions(sessionsPath(configFile), toStored(chatsRef.current));
    } catch (error) {
      setStatus(`salvataggio non riuscito: ${error instanceof Error ? error.message : String(error)}`);
    }
  }, [configFile]);

  const commit = useCallback((next: ChatState[], nextActive = activeRef.current, force = false) => {
    chatsRef.current = next;
    activeRef.current = nextActive;
    setChats(next);
    setActive(nextActive);
    persist(force);
  }, [persist]);

  const updateConfig = useCallback((patch: Partial<NokkConfig>) => {
    const next = { ...configRef.current, ...patch };
    configRef.current = next;
    setConfigState(next);
    try {
      saveConfig(next, configFile);
    } catch (error) {
      setStatus(`config non salvata: ${error instanceof Error ? error.message : String(error)}`);
    }
  }, [configFile]);

  const updateActive = useCallback((updater: (chat: ChatState) => ChatState, force = false) => {
    const next = chatsRef.current.map((chat, index) =>
      index === activeRef.current ? updater(chat) : chat,
    );
    commit(next, activeRef.current, force);
  }, [commit]);

  const addView = useCallback((message: ViewMessage) => {
    updateActive((chat) => ({ ...chat, view: [...chat.view, message] }));
  }, [updateActive]);

  const addStored = useCallback((message: StoredMessage) => {
    updateActive((chat) => ({ ...chat, messages: [...chat.messages, message] }));
  }, [updateActive]);

  const appendExchange = useCallback((role: "user" | "assistant", content: string, hidden = false) => {
    const message: StoredMessage = { role, content, ...(hidden ? { hidden: true } : {}) };
    updateActive((chat) => {
      const title =
        role === "user" && !hidden && (!chat.title || /^Chat \d+$/.test(chat.title))
          ? content.length > 42 ? `${content.slice(0, 41)}…` : content
          : chat.title;
      return {
        ...chat,
        title,
        messages: [...chat.messages, message],
        view: hidden ? chat.view : [...chat.view, { role, content } as ViewMessage],
      };
    });
  }, [updateActive]);

  const addTool = useCallback((command: string, result: LocalResult) => {
    addView({
      role: "tool",
      content: result.output.trim() || "(nessun output)",
      command,
      exitCode: result.exitCode,
    });
  }, [addView]);

  const askConfirm = useCallback((title: string, detail: string): Promise<boolean> => (
    new Promise((resolve) => setDialog({ kind: "confirm", title, detail, resolve }))
  ), []);

  const askSecret = useCallback((title: string, detail: string): Promise<string | null> => (
    new Promise((resolve) => setDialog({ kind: "password", title, detail, resolve }))
  ), []);

  const setBusyState = useCallback((value: boolean) => {
    busyRef.current = value;
    setBusy(value);
    if (value) {
      setStartedAt(Date.now());
      setElapsed(0);
    }
  }, []);

  useEffect(() => {
    if (!busy) return undefined;
    const timer = setInterval(() => {
      if (startedAt) setElapsed((Date.now() - startedAt) / 1000);
    }, 100);
    return () => clearInterval(timer);
  }, [busy, startedAt]);

  const checkHealth = useCallback(async () => {
    try {
      const data = await client().health();
      setOnline(true);
      const provider = typeof data.provider === "string" ? data.provider : "";
      const model = typeof data.model === "string" ? data.model : "";
      setModelLabel([provider, model].filter(Boolean).join("/"));
    } catch {
      setOnline(false);
    }
  }, [client]);

  useEffect(() => {
    if (!initialised.current) {
      initialised.current = true;
      void checkHealth();
    }
  }, [checkHealth]);

  const appendSystem = useCallback((content: string) => {
    addView({ role: "system", content });
  }, [addView]);

  const switchProfile = useCallback((profile: "local" | "hosting") => {
    const current = configRef.current;
    if (profile === "hosting" && !current.hostingUrl) {
      addView({ role: "error", content: "Profilo hosting non configurato: usa /url <indirizzo> e /key." });
      return;
    }
    const next: NokkConfig = { ...current, profile };
    if (profile === "local") {
      next.baseUrl = current.localUrl || DEFAULT_BASE_URL;
      next.apiKey = current.localApiKey;
    } else {
      next.baseUrl = current.hostingUrl;
      next.apiKey = current.hostingApiKey;
    }
    updateConfig(next);
    void checkHealth();
    appendSystem(`Profilo: ${profile} · ${next.baseUrl}`);
  }, [addView, appendSystem, checkHealth, updateConfig]);

  const finishRun = useCallback(() => {
    activeLocalRef.current = null;
    setBusyState(false);
    setPartial("");
    setStatus("pronto");
    currentJobRef.current = null;
    if (configRef.current.bellOnFinish) process.stdout.write("\u0007");
  }, [setBusyState]);

  const runShell = useCallback(async (command: string) => {
    const trimmed = command.trim();
    if (!trimmed) return;
    setBusyState(true);
    setStatus("comando locale");
    try {
      const password = needsSudo(trimmed)
        ? await askSecret("Password sudo", `Serve per eseguire: ${trimmed}`)
        : undefined;
      if (password === null) {
        appendSystem("Comando annullato: password sudo non inserita.");
        return;
      }
      const controller = new AbortController();
      activeLocalRef.current = controller;
      const result = await runLocal(trimmed, process.cwd(), password || undefined, controller.signal);
      activeLocalRef.current = null;
      addTool(trimmed, result);
      appendExchange("user", formatResult(result), true);
      if (result.cancelled) appendSystem("Comando locale annullato.");
    } catch (error) {
      addView({ role: "error", content: error instanceof Error ? error.message : String(error) });
    } finally {
      finishRun();
    }
  }, [addTool, appendExchange, appendSystem, askSecret, finishRun, setBusyState, addView]);

  const pollJob = useCallback(async (jobId: string): Promise<Job> => {
    const deadline = Date.now() + configRef.current.jobTimeout * 1000;
    const seen = new Set<number>();
    while (Date.now() < deadline) {
      if (cancelRef.current) {
        try { await client().cancel(jobId); } catch { /* best effort */ }
        throw new NokkError("Attività annullata.");
      }
      const job = await client().job(jobId);
      if (typeof job.partial_reply === "string") {
        setPartial(job.partial_reply);
        setStatus(`NOKK sta scrivendo… ${job.partial_reply.length} caratteri`);
      }
      (job.tool_events || []).forEach((event: ToolEvent, index: number) => {
        if (seen.has(index)) return;
        seen.add(index);
        const command = event.command || event.tool || "tool";
        setStatus(`tool: ${command.slice(0, 50)}`);
      });
      if (job.status === "complete" || job.status === "failed" || job.status === "cancelled") {
        return job;
      }
      if (job.status === "awaiting_approval") {
        const action = job.action || {};
        const actionId = typeof action.id === "string" ? action.id : "";
        const approved = configRef.current.autoApprove
          ? true
          : await askConfirm(
              "Approvazione server",
              `NOKK vuole eseguire sul server:\n${action.command || "(comando)"}`,
            );
        if (actionId) await client().approve(jobId, actionId, approved);
        setStatus(approved ? "comando server approvato" : "comando server rifiutato");
        continue;
      }
      await sleep(POLL_MS);
    }
    throw new NokkError(`Attività non conclusa entro ${configRef.current.jobTimeout} secondi.`);
  }, [askConfirm, client]);

  const runConversation = useCallback(async (text: string) => {
    if (busyRef.current) {
      appendSystem("Attendi: NOKK sta già lavorando.");
      return;
    }
    setBusyState(true);
    setStatus("NOKK sta pensando…");
    setPartial("");
    cancelRef.current = false;
    appendExchange("user", text);
    const fileContext = collectFileContext(text, process.cwd());
    if (fileContext) appendExchange("user", fileContext, true);
    let round = 0;

    try {
      while (true) {
        const chat = chatsRef.current[activeRef.current];
        const messages = chat.messages.map((message) => ({ role: message.role, content: message.content }));
        const options = {
          mode: configRef.current.mode,
          stream: configRef.current.stream,
          terminalEnabled: configRef.current.agent ? false : undefined,
          localTerminal: configRef.current.agent,
          provider: modelOverride?.provider,
          model: modelOverride?.model,
        };
        const jobId = await client().startChat(messages, options);
        currentJobRef.current = jobId;
        const job = await pollJob(jobId);
        currentJobRef.current = null;
        setPartial("");

        if (job.status === "failed") {
          throw new NokkError(job.error || "Attività fallita sul server.", job.hint || job.details);
        }
        if (job.status === "cancelled") {
          addView({ role: "system", content: "Attività annullata." });
          return;
        }
        const reply = (job.reply || "").trim();
        if (!reply) throw new NokkError("Il server ha restituito una risposta vuota.");
        appendExchange("assistant", reply);
        const commands = configRef.current.agent ? extractRunCommands(reply) : [];
        if (!commands.length) break;
        if (configRef.current.maxRounds && round >= configRef.current.maxRounds) {
          appendSystem("Limite di comandi locali raggiunto.");
          break;
        }
        for (const command of commands) {
          const approved = configRef.current.autoApprove
            || await askConfirm("Eseguire il comando locale?", command);
          if (!approved) {
            appendSystem("Comando locale rifiutato.");
            return;
          }
          let password: string | undefined;
          if (needsSudo(command)) {
            const secret = await askSecret("Password sudo", `Serve per eseguire: ${command}`);
            if (secret === null) {
              appendSystem("Password sudo non inserita: comando annullato.");
              return;
            }
            password = secret;
          }
          setStatus(`comando locale: ${command.slice(0, 60)}`);
          const controller = new AbortController();
          activeLocalRef.current = controller;
          const result = await runLocal(command, process.cwd(), password, controller.signal);
          activeLocalRef.current = null;
          addTool(command, result);
          appendExchange("user", formatResult(result), true);
          if (result.cancelled || cancelRef.current) {
            appendSystem("Comando locale annullato.");
            return;
          }
        }
        round += 1;
        setStatus("NOKK sta pensando…");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const hint = error instanceof NokkError && error.hint ? `\n${error.hint}` : "";
      addView({ role: "error", content: message + hint });
    } finally {
      finishRun();
    }
  }, [addTool, addView, appendExchange, appendSystem, askConfirm, askSecret, client, finishRun, modelOverride, pollJob, setBusyState]);

  const exportChat = useCallback(async (filename?: string) => {
    const chat = chatsRef.current[activeRef.current];
    const lines = [`# ${chat.title}`, ""];
    for (const message of chat.messages.filter((item) => !item.hidden)) {
      lines.push(`## ${message.role === "user" ? "Tu" : "NOKK"}`, "", message.content, "");
    }
    const target = filename || `nokk-chat-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}.md`;
    try {
      fs.writeFileSync(path.resolve(process.cwd(), target), lines.join("\n"), "utf8");
      appendSystem(`Chat esportata in ${target}.`);
    } catch (error) {
      addView({ role: "error", content: `Esportazione non riuscita: ${error instanceof Error ? error.message : String(error)}` });
    }
  }, [addView, appendSystem]);

  const copyChat = useCallback(async (argument: string) => {
    const chat = chatsRef.current[activeRef.current];
    const visible = chat.messages.filter((message) => !message.hidden);
    const text = argument === "all"
      ? visible.map((message) => `${message.role === "user" ? "Tu" : "NOKK"}: ${message.content}`).join("\n\n")
      : visible.filter((message) => message.role === "assistant").at(-1)?.content || "";
    if (!text) {
      appendSystem("Nessuna risposta da copiare.");
      return;
    }
    const ok = await copyText(text);
    appendSystem(ok ? "Testo copiato negli appunti." : "Clipboard non disponibile su questo sistema.");
  }, [appendSystem]);

  const gitCommand = useCallback(async (args: string) => {
    const result = await runCapture(`git ${args}`, process.cwd());
    addTool(`git ${args}`, result);
  }, [addTool]);

  const updateRepository = useCallback(async () => {
    const statusResult = await runCapture("git status --porcelain", process.cwd());
    if (statusResult.exitCode !== 0) {
      addView({ role: "error", content: statusResult.output || "Non sono in un repository Git." });
      return;
    }
    if (statusResult.output.trim()) {
      appendSystem("Aggiornamento annullato: ci sono modifiche locali non committate.");
      return;
    }
    const pull = await runCapture("git pull --ff-only", process.cwd());
    addTool("git pull --ff-only", pull);
  }, [addTool, addView, appendSystem]);

  const handleCommand = useCallback(async (line: string) => {
    const [rawName, ...rest] = line.slice(1).trim().split(/\s+/);
    const name = `/${rawName}`;
    const argument = rest.join(" ").trim();
    const chat = chatsRef.current[activeRef.current];
    switch (name) {
      case "/help":
        setOverlay("help");
        return;
      case "/new": {
        const next = [...chatsRef.current, toChat(newChat(`Chat ${chatsRef.current.length + 1}`))];
        commit(next, next.length - 1, true);
        return;
      }
      case "/clear": {
        updateActive((current) => ({
          ...current,
          messages: [],
          view: [{ role: "system", content: "Transcript pulito." }],
        }), true);
        return;
      }
      case "/pwd":
        appendSystem(process.cwd());
        return;
      case "/cd": {
        if (!argument) {
          appendSystem(`Directory: ${process.cwd()}`);
          return;
        }
        const target = path.resolve(process.cwd(), argument.replace(/^~(?=$|\/)/, process.env.HOME || "~"));
        try {
          if (!fs.statSync(target).isDirectory()) throw new Error("non è una cartella");
          process.chdir(target);
          updateConfig({ initialCwd: target });
          appendSystem(`Directory: ${target}`);
        } catch (error) {
          addView({ role: "error", content: `Directory non valida: ${error instanceof Error ? error.message : String(error)}` });
        }
        return;
      }
      case "/run":
        if (!argument) appendSystem("Uso: /run <comando>");
        else await runShell(argument);
        return;
      case "/agent": {
        const value = argument ? argument === "on" || argument === "true" || argument === "1" : !configRef.current.agent;
        updateConfig({ agent: value });
        appendSystem(`Agente locale: ${value ? "on" : "off"}.`);
        return;
      }
      case "/mode": {
        if (!argument) {
          appendSystem(`Modalità: ${configRef.current.mode || "predefinita"}`);
          return;
        }
        const mode = normalizeMode(argument);
        if (argument !== "off" && mode === null) {
          addView({ role: "error", content: "Modalità non valida. Usa codice, studio, analista o off." });
          return;
        }
        updateConfig({ mode });
        appendSystem(`Modalità: ${mode || "predefinita"}.`);
        return;
      }
      case "/model": {
        if (!argument) {
          appendSystem(modelOverride ? `Modello: ${modelOverride.provider}/${modelOverride.model}` : "Modello: quello del server.");
          return;
        }
        if (argument === "reset" || argument === "off") {
          setModelOverride(null);
          appendSystem("Modello della sessione azzerato.");
          return;
        }
        const slash = argument.indexOf("/");
        if (slash <= 0 || slash === argument.length - 1) {
          appendSystem("Uso: /model <provider>/<modello> oppure /model reset");
          return;
        }
        setModelOverride({ provider: argument.slice(0, slash), model: argument.slice(slash + 1) });
        appendSystem(`Modello: ${argument}.`);
        return;
      }
      case "/url": {
        if (!argument) {
          appendSystem(configRef.current.baseUrl);
          return;
        }
        try {
          const url = new URL(argument.startsWith("http") ? argument : `http://${argument}`);
          const baseUrl = url.toString().replace(/\/+$/, "").replace(/\/api(?:\/v1)?$/i, "");
          const patch: Partial<NokkConfig> = { baseUrl };
          if (configRef.current.profile === "local") patch.localUrl = baseUrl;
          else patch.hostingUrl = baseUrl;
          updateConfig(patch);
          void checkHealth();
          appendSystem(`Server: ${baseUrl}`);
        } catch {
          addView({ role: "error", content: "URL non valido." });
        }
        return;
      }
      case "/key": {
        const key = await askSecret("Chiave API", "Incolla la chiave di NOKK. Non verrà mostrata.");
        if (key === null) return;
        const patch: Partial<NokkConfig> = { apiKey: key };
        if (configRef.current.profile === "local") patch.localApiKey = key;
        else patch.hostingApiKey = key;
        updateConfig(patch);
        void checkHealth();
        appendSystem(key ? "Chiave aggiornata." : "Chiave rimossa.");
        return;
      }
      case "/profile": {
        const profile = argument || configRef.current.profile;
        if (profile !== "local" && profile !== "hosting") {
          appendSystem("Uso: /profile local|hosting");
          return;
        }
        switchProfile(profile);
        return;
      }
      case "/settings":
        setOverlay("settings");
        return;
      case "/server":
      case "/status": {
        try {
          const data = await client().health();
          setOnline(true);
          if (name === "/server") {
            appendSystem(Object.entries(data).map(([key, value]) => `${key}: ${String(value)}`).join("\n"));
          } else {
            appendSystem([
              `server: ${configRef.current.baseUrl}`,
              `profilo: ${configRef.current.profile}`,
              `modalità: ${configRef.current.mode || "predefinita"}`,
              `agente: ${configRef.current.agent ? "on" : "off"}`,
              `auto-approva: ${configRef.current.autoApprove ? "on" : "off"}`,
              `round: ${configRef.current.maxRounds || "illimitati"}`,
              `timeout attività: ${configRef.current.jobTimeout}s`,
              `directory: ${process.cwd()}`,
              `chat: ${chat.title}`,
            ].join("\n"));
          }
        } catch (error) {
          setOnline(false);
          addView({ role: "error", content: error instanceof Error ? error.message : String(error) });
        }
        return;
      }
      case "/sessions":
        appendSystem(chatsRef.current.map((item, index) => {
          const marker = index === activeRef.current ? "→" : " ";
          return `${marker} ${index + 1}. ${item.title} · ${item.messages.filter((message) => !message.hidden).length} msg`;
        }).join("\n"));
        return;
      case "/resume": {
        const number = Number.parseInt(argument, 10);
        if (!Number.isInteger(number) || number < 1 || number > chatsRef.current.length) {
          appendSystem("Uso: /resume <numero> (vedi /sessions)");
          return;
        }
        commit(chatsRef.current, number - 1);
        appendSystem(`Sessione: ${chatsRef.current[number - 1].title}`);
        return;
      }
      case "/delete":
      case "/remove": {
        let targets: number[];
        if (argument === "all" || argument === "tutte" || argument === "*") {
          targets = chatsRef.current.map((_, index) => index);
        } else if (argument) {
          const number = Number.parseInt(argument, 10);
          if (!Number.isInteger(number) || number < 1 || number > chatsRef.current.length) {
            appendSystem("Uso: /delete [numero|all]");
            return;
          }
          targets = [number - 1];
        } else {
          targets = [activeRef.current];
        }
        const label = targets.length === chatsRef.current.length
          ? "tutte le chat salvate"
          : `la chat «${chatsRef.current[targets[0]].title}»`;
        const approved = configRef.current.autoApprove
          || await askConfirm("Eliminare dalla memoria?", `Sto per eliminare ${label}.`);
        if (!approved) {
          appendSystem("Eliminazione annullata.");
          return;
        }
        const oldActive = activeRef.current;
        const remaining = chatsRef.current.filter((_, index) => !targets.includes(index));
        if (!remaining.length) remaining.push(toChat(newChat()));
        const nextActive = targets.includes(oldActive)
          ? Math.min(targets[0], remaining.length - 1)
          : oldActive - targets.filter((index) => index < oldActive).length;
        commit(remaining, Math.max(0, nextActive), true);
        appendSystem(`Eliminata ${label} dalla memoria.`);
        return;
      }
      case "/rename": {
        if (!argument) {
          appendSystem(`Titolo: ${chat.title}`);
          return;
        }
        updateActive((current) => ({ ...current, title: argument.slice(0, 60) }), true);
        appendSystem(`Sessione rinominata: ${argument.slice(0, 60)}`);
        return;
      }
      case "/diff":
        await gitCommand("diff");
        return;
      case "/git":
        await gitCommand(argument || "status");
        return;
      case "/cancel":
        cancelRef.current = true;
        activeLocalRef.current?.abort();
        if (currentJobRef.current) {
          try { await client().cancel(currentJobRef.current); } catch { /* best effort */ }
        }
        appendSystem("Annullamento richiesto.");
        return;
      case "/jobs": {
        try {
          const data = await client().jobs();
          appendSystem(JSON.stringify(data, null, 2));
        } catch (error) {
          addView({ role: "error", content: error instanceof Error ? error.message : String(error) });
        }
        return;
      }
      case "/update":
        await updateRepository();
        return;
      case "/config":
        appendSystem(JSON.stringify(safeConfig(configRef.current), null, 2));
        return;
      case "/export":
        await exportChat(argument);
        return;
      case "/copy":
        await copyChat(argument);
        return;
      case "/retry": {
        const lastUser = [...chat.messages].reverse().find((message) => message.role === "user" && !message.hidden);
        if (!lastUser) appendSystem("Nessuna domanda da ripetere.");
        else await runConversation(lastUser.content);
        return;
      }
      case "/exit":
        exit();
        return;
      default:
        addView({ role: "error", content: `Comando sconosciuto: ${name}. Usa /help.` });
    }
  }, [addView, appendSystem, askConfirm, askSecret, checkHealth, client, commit, copyChat, exit, exportChat, gitCommand, modelOverride, runConversation, runShell, switchProfile, updateActive, updateConfig, updateRepository]);

  const submit = useCallback(async () => {
    const text = input.trim();
    if (!text || busyRef.current) return;
    setInput("");
    if (text.startsWith("!")) {
      await runShell(text.slice(1));
      return;
    }
    if (text.startsWith("/")) {
      await handleCommand(text);
      return;
    }
    await runConversation(text);
  }, [handleCommand, input, runConversation, runShell]);

  useInput((value, key) => {
    if (key.ctrl && value === "c") {
      if (busyRef.current) {
        cancelRef.current = true;
        activeLocalRef.current?.abort();
        if (currentJobRef.current) void client().cancel(currentJobRef.current).catch(() => undefined);
        appendSystem("Annullamento richiesto.");
      } else {
        exit();
      }
    }
    if (key.ctrl && value === "q") exit();
    if (key.ctrl && value === "l") {
      updateActive((current) => ({ ...current, view: [] }));
    }
    if (key.ctrl && value === "e") {
      void exportChat();
    }
    if (key.ctrl && value === "y") {
      void copyChat("");
    }
    if (key.ctrl && value === "n" && !busyRef.current) {
      void handleCommand("/new");
    }
    if (key.ctrl && value === "r" && !busyRef.current) {
      void handleCommand("/retry");
    }
    if (key.ctrl && value === "x") {
      cancelRef.current = true;
      activeLocalRef.current?.abort();
      if (currentJobRef.current) {
        void client().cancel(currentJobRef.current).catch(() => undefined);
      }
      appendSystem("Annullamento richiesto.");
    }
  });

  const dialogNode = useMemo(() => {
    if (!dialog) return null;
    if (dialog.kind === "confirm") {
      return (
        <ConfirmPanel
          title={dialog.title}
          detail={dialog.detail}
          onResolve={(approved) => {
            setDialog(null);
            dialog.resolve(approved);
          }}
        />
      );
    }
    return (
      <PasswordPanel
        title={dialog.title}
        detail={dialog.detail}
        onSubmit={(secret) => {
          setDialog(null);
          dialog.resolve(secret);
        }}
        onCancel={() => {
          setDialog(null);
          dialog.resolve(null);
        }}
      />
    );
  }, [dialog]);

  const palette = input.startsWith("/") && !input.includes(" ") ? (
    <CommandPalette query={input} commands={COMMAND_NAMES} />
  ) : null;

  return (
    <Box flexDirection="column">
      <Header config={config} connected={online} />
      <Box flexDirection="column" paddingX={1}>
        {config.showBanner && activeChat.messages.length === 0 ? <Banner /> : null}
        <Transcript messages={activeChat.view} />
        {partial ? (
          <Box marginBottom={1} flexDirection="column">
            <Text color={COLORS.purple} bold>{"✦ NOKK"}</Text>
            <Box paddingLeft={2}><Text wrap="wrap">{partial}</Text></Box>
          </Box>
        ) : null}
      </Box>
      {palette}
      {overlay === "help" ? <HelpPanel onClose={() => setOverlay(null)} /> : null}
      {overlay === "settings" ? (
        <SettingsPanel
          config={config}
          onChange={updateConfig}
          onProfile={switchProfile}
          onClose={() => setOverlay(null)}
        />
      ) : null}
      {dialogNode}
      <StatusBar
        busy={busy}
        status={status}
        elapsed={elapsed}
        autoApprove={config.autoApprove}
        model={modelOverride ? `${modelOverride.provider}/${modelOverride.model}` : modelLabel}
      />
      <Box paddingX={1} flexDirection="column">
        <Text color={COLORS.dim} wrap="truncate">{`${config.agent ? "agente" : "chat"} · ${chats.length} chat · ${shortPath(process.cwd(), 60)}`}</Text>
        <Text color={COLORS.dim}>{"ctrl+c interrompe/esce · ctrl+l pulisce · ctrl+e esporta"}</Text>
      </Box>
      <Composer
        value={input}
        onChange={setInput}
        onSubmit={() => { void submit(); }}
        disabled={busy}
      />
    </Box>
  );
}
