# Istruzioni per chi lavora su questo repository

NOKK esiste in due varianti volutamente separate, una per il desktop/locale e una
per l'hosting web. Non sono due copie dello stesso ramo: hanno entrypoint,
persistenza, dipendenze e file di deploy diversi.

## I due rami

| Ramo | Variante | Entrypoint | Persistenza |
| --- | --- | --- | --- |
| `main` | desktop / locale | `linux_start.py` | file JSON locali (`config.json`, `workflows.json`, `chats.json`, `memories.json`) |
| `copilot/supabase-config-storage` | hosting web (Render/Fly) | `render_start.py`, `fly_start.py` | tabella privata `app_state` su Supabase tramite `supabase_store.py` |

Differenze da tenere presenti:

- Il ramo desktop contiene `linux_start.py`, `web/chat-history.css`, gli strumenti
  di auto-modifica con pull request e non ha artefatti di deploy (`Dockerfile`,
  `render.yaml`, `fly.toml`, `.devcontainer`, `FLY_DEPLOY.md`, `RENDER_DEPLOY.md`),
  rimossi deliberatamente.
- Il ramo web contiene `Dockerfile`, `render.yaml`, `fly.toml`, `render_start.py`,
  `supabase_store.py`, `supabase/schema.sql` e le migrazioni, e ha `supabase` tra
  le dipendenze. La logica di persistenza vive lì, non in `app.py`.
- `web/chat-history.js` è implementato in modo diverso nei due rami: lato client
  sul desktop, lato backend/Supabase sull'hosting. Non è un file "condiviso".
- Anche i fix recenti sono stati reimplementati in parallelo e non condivisi
  (per esempio il modello selezionato per provider).

## Regola principale: i rami non si fondono mai

Non eseguire **mai** merge, rebase, cherry-pick o pull request che uniscano
`main` e `copilot/supabase-config-storage`, in nessuna direzione. Non usare
`git merge` per "allineare" i rami e non risolvere a mano un merge tra loro.

Ogni modifica va realizzata **ad hoc per il ramo di destinazione**:

1. Identifica il ramo giusto per la richiesta (desktop → `main`, hosting →
   `copilot/supabase-config-storage`).
2. Se la stessa funzionalità serve su entrambi, scrivi due implementazioni
   separate, ognuna coerente con l'entrypoint e lo storage di quel ramo. Portare
   una modifica significa riscriverla sul codice dell'altro ramo, non spostarla
   con git.
3. Verifica il risultato sul ramo in cui hai lavorato, con i suoi test e il suo
   comando di avvio.

Quando lavori sul ramo web, crea un branch a partire da
`origin/copilot/supabase-config-storage`. Quando lavori sul desktop, parti da
`origin/main`. Non cambiare ramo dentro un worktree già aperto da altri.

## File che sembrano condivisi ma non lo sono

`README.md`, `.gitignore`, `app.py`, `web/app.js`, `web/index.html`,
`web/style.css`, `web/chat-history.js`, `tests/test_app.py` e
`tests/test_providers.py` esistono su entrambi i rami ma sono già divergenti.
Prima di modificarne uno, controlla il contenuto del ramo di destinazione: non
applicare una patch pensata per l'altro ramo senza adattarla.

## Segreti e configurazione

Non inserire chiavi API, token o password nel repository, nei test o nei file di
stato. `config.json` e `workflows.json` sono già ignorati da git.

- Desktop: la configurazione resta nei file JSON locali accanto all'app.
- Hosting: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `APP_USERNAME` e
  `APP_PASSWORD` vanno impostati come variabili d'ambiente o segreti del servizio,
  mai nel codice. La service role key non deve mai raggiungere il browser.

## Avvio e test

Desktop:

```bash
python -m pip install -r requirements.txt
python linux_start.py
python -m unittest discover -s tests
```

Hosting (in locale, con `python app.py` la persistenza Supabase non è attiva):

```bash
python -m pip install -r requirements.txt
python render_start.py   # solo per il deploy hosted
python -m unittest discover -s tests
```

In questo ambiente cloud non c'è browser e non è possibile completare un deploy
interattivo: segnala i passaggi di hosting che richiedono l'accesso dell'utente
invece di simularli.
