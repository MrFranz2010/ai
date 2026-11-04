# NOKK — assistente AI locale

NOKK è un'app web Python che può usare API cloud di OpenAI, Anthropic, Google Gemini o OpenRouter.

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
configurazione usa DuckDuckGo tramite la sua pagina HTML pubblica.

Sono supportati anche provider opzionali con piano gratuito senza carta:

- **Exa**: imposta `EXA_API_KEY` (crediti gratuiti iniziali e mensili).
- **Tavily**: imposta `TAVILY_API_KEY` (circa 1.000 ricerche al mese).

L'ordine è Exa, Tavily, DuckDuckGo e infine Serper se la vecchia
`SERPER_API_KEY` è ancora presente. Serper non è più obbligatorio e non viene
usato se non configurato.

Le chiavi restano solo lato server e non vengono salvate nel repository, nella
configurazione dell'app o nella cronologia chat. Le query vengono inviate al
provider scelto: non inserire dati riservati. DuckDuckGo può temporaneamente
bloccare le richieste automatizzate; in quel caso configura Exa o Tavily.

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
