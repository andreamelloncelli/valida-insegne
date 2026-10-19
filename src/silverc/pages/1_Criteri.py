"""Pagina informativa: criteri di valutazione delle insegne FAI."""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Criteri di valutazione", page_icon="📋")
st.title("Criteri di valutazione")

st.info(
    "Le soglie qui riportate provengono da fonti secondarie e vanno "
    "verificate sull'edizione in vigore del Sporting Code prima di una "
    "richiesta ufficiale di omologazione."
)

st.markdown(
    """
Per entrambe le insegne le tre prove sono indipendenti e possono essere
ottenute in **voli diversi**. Ogni volo va documentato con una traccia IGC
di un logger approvato, firmata (G-record) e convalidata da un Osservatore
Ufficiale.

## Controlli sul file IGC

- **Intestazione**: nome **e** cognome del pilota (HFPLT), tipo di aliante
  riconoscibile (HFGTY) e marche (HFGID). La sigla di gara (HFCID) è
  facoltativa.
- **Registratore**: si distingue fra *Flight Recorder* approvato IGC e
  semplice *Position Recorder* (§2.2.6a: entrambi ammessi per Argento e Oro).
  È considerato Flight Recorder solo un logger con codice costruttore
  approvato nel record A, G-record presente e modello dichiarato (HFFTY); in
  ogni altro caso, anche con una descrizione vaga, si ricade sul Position
  Recorder, l'ipotesi più severa. Il modello va comunque confrontato con la
  [lista FAI dei registratori approvati](https://www.fai.org/page/igc-approved-flight-recorders).
  Il tipo si può indicare a mano quando è noto.

## Come si individua lo sgancio

Durata e guadagno di quota si contano dallo sgancio, ma l'IGC non lo
registra: viene dedotto con questa euristica.

1. Trova il decollo: il primo fix da cui l'aliante si allontana di oltre
   40 m entro 60 secondi (spostamento netto, non velocità tra fix
   consecutivi, dominata a 1 Hz dal rumore GPS).
2. Da lì scorre la traccia tenendo il massimo di quota corrente.
3. Il primo istante in cui la quota scende di 50 m sotto quel massimo,
   lo sgancio è il punto del massimo.

Non è una regola FAI ma una stima: il report la dichiara sempre con la sua
confidenza.

## Insegna d'argento (Silver C)

### 1. Durata — 5 ore
- Volo di almeno **5 h 00 m** continuative.
- Il conteggio parte dallo **sgancio** (o dall'ultimo istante di volo
  propulso) e finisce all'**atterraggio**.
- Nessuna tolleranza: 4 h 59 m non è valido.

### 2. Distanza — 50 km
- Almeno **50 km** in linea retta dal punto di sgancio al punto più
  lontano raggiunto in volo.
- Lo stesso fix d'arrivo deve distare oltre 50 km **sia dallo sgancio sia
  dal fix d'inizio della corsa di decollo** (§2.2.1a). Se il punto più
  lontano dallo sgancio non basta, si cerca il fix più lontano da entrambi.
- La distanza dovrebbe essere volata senza la guida di un altro pilota
  (§2.2.1a, testo informativo): non è verificabile dalla traccia.
- **Perdita di quota** fra punto di partenza e punto d'arrivo (§2.4.4):
  fino a 100 km non oltre l'**1% della distanza** (500 m su 50 km),
  altrimenti la prova non è valida; oltre i 100 km il limite è
  **1000 m** e ogni metro in eccesso toglie 100 m alla distanza. Con la
  quota GNSS entrambi i limiti scendono di 100 m.

### 3. Guadagno di quota — 1000 m
- Almeno **1000 m** fra un **punto basso** e un **punto alto
  successivo**, entrambi dopo lo sgancio.
- Non è la differenza fra quota massima e minima del volo: il punto
  basso deve precedere quello alto.
- Con un **Flight Recorder** approvato si usa la **quota barometrica** e
  basta la soglia prevista. Con un **Position Recorder** si usa la **quota
  GNSS** e la soglia sale di **100 m** (1100 m invece di 1000 m).

## Insegna d'oro (Gold C)

Presuppone l'insegna d'argento già conseguita.

### 1. Durata — 5 ore
- Identica alla prova d'argento: lo stesso volo di 5 h vale per entrambe
  le insegne, non va ripetuto.

### 2. Distanza — 300 km
- Almeno **300 km**, o in **linea retta con partenza allo sgancio**
  (senza coordinate dichiarate, §1.4.2d e §2.3), oppure su un
  percorso **dichiarato prima del volo**, con un
  massimo di 3 punti di virata (linea retta, andata e ritorno o
  triangolo).
- Ogni punto dichiarato va effettivamente volato: un tema dichiarato
  correttamente ma non percorso non vale. Il volo vale comunque come
  linea retta dallo sgancio, se ne soddisfa i requisiti (§2.2).
- **Perdita di quota** oltre i 100 km (§2.4.4): limite di **1000 m**
  (900 m con quota GNSS); ogni metro in eccesso toglie 100 m alla
  distanza. 2000 m di perdita su 300 km lasciano 200 km.

### 3. Guadagno di quota — 3000 m
- Almeno **3000 m** fra un punto basso e un punto alto successivo, con
  lo stesso criterio della prova d'argento.
- Con un Position Recorder: quota GNSS e soglia di 3100 m.

## Fonti

- [FAI — Badges and Diplomas](https://www.fai.org/page/badges-and-diplomas)
- [FAI Sporting Code Section 3 — Gliding, ed. 2025](https://www.fai.org/sites/default/files/document/file/sc3_2025.pdf)
- [Sporting Code Section 3, Annex C — Official Observer & Pilot Guide](https://fai.org/sites/default/files/sc3c_-_2020.pdf)
- [IGC — Documenti e pubblicazioni](https://www.fai.org/igc-documents)
"""
)
