# NOKK — assistente AI locale

NOKK è un'app web Python che può usare le API di OpenAI, Anthropic, Google Gemini,
Mistral AI, Groq, DeepSeek, xAI (Grok) o OpenRouter. Con il provider **API
compatibile OpenAI** puoi collegare anche altri servizi, come Together AI,
Fireworks, OpenRouter alternativo, un server Ollama o LM Studio: basta indicare
l'indirizzo di base dell'API (per esempio `https://api.together.xyz/v1`) e il nome
del modello. Gli endpoint remoti richiedono `https://`; `http://` è accettato solo
per `localhost`, così il backend non può essere usato per raggiungere altri host
della rete.

## Linux e avvio locale

1. Installa Python 3.10 o successivo.
2. Installa i pacchetti: `python -m pip install -r requirements.txt`.
3. Avvia il server locale con `python linux_start.py`.
4. Apri <http://127.0.0.1:8000> nel browser.
5. In **Impostazioni**, scegli il provider, il modello e inserisci la chiave API.

Il launcher `linux_start.py` mantiene la compatibilità con il server locale e aggiunge
la cronologia delle chat. Su Linux le conversazioni sono salvate in `chats.json`
accanto alla configurazione dell’app; puoi crearne molte, riaprirle ed eliminarle.

## Terminale (`nokk`)

`nokk_cli.py` è un client da terminale in stile Claude Code: usa lo stesso
backend della pagina web e lavora nella cartella da cui lo avvii. La modalità
predefinita è una TUI a pannelli con la chat a sinistra e, a destra, agenti,
chat, utilizzo delle risorse, widget e attività.

```bash
python -m pip install -r requirements-tui.txt   # una volta sola
python nokk_cli.py
```

```text
┌ chat / transcript ─────────────────┬ agenti · chat · risorse ─┐
│ tu: …                              │ ● NOKK API      online   │
│ NOKK: …                            │ ● Agente        pronto   │
│ !comando                           │ ● Terminale     conferma │
│                                    │ CPU/RAM/Disco · token    │
│ > scrivi a NOKK…                   │ chat · modalità · cwd    │
└────────────────────────────────────┴──────────────────────────┘
```

Nella TUI puoi scrivere normalmente all'assistente, usare `!comando` per
eseguire subito un comando locale e `/help` per gli altri comandi (`/cd`,
`/run`, `/agent`, `/mode`, `/url`, `/key`, `/server`, `/status`, `/export`,
`/copy`, `/retry`, `/sessions`, `/resume`, `/rename`, `/model`, `/diff`,
`/git`, `/cancel`). Con l'agente attivo,
se NOKK propone un comando in un blocco `nokk-run`, il client chiede conferma,
lo esegue **sulla macchina locale** e restituisce l'output al modello; i comandi
che NOKK vuole eseguire sul server restano soggetti alle approvazioni del server.

Tasti: `Ctrl+Q` esce, `Ctrl+N` nuova chat, `Ctrl+B` mostra o nasconde la
barra laterale, `Ctrl+E` esporta la chat, `Ctrl+Y` copia l'ultima risposta,
`Ctrl+R` ripete l'ultima domanda, `Ctrl+L` pulisce il transcript, `F1` apre
l'aiuto e `F2` le impostazioni. Da
`F2` (o `/settings`) scegli il profilo **Locale** o **Hosting** e modifichi
server, chiave API, modalità e agente: i due profili restano salvati
separatamente nello stesso file di configurazione. `/export [file]` salva la
conversazione in Markdown (per impostazione predefinita in
`nokk-chat-<data>.md`), `/copy [numero|all]` copia l'ultima risposta, una
risposta precedente o tutto il transcript, mentre `/status` riassume profilo,
connessione, provider, modello, directory e configurazione. Le sessioni sono
salvate in `sessions.json`: `/sessions`, `/resume <n>` e `/rename <titolo>`;
`/model <provider>/<modello>` cambia modello per la sessione, `@file` allega
file al contesto e `/diff`/`/git status` mostrano il repository. `Ctrl+X` o
`/cancel` annulla il job in corso. Su terminali stretti la barra laterale si
nasconde da sola. Se Textual non è installato, il client ripiega sul
terminale a righe; `--plain` lo forza e `--tui` richiede esplicitamente la TUI.

```bash
python nokk_cli.py --plain
python nokk_cli.py "controlla perché il test fallisce"
python nokk_cli.py --exec "git status"
```

Nelle esecuzioni one-shot i comandi sono bloccati per sicurezza: aggiungi `--yes`
per approvarli automaticamente.

### MCP

`nokk_mcp.py` espone NOKK come server MCP su stdio con i tool `nokk_health` e
`nokk_chat`; un client MCP può avviarlo con `python3 nokk_mcp.py` e le normali
variabili `NOKK_URL`/`NOKK_API_KEY`. Non approva automaticamente i comandi del
server: se un job è in attesa, restituisce un errore e invita ad approvarlo
dalla web o dalla TUI.

### Client unificato

Il terminale è disponibile anche nel ramo **`nokk-cli-unified`**, che contiene
solo client, TUI e test. Si collega indifferentemente al NOKK locale o a quello
hosting tramite i profili Locale/Hosting in `F2`, senza duplicare il codice del
terminale. Non è un merge dei due rami server: le varianti desktop e hosting
restano separate, come richiesto da `AGENTS.md`.

