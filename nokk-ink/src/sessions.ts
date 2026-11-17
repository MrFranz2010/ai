import fs from "node:fs";
import path from "node:path";

export interface StoredMessage {
  role: "user" | "assistant";
  content: string;
  hidden?: boolean;
}

export interface ChatSession {
  title: string;
  createdAt: number;
  messages: StoredMessage[];
}

const MAX_SESSIONS = 100;
const MAX_SESSION_MESSAGES = 200;

export function newChat(title = "Chat 1"): ChatSession {
  return { title, createdAt: Date.now() / 1000, messages: [] };
}

export function loadSessions(file: string): ChatSession[] {
  const chats: ChatSession[] = [];
  try {
    if (!fs.existsSync(file)) return chats;
    const parsed = JSON.parse(fs.readFileSync(file, "utf8")) as {
      chats?: Array<{ title?: unknown; created_at?: unknown; messages?: unknown }>;
    };
    if (!parsed || !Array.isArray(parsed.chats)) return chats;
    for (const item of parsed.chats.slice(0, MAX_SESSIONS)) {
      if (!item || typeof item !== "object") continue;
      const title = typeof item.title === "string" ? item.title.trim().slice(0, 80) : "";
      const createdAt =
        typeof item.created_at === "number" && Number.isFinite(item.created_at)
          ? item.created_at
          : Date.now() / 1000;
      const messages: StoredMessage[] = [];
      if (Array.isArray(item.messages)) {
        for (const raw of item.messages.slice(-MAX_SESSION_MESSAGES)) {
          if (!raw || typeof raw !== "object") continue;
          const message = raw as { role?: unknown; content?: unknown; hidden?: unknown };
          if (message.role !== "user" && message.role !== "assistant") continue;
          if (typeof message.content !== "string") continue;
          messages.push({
            role: message.role,
            content: message.content,
            hidden: message.hidden === true,
          });
        }
      }
      chats.push({ title: title || "Chat 1", createdAt, messages });
    }
  } catch {
    return [];
  }
  return chats;
}

export function saveSessions(file: string, chats: ChatSession[]): void {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const payload = {
    version: 1,
    chats: chats.slice(0, MAX_SESSIONS).map((chat) => ({
      title: chat.title,
      created_at: chat.createdAt,
      messages: chat.messages.slice(-MAX_SESSION_MESSAGES),
    })),
  };
  const temporary = path.join(path.dirname(file), `.${path.basename(file)}.tmp`);
  fs.writeFileSync(temporary, `${JSON.stringify(payload, null, 2)}\n`, {
    encoding: "utf8",
    mode: 0o600,
  });
  fs.renameSync(temporary, file);
}
