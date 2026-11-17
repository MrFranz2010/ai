export interface WireMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ToolEvent {
  tool?: string;
  command?: string;
  output?: string;
  exit_code?: number;
  executed?: boolean;
  automatic?: boolean;
}

export interface Job {
  id?: string;
  status: "running" | "complete" | "failed" | "cancelled" | "awaiting_approval";
  reply?: string;
  partial_reply?: string;
  error?: string;
  hint?: string;
  details?: string;
  tool_events?: ToolEvent[];
  action?: { id?: string; command?: string; workspace?: string };
}

export interface ChatOptions {
  mode?: string | null;
  provider?: string;
  model?: string;
  stream?: boolean;
  terminalEnabled?: boolean;
  localTerminal?: boolean;
}

const JOB_ID = /^[A-Za-z0-9_-]{6,128}$/;

export class NokkError extends Error {
  hint: string | null;

  constructor(message: string, hint?: string | null) {
    super(message);
    this.name = "NokkError";
    this.hint = hint || null;
  }
}

export class NokkClient {
  baseUrl: string;
  apiKey: string;
  timeoutMs: number;

  constructor(baseUrl: string, apiKey = "", timeoutMs = 30_000) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.apiKey = apiKey.trim();
    this.timeoutMs = timeoutMs;
  }

  get versioned(): boolean {
    return Boolean(this.apiKey);
  }

  async request<T = Record<string, unknown>>(
    method: string,
    route: string,
    payload?: unknown,
  ): Promise<T> {
    const headers: Record<string, string> = {
      Accept: "application/json",
      "User-Agent": "NOKK-Ink/0.1.0",
    };
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    if (this.apiKey) headers["X-API-Key"] = this.apiKey;

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${route}`, {
        method,
        headers,
        body: payload === undefined ? undefined : JSON.stringify(payload),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      throw new NokkError(
        `Server NOKK non raggiungibile: ${this.baseUrl}`,
        `${detail}. Avvia NOKK o controlla /url.`,
      );
    }

    const raw = await response.text();
    let data: Record<string, unknown> = {};
    if (raw) {
      try {
        data = JSON.parse(raw) as Record<string, unknown>;
      } catch {
        data = {};
      }
    }
    if (!response.ok) {
      const message =
        (typeof data.error === "string" && data.error) ||
        response.statusText ||
        `HTTP ${response.status}`;
      let hint: string | null = null;
      if (response.status === 401) hint = "Controlla la chiave API (/key).";
      if (response.status === 403) hint = "Attiva l'API HTTP nelle impostazioni di NOKK.";
      if (response.status === 429) hint = "Troppe richieste: attendi qualche secondo.";
      throw new NokkError(`HTTP ${response.status}: ${message}`, hint);
    }
    return data as T;
  }

  health(): Promise<Record<string, unknown>> {
    return this.request("GET", this.versioned ? "/api/v1/health" : "/api/config");
  }

  async startChat(messages: WireMessage[], options: ChatOptions = {}): Promise<string> {
    const payload: Record<string, unknown> = { messages };
    if (options.mode) payload.mode = options.mode;
    if (options.provider) payload.provider = options.provider;
    if (options.model) payload.model = options.model;
    if (options.stream) payload.stream = true;
    if (options.terminalEnabled === false) payload.terminal_enabled = false;
    if (options.localTerminal) payload.local_terminal = true;
    const data = await this.request<{ job_id?: string }>(
      "POST",
      this.versioned ? "/api/v1/chat" : "/api/chat",
      payload,
    );
    if (typeof data.job_id !== "string" || !JOB_ID.test(data.job_id)) {
      throw new NokkError("Il server non ha restituito un identificativo di attività valido.");
    }
    return data.job_id;
  }

  job(id: string): Promise<Job> {
    if (!JOB_ID.test(id)) throw new NokkError("Identificativo di attività non valido.");
    return this.request<Job>(
      "GET",
      this.versioned ? `/api/v1/jobs/${id}` : `/api/jobs/${id}`,
    );
  }

  jobs(): Promise<Record<string, unknown>> {
    return this.request("GET", this.versioned ? "/api/v1/jobs" : "/api/jobs");
  }

  approve(id: string, actionId: string, approved: boolean): Promise<Record<string, unknown>> {
    if (!JOB_ID.test(id)) throw new NokkError("Identificativo di attività non valido.");
    return this.request(
      "POST",
      this.versioned ? `/api/v1/jobs/${id}/approval` : `/api/jobs/${id}/approval`,
      { action_id: actionId, approved },
    );
  }

  cancel(id: string): Promise<Record<string, unknown>> {
    if (!JOB_ID.test(id)) throw new NokkError("Identificativo di attività non valido.");
    return this.request(
      "POST",
      this.versioned ? `/api/v1/jobs/${id}/cancel` : `/api/jobs/${id}/cancel`,
      {},
    );
  }
}
