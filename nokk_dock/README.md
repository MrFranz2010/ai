# NOKK Dock

Barra da scrivania per NOKK: una piccola dock ancorata al bordo dello schermo,
sempre sopra le altre finestre, che si espande al passaggio del mouse e mostra
musica, meteo, ora e un pulsante per chiedere a NOKK cosa c'è sullo schermo.

Il dock è un programma della variante **desktop**: vive su `main`, non viene
servito dall'hosting. Non modifica il backend: usa l'API HTTP pubblica
(`/api/v1/*`), quindi funziona sia contro `http://127.0.0.1:8000` sia contro
un'istanza su Render/Fly.

## Cosa fa

- **Dock personalizzabile**: quattro bordi (basso, alto, sinistra, destra),
  posizione lungo il bordo, spessore, lunghezza, distanza dal bordo, opacità,
  scala, nascondiglio automatico.
- **Forma «notch»** (predefinita): una pillola compatta in alto al centro, con
  ora e stato di NOKK, che si srotola nel pannello completo al passaggio del
  mouse. Chi preferisce la barra classica sceglie `dock.style = "dock"`.
- **Espansione al passaggio del mouse**: molla smorzata e rigida (non
  interpolazione lineare), ~0,2 s dall'apertura alla posa, con ritardo di
  apertura e chiusura regolabili.
- **Ingrandimento magnetico**: i widget vicini al cursore si allargano e il
  contenuto cresce con loro; l'intensità è regolabile (`dock.magnify`).
- **Etichette al passaggio del mouse**: una pillola compatta spiega ogni widget
  e mostra brano o città correnti (`dock.show_labels`).
- **Widget musicali** via MPRIS (`playerctl`): copertina del brano, brano,
  artista, barra di avanzamento colorata con l'accento estratto dalla
  copertina, precedente / play-pausa / successivo.
- **Meteo e ora**: Open-Meteo senza chiave API (basta il nome della città),
  aggiornamento periodico e data/ora locali.
- **Stato di NOKK**: pallino verde/ambra e testo «Connesso / Non raggiungibile».
- **Cattura schermo → NOKK**: la scorciatoia cattura lo schermo, apre la
  finestra «Chiedi a NOKK» con l'immagine allegata e mostra la risposta. Si può
  anche chiedere senza screenshot, oppure continuare la conversazione.
- **Temi**: cinque preset (NOKK, Midnight, Graphite, Mint, Sand), colore accento,
  angoli e dimensione; tutto modificabile anche dal pannello impostazioni.

L'aspetto segue le notch moderne come **Nusa**: pillola compatta agganciata in
alto al centro che si apre con una molla rapida, superfici in vetro (riflesso
superiore, ombra interna, alone esterno), copertina del brano con accento
cromatico derivato dall'immagine e ingrandimento magnetico sotto il puntatore.

## Requisiti

Funziona su **Linux** e **Windows** con lo stesso codice: cambiano solo i
backend di scorciatoia, cattura e musica.

- Python 3.10 o successivo con **tkinter**.
  - Linux: `sudo apt install python3-tk`.
  - Windows: l'installer di <https://www.python.org/downloads/windows/> include
    già Tcl/Tk; basta spuntare «Add python.exe to PATH».
- Una sessione grafica (X11/Wayland su Linux, desktop Windows 10 o 11).
- Consigliati su Linux:
  - `playerctl` per il widget musicale (`sudo apt install playerctl`);
  - `grim` (Wayland) oppure `scrot` / `gnome-screenshot` / `spectacle` (X11) per
    la cattura;
  - `Pillow` per ridurre automaticamente gli screenshot oltre i 4 MB e per
    ritagliare le copertine con gli angoli arrotondati:
    `python -m pip install -r requirements-dock.txt`.

Senza Pillow la copertina compare solo se il player fornisce già un PNG/GIF e
l'accento resta quello del tema; tutto il resto funziona ugualmente.

Su Windows non serve installare nulla: la cattura usa PowerShell con
`System.Drawing` e i controlli musicali usano i tasti multimediali di sistema
(`VK_MEDIA_*`), quindi funzionano con Spotify, browser, Groove e qualsiasi
altro player collegato alla sessione multimediale. I titoli dei brani arrivano
dai metadati WinRT; se Windows non li espone i controlli restano attivi e il
widget lo segnala.

Nessuno di questi strumenti è obbligatorio: se manca qualcosa il widget lo dice
invece di bloccare il dock.

## Avvio

```bash
python -m pip install -r requirements.txt      # dipendenze di NOKK
python linux_start.py                          # NOKK in un terminale
python dock_start.py                           # il dock in un altro
```

Poi apri **Impostazioni del dock** (ingranaggio o tasto destro) e incolla
l'indirizzo e la chiave API creata in NOKK → Impostazioni → API.

Su Windows, dal Prompt dei comandi o da PowerShell:

```bat
python -m pip install -r requirements.txt
python linux_start.py
python dock_start.py
```

Per non tenere aperta la console puoi avviare il dock con `pythonw dock_start.py`
e creare un collegamento nella cartella Esecuzione automatica
(`shell:startup`) per averlo all'accensione.

Su Windows il dock si ancora ai bordi del monitor primario, usa la trasparenza
per gli angoli arrotondati e attiva la consapevolezza DPI così testo e icone
restano nitidi con il ridimensionamento dello schermo al 125% o 150%.

## Scorciatoia per lo screenshot

1. Apri il pannello impostazioni, sezione *Cattura schermo*, e scegli la
   combinazione (predefinita `ctrl+alt+n`).
2. Su **Windows** la scorciatoia viene registrata con `RegisterHotKey`: funziona
   da qualunque applicazione e il tasto non arriva alle altre finestre.
