# NOKK — assistente AI locale

Una piccola applicazione web locale per chattare con API cloud di OpenAI,
Anthropic, Google Gemini o OpenRouter. Non richiede Ollama o Node.js.

## Hosting online (Render + Supabase)

Questo branch può essere distribuito su Render. In quel caso configurazione,
procedure, calendario, Telegram e cronologia chat sono salvati nella tabella
privata `app_state` di Supabase e sopravvivono ai riavvii, invece di usare i
file JSON locali. Imposta `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` come
variabili segrete del servizio, esegui [`supabase/schema.sql`](supabase/schema.sql)
e segui [`RENDER_DEPLOY.md`](RENDER_DEPLOY.md). Non esporre la service role key
nel browser o nel repository.

## Ricerca Google

Questo branch espone lo strumento `google_search`, che restituisce titolo, URL
ed estratto dei risultati Google tramite [Serper](https://serper.dev/). Imposta
`SERPER_API_KEY` come variabile d'ambiente (su Render: variabile segreta del
servizio). La chiave resta solo lato server e non viene salvata in Supabase, nel
repository o nella cronologia. Le query vengono inviate al servizio esterno: non
inserire dati riservati.

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
- Puoi allegare fino a 5 file per messaggio (massimo 4 MB per file): testo,
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
- Non esegue ancora codice generato come skill né si auto-modifica.
- La cronologia delle conversazioni è disponibile nel deploy online e viene
  salvata in Supabase; con `python app.py` in locale la pagina non mostra il
  pannello delle chat salvate. La configurazione resta salvata tra i riavvii.

La creazione e l'attivazione di skill generate sono una fase successiva.

## Test

Esegui `python -m unittest discover -s tests`.
