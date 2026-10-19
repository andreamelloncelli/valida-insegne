# silverc — validatore insegne FAI da file IGC

Analizza una traccia IGC e produce un report che dice, per ciascuno dei tre
requisiti dell'insegna (argento o oro), se e' soddisfatto, **come** e' stato
verificato e **perche'** e' stato accettato o rifiutato.

## Insegna d'argento (default)

| Requisito | Soglia | Come viene misurato |
|-----------|--------|---------------------|
| Durata | 5 h | Dallo sgancio all'atterraggio (i fix registrati da fermo a fine volo vengono scartati) |
| Distanza | 50 km | Distanza geodetica dallo sgancio a un **fix d'arrivo** scelto fra quelli della traccia (§1.2.10c) col miglior esito ufficiale, non necessariamente il più lontano; dev'essere oltre 50 km sia dallo sgancio sia dal fix d'inizio della corsa di decollo (§2.2.1a), con perdita di quota entro i limiti del §2.4.4 (1% fino a 100 km, poi 1000 m con riduzione della distanza) |
| Guadagno di quota | 1000 m | Massima differenza fra un punto alto e un punto basso **che lo precede**, entrambi dopo lo sgancio. Senza dati di taratura barometrica: quota GNSS e soglia +100 m (§2.4.6a) |

## Insegna d'oro (`--badge oro`)

| Requisito | Soglia | Come viene misurato |
|-----------|--------|---------------------|
| Durata | 5 h | identica all'argento |
| Distanza | 300 km | con dichiarazione (record C dell'IGC): il percorso dichiarato nell'ordine dichiarato e, con 1-3 virate, anche come **distanza fino a 3 virate** (§1.4.2f: ordine libero, partenza dichiarata o sgancio, arrivo dichiarato o un fix). Virate: cilindro di 500 m. Partenza e arrivo: linee di 1 km perpendicolari alla prima e all'ultima tratta, attraversate nel verso della tratta, con quota interpolata (§1.2.12, §2.4.3b). In ogni caso anche la linea retta dallo sgancio al fix d'arrivo migliore (§1.4.2d). Vale l'esito migliore (§2.2) |
| Guadagno di quota | 3000 m | stesso criterio dell'argento |

Se il file non contiene una dichiarazione, la distanza d'oro si valuta come
distanza in linea retta con partenza allo sgancio (§1.4.2d): per questa
geometria la dichiarazione non deve contenere le coordinate dei punti (§2.3). A
differenza dell'argento non si applica il vincolo dei 50 km anche dal fix di
decollo, che il §2.2.1a pone solo per la distanza d'argento.

I riferimenti `§` sono al FAI Sporting Code Section 3 — Gliding, ed. 2025
([`data/FAI_SC3_2025.pdf`](data/FAI_SC3_2025.pdf), fonte in
[`data/FONTI.md`](data/FONTI.md)).

## Controlli sul file IGC

Il report ha una sezione *Documentazione* che non incide sull'esito delle tre
prove:

- **intestazione**: nome e cognome del pilota e identificativo dell'aliante,
  cioè marche **oppure** sigla di gara (§1.1.3); il tipo di aliante, se manca,
  lo conferma l'OO (§4.3.1);
- **registratore**: *Flight Recorder* approvato IGC solo se il codice
  costruttore del record A è fra quelli approvati (`rules.RECORDERS`), il
  G-record è presente e il modello è dichiarato, altrimenti *Position
  Recorder*. Con `--recorder fr|pr` il tipo si indica a mano.
- **quota**: senza dati di taratura barometrica, con un FR come con un PR, si
  usa la quota GNSS con un margine di 100 m su tutti i requisiti di quota
  (§2.4.6a, §2.4.3c). Con `--calibrated` si usa la quota barometrica.

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
  il verdetto su durata e quota diventa `NON DETERMINABILE`. Nella pagina web lo
  stesso orario si indica nel campo *Orario di sgancio*.
- `--recorder auto|fr|pr`: tipo di registratore (default `auto`, ricavato
  dal file).
- `--motorglider`: aliante con motore (§1.2.8, §1.3.2c).
- `--internet-declaration`: il pilota ha usato una dichiarazione via internet,
  che sostituisce quella del registratore (§2.3a).
- `--calibrated`: il registratore ha dati di taratura barometrica; si usa la
  quota barometrica senza margine. Senza questa opzione quota GNSS e margine
  di 100 m (§2.4.6a).
- `--gnss-altitude`: usa la quota GNSS anche con dati di taratura, con il
  margine di 100 m.
- `--verbose`: log di dettaglio su stderr.

Codici di uscita: `0` volo che copre tutti e tre i requisiti, `1` copertura
parziale o nulla, `2` errore di lettura del file.

## Limiti noti

- Le soglie regolamentari sono raccolte in [`src/silverc/rules.py`](src/silverc/rules.py),
  ciascuna col suo paragrafo SC3. Le regole non ancora implementate sono negli
  audit [`data/AUDIT_1_GENERALE.md`](data/AUDIT_1_GENERALE.md),
  [`AUDIT_2_ARGENTO.md`](data/AUDIT_2_ARGENTO.md) e
  [`AUDIT_3_ORO.md`](data/AUDIT_3_ORO.md).
- Il **G-record non viene verificato**: la firma digitale richiede il programma
  `vali-*` del costruttore del logger. Il report lo dichiara esplicitamente.
- Per un aliante con motore va indicato `--motorglider` (o la casella nella
  pagina web): lo sgancio di un decollo autonomo diventa lo spegnimento del
  motore e le prove finiscono al suo avvio, rilevati da ENL o MOP con una
  soglia non regolamentare. Senza l'indicazione l'uso del motore è solo
  segnalato.
- Il report e' un ausilio all'analisi, non un'omologazione.

## Sviluppo

```bash
uv sync && uv run pytest -q
```

Le tracce di test sono sintetiche e generate da `test/igc_builder.py`
(rollover di mezzanotte, spike di quota, fix a terra finali, massimo di quota
che precede il minimo).

## Documentazione

- [Pubblicazione su Railway](docs/deploy-railway.md) — prerequisiti, prova
  locale con Docker, comandi di deploy e diagnostica.
- [Convenzioni di sviluppo](docs/convenzioni.md) — stile, logging, testing,
  versionamento, regole sui commit.
- [Requisiti delle insegne](REQUISITI.md) — condizioni minime delle prove.
