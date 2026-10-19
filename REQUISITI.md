# Insegne d'argento e d'oro — condizioni minime

Per entrambe le insegne le tre prove sono indipendenti e possono essere
ottenute in **voli diversi**.
Ogni volo va documentato con una traccia IGC di un logger approvato, firmata
(G-record) e convalidata da un Osservatore Ufficiale.

## Controlli sul file IGC

- **Intestazione**: nome **e** cognome del pilota (HFPLT) e identificativo
  dell'aliante: marche (HFGID) **oppure** sigla di gara (HFCID) (§1.1.3). Il
  tipo di aliante (HFGTY) non fa parte della dichiarazione: se manca lo
  conferma l'OO al decollo (§4.3.1).
- **Registratore**: si distingue fra *Flight Recorder* approvato IGC e
  semplice *Position Recorder* (§2.2.6a: entrambi ammessi per Argento e Oro).
  È considerato Flight Recorder solo un logger con codice costruttore
  approvato nel record A, G-record presente e modello dichiarato (HFFTY); in
  ogni altro caso, anche con una descrizione vaga, si ricade sul Position
  Recorder, l'ipotesi più severa. Il modello va comunque confrontato con la
  [lista FAI dei registratori approvati](https://www.fai.org/page/igc-approved-flight-recorders).
  Il tipo si può indicare a mano quando è noto.

## Come si individua lo sgancio

Durata e guadagno di quota si contano dallo sgancio, ma **l'IGC non lo
registra**, viene dedotto con questa euristica:

1. Trova il decollo: il primo fix da cui l'aliante si allontana di oltre 40 m
   entro 60 secondi (criterio sullo spostamento netto, non sulla velocità tra
   fix consecutivi, che a 1 Hz è dominata dal rumore GPS).
2. Da lì scorre la traccia tenendo il massimo di quota corrente.
3. Il primo istante in cui la quota scende di 50 m sotto quel massimo, lo
   sgancio è il punto del massimo.

Non è una regola FAI ma una stima: il report la dichiara sempre con la sua
confidenza.

## Insegna d'argento (Silver C)

### 1. Durata — 5 ore

- Volo di almeno **5 h 00 m** continuative.
- Il conteggio parte dallo **sgancio** (o dall'ultimo istante di volo propulso)
  e finisce all'**atterraggio**.
- Nessuna tolleranza: 4 h 59 m non è valido.

### 2. Distanza — 50 km

- Almeno **50 km** in linea retta dal punto di sgancio a un **fix d'arrivo**
  scelto dopo il volo fra quelli registrati (§1.2.10c), non necessariamente il
  più lontano: conta l'esito ufficiale, perdita di quota compresa.
- Lo stesso fix d'arrivo deve distare oltre 50 km **sia dallo sgancio sia dal
  fix d'inizio della corsa di decollo** (§2.2.1a).
- La distanza dovrebbe essere volata senza la guida di un altro pilota
  (§2.2.1a, testo informativo): non è verificabile dalla traccia.
- **Perdita di quota** fra punto di partenza e punto d'arrivo (§2.4.4): fino a
  100 km non oltre l'**1% della distanza** (500 m su 50 km), altrimenti la
  prova non è valida; oltre i 100 km il limite è **1000 m** e ogni metro in
  eccesso toglie 100 m alla distanza. Con la quota GNSS entrambi i limiti
  scendono di 100 m.

### 3. Guadagno di quota — 1000 m

- Almeno **1000 m** fra un **punto basso** e un **punto alto successivo**,
  entrambi dopo lo sgancio.
- Non è la differenza fra quota massima e minima del volo: il punto basso deve
  precedere quello alto.
- Con **dati di taratura barometrica** si usa la **quota barometrica** e
  basta la soglia prevista. Senza taratura, con un Flight Recorder come con un
  Position Recorder, si usa la **quota GNSS** e la soglia sale di **100 m**
  (1100 m invece di 1000 m, §2.4.6a, §2.4.3c).

## Insegna d'oro (Gold C)

Presuppone l'insegna d'argento già conseguita.

### 1. Durata — 5 ore

- Identica alla prova d'argento: lo stesso volo di 5 h vale per entrambe le
  insegne, non va ripetuto.

### 2. Distanza — 300 km

- Almeno **300 km**. Due strade:
  - **linea retta con partenza allo sgancio**: senza coordinate dichiarate
    (§1.4.2d, §2.3), fino al fix d'arrivo con la distanza ufficiale migliore;
  - **percorso dichiarato prima del volo** (meta, fino a 3 punti di virata,
    andata e ritorno o triangolo): i punti rivendicati vanno effettivamente
    volati, un tema dichiarato ma non percorso non vale;
  - con 1-3 virate dichiarate il volo vale anche come **distanza fino a 3
    virate** (§1.4.2f): virate in qualsiasi ordine, anche solo alcune delle
    dichiarate, partenza dichiarata o sgancio, arrivo dichiarato o un fix.
    Per un'insegna non è mai inferiore ad andata e ritorno o triangolo;
  - virate: settore a 90° di raggio illimitato o cilindro di 500 m; ogni
    virata presa solo col cilindro toglie 1 km (§1.2.6, §1.3.6). Partenza e
    arrivo: linee di 1 km perpendicolari alla tratta (§1.2.12);
  - ogni percorso dichiarato vale anche come linea retta dalla partenza
    dichiarata a un fix (§1.4.2d);
  - vale la geometria con l'esito migliore, linea retta compresa (§2.2). Le
    distanze libere (§1.4.2i–l) valgono solo per i record.
- **Perdita di quota** oltre i 100 km (§2.4.4): limite di **1000 m** (900 m
  con quota GNSS); ogni metro in eccesso toglie 100 m alla distanza. 2000 m di
  perdita su 300 km lasciano 200 km.

### 3. Guadagno di quota — 3000 m

- Almeno **3000 m** fra un punto basso e un punto alto successivo, con lo
  stesso criterio della prova d'argento.
- Senza dati di taratura: quota GNSS e soglia di 3100 m.

---

> Le soglie qui riportate provengono da fonti secondarie e vanno verificate
> sull'edizione in vigore del Sporting Code prima di una richiesta ufficiale.

## Fonti

- [FAI — Badges and Diplomas](https://www.fai.org/page/badges-and-diplomas)
- [FAI Sporting Code Section 3 — Gliding, ed. 2025](https://www.fai.org/sites/default/files/document/file/sc3_2025.pdf)
  — copia locale di riferimento in `data/FAI_SC3_2025.pdf`, scaricata da <https://naa.aero/wp-content/uploads/2026/03/sc3_2025.pdf>
- [Sporting Code Section 3, Annex C — Official Observer & Pilot Guide](https://fai.org/sites/default/files/sc3c_-_2020.pdf)
- [IGC — Documenti e pubblicazioni](https://www.fai.org/igc-documents)
