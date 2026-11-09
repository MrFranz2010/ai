# NOKK — assistente AI locale

NOKK è un'app web Python per chattare con le API di OpenAI, Anthropic,
Google Gemini, Mistral AI, Groq, DeepSeek, xAI (Grok) o OpenRouter, senza
Ollama o Node.js. Con il provider **API compatibile OpenAI** puoi collegare
anche altri servizi, come Together AI, Fireworks o un server LM Studio: basta
indicare l'indirizzo di base dell'API (per esempio `https://api.together.xyz/v1`)
e il nome del modello. Gli endpoint remoti richiedono `https://`; `http://`
è accettato solo per `localhost`, così il backend non può raggiungere altri
host della rete.

## Hosting online (Render + Supabase)

Questo branch può essere distribuito su Render. In quel caso configurazione,
procedure, calendario, Telegram e cronologia chat sono salvati nella tabella
privata `app_state` di Supabase e sopravvivono ai riavvii, invece di usare i
file JSON locali. Imposta `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` come
variabili segrete del servizio, esegui [`supabase/schema.sql`](supabase/schema.sql)
e segui [`RENDER_DEPLOY.md`](RENDER_DEPLOY.md). Non esporre la service role key
nel browser o nel repository.

## Ricerca Google

L'assistente usa lo strumento `web_search`, che restituisce titolo, URL ed
estratto dei risultati. **Non serve alcuna chiave a pagamento**: senza
configurazione usa DuckDuckGo tramite la sua pagina HTML pubblica e, se
DuckDuckGo non risponde o chiede una verifica anti-bot, ripiega su Yahoo e
poi su Bing.

Sono supportati anche provider opzionali con piano gratuito senza carta:

- **Exa**: imposta `EXA_API_KEY` (crediti gratuiti iniziali e mensili).
- **Tavily**: imposta `TAVILY_API_KEY` (circa 1.000 ricerche al mese).

L'ordine è Exa, Tavily, DuckDuckGo, Yahoo, Bing e infine Serper se la vecchia
`SERPER_API_KEY` è ancora presente. Serper non è più obbligatorio e non viene
usato se non configurato. Se nessun motore risponde, NOKK ripiega sulle voci di
Wikipedia, segnalando che non si tratta di notizie aggiornate.

Le chiavi restano solo lato server e non vengono salvate in Supabase, nel
repository o nella cronologia chat. Le query vengono inviate al provider scelto:
non inserire dati riservati. DuckDuckGo può temporaneamente bloccare le
richieste automatizzate: in quel caso NOKK prova automaticamente con Yahoo e
poi con Bing, scartando i risultati di Bing che non riguardano la query,
mentre Exa o Tavily restano i provider più affidabili.

## Google Calendar

Puoi collegare il tuo Google Calendar e lasciare che l'assistente legga,
crei o elimini eventi con lo strumento `google_calendar`.

1. In Google Cloud Console crea un progetto e abilita la **Google Calendar API**.
2. Crea un client OAuth di tipo **Applicazione web**.
3. Apri **Impostazioni → Google Calendar** in NOKK, copia l'URI di
   reindirizzamento mostrato (nel deploy hosted è l'indirizzo Render del
   servizio seguito da `/oauth/google/callback`) e incollalo tra gli URI
   autorizzati del client.
4. Salva client ID, client secret e ID del calendario, premi **Collega Google
   Calendar** e autorizza l'accesso: NOKK chiede solo `calendar.events`.

Client ID, client secret e token di aggiornamento restano lato server: il
secret non viene mai restituito all'interfaccia e `google_calendar.json` è
salvato nella tabella privata `app_state` su Supabase, insieme al resto della
configurazione, quindi non finisce nel repository né nella cronologia chat. Se
preferisci, fornisci le credenziali con `GOOGLE_CLIENT_ID` e
`GOOGLE_CLIENT_SECRET` e imposta l'URI con `GOOGLE_OAUTH_REDIRECT_URI`. Per un
calendario diverso da quello principale indica il suo ID nelle impostazioni;
**Disconnetti** rimuove il token salvato.

## Avvio

