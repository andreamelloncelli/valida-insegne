# Insegna d'argento (Silver C) — condizioni minime

Le tre prove sono indipendenti e possono essere ottenute in **voli diversi**.
Ogni volo va documentato con una traccia IGC di un logger approvato, firmata
(G-record) e convalidata da un Osservatore Ufficiale.

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

## 1. Durata — 5 ore

- Volo di almeno **5 h 00 m** continuative.
- Il conteggio parte dallo **sgancio** (o dall'ultimo istante di volo propulso)
  e finisce all'**atterraggio**.
- Nessuna tolleranza: 4 h 59 m non è valido.

## 2. Distanza — 50 km

- Almeno **50 km** in linea retta dal punto di sgancio al punto più lontano
  raggiunto in volo.
- Il punto più lontano deve distare oltre 50 km **sia dallo sgancio sia
  dall'aeroporto di decollo**.
- **Perdita di quota** fra punto di partenza e punto d'arrivo non superiore
  all'**1% della distanza** (500 m su 50 km). Superarla invalida la prova.

## 3. Guadagno di quota — 1000 m

- Almeno **1000 m** fra un **punto basso** e un **punto alto successivo**,
  entrambi dopo lo sgancio.
- Non è la differenza fra quota massima e minima del volo: il punto basso deve
  precedere quello alto.
- Si usa la **quota barometrica**. Con la sola quota GNSS (ammessa per Silver e
  Gold) tutti i requisiti di quota vanno maggiorati di **100 m** di margine
  d'errore.

---

> Le soglie qui riportate provengono da fonti secondarie e vanno verificate
> sull'edizione in vigore del Sporting Code prima di una richiesta ufficiale.

## Fonti

- [FAI — Badges and Diplomas](https://www.fai.org/page/badges-and-diplomas)
- [FAI Sporting Code Section 3 — Gliding, ed. 2025](https://www.fai.org/sites/default/files/document/file/sc3_2025.pdf)
- [Sporting Code Section 3, Annex C — Official Observer & Pilot Guide](https://fai.org/sites/default/files/sc3c_-_2020.pdf)
- [IGC — Documenti e pubblicazioni](https://www.fai.org/igc-documents)