3. Su **X11** la scorciatoia viene registrata subito dal dock.
4. Su **Wayland** nessun programma può catturare tasti a livello globale: assegna
   a `python dock_start.py --capture` la scorciatoia che preferisci nelle
   impostazioni del desktop (GNOME: Impostazioni → Tastiera → Scorciatoie
   personalizzate; KDE: Impostazioni di sistema → Scorciatoie).

Dal terminale funzionano anche:

```bash
python dock_start.py --capture      # cattura e chiedi (dock già avviato)
python dock_start.py --ask "Riassumi cosa vedi"
python dock_start.py --position top # sposta il dock e salva
python dock_start.py --settings     # apre le impostazioni del dock attivo
python dock_start.py --check        # diagnostica ambiente e collegamento
python dock_start.py --reset        # ripristina i valori predefiniti
```

## Configurazione

- Linux: `$XDG_CONFIG_HOME/nokk/dock.json` (in genere `~/.config/nokk/dock.json`).
- Windows: `%APPDATA%\nokk\dock.json`.

Il file viene creato al primo salvataggio con permessi riservati all'utente. Si
può indicare un altro percorso con `--config FILE` o con la variabile
`NOKK_DOCK_CONFIG`.

| Chiave | Valore predefinito | Significato |
| --- | --- | --- |
| `nokk.base_url` | `http://127.0.0.1:8000` | indirizzo di NOKK |
| `nokk.api_key` | vuota | chiave `nokk_…` dell'API |
| `nokk.mode` | vuota | `codice`, `studio`, `analista` o vuota |
| `dock.position` | `bottom` | `bottom`, `top`, `left`, `right` |
| `dock.offset` | `0.5` | posizione lungo il bordo (0–1) |
| `dock.thickness` | `60` | spessore del dock in pixel |
| `dock.length` | `660` | lunghezza massima del dock |
| `dock.auto_hide` | `false` | nasconde il dock quando il mouse è altrove |
| `dock.opacity` | `1.0` | trasparenza della finestra |
| `dock.style` | `notch` | `notch` (pillola in alto al centro) o `dock` (barra sul bordo) |
| `dock.magnify` | `1.25` | ingrandimento massimo del widget sotto il cursore (1.0–1.6) |
| `dock.show_labels` | `true` | etichetta al passaggio del mouse |
| `theme.preset` | `nokk` | `nokk`, `midnight`, `graphite`, `mint`, `sand` |
| `theme.accent` | vuoto | colore accento `#rrggbb` (vuoto = preset) |
| `theme.scale` | `1.0` | dimensione complessiva |
| `widgets` | tutti | ordine e widget visibili |
| `weather.city` | vuota | città per il meteo |
| `weather.units` | `metric` | `metric` o `imperial` |
| `music.player` | vuoto | nome del player MPRIS da controllare |
| `capture.shortcut` | `ctrl+alt+n` | scorciatoia della cattura |
| `capture.scale` | `1.0` | riduzione dello screenshot alla fonte |
| `ask.prompt` | testo italiano | domanda proposta dopo lo screenshot |

I nomi dei widget sono `music`, `weather`, `clock`, `nokk`, `capture`,
`settings`.

## Come parla con NOKK

Il dock usa gli endpoint documentati in `API.md`:

1. `GET /api/v1/health` per il pallino di stato;
2. `POST /api/v1/chat` con `messages` (e `attachments` di tipo `image` per lo
   screenshot);
3. `GET /api/v1/jobs/<id>` in polling finché il job non è `complete`.

L'immagine viene inviata in base64 come già fa l'interfaccia web: nessuna rotta
nuova, nessuna modifica al backend. Se NOKK attende l'approvazione di un comando
il dock lo segnala e invita a confermare dalla pagina web.

La chiave API resta nel file di configurazione locale con permessi `600`, non
viene mai scritta nei log e non viene mostrata in chiaro nel pannello.

## Risoluzione dei problemi

- **Il dock non parte**: `python dock_start.py --check` elenca tkinter, sessione
  grafica, strumenti di cattura, `playerctl`/PowerShell, backend della
  scorciatoia, stato del dock e raggiungibilità di NOKK.
- **Windows: «Failed to execute script» o finestra senza angoli**: aggiorna
  Python e verifica che il servizio «Client: Desktop» non sia disattivato da
  criteri di gruppo; il dock richiede una sessione desktop interattiva.
- **Windows: nessun titolo nel widget musica**: i metadati WinRT non sono
  disponibili per quel player; i pulsanti funzionano comunque con i tasti
  multimediali.
- **Il widget musicale dice «Nessun player attivo»**: avvia la musica in Spotify,
  Firefox, VLC o un altro player MPRIS; verifica con `playerctl status`.
- **La cattura non funziona su Wayland**: installa `grim`; su GNOME Wayland
  `gnome-screenshot` cattura solo via XWayland.
- **La schermata è troppo grande per NOKK**: installa Pillow, il dock riduce lo
  scatto sotto i 4 MB mantenendo leggibile il testo.
- **La finestra non resta sopra le altre**: attiva *Sempre sopra le finestre* e
  verifica che il compositor sia attivo (`-alpha` e `-type dock` richiedono un
  window manager X11 o un compositor Wayland).

## Test

```bash
python -m unittest discover -s tests -p "test_dock*.py" -v
python -m unittest discover -s tests
```

I test coprono configurazione, geometria del notch e del dock, ingrandimento magnetico,
molla dell'animazione, copertine (download, cache, miniature, accento), temi,
client HTTP, cattura, meteo, MPRIS, scorciatoia, IPC e icone. Non aprono
finestre: `tests/test_dock_drawing.py` sostituisce Tk con uno stub e verifica
che i widget vengano davvero disegnati, anche con l'ingrandimento attivo.