1. Installa Python 3.10 o successivo.
2. Installa la dipendenza per leggere i PDF: `python -m pip install -r requirements.txt`.
3. Apri un terminale in questa cartella ed esegui `python app.py`.
4. Apri <http://127.0.0.1:8000> nel browser.
5. In **Impostazioni**, scegli il provider, il modello e inserisci una chiave
   API ottenuta dal provider. Puoi anche impostare le istruzioni permanenti
   dell'assistente: vengono salvate in locale e incluse in ogni richiesta.

Per usare OpenRouter, crea una chiave su <https://openrouter.ai/keys> e scegli
**OpenRouter · modelli gratuiti automatici**. Il router `openrouter/free`
seleziona automaticamente un modello gratuito disponibile. L'app non usa
modelli a pagamento con questa opzione; i modelli gratuiti possono comunque
avere limiti di richiesta, disponibilità o tempi di attesa. OpenRouter inoltra
i messaggi al provider del modello scelto: evita di inviare dati sensibili.
La selezione automatica avviene a ogni richiesta; non garantisce un nuovo
tentativo se una richiesta fallisce dopo essere stata instradata.

Dettagli sul [router gratuito di OpenRouter](https://openrouter.ai/docs/guides/routing/routers/free-router.md).

Per gli altri provider, il nome del modello deve essere disponibile per la tua
chiave e il tuo account; il loro uso può comportare costi.

La configurazione, inclusa la chiave API, viene salvata in `config.json` nella
cartella di configurazione dell'utente:

- Linux: `~/.config/assistente-ai/config.json` (o `$XDG_CONFIG_HOME/assistente-ai/config.json`)
- Windows: `%APPDATA%\assistente-ai\config.json`

Puoi specificare un altro percorso impostando `AI_CONFIG_FILE` prima di avviare
l'applicazione. Su Linux il file viene creato con permessi `600` (solo il tuo
utente può leggerlo o modificarlo). Su Windows eredita i permessi della
cartella del profilo utente. La chiave è salvata in chiaro: non condividere il
file, non inserirlo nel controllo versione e non rendere il server accessibile
a Internet. `/api/config` non restituisce mai la chiave al browser.
Il token Telegram viene salvato separatamente in `telegram.json`, accanto alla
configurazione, con le stesse protezioni locali.

## Cosa fa e cosa non fa ancora

- La pagina web permette di configurare provider e modello e mantenere una
  conversazione finché la pagina resta aperta.
- La barra di ricerca centrale apre le applicazioni e le azioni di NOKK
  (Ctrl+K su Windows/Linux, Cmd+K su macOS). Chat, calendario, attività,
  procedure, impostazioni e stato della macchina sono raggiungibili dal menu;
  le finestre possono essere spostate, ridotte a icona, ripristinate e
  ingrandite.
- Calendario e attività vengono salvati in `planner.json` nella cartella di
  configurazione locale. Il calendario gestisce appuntamenti con data, ora e
  note; le attività possono avere una scadenza ed essere completate, con
  ricerca e filtri per attività da fare, scadute e completate. NOKK può leggere
  e modificare calendario, attività e procedure tramite strumenti AI. I dati
  vengono inviati al provider solo quando una richiesta richiede l'uso di
  queste sezioni.
- Lo stato della macchina mostra sistema operativo, versione Python, processori
  disponibili, memoria, spazio disco e tempo dall'avvio. Non mostra hostname,
  nome utente o percorsi personali.
- L'interfaccia NOKK usa il tema scuro per impostazione predefinita; il pulsante
  nella barra superiore alterna tema scuro e chiaro e ricorda la scelta nel
  browser.
- Puoi allegare fino a 22 file per messaggio, con un massimo di 20 immagini,
  4 MB per file e 40 MB in totale: testo,
  codice, PDF, DOCX e immagini PNG, JPEG, WEBP o GIF. Il testo dei documenti
  viene estratto localmente; i PDF scansionati richiedono OCR e non sono
  supportati. Le immagini vengono inviate al provider e richiedono un modello
  con supporto visivo. I file non vengono salvati dall'app, ma il loro
  contenuto e la conversazione vengono inviati al provider scelto; evita
  documenti sensibili e controlla le condizioni del provider.
- Le impostazioni sono divise in sezioni richiudibili: connessione,
  personalità, voce, strumenti e Telegram.
- L'assistente può consultare anche lo stato macchina e le impostazioni non
  sensibili. Chiavi API, token Telegram e istruzioni personalizzate non vengono
  esposti agli strumenti AI. Lo stato macchina è disponibile in sola lettura.
