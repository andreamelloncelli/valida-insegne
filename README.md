# silverc — validatore insegna d'argento FAI da file IGC

Analizza una traccia IGC e produce un report che dice, per ciascuno dei tre
requisiti dell'insegna d'argento (Silver C), se e' soddisfatto, **come** e'
stato verificato e **perche'** e' stato accettato o rifiutato.

## Requisiti verificati

| Requisito | Soglia | Come viene misurato |
|-----------|--------|---------------------|
| Durata | 5 h | Dallo sgancio all'atterraggio (i fix registrati da fermo a fine volo vengono scartati) |
| Distanza | 50 km | Distanza geodetica dallo sgancio al **punto più lontano** della traccia (non l'atterraggio); dev'essere oltre 50 km sia dallo sgancio sia dall'aeroporto di decollo, con perdita di quota ≤ 1% |
| Guadagno di quota | 1000 m | Massima differenza fra un punto alto e un punto basso **che lo precede**, entrambi dopo lo sgancio |

I tre requisiti possono essere ottenuti in **voli diversi**: il report li valuta
in modo indipendente e indica quali sono coperti dalla traccia in esame.

## Uso

```bash
uv run silverc volo.igc
```

Opzioni utili:

```bash
uv run silverc volo.igc --release-time 11:42:30 --verbose
```

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
