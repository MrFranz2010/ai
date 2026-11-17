import React, { type ReactNode, useState } from "react";
import { Box, Text, useInput } from "ink";
import TextInput from "ink-text-input";
import Spinner from "ink-spinner";
import type { NokkConfig } from "./config.js";
import type { ViewMessage } from "./types.js";

export const COLORS = {
  accent: "#d97757",
  accentSoft: "#f0b39d",
  green: "#7ee787",
  purple: "#bc8cff",
  blue: "#79c0ff",
  yellow: "#e3b341",
  red: "#ff7b72",
  dim: "#8b949e",
  text: "#e6edf3",
  border: "#30363d",
  panel: "#161b22",
};

function inline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <Text key={index} bold>{part.slice(2, -2)}</Text>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <Text key={index} color={COLORS.accentSoft}>{part.slice(1, -1)}</Text>;
    }
    return <Text key={index}>{part}</Text>;
  });
}

export function RichText({ text }: { text: string }): React.ReactElement {
  const blocks = text.split(/(```[\s\S]*?```)/g);
  return (
    <Box flexDirection="column">
      {blocks.map((block, index) => {
        if (block.startsWith("```")) {
          const body = block.replace(/^```[^\n]*\n?/, "").replace(/```$/, "").replace(/\n$/, "");
          return (
            <Box key={index} flexDirection="column" marginY={1} paddingX={1} borderStyle="round" borderColor={COLORS.border}>
              {body.split("\n").map((line, lineIndex) => (
                <Text key={lineIndex} color={COLORS.text}>{line || " "}</Text>
              ))}
            </Box>
          );
        }
        return (
          <Text key={index} wrap="wrap">
            {inline(block)}
          </Text>
        );
      })}
    </Box>
  );
}

function Message({ message }: { message: ViewMessage }): React.ReactElement {
  if (message.role === "user") {
    return (
      <Box marginBottom={1} flexDirection="column">
        <Text color={COLORS.accent} bold>{"› tu"}</Text>
        <Box paddingLeft={2}><RichText text={message.content} /></Box>
      </Box>
    );
  }
  if (message.role === "assistant") {
    return (
      <Box marginBottom={1} flexDirection="column">
        <Text color={COLORS.purple} bold>{"✦ NOKK"}{message.streaming ? <Text color={COLORS.dim}> in scrittura…</Text> : null}</Text>
        <Box paddingLeft={2}><RichText text={message.content || " "} /></Box>
      </Box>
    );
  }
  if (message.role === "tool") {
    const color = message.exitCode === 0 ? COLORS.green : COLORS.red;
    return (
      <Box marginBottom={1} flexDirection="column">
        <Text color={color} bold>
          {"● shell"}<Text color={COLORS.dim}>{`  exit ${message.exitCode ?? "?"}`}</Text>
        </Text>
        <Box paddingLeft={2} flexDirection="column">
          <Text color={COLORS.dim}>{message.command || ""}</Text>
          <Text color={COLORS.text} wrap="wrap">{message.content || "(nessun output)"}</Text>
        </Box>
      </Box>
    );
  }
  if (message.role === "error") {
    return (
      <Box marginBottom={1} flexDirection="column">
        <Text color={COLORS.red} bold>{"✖ errore"}</Text>
        <Box paddingLeft={2}><Text color={COLORS.red} wrap="wrap">{message.content}</Text></Box>
      </Box>
    );
  }
  return <Box marginBottom={1}><Text color={COLORS.dim} wrap="wrap">{message.content}</Text></Box>;
}

export function Header({
  config,
  connected,
}: {
  config: NokkConfig;
  connected: boolean | null;
}): React.ReactElement {
  return (
    <Box
      borderStyle="round"
      borderColor={COLORS.border}
      paddingX={1}
      marginBottom={1}
      flexDirection="column"
    >
      <Box justifyContent="space-between">
        <Box>
          <Text color={COLORS.accent} bold>{"◆ NOKK"}</Text>
          <Text color={COLORS.dim}>{"  ink  "}</Text>
          <Text color={COLORS.accentSoft}>{config.mode || "predefinita"}</Text>
        </Box>
        <Text color={connected ? COLORS.green : connected === false ? COLORS.red : COLORS.dim}>
          {connected ? "● online" : connected === false ? "● offline" : "● connessione…"}
        </Text>
      </Box>
      <Text color={COLORS.dim} wrap="truncate">
        {`${config.profile} · ${shortPath(process.cwd(), 52)}`}
      </Text>
    </Box>
  );
}