- Puoi salvare fino a 30 procedure con istruzioni riutilizzabili. Avviarle
  inserisce il testo nella chat senza inviarlo automaticamente: puoi rivederlo,
  modificarlo e inviarlo tu. Le procedure sono salvate in `workflows.json`
  accanto alla configurazione.
- Nelle impostazioni puoi personalizzare il prompt di sistema dell'assistente
  (fino a 10.000 caratteri); lasciandolo vuoto vengono usate le istruzioni
  predefinite dell'applicazione.
- La chat offre dettatura STT, wake word configurabile e lettura TTS delle
  risposte. La wake word va attivata con il relativo pulsante a ogni apertura
  della pagina; mentre è attiva, resta in ascolto dopo i comandi e prova a
  riavviarsi circa 300 ms dopo un'interruzione del browser. Se il browser non
  riesce ad avviare il microfono, i tentativi aumentano gradualmente fino a
  2 secondi. Anche quando cambi scheda, il browser o il sistema operativo
  possono sospendere il microfono: il riconoscimento non è garantito a pagina
  chiusa o quando il browser lo limita. La voce dettata resta nel compositore
  e non viene inviata da sola. STT usa il riconoscimento vocale integrato nel browser: a seconda
  del browser, l'audio può essere elaborato da un servizio online. TTS usa le
  voci del browser. Queste funzioni richiedono un browser compatibile e, per il
  microfono, il relativo permesso.
- Il pannello dei messaggi scorre indipendentemente dal resto della pagina;
  barra laterale e compositore restano fermi.
- Le risposte dell'assistente supportano Markdown comune: titoli, enfasi,
  liste, citazioni, link, tabelle e blocchi di codice. L'HTML ricevuto dal
  modello non viene eseguito.
- Il backend invia i messaggi direttamente al provider selezionato. La chiave
  API non viene salvata dal browser né inclusa nella cronologia.
- L'uso del terminale è disattivato inizialmente. Se lo abiliti nelle
  impostazioni, l'assistente può proporre comandi nella cartella di lavoro
  selezionata: in modalità standard devi approvare ogni comando mostrando
  anteprima, cartella e output. I comandi approvati girano con i permessi del
  tuo utente e **non** sono confinati alla cartella di lavoro; controllali prima
  di approvarli.
- La modalità automatica esegue senza richiesta solo `pwd`, `ls`, `cat`,
  `head`/`tail` su file locali non sensibili della cartella e fino a 100 KB.
  Non abilita scrittura o composizione di comandi. Gli altri comandi richiedono
  comunque conferma. I comandi manuali hanno un timeout di 30 secondi e
  l'output mostrato è limitato.
- Il terminale supporta richieste di funzione dei provider OpenAI, Anthropic,
  Google e OpenRouter; il modello e il provider devono supportare l'uso degli
  strumenti.
- Puoi collegare un bot Telegram dalle impostazioni. Il token viene verificato
  con `getMe` e salvato solo nel file locale `telegram.json`; non viene mai
  restituito all'interfaccia o all'assistente. Il processo locale usa il
  long-polling Telegram, senza webhook o porte Internet in ingresso. Genera un
  codice temporaneo e invia `/pair CODICE` al bot in una chat privata per
  autorizzarla; le chat non associate e i gruppi vengono ignorati. Per
  proteggere il computer, le chat Telegram non possono usare il terminale.
  Messaggi e contesto della chat autorizzata vengono inoltrati al provider AI
  configurato; disconnettere il bot rimuove token e chat autorizzate.
- Puoi collegare Google Calendar dalle impostazioni con un client OAuth
  personale; credenziali e token restano lato server (in `app_state` su
  Supabase) e l'assistente può leggere, creare o eliminare eventi con lo
  strumento `google_calendar`.
- Non esegue ancora codice generato come skill né si auto-modifica.
- La cronologia delle conversazioni è disponibile nel deploy online e viene
  salvata in Supabase; con `python app.py` in locale la pagina non mostra il
  pannello delle chat salvate. La configurazione resta salvata tra i riavvii.

La creazione e l'attivazione di skill generate sono una fase successiva.

## Test

Esegui `python -m unittest discover -s tests`.
