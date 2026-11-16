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

## Server MCP esterni

NOKK può avviare server MCP locali via stdio e usarne i tool durante una chat.
I server si configurano nel file di configurazione, nella chiave `mcp_servers`:

```json
{
  "mcp_servers": [
    {
      "name": "filesystem",
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/home/tuo-utente/progetti"
      ],
      "enabled": true
    }
  ]
}
```

I tool vengono esposti al modello come `mcp_<server>_<tool>`; NOKK scopre la
lista all'avvio di ogni richiesta e inoltra le chiamate allo stesso processo.
`env` può aggiungere variabili d'ambiente, mentre quelle del server non
necessarie non vengono ereditate. Un server che non parte viene saltato senza
bloccare la chat.

Il comando del server esegue codice sulla macchina di NOKK: configura solo
server fidati e limita gli argomenti alla cartella che vuoi rendere accessibile.
Le chiamate MCP non passano dalla conferma dei comandi del terminale, quindi il
contenuto a cui il server può accedere dipende dai suoi permessi.

## Consapevolezza operativa

NOKK riceve nel system prompt una descrizione del proprio stato: identità di
assistente software, provider e modello in uso, modalità, numero di attività
attive, terminale e strumenti disponibili. La descrizione include anche i limiti:
NOKK non ha sensi, non percepisce file o rete senza uno strumento e non deve
dichiarare azioni non confermate. Non vengono esposte chiavi API o altri segreti.

NOKK non modifica calendario o attività come effetto collaterale: i comandi da
terminale, le operazioni sui file e le richieste di codice non possono creare
eventi. La modifica richiede una richiesta esplicita dell'utente nell'ultimo
messaggio; in caso contrario il tool viene rifiutato e NOKK chiede conferma.

## Attività persistenti

I metadati delle richieste vengono salvati in `jobs.json` accanto alla
configurazione, così lo stato resta disponibile dopo un riavvio. Al riavvio le
attività rimaste in corso vengono chiuse come fallite, perché il processo che
le eseguiva non esiste più.

Gli errori transitori del provider (`408`, `425`, `429`, `5xx`, timeout e
connessione interrotta) vengono ritentati fino a tre volte con attesa crescente.
Gli errori di autenticazione, modello o richiesta non vengono ritentati.

`GET /api/jobs` e `GET /api/v1/jobs` restituiscono attività recenti, provider,
modello, durata, tentativi e ultimo errore.

## Note sulla cronologia chat

Sono supportate fino a 100 chat, con fino a 500 messaggi testuali per chat. Gli
allegati non vengono conservati nella cronologia. Quando invia una nuova richiesta
al provider, l'app limita il contesto trasmesso agli ultimi 40 messaggi. Le chat
sono persistenti sul dispositivo locale (file JSON).

## Test

Esegui `python -m unittest discover -s tests`.
