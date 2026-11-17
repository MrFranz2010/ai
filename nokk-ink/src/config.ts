import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export type Mode = "codice" | "studio" | "analista" | null;

export interface NokkConfig {
  baseUrl: string;
  apiKey: string;
  mode: Mode;
  agent: boolean;
  profile: "local" | "hosting";
  localUrl: string;
  localApiKey: string;
  hostingUrl: string;
  hostingApiKey: string;
  initialCwd: string;
  jobTimeout: number;
  autoApprove: boolean;
  stream: boolean;
  saveSessions: boolean;
  maxRounds: number;
  bellOnFinish: boolean;
  showBanner: boolean;
}

export const DEFAULT_BASE_URL = "http://127.0.0.1:8000";
export const DEFAULT_JOB_TIMEOUT = 300;
export const MAX_ROUNDS_LIMIT = 20;

const MODE_ALIASES: Record<string, Mode> = {
  code: "codice",
  codice: "codice",
  study: "studio",
  studio: "studio",
  analyst: "analista",
  analista: "analista",
  off: null,
  none: null,
  nessuna: null,
};

export function normalizeMode(value: unknown): Mode {
  if (value === null || value === undefined || value === "") return null;
  const key = String(value).trim().toLowerCase();
  return key in MODE_ALIASES ? MODE_ALIASES[key] : null;
}

export function normalizeBaseUrl(value: string): string {
  const trimmed = String(value || "").trim().replace(/\/+$/, "");
  return trimmed.replace(/\/api(?:\/v1)?$/i, "") || DEFAULT_BASE_URL;
}

export function configPath(): string {
  const explicit = process.env.NOKK_CLI_CONFIG;
  if (explicit) return path.resolve(explicit);
  return path.join(
    process.env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config"),
    "nokk",
    "cli.json",
  );
}

export function sessionsPath(forConfig = configPath()): string {
  return path.join(path.dirname(forConfig), "sessions.json");
}

function inferredProfile(url: string): "local" | "hosting" {
  return /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(?::\d+)?(?:\/|$)/i.test(url)
    ? "local"
    : "hosting";
}

function boundedInt(value: unknown, fallback: number, min: number, max: number): number {
  const parsed = typeof value === "number" ? value : Number.parseInt(String(value), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(parsed)));
}

export function loadConfig(file = configPath()): NokkConfig {
  let saved: Record<string, unknown> = {};
  try {
    if (fs.existsSync(file)) {
      const parsed = JSON.parse(fs.readFileSync(file, "utf8"));
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        saved = parsed as Record<string, unknown>;
      }
    }
  } catch {
    saved = {};
  }

  const baseUrl = normalizeBaseUrl(
    String(process.env.NOKK_URL || saved.base_url || saved.local_url || DEFAULT_BASE_URL),
  );
  const apiKey = String(process.env.NOKK_API_KEY || saved.api_key || "");
  const profile =
    saved.profile === "local" || saved.profile === "hosting"
      ? saved.profile
      : inferredProfile(baseUrl);

  return {
    baseUrl,
    apiKey,
    mode: normalizeMode(saved.mode),
    agent: saved.agent !== false,
    profile,
    localUrl: normalizeBaseUrl(String(saved.local_url || (profile === "local" ? baseUrl : DEFAULT_BASE_URL))),
    localApiKey: String(saved.local_api_key || (profile === "local" ? apiKey : "")),
    hostingUrl: String(saved.hosting_url || (profile === "hosting" ? baseUrl : "")),
    hostingApiKey: String(saved.hosting_api_key || (profile === "hosting" ? apiKey : "")),
    initialCwd: String(saved.initial_cwd || ""),
    jobTimeout: boundedInt(saved.job_timeout, DEFAULT_JOB_TIMEOUT, 10, 3600),
    autoApprove: saved.auto_approve !== false,
    stream: saved.stream !== false,
    saveSessions: saved.save_sessions !== false,
    maxRounds: boundedInt(saved.max_rounds, 0, 0, MAX_ROUNDS_LIMIT),
    bellOnFinish: saved.bell_on_finish === true,
    showBanner: saved.show_banner !== false,
  };
}

export function saveConfig(config: NokkConfig, file = configPath()): void {
  let existing: Record<string, unknown> = {};
  try {
    if (fs.existsSync(file)) {
      const parsed = JSON.parse(fs.readFileSync(file, "utf8"));
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        existing = parsed as Record<string, unknown>;
      }
    }
  } catch {
    existing = {};
  }
  const payload: Record<string, unknown> = {
    ...existing,
    base_url: normalizeBaseUrl(config.baseUrl),
    api_key: config.apiKey,
    mode: config.mode,
    agent: config.agent,
    profile: config.profile,
    local_url: normalizeBaseUrl(config.localUrl),
    local_api_key: config.localApiKey,
    hosting_url: config.hostingUrl ? normalizeBaseUrl(config.hostingUrl) : "",
    hosting_api_key: config.hostingApiKey,
    initial_cwd: config.initialCwd,
    job_timeout: boundedInt(config.jobTimeout, DEFAULT_JOB_TIMEOUT, 10, 3600),
    auto_approve: config.autoApprove,
    stream: config.stream,
    save_sessions: config.saveSessions,
    max_rounds: boundedInt(config.maxRounds, 0, 0, MAX_ROUNDS_LIMIT),
    bell_on_finish: config.bellOnFinish,
    show_banner: config.showBanner,
  };
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const temporary = path.join(path.dirname(file), `.${path.basename(file)}.tmp`);
  fs.writeFileSync(temporary, `${JSON.stringify(payload, null, 2)}\n`, { mode: 0o600 });
  fs.renameSync(temporary, file);
}