export function Transcript({ messages }: { messages: ViewMessage[] }): React.ReactElement {
  return (
    <Box flexDirection="column">
      {messages.map((message, index) => <Message key={index} message={message} />)}
    </Box>
  );
}

export function StatusBar({
  busy,
  status,
  elapsed,
  autoApprove,
  model,
}: {
  busy: boolean;
  status: string;
  elapsed: number;
  autoApprove: boolean;
  model: string;
}): React.ReactElement {
  return (
    <Box justifyContent="space-between" paddingX={1} marginTop={1}>
      <Box>
        {busy ? <Text color={COLORS.yellow}><Spinner type="dots" /> </Text> : <Text color={COLORS.green}>{"● "}</Text>}
        <Text color={COLORS.dim}>{status}</Text>
        {busy ? <Text color={COLORS.dim}>{`  ${elapsed.toFixed(1)}s`}</Text> : null}
      </Box>
      <Box>
        <Text color={autoApprove ? COLORS.yellow : COLORS.dim}>{autoApprove ? "auto" : "conferma"}</Text>
        <Text color={COLORS.dim}>{"  ·  "}</Text>
        <Text color={COLORS.dim}>{model || "modello server"}</Text>
      </Box>
    </Box>
  );
}

export function Composer({
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}): React.ReactElement {
  return (
    <Box borderStyle="round" borderColor={COLORS.accent} paddingX={1} marginTop={1}>
      <Text color={COLORS.accent} bold>{"> "}</Text>
      <TextInput
        value={value}
        onChange={onChange}
        onSubmit={onSubmit}
        placeholder={disabled ? "attendi…" : "scrivi un messaggio o /help"}
        focus={!disabled}
      />
    </Box>
  );
}

export function CommandPalette({ query, commands }: { query: string; commands: string[] }): React.ReactElement {
  const matches = commands.filter((command) => command.startsWith(query)).slice(0, 8);
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={COLORS.border} paddingX={1} marginBottom={1}>
      <Text color={COLORS.dim}>comandi</Text>
      {matches.map((command) => <Text key={command} color={COLORS.text}>{command}</Text>)}
      {!matches.length ? <Text color={COLORS.dim}>nessuna corrispondenza</Text> : null}
    </Box>
  );
}

export function Banner(): React.ReactElement {
  return (
    <Box flexDirection="column" marginBottom={1} paddingX={1}>
      <Text color={COLORS.accent} bold>{"◆ NOKK"}</Text>
      <Text color={COLORS.dim}>{"Scrivi, usa /help per i comandi, !comando per la shell locale."}</Text>
    </Box>
  );
}

const HELP_LINES = [
  ["/new", "nuova chat"],
  ["/clear", "pulisce il transcript"],
  ["/cd [dir]", "cambia directory locale"],
  ["/run <cmd>", "esegue un comando locale"],
  ["/agent [on|off]", "comandi locali proposti da NOKK"],
  ["/mode [modalità]", "codice, studio, analista, off"],
  ["/model [provider/modello]", "modello per la sessione"],
  ["/profile [local|hosting]", "profilo salvato"],
  ["/url [url]", "server NOKK"],
  ["/key", "chiave API"],
  ["/settings", "impostazioni interattive"],
  ["/status", "stato sessione e server"],
  ["/sessions", "sessioni salvate"],
  ["/resume <n>", "riapre una sessione"],
  ["/delete [n|all]", "elimina chat salvate"],
  ["/rename <titolo>", "rinomina la chat"],
  ["/export [file]", "esporta in Markdown"],
  ["/copy [n|all]", "copia risposta"],
  ["/retry", "ripete l'ultima domanda"],
  ["/diff", "/git status", "Git"],
  ["/jobs", "attività recenti"],
  ["/update", "aggiorna il repository"],
  ["/cancel", "annulla il job"],
  ["/exit", "esci"],
];

export function HelpPanel({ onClose }: { onClose: () => void }): React.ReactElement {
  useInput((input, key) => {
    if (key.escape || key.return || input === "q") onClose();
  });
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={COLORS.border} paddingX={1}>
      <Text color={COLORS.accent} bold>{"Comandi NOKK"}</Text>
      {HELP_LINES.map(([command, description]) => (
        <Box key={command}>
          <Box width={26}><Text color={COLORS.accentSoft}>{command}</Text></Box>
          <Text color={COLORS.dim}>{description}</Text>
        </Box>
      ))}
      <Text color={COLORS.dim}>{"Esc o Invio per chiudere"}</Text>
    </Box>
  );
}

const ROUND_VALUES = [0, 3, 6, 10, 20];
const TIMEOUT_VALUES = [60, 300, 900, 3600];

