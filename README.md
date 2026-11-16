# NOKK Terminal

Client da terminale per NOKK, con TUI a pannelli. Funziona con entrambe le
varianti del server: quella locale (`linux_start.py`) e quella hosting
(Render/Fly con Supabase). Questo ramo contiene **solo il client**, così non
serve mantenere due copie del terminale.

## Installazione

```bash
python -m pip install -r requirements-tui.txt
python nokk_cli.py
```

La TUI apre la chat a sinistra e, a destra, agenti, chat, utilizzo delle
risorse, widget e attività.

## Profili Locale e Hosting

Premi `F2` (oppure scrivi `/settings`) per aprire le impostazioni:

- **Locale**: per esempio `http://127.0.0.1:8000`, senza chiave API.
- **Hosting**: indirizzo pubblico e chiave creata in **Impostazioni → API**.
- Server e chiave dei due profili restano salvati separatamente in
  `~/.config/nokk/cli.json` (permessi `600`).
- Il pulsante **Prova connessione** verifica il profilo prima di salvarlo.

Puoi anche usare le variabili d'ambiente:

```bash
NOKK_URL=https://tuo-nokk.onrender.com NOKK_API_KEY=nokk_... python nokk_cli.py
```

## Uso

```bash
python nokk_cli.py                 # TUI
python nokk_cli.py --plain         # terminale a righe
python nokk_cli.py "domanda"       # one-shot
python nokk_cli.py --exec "git status"
```

- `!comando` esegue un comando locale e aggiunge l'output al contesto.
- L'agente propone comandi locali nei blocchi `nokk-run`; il client chiede
  conferma e li esegue sulla macchina locale.
- I comandi che NOKK vuole eseguire sul server passano dalle approvazioni.
- `Ctrl+Q` esce, `Ctrl+N` nuova chat, `Ctrl+B` sidebar, `Ctrl+L` pulisce,
  `F1` aiuto, `F2` impostazioni.

## Test

```bash
python -m unittest discover -s tests
```
