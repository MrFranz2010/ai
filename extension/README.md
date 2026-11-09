# NOKK per il browser

Estensione Chrome/Edge (MV3) che apre NOKK accanto alla pagina che stai
leggendo: testo selezionato, domande rapide e le tre modalità di risposta.

## Installazione

1. Apri `chrome://extensions` (o `edge://extensions`) e attiva **Modalità sviluppatore**.
2. Premi **Carica estensione non pacchettizzata** e scegli questa cartella `extension/`.
3. Apri il popup di NOKK, premi **Impostazioni** e compila:
   - **Indirizzo**: `https://ai-49bx.onrender.com` oppure `http://127.0.0.1:8000` in locale;
   - **Chiave API**: la chiave creata in NOKK → Impostazioni → API.
4. Premi **Verifica**: deve comparire «Connessione riuscita».

## Cosa fa

- **Popup**: scrivi una domanda, scegli la modalità (`Codice`, `Studio`,
  `Analista`) e leggi la risposta. Il pulsante copia la risposta.
- **Menu contestuale**: seleziona del testo in una pagina, tasto destro →
  «Chiedi a NOKK: …». La risposta arriva come notifica del browser e resta nel
  popup.
- Le risposte lunghe vengono troncate nella notifica (900 caratteri); il testo
  completo è nel popup.

## Dove finisce la chiave

La chiave viene salvata in `chrome.storage.local`, quindi resta su questo
profilo del browser e non viene inviata a nessun sito tranne il tuo NOKK. Non
inserirla in pagine web o script condivisi: chi la conosce può usare il tuo
NOKK. Revocala da NOKK → Impostazioni → API quando non ti serve più.

L'estensione richiede i permessi `storage`, `contextMenus`, `notifications` e
l'accesso agli host `https://*` per poter parlare con qualunque istanza di NOKK
(Render, Fly o locale). Non legge il contenuto delle pagine: riceve solo il
testo che selezioni dal menu contestuale.

## Limiti

- Se in NOKK è attiva l'approvazione manuale dei comandi, una richiesta che vuole
  eseguire un comando resta in attesa: l'estensione te lo segnala e devi
  approvarla dalla pagina di NOKK.
- `POST /api/v1/chat` accetta al massimo 60 richieste al minuto per chiave.
