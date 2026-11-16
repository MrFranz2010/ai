# NOKK Terminal

Client da terminale per **NOKK**, con TUI a pannelli in stile Claude Code.
Questo ramo contiene solo il client: si collega indifferentemente al NOKK
locale o al NOKK hosting, quindi non serve mantenere due copie del terminale.

## Requisiti

- Python 3.10 o successivo.
- Un server NOKK raggiungibile (locale o hosting).
- `textual` solo per la TUI: è una dipendenza opzionale del client, non del server.

## Avvio rapido

```bash
git switch nokk-cli-unified
python -m pip install -r requirements-tui.txt
python nokk_cli.py
```

La TUI apre la chat a sinistra e, a destra, la barra con:

- **Agenti:** stato di NOKK API, agente locale, terminale e approvazioni.
- **Chat:** sessioni della sessione corrente.
- **Risorse:** CPU, RAM, disco, token di contesto stimati, richieste, latenza e
  memoria del processo.
- **Widget:** profilo attivo, modalità, agente, directory corrente e branch Git.
- **Attività:** ultimi comandi e approvazioni.

Se `textual` non è installato, il client usa automaticamente la modalità a
righe. `--plain` la forza, mentre `--tui` richiede esplicitamente la TUI.

## Profili Locale e Hosting

Premi **`F2`** oppure scrivi **`/settings`**. Nella schermata puoi:

- scegliere il profilo **Locale** o **Hosting**;
- modificare URL del server e chiave API del profilo selezionato;
- scegliere la modalità (`codice`, `studio`, `analista`, `off`);
- attivare o disattivare i comandi locali proposti dall'agente;
- provare la connessione prima di salvare.

I due profili restano salvati separatamente in `~/.config/nokk/cli.json`,
creato con permessi `600`. Cambiare server non cancella la chiave dell'altro
profilo.

Valori predefiniti:

| Profilo | URL tipico | Chiave |
| --- | --- | --- |
| Locale | `http://127.0.0.1:8000` | di solito non serve |
| Hosting | `https://tuo-nokk.onrender.com` | `nokk_...` da Impostazioni → API |

Puoi anche usare le variabili d'ambiente, che hanno la precedenza sul file di
configurazione all'avvio:

```bash
NOKK_URL=https://tuo-nokk.onrender.com NOKK_API_KEY=nokk_... python nokk_cli.py
```

Non passare la chiave come argomento della riga di comando: finirebbe nella
cronologia della shell. Usa `F2` o `/key`.

## Uso

```bash
python nokk_cli.py                 # TUI
python nokk_cli.py --cwd /         # TUI partendo dalla radice
python nokk_cli.py --plain         # terminale a righe
python nokk_cli.py "domanda"       # one-shot
python nokk_cli.py --exec "git status"
```

