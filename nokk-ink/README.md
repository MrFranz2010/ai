# NOKK Ink

Terminale interattivo per NOKK costruito con Ink e React. Usa lo stesso backend,
lo stesso `cli.json` e lo stesso `sessions.json` della TUI Python, ma con una
interfaccia più essenziale: transcript, palette dei comandi, stato del job e
composer.

## Avvio

Richiede Node 22 o successivo.

```bash
cd nokk-ink
npm install
npm run build
node dist/cli.js --url http://127.0.0.1:8000
```

Durante lo sviluppo:

```bash
npm run dev
```

Opzioni: `--url`, `--mode`, `--agent/--no-agent`, `--cwd`, `--key`,
`--config` e `--help`.

## Funzioni

- Chat con polling del job, risposta parziale in streaming e cronometro.
- Auto-approvazione locale attiva per impostazione predefinita; disattivabile
  da `/settings` o con `"auto_approve": false`.
- Blocchi `nokk-run` eseguiti sulla macchina locale, chiusi sia con il
  delimitatore Markdown sia con `</parameter>`; nessun limite locale di round,
  comandi o durata.
- Password `sudo` richiesta in modo nascosto e passata via stdin.
- Menzioni `@file` lette nel contesto della richiesta.
- Sessioni compatibili con la TUI Python: `/history` apre l'elenco interattivo
  (Invio riapre, `d` elimina con conferma), `/sessions`, `/resume`, `/delete`,
  `/rename`, `/export`, `/retry`.
- Profili `local`/`hosting`, `/url`, `/key`, `/model`, `/mode`, `/agent`,
  `/settings`, `/status`, `/jobs`, `/diff`, `/git`, `/update`, `/cancel`.
- `!comando` e `/run <comando>` per la shell locale.
- Comandi locali proposti dall'agente eseguiti sul PC, mai sul server.

Tasti: `Ctrl+C` interrompe il job o il comando locale in corso; premuto di
nuovo esce. `Ctrl+L` pulisce il transcript, `Ctrl+E` esporta, `Ctrl+Y` copia
l'ultima risposta, `Ctrl+N` nuova chat, `Ctrl+R` ripete, `Ctrl+X` annulla e
`Ctrl+Q` esce.

## Test

```bash
npm test
```

I test coprono protocollo HTTP, parser `nokk-run`, file `@`, sessioni e
configurazione.
