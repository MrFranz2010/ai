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

## Ricerca Google

Nel branch `main` l'assistente può cercare risultati Google con lo strumento
`google_search`, che restituisce titolo, URL ed estratto dei risultati
principali. La ricerca usa [Serper](https://serper.dev/), che espone i risultati
Google tramite una API con chiave e offre un piano gratuito iniziale.

Imposta `SERPER_API_KEY` come variabile d'ambiente del server prima di avviare
`python linux_start.py`:

```bash
export SERPER_API_KEY="la-tua-chiave"
```

La chiave resta solo lato server, non viene salvata nel repository, nella
configurazione dell'app o nella cronologia chat. Le query vengono inviate al
servizio di ricerca esterno: non inserire dati riservati. Senza
`SERPER_API_KEY` lo strumento risponde con un errore di configurazione e
l'assistente continua a funzionare normalmente.

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
