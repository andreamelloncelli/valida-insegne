# silverc — validatore insegne FAI da file IGC

Analizza una traccia IGC e produce un report che dice, per ciascuno dei tre
requisiti dell'insegna (argento o oro), se e' soddisfatto, **come** e' stato
verificato e **perche'** e' stato accettato o rifiutato.

## Insegna d'argento (default)

| Requisito | Soglia | Come viene misurato |
|-----------|--------|---------------------|
| Durata | 5 h | Dallo sgancio all'atterraggio (i fix registrati da fermo a fine volo vengono scartati) |
| Distanza | 50 km | Distanza geodetica dallo sgancio al **punto più lontano** della traccia (non l'atterraggio); dev'essere oltre 50 km sia dallo sgancio sia dal fix d'inizio della corsa di decollo (§2.2.1a), con perdita di quota entro i limiti del §2.4.4 (1% fino a 100 km, poi 1000 m con riduzione della distanza) |
| Guadagno di quota | 1000 m | Massima differenza fra un punto alto e un punto basso **che lo precede**, entrambi dopo lo sgancio. Con un Position Recorder: quota GNSS e soglia +100 m |

## Insegna d'oro (`--badge oro`)

| Requisito | Soglia | Come viene misurato |
|-----------|--------|---------------------|
| Durata | 5 h | identica all'argento |
| Distanza | 300 km | con dichiarazione (record C dell'IGC): somma delle tratte del **percorso dichiarato**, ogni punto toccato **nell'ordine dichiarato** entrando nella sua zona di osservazione (500 m sulle virate, 1 km su partenza e arrivo). Senza dichiarazione, o se il percorso dichiarato non e' completato: distanza in linea retta dallo sgancio al punto piu' lontano (§2.2) |
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

- **intestazione**: nome e cognome del pilota, tipo di aliante e marche; la
  sigla di gara è facoltativa;
- **registratore**: *Flight Recorder* approvato IGC solo se il codice
  costruttore del record A è fra quelli approvati (`rules.RECORDERS`), il
  G-record è presente e il modello è dichiarato. Altrimenti *Position
  Recorder*: quota GNSS e soglia del guadagno di quota maggiorata di 100 m.
  Con `--recorder fr|pr` il tipo si indica a mano.

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
- `--recorder auto|fr|pr`: tipo di registratore (default `auto`, ricavato
  dal file). Con `pr` si usa la quota GNSS e la soglia di quota sale di 100 m.
- `--gnss-altitude`: usa la quota GNSS anche con un Flight Recorder,
  applicando la stessa maggiorazione di 100 m.
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

## Documentazione

- [Pubblicazione su Railway](docs/deploy-railway.md) — prerequisiti, prova
  locale con Docker, comandi di deploy e diagnostica.
- [Convenzioni di sviluppo](docs/convenzioni.md) — stile, logging, testing,
  versionamento, regole sui commit.
- [Requisiti delle insegne](REQUISITI.md) — condizioni minime delle prove.
