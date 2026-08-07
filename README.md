# silverc — validatore insegne FAI da file IGC

Analizza una traccia IGC e produce un report che dice, per ciascuno dei tre
requisiti dell'insegna (argento o oro), se e' soddisfatto, **come** e' stato
verificato e **perche'** e' stato accettato o rifiutato.

## Insegna d'argento (default)

| Requisito | Soglia | Come viene misurato |
|-----------|--------|---------------------|
| Durata | 5 h | Dallo sgancio all'atterraggio (i fix registrati da fermo a fine volo vengono scartati) |
| Distanza | 50 km | Distanza geodetica dallo sgancio al **punto più lontano** della traccia (non l'atterraggio); dev'essere oltre 50 km sia dallo sgancio sia dall'aeroporto di decollo, con perdita di quota ≤ 1% |
| Guadagno di quota | 1000 m | Massima differenza fra un punto alto e un punto basso **che lo precede**, entrambi dopo lo sgancio |

## Insegna d'oro (`--badge oro`)

| Requisito | Soglia | Come viene misurato |
|-----------|--------|---------------------|
| Durata | 5 h | identica all'argento |
| Distanza | 300 km | somma delle tratte del **percorso dichiarato** (record C dell'IGC); ogni punto va toccato **nell'ordine dichiarato** entrando nella sua zona di osservazione (500 m sulle virate, 1 km su partenza e arrivo) |
| Guadagno di quota | 3000 m | stesso criterio dell'argento |

Se il file non contiene una dichiarazione, la distanza d'oro e'
`NON DETERMINABILE`: va dichiarata prima del volo.

I tre requisiti possono essere ottenuti in **voli diversi**: il report li valuta
in modo indipendente e indica quali sono coperti dalla traccia in esame.

## Uso

```bash
uv run silverc volo.igc
```

Opzioni utili:

```bash
uv run silverc volo.igc --badge oro --release-time 11:42:30 --verbose
```

- `--badge argento|oro`: insegna da verificare (default `argento`).
- `--release-time HH:MM:SS` (UTC): l'IGC **non registra lo sgancio**. Senza
  questo parametro il programma lo stima dalla traccia (fine della salita
  continua iniziale) e lo dichiara nel report; se la stima e' poco affidabile
  il verdetto su durata e quota diventa `NON DETERMINABILE`.
- `--gnss-altitude`: usa la quota GNSS al posto di quella barometrica,
  applicando la penalizzazione di 100 m prevista per le insegne Silver/Gold.
- `--verbose`: log di dettaglio su stderr.

Codici di uscita: `0` volo che copre tutti e tre i requisiti, `1` copertura
parziale o nulla, `2` errore di lettura del file.

## Limiti noti

- Le soglie regolamentari sono raccolte in [`src/silverc/rules.py`](src/silverc/rules.py)
  e provengono da **fonti secondarie**: il PDF ufficiale del FAI Sporting Code
  Section 3 non era raggiungibile durante lo sviluppo. Ogni costante e' marcata
  `TO VERIFY` con il riferimento presunto.
- Il **G-record non viene verificato**: la firma digitale richiede il programma
  `vali-*` del costruttore del logger. Il report lo dichiara esplicitamente.
- L'euristica di sgancio non distingue un decollo autonomo a motore da un
  traino; in presenza di estensione ENL il report segnala l'eventuale uso del
  motore.
- Il report e' un ausilio all'analisi, non un'omologazione.

## Sviluppo

```bash
uv sync && uv run pytest -q
```

Le tracce di test sono sintetiche e generate da `test/igc_builder.py`
(rollover di mezzanotte, spike di quota, fix a terra finali, massimo di quota
che precede il minimo).

## Pubblicazione su Railway

L'app e' containerizzata: Railway rileva il `Dockerfile` e la configurazione in
`railway.json` (healthcheck su `/_stcore/health`). La porta arriva dalla
variabile d'ambiente `PORT`, assegnata da Railway a runtime.

Prova locale, identica a quella che gira in produzione:

```bash
make docker-run
```

Deploy dalla cartella corrente, senza bisogno di un remote git:

```bash
railway login && railway init && railway up
```

In alternativa si collega un repo GitHub dalla dashboard Railway e ogni push
fa il deploy.

Nessuna variabile d'ambiente da configurare: l'app non usa segreti e non
persiste i file caricati.