```bash
git switch nokk-cli-unified
python -m pip install -r requirements-tui.txt
python nokk_cli.py
```

Il server predefinito è `http://127.0.0.1:8000` (quello di `linux_start.py`).
Per l'hosting indica l'indirizzo e una chiave API creata in **Impostazioni →
API**, preferibilmente tramite variabili d'ambiente così la chiave non finisce
nella cronologia della shell:

```bash
NOKK_URL=https://tuo-nokk.onrender.com NOKK_API_KEY=nokk_... python nokk_cli.py
```

La chiave può anche essere impostata una volta con `/key` (viene chiesta in modo
nascosto e salvata in `~/.config/nokk/cli.json` con permessi `600`).

## Ricerca web gratuita

L'assistente usa lo strumento `web_search`, che restituisce titolo, URL ed
estratto dei risultati. **Non serve alcuna chiave a pagamento**: senza
configurazione usa DuckDuckGo tramite la sua pagina HTML pubblica e, se
DuckDuckGo non risponde o chiede una verifica anti-bot, ripiega su Yahoo e
poi su Bing, così la ricerca continua a funzionare anche quando un motore
blocca le richieste automatiche.

Sono supportati anche provider opzionali con piano gratuito senza carta:

- **Exa**: imposta `EXA_API_KEY` (crediti gratuiti iniziali e mensili).
- **Tavily**: imposta `TAVILY_API_KEY` (circa 1.000 ricerche al mese).

L'ordine è Exa, Tavily, DuckDuckGo, Yahoo, Bing e infine Serper se la vecchia
`SERPER_API_KEY` è ancora presente. Serper non è più obbligatorio e non viene
usato se non configurato. Se nessun motore risponde, NOKK ripiega sulle voci di
Wikipedia, segnalando che non si tratta di notizie aggiornate.

Prima di restituire i risultati, NOKK controlla che contengano almeno un
termine significativo della query: Bing a volte risponde a una ricerca senza
risultati con pagine di altre ricerche, e quei risultati vengono scartati
invece di essere presentati come attendibili.

Le chiavi restano solo lato server e non vengono salvate nel repository, nella
configurazione dell'app o nella cronologia chat. Le query vengono inviate al
provider scelto: non inserire dati riservati. DuckDuckGo può temporaneamente
bloccare le richieste automatizzate: in quel caso NOKK prova automaticamente
con Yahoo e poi con Bing, mentre Exa o Tavily restano i provider più
affidabili.

## Google Calendar

Puoi collegare il tuo Google Calendar e lasciare che l'assistente legga,
crei o elimini eventi con lo strumento `google_calendar`.

1. In Google Cloud Console crea un progetto e abilita la **Google Calendar API**.
2. Crea un client OAuth di tipo **Applicazione web**.
3. Apri **Impostazioni → Google Calendar** in NOKK, copia l'URI di
   reindirizzamento mostrato (in locale è
   `http://127.0.0.1:8000/oauth/google/callback`) e incollalo tra gli URI
   autorizzati del client.
4. Salva client ID, client secret e ID del calendario, premi **Collega Google
   Calendar** e autorizza l'accesso: NOKK chiede solo `calendar.events`.

Client ID, client secret e token di aggiornamento restano lato server: il
secret non viene mai restituito all'interfaccia, il token è salvato in
`google_calendar.json` con accesso limitato al tuo utente e non finisce nella
cronologia chat né nel repository. Se preferisci, fornisci le credenziali con
`GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` e imposta l'URI con
`GOOGLE_OAUTH_REDIRECT_URI`. Per un calendario diverso da quello principale
indica il suo ID nelle impostazioni; **Disconnetti** rimuove il token salvato.

## Auto-modifica del codice (branch `main`)

Nel branch `main` l'assistente può leggere i file del proprio repository e proporre
modifiche tramite pull request con gli strumenti `list_repository_files`,
`read_repository_file` e `create_pull_request`. Non può leggere chiavi, token o
file di stato privati e non pubblica direttamente sul branch base: le modifiche
diventano attive solo dopo revisione, merge e redeploy.

Per abilitare le pull request configura sul server, senza scriverlo nel repository
né nella chat:

- `GITHUB_TOKEN`: token GitHub con permesso di scrittura su contenuto e pull
  request del repository.
- `GITHUB_REPOSITORY`: repository nel formato `owner/repository` (predefinito
  `MrFranz2010/ai`).
- `GITHUB_BASE_BRANCH`: branch di destinazione delle pull request (predefinito
  `main`).

In locale esporta le variabili prima di avviare `python linux_start.py`. Senza
`GITHUB_TOKEN` restano disponibili solo la lettura del codice e l'elenco dei file.

## Note sulla cronologia chat

Sono supportate fino a 100 chat, con fino a 500 messaggi testuali per chat. Gli
allegati non vengono conservati nella cronologia. Quando invia una nuova richiesta
al provider, l'app limita il contesto trasmesso agli ultimi 40 messaggi. Le chat
sono persistenti sul dispositivo locale (file JSON).

## Test

Esegui `python -m unittest discover -s tests`.