La cartella indicata con `--cwd` è solo il punto di partenza: i comandi locali
girano con i permessi del tuo utente e possono leggere o modificare tutto il
sistema, anche con percorsi assoluti fuori da quella cartella. Nella TUI puoi
cambiarla con `/cd /` (Linux/macOS), `/cd C:\` (Windows) o `/cd ~`.

Se un comando usa `sudo`, la TUI mostra una richiesta nascosta per la password e
la passa a sudo tramite stdin (`sudo -S`); nella modalità a righe la password
viene chiesta con `getpass`. La password resta solo in memoria, non viene
salvata, non compare nel transcript e non viene inviata al modello.

Da `F2` (`/settings`) configuri anche: cartella iniziale, timeout delle attività,
numero massimo di round dell'agente, esecuzione automatica dei comandi locali,
streaming della risposta, salvataggio delle sessioni, segnale acustico finale e
pannello di benvenuto. Le stesse impostazioni restano nel file `cli.json` e
valgono anche per la CLI.

- `!comando` esegue subito un comando locale e aggiunge l'output al contesto.
- Con l'agente attivo, se NOKK propone un comando nel blocco `nokk-run`, il
  client chiede conferma, lo esegue **sulla macchina locale** e rimanda
  l'output al modello. Il client disattiva il terminale del server per quella
  richiesta: anche collegandosi all'hosting, i comandi girano sul PC.
- La pagina web non può accedere al computer dell'utente: lì il terminale agisce
  sulla macchina che ospita NOKK. Per lavorare sul proprio PC serve la CLI o la
  TUI.
- Nelle esecuzioni one-shot i comandi sono bloccati per sicurezza; `--yes` li
  approva automaticamente.
- `/new`, `/cd`, `/run`, `/agent`, `/mode`, `/url`, `/key`, `/server`,
  `/status`, `/config`, `/settings`, `/export`, `/copy` e `/retry` sono
  disponibili anche come comandi slash.
- `/export [file]` salva la chat corrente in Markdown, `/copy [numero|all]`
  copia l'ultima risposta, una risposta precedente o tutto il transcript,
  `/retry` ripete l'ultima domanda e `/status` riassume connessione, provider,
  modello, directory e configurazione.
- Le sessioni sono salvate in `sessions.json` accanto a `cli.json`:
  `/sessions`, `/resume <n>` e `/rename <titolo>`.
- `/model <provider>/<modello>` sceglie il modello per la sessione;
  `@file` allega file al contesto; `/diff`, `/git status` e `/git log`
  mostrano il repository.
- `/cancel` o `Ctrl+X` annulla il job in corso. Con i provider
  OpenAI-compatibili la risposta compare mentre viene generata.

### Tasti della TUI

| Tasto | Azione |
| --- | --- |
| `Ctrl+Q` | esci |
| `Ctrl+N` | nuova chat |
| `Ctrl+B` | mostra/nascondi la barra laterale |
| `Ctrl+E` | esporta la chat in Markdown |
| `Ctrl+Y` | copia l'ultima risposta |
| `Ctrl+R` | ripete l'ultima domanda |
| `Ctrl+L` | pulisci il transcript |
| `F1` | aiuto |
| `F2` | impostazioni |

Su terminali stretti la barra laterale si nasconde automaticamente.

## MCP

`nokk_mcp.py` espone NOKK come server MCP su stdio con i tool `nokk_health` e
`nokk_chat`.

```json
{
  "mcpServers": {
    "nokk": {
      "command": "python3",
      "args": ["/percorso/nokk_mcp.py"],
      "env": {"NOKK_URL": "https://tuo-nokk.onrender.com"}
    }
  }
}
```

Se un job richiede approvazione, il tool restituisce un errore: l'approvazione
resta un'azione esplicita nella web o nella TUI.

## Rami

| Ramo | Contenuto |
| --- | --- |
| `nokk-cli-unified` | solo client e TUI; funziona con locale e hosting |
| `nokk-cli` | app desktop/locale + client |
| `nokk-cli-hosting` | app hosting (Render/Fly + Supabase) + client |

I rami server restano separati: `AGENTS.md` vieta il merge tra la variante
desktop e quella hosting. Il ramo unificato non è un merge, è il client comune
che parla con entrambi tramite le API HTTP.

## API usate

Il client usa le rotte stabili di NOKK:

- `POST /api/v1/chat`
- `GET /api/v1/jobs/<id>`
- `POST /api/v1/jobs/<id>/approval`

Con una chiave API usa sempre `/api/v1/*`; senza chiave usa le rotte del
browser, comode su un NOKK locale. Le approvazioni dal terminale richiedono una
versione del server che esponga la rotta `/api/v1/jobs/<id>/approval`.

## Attività persistenti

Il server conserva i metadati delle richieste in `jobs.json` (o in Supabase
nell'hosting), quindi restano disponibili dopo un riavvio; le attività rimaste
in corso vengono chiuse come fallite. Gli errori transitori del provider
(`408`, `425`, `429`, `5xx`, timeout e connessione interrotta) vengono ritentati
fino a tre volte con attesa crescente, mentre gli errori di autenticazione,
modello o richiesta non vengono ritentati.

Usa `/jobs` per vedere attività recenti, provider, modello, durata, tentativi e
ultimo errore. La stessa lista è disponibile su `GET /api/jobs` e
`GET /api/v1/jobs`.

## Test

```bash
python -m unittest discover -s tests
```

I test del client non richiedono il backend: usano un server simulato e la
test harness headless di Textual.
