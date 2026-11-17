export type ViewRole = "user" | "assistant" | "system" | "error" | "tool";

export interface ViewMessage {
  role: ViewRole;
  content: string;
  command?: string;
  exitCode?: number;
  streaming?: boolean;
}

export interface ChatState {
  title: string;
  createdAt: number;
  messages: Array<{
    role: "user" | "assistant";
    content: string;
    hidden?: boolean;
  }>;
  view: ViewMessage[];
}

export function viewFromMessages(
  messages: Array<{ role: "user" | "assistant"; content: string; hidden?: boolean }>,
): ViewMessage[] {
  return messages
    .filter((message) => !message.hidden)
    .map((message) => ({ role: message.role, content: message.content }));
}
