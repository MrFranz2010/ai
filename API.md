# API HTTP di NOKK

L'API permette a script, cron job, webhook e all'estensione del browser di usare
NOKK senza aprire la pagina. Si attiva dalle impostazioni, scheda **API**: serve
un'istanza NOKK in esecuzione con provider e chiave AI già configurati.

## Chiavi

1. Apri **Impostazioni → API** e attiva «Abilita l'API HTTP e i webhook».
2. Scrivi un nome (per esempio `Estensione browser`) e premi **Crea chiave**.
3. Copia subito la chiave: viene mostrata una sola volta.

Si possono creare fino a 5 chiavi. Nel file di stato (`api.json`) resta solo
l'impronta SHA-256 e le ultime quattro lettere, quindi un backup non contiene
chiavi utilizzabili. **Revoca** elimina una chiave all'istante.

La chiave si invia in uno di questi due modi:

```
X-API-Key: nokk_...
Authorization: Bearer nokk_...
```

Ogni chiave accetta al massimo **60 richieste al minuto**; oltre si riceve
`429` con il messaggio «Troppe richieste».

## Endpoint

| Metodo | Percorso | Descrizione |
| --- | --- | --- |
| GET | `/api/v1/health` | Stato del servizio, senza chiave |
| POST | `/api/v1/chat` | Avvia una conversazione |
| GET | `/api/v1/jobs/<id>` | Legge l'esito di una conversazione |
| POST | `/api/v1/reminders` | Crea un promemoria da testo italiano |
| GET | `/api/v1/planner` | Elenca eventi e attività |

Le risposte sono JSON e includono le intestazioni CORS, quindi possono essere
chiamate da un'estensione o da una pagina su un altro dominio. Su Render/Fly le
rotte `/api/v1/*` non chiedono la password Basic della pagina: l'autenticazione
è la chiave.

### Avviare una conversazione

```bash
curl -sS https://tuo-nokk.onrender.com/api/v1/chat \
  -H "X-API-Key: nokk_..." \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Riassumi i compiti di oggi"}],"mode":"studio"}'
```

```json
{"job_id": "8f2c..."}
```

`mode` è facoltativo e accetta `codice`, `studio`, `analista`.

### Leggere l'esito

```bash
curl -sS https://tuo-nokk.onrender.com/api/v1/jobs/8f2c... \
  -H "X-API-Key: nokk_..."
```

La risposta contiene `status` (`running`, `awaiting_approval`, `complete`,
`failed`) e, quando la conversazione è finita, `reply` con il testo e
`tool_events` con gli strumenti usati.

### Creare un promemoria

```bash
curl -sS https://tuo-nokk.onrender.com/api/v1/reminders \
  -H "X-API-Key: nokk_..." \
  -H "Content-Type: application/json" \
  -d '{"text":"Riunione con cliente domani alle 10"}'
```

```json
{"ok": true, "label": "domani alle 10:00",
 "item": {"id": "...", "title": "Riunione con cliente",
          "starts_at": "2026-11-10T10:00", "due_date": "2026-11-10"}}
```

Se Telegram è collegato, il promemoria arriva anche 30 minuti prima dell'orario.

## Codici di stato

| Codice | Significato |
| --- | --- |
| 200 / 202 | Richiesta accettata |
| 400 | Payload non valido o modalità sconosciuta |
| 401 | Chiave mancante o errata |
| 403 | API disattivata |
| 404 | Endpoint, chiave o attività inesistente |
| 409 | Provider AI non configurato |
| 429 | Limite di richieste superato |
| 502 / 503 | Servizio AI o servizio esterno non disponibile |

## Sicurezza

- Le chiavi non compaiono mai nel repository né nei backup di stato.
- Non inserire la chiave nel codice di una pagina pubblica: chiunque la legga
  può usare il tuo NOKK. Per il browser usa l'estensione, che la conserva in
  `chrome.storage.local`.
- Revoca una chiave appena un dispositivo o uno script non ti servono più.
