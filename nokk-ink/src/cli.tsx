#!/usr/bin/env node
import React from "react";
import { render } from "ink";
import { App } from "./app.js";
import {
  configPath,
  loadConfig,
  normalizeBaseUrl,
  normalizeMode,
  saveConfig,
  type NokkConfig,
} from "./config.js";

const VERSION = "0.1.0";

function usage(): string {
  return [
    "NOKK Ink — terminale moderno per NOKK",
    "",
    "Uso: nokk-ink [opzioni]",
    "",
    "  --url <url>        server NOKK (default: cli.json o http://127.0.0.1:8000)",
    "  --key <chiave>     chiave API (meglio usare /key o NOKK_API_KEY)",
    "  --mode <modalità>  codice, studio, analista, off",
    "  --agent            abilita i comandi locali",
    "  --no-agent         disabilita i comandi locali",
    "  --cwd <cartella>   directory di lavoro iniziale",
    "  --config <file>    percorso alternativo di cli.json",
    "  -h, --help         mostra questo aiuto",
    "  -v, --version      versione",
  ].join("\n");
}

function parse(argv: string[]): { configFile: string; config: NokkConfig; cwd?: string } {
  let configFile = configPath();
  // Il file di configurazione va risolto prima di caricarlo: altrimenti
  // --config verrebbe applicato solo alla scrittura, ignorando le impostazioni
  // del file scelto (per esempio auto_approve o il profilo).
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--config" && argv[index + 1]) {
      configFile = argv[index + 1];
      index += 1;
    }
  }
  const config = loadConfig(configFile);
  let cwd: string | undefined;

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    const next = () => argv[++index] || "";
    switch (argument) {
      case "--config":
        configFile = next();
        break;
      case "--url":
        config.baseUrl = normalizeBaseUrl(next());
        break;
      case "--key":
        config.apiKey = next();
        break;
      case "--mode":
        config.mode = normalizeMode(next());
        break;
      case "--agent":
        config.agent = true;
        break;
      case "--no-agent":
        config.agent = false;
        break;
      case "--cwd":
        cwd = next();
        break;
      case "-h":
      case "--help":
        console.log(usage());
        process.exit(0);
        break;
      case "-v":
      case "--version":
        console.log(VERSION);
        process.exit(0);
        break;
      default:
        if (argument.startsWith("-")) {
          console.error(`Opzione sconosciuta: ${argument}\n\n${usage()}`);
          process.exit(2);
        }
    }
  }

  return { configFile, config, cwd };
}

const { configFile, config, cwd } = parse(process.argv.slice(2));
try {
  saveConfig(config, configFile);
} catch {
  // La configurazione può essere in sola lettura: la sessione funziona lo stesso.
}

const target = cwd || config.initialCwd;
if (target) {
  try {
    process.chdir(target);
  } catch {
    console.error(`Directory non valida: ${target}`);
  }
}

process.on("SIGTERM", () => process.exit(0));
process.on("SIGINT", () => process.exit(0));

render(
  <App initialConfig={config} configFile={configFile} />,
  { exitOnCtrlC: false },
);
