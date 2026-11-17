import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export interface LocalResult {
  command: string;
  exitCode: number;
  output: string;
  timedOut: boolean;
  cancelled: boolean;
}

const RUN_BLOCK = /```nokk-run[^\n]*\n([\s\S]*?)(?:\n?```|<\/parameter>)/g;
const TOOL_MARKUP = /<\/?(?:antml:)?(?:parameter|function|tool_call)(?:\s[^>]*)?>/g;

export function cleanToolMarkup(value: string): string {
  return value.replace(TOOL_MARKUP, "").trim();
}

export function extractRunCommands(text: string): string[] {
  if (typeof text !== "string") return [];
  const commands: string[] = [];
  for (const match of text.matchAll(RUN_BLOCK)) {
    const command = cleanToolMarkup(match[1] || "");
    if (command) commands.push(command);
  }
  return commands;
}

const FILE_CONTEXT_LIMIT = 40_000;
const FILE_CONTEXT_TOTAL = 100_000;
const FILE_MENTION = /(?<![\w@])@([^\s@]+)/g;

export function collectFileContext(text: string, cwd: string): string {
  const root = path.resolve(cwd);
  const seen = new Set<string>();
  const blocks: string[] = [];
  let total = 0;
  for (const match of text.matchAll(FILE_MENTION)) {
    const raw = (match[1] || "").replace(/[.,;:!?)\]}]+$/, "");
    if (!raw) continue;
    const expanded = raw.startsWith("~") ? path.join(process.env.HOME || "", raw.slice(1)) : raw;
    const candidate = path.isAbsolute(expanded) ? expanded : path.resolve(root, expanded);
    let absolute: string;
    try {
      absolute = fs.realpathSync(candidate);
      if (seen.has(absolute)) continue;
      seen.add(absolute);
      if (!fs.statSync(absolute).isFile()) continue;
    } catch {
      continue;
    }
    const size = fs.statSync(absolute).size;
    if (size > FILE_CONTEXT_LIMIT) {
      blocks.push(`File: ${absolute}\n(file troppo grande, non incluso)`);
      continue;
    }
    let content: string;
    try {
      content = fs.readFileSync(absolute, "utf8");
    } catch (error) {
      blocks.push(`File: ${absolute}\n(impossibile leggerlo: ${error instanceof Error ? error.message : String(error)})`);
      continue;
    }
    if (content.includes("\0")) {
      blocks.push(`File: ${absolute}\n(file binario, non incluso)`);
      continue;
    }
    if (total + content.length > FILE_CONTEXT_TOTAL) {
      blocks.push("(limite complessivo del contesto file raggiunto)");
      break;
    }
    total += content.length;
    const label = path.relative(root, absolute) || absolute;
    blocks.push(`File: ${label}\n\`\`\`\n${content.replace(/\s+$/, "")}\n\`\`\``);
  }
  return blocks.length ? `Contesto dei file citati dall'utente:\n\n${blocks.join("\n\n")}` : "";
}

export function needsSudo(command: string): boolean {
  return command
    .split(/(?:&&|\|\||[;|])/)
    .some((segment) => /^\s*(?:[A-Za-z_]\w*=\S+\s+)*sudo(?:\s|$)/.test(segment));
}

export function runLocal(
  command: string,
  cwd: string,
  sudoPassword?: string,
  signal?: AbortSignal,
): Promise<LocalResult> {
  const trimmed = (command || "").trim();
  if (!trimmed) {
    return Promise.resolve({ command: "", exitCode: 1, output: "Comando vuoto.", timedOut: false, cancelled: false });
  }
  if (signal?.aborted) {
    return Promise.resolve({
      command: trimmed,
      exitCode: 130,
      output: "[comando annullato]",
      timedOut: false,
      cancelled: true,
    });
  }

  return new Promise((resolve) => {
    const useSudo = Boolean(sudoPassword) && needsSudo(trimmed);
    const child = useSudo
      ? spawn("sudo", ["-S", "-p", "", "sh", "-c", trimmed], {
          cwd,
          env: process.env,
          stdio: ["pipe", "pipe", "pipe"],
          detached: process.platform !== "win32",
        })
      : spawn(trimmed, {
          cwd,
          env: process.env,
          shell: true,
          stdio: ["ignore", "pipe", "pipe"],
          detached: process.platform !== "win32",
        });

    const chunks: Buffer[] = [];
    let settled = false;
    let cancelled = false;

    const killTree = (sig: NodeJS.Signals) => {
      if (!child.pid) return;
      try {
        if (process.platform === "win32") child.kill(sig);
        else process.kill(-child.pid, sig);
      } catch {
        try { child.kill(sig); } catch { /* già terminato */ }
      }
    };

    const onAbort = () => {
      if (settled || cancelled) return;
      cancelled = true;
      killTree("SIGTERM");
      const force = setTimeout(() => {
        if (!settled) killTree("SIGKILL");
      }, 1500);
      force.unref();
    };

    signal?.addEventListener("abort", onAbort, { once: true });
    child.stdout?.on("data", (chunk: Buffer) => chunks.push(chunk));
    child.stderr?.on("data", (chunk: Buffer) => chunks.push(chunk));
    child.once("spawn", () => {
      if (signal?.aborted) onAbort();
    });
    if (useSudo) {
      child.stdin?.end(`${sudoPassword}\n`);
    }

    const finish = (exitCode: number, extra = "") => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener("abort", onAbort);
      const output = chunks.map((chunk) => chunk.toString("utf8")).join("") + extra;
      resolve({
        command: trimmed,
        exitCode: cancelled ? 130 : exitCode,
        output: cancelled && !output.trim() ? "[comando annullato]" : output,
        timedOut: false,
        cancelled,
      });
    };

    child.on("error", (error) => {
      finish(1, error.message);
    });
    child.on("close", (code) => {
      finish(typeof code === "number" ? code : -1);
    });
  });
}

export function runCapture(command: string, cwd: string): Promise<LocalResult> {
  return runLocal(command, cwd);
}

export async function copyText(text: string): Promise<boolean> {
  const candidates: Array<[string, string[]]> =
    os.platform() === "darwin"
      ? [["pbcopy", []]]
      : os.platform() === "win32"
        ? [["clip", []]]
        : [
            ["wl-copy", []],
            ["xclip", ["-selection", "clipboard"]],
            ["xsel", ["--clipboard", "--input"]],
          ];

  for (const [program, args] of candidates) {
    const ok = await new Promise<boolean>((resolve) => {
      const child = spawn(program, args, { stdio: ["pipe", "ignore", "ignore"] });
      child.on("error", () => resolve(false));
      child.on("close", (code) => resolve(code === 0));
      child.stdin?.end(text);
    });
    if (ok) return true;
  }
  return false;
}