export function SettingsPanel({
  config,
  onChange,
  onProfile,
  onClose,
}: {
  config: NokkConfig;
  onChange: (patch: Partial<NokkConfig>) => void;
  onProfile: (profile: "local" | "hosting") => void;
  onClose: () => void;
}): React.ReactElement {
  const [index, setIndex] = useState(0);
  const rows: Array<{ label: string; value: string; act: () => void }> = [
    { label: "Profilo", value: config.profile, act: () => onProfile(config.profile === "local" ? "hosting" : "local") },
    { label: "Auto-approvazione", value: config.autoApprove ? "on" : "off", act: () => onChange({ autoApprove: !config.autoApprove }) },
    { label: "Agente locale", value: config.agent ? "on" : "off", act: () => onChange({ agent: !config.agent }) },
    { label: "Streaming", value: config.stream ? "on" : "off", act: () => onChange({ stream: !config.stream }) },
    { label: "Salva sessioni", value: config.saveSessions ? "on" : "off", act: () => onChange({ saveSessions: !config.saveSessions }) },
    { label: "Campanello finale", value: config.bellOnFinish ? "on" : "off", act: () => onChange({ bellOnFinish: !config.bellOnFinish }) },
    { label: "Banner iniziale", value: config.showBanner ? "on" : "off", act: () => onChange({ showBanner: !config.showBanner }) },
    { label: "Round agente", value: config.maxRounds ? String(config.maxRounds) : "illimitati", act: () => {
      const at = ROUND_VALUES.indexOf(config.maxRounds);
      onChange({ maxRounds: ROUND_VALUES[(at + 1) % ROUND_VALUES.length] });
    } },
    { label: "Timeout attività", value: `${config.jobTimeout}s`, act: () => {
      const at = TIMEOUT_VALUES.indexOf(config.jobTimeout);
      onChange({ jobTimeout: TIMEOUT_VALUES[(at + 1) % TIMEOUT_VALUES.length] });
    } },
    { label: "Chiudi", value: "↩", act: onClose },
  ];

  useInput((input, key) => {
    if (key.escape || input === "q") return onClose();
    if (key.upArrow) setIndex((value) => Math.max(0, value - 1));
    if (key.downArrow) setIndex((value) => Math.min(rows.length - 1, value + 1));
    if (key.return || input === " ") rows[index].act();
  });

  return (
    <Box flexDirection="column" borderStyle="round" borderColor={COLORS.border} paddingX={1}>
      <Text color={COLORS.accent} bold>{"Impostazioni"}</Text>
      {rows.map((row, at) => (
        <Box key={row.label}>
          <Box width={24}><Text color={at === index ? COLORS.accent : COLORS.text}>{`${at === index ? "› " : "  "}${row.label}`}</Text></Box>
          <Text color={COLORS.dim}>{row.value}</Text>
        </Box>
      ))}
      <Text color={COLORS.dim}>{"↑↓ scegli · Invio modifica · Esc chiude"}</Text>
    </Box>
  );
}

export function ConfirmPanel({
  title,
  detail,
  onResolve,
}: {
  title: string;
  detail: string;
  onResolve: (approved: boolean) => void;
}): React.ReactElement {
  useInput((input, key) => {
    if (input === "y" || input === "s" || key.return) onResolve(true);
    if (input === "n" || key.escape) onResolve(false);
  });
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={COLORS.yellow} paddingX={1}>
      <Text color={COLORS.yellow} bold>{title}</Text>
      <Text color={COLORS.text} wrap="wrap">{detail}</Text>
      <Text color={COLORS.dim}>{"y per confermare · n per annullare"}</Text>
    </Box>
  );
}

export function PasswordPanel({
  title,
  detail,
  onSubmit,
  onCancel,
}: {
  title: string;
  detail: string;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}): React.ReactElement {
  const [value, setValue] = useState("");
  useInput((_input, key) => {
    if (key.escape) onCancel();
  });
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={COLORS.yellow} paddingX={1}>
      <Text color={COLORS.yellow} bold>{title}</Text>
      <Text color={COLORS.dim}>{detail}</Text>
      <Box>
        <Text color={COLORS.accent}>{"> "}</Text>
        <TextInput value={value} onChange={setValue} onSubmit={onSubmit} mask="*" focus />
      </Box>
      <Text color={COLORS.dim}>{"Invio conferma · Esc annulla"}</Text>
    </Box>
  );
}

export function shortPath(value: string, limit: number): string {
  const home = process.env.HOME;
  let text = home && value.startsWith(home) ? `~${value.slice(home.length)}` : value;
  if (text.length > limit) text = `…${text.slice(-(limit - 1))}`;
  return text;
}
