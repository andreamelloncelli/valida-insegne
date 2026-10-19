# Audit codice vs. Regolamento Insegne FAI — Volo a Vela (ed. 1° novembre 2025)

Confronto fra il regolamento in `data/2025 - 1. Volo a Vela - REGOLAMENTO INSEGNE FAI.pdf`
e l'implementazione in `src/silverc/` + `test/`.

## Sintesi

Le tre soglie base (5 h, 50 km, 1000 m / 300 km, 3000 m) sono corrette e confermate
dagli artt. 5.1 e 6.1. Le lacune stanno tutte nelle **regole di percorso** (artt. 13–17),
dove il codice è in alcuni punti più severo del regolamento e in altri più permissivo.

## Difetti che producono verdetti sbagliati

### 1. Perdita di quota per voli > 100 km: regola sbagliata (art. 17.1) — impatta l'Oro
`validator.check_declared_distance` e `check_distance` applicano sempre
`max_loss = distanza × 1%` e in caso di superamento invalidano la prova.
Il regolamento distingue:
- **≤ 100 km** (art. 17.2): perdita > 1% ⇒ prova **non valida** — quello che fa il codice, corretto per l'Argento.
- **> 100 km** (art. 17.1): il limite assoluto è **1000 m** e il superamento **non invalida**:
  la distanza valida diventa `volata − 100 × eccedenza`.

Sull'Oro il codice usa quindi una soglia di 3000 m invece di 1000 m (troppo permissivo)
e, quando scatta, boccia invece di penalizzare (troppo severo). Nessun test copre il caso.
Riguarda anche l'**Argento**: `check_distance` non ramifica sulla distanza, quindi un volo
d'argento di 130 km viene giudicato con l'1% (1300 m) invece del limite assoluto di 1000 m
con penalizzazione dell'art. 17.1.

### 2. Ordine dei punti di virata: vincolo applicato a tutte le geometrie (art. 13.4)
`analysis.verify_declared_task` avanza un cursore e pretende l'ordine dichiarato;
`check_declared_distance` boccia se anche un solo punto non è raggiunto.
Art. 13.4 — **e solo l'art. 13.4**, cioè la geometria «distanza con un massimo di 3 punti
di virata» — dice: «I punti di Virata dichiarati possono essere sorvolati in qualsiasi
sequenza, indipendentemente dall'ordine indicato nella dichiarazione, e **non è necessario
utilizzarli tutti**». Su andata e ritorno (13.5) e triangolo (13.6) la sequenza resta
vincolata: è il percorso chiuso stesso a definirla.
Il codice applica il vincolo d'ordine indistintamente e quindi boccia voli 13.4 validi;
`test/test_gold.py:124` (`test_turnpoints_must_be_in_declared_order`) **codifica il
comportamento sbagliato per quella geometria**.
Corollari mancanti: se un punto non è usato, la distanza ufficiale va ricalcolata sul
percorso effettivamente volato; e l'art. 13.4 ha una regola di quota propria — l'arrivo
può differire da quello dichiarato «purché la perdita di quota rispetto all'effettiva
partenza sia inferiore a 1000 metri», distinta dall'art. 17.
**Dipendenza**: non implementabile prima della classificazione delle geometrie di percorso
(vedi «Lacune di copertura»), perché la regola va applicata solo alla geometria 13.4.

### 3. Riduzione di 0,5 km per ogni ZO "barattolo" intersecata (art. 15.2) — assente
La distanza d'oro è la somma delle tratte fra i punti dichiarati, senza alcuna riduzione.
Il regolamento impone di togliere 0,5 km a ciascun lato per ogni ZO cilindrica
intersecata da quel lato. Un percorso dichiarato di 300,5 km risulta oggi SODDISFATTO
quando la distanza ufficiale sarebbe 299,5 km.
**Da rilasciare insieme al punto 5**: la riduzione vale solo per la ZO «barattolo». Se il
pilota usa il settore FAI non si applica; implementarla senza implementare il settore
sotto-crediterebbe sistematicamente le virate volate a settore.

### 4. Zone di partenza/arrivo: 1 km di raggio invece di una linea da 1 km (artt. 14.1b, 16.2c)
`PARAMS.start_finish_zone_radius_m = 1000` modella un cilindro di raggio 1 km.
Il regolamento prevede una **linea** perpendicolare alla rotta di **lunghezza totale 1 km**
(quindi 500 m per lato) da attraversare. Il codice accetta passaggi che il regolamento
non ammette. Manca inoltre, **sul solo percorso dichiarato**, il caso 16.2b (punto d'arrivo
scelto dopo il volo fra i fix registrati: `check_distance` lo fa già per l'Argento, ma
`check_declared_distance` no) e il vincolo 16 N.B. (nei percorsi chiusi arrivo ≡ partenza).

### 5. Settore FAI 90° non implementato (art. 15.1a)
È prevista solo la ZO "barattolo" r = 0,5 km. Il settore di 90° **senza limiti di
distanza** sulla bisettrice è un'alternativa legittima e molto più ampia: voli validi
vengono bocciati. (Il commento in `rules.py:85-86` parla di «settore FAI di 90 gradi e
raggio 3 km»: il raggio 3 km non compare nel regolamento, il settore è illimitato.)

### 6. Distanza d'Oro senza dichiarazione: NON DETERMINABILE invece che ammessa (art. 13.2) — ✅ CORRETTO
~~`GOLD.requires_declared_task = True` e `check_declared_distance` restituivano
`NON DETERMINABILE` in assenza di record C. Art. 13.2: la distanza in linea retta
**con partenza allo sgancio non richiede dichiarazione pre-volo** ed è esplicitamente
«utilizzabile per l'Insegna d'Oro». Un 300 km in linea retta dallo sgancio va valutato
con la stessa logica dell'Argento (`check_distance` con soglia 300 km).~~

**Risolto**: `validate_badge` instrada su `check_declared_distance` solo se la traccia
contiene davvero una dichiarazione, altrimenti valuta la linea retta dallo sgancio.
Il flag è stato rinominato `accepts_declared_task` (la dichiarazione è un requisito della
geometria, non dell'insegna) ed è stato aggiunto `requires_distance_from_takeoff`, vero
solo per l'Argento: il vincolo dei 50 km anche dal luogo di decollo è dell'art. 5.1a e non
si applica alla linea retta d'oro. Documentazione e pagina Criteri aggiornate; tre nuovi
test in `test/test_gold.py`.
**Tensione nel regolamento da conoscere**: l'art. 10.1 rende obbligatoria la dichiarazione
elettronica «per qualsiasi prestazione, con esclusione dei voli di durata», mentre il 13.2
la esclude esplicitamente per la linea retta con partenza allo sgancio. Il 13.2 è la norma
speciale sulla geometria e prevale; vale la pena citarlo esplicitamente nel report, perché
è il punto su cui si può discutere con il Giudice Sportivo.

### 7. Guadagno di quota: manca il vincolo sul punto basso (art. 12.1)
`analysis.compute_height_gain` prende il massimo dislivello fra un minimo corrente e un
punto alto successivo, senza altri vincoli. Art. 12.1 ammette solo la differenza fra
quota massima e **quota di sgancio**, oppure fra quota massima e una precedente quota
minima **inferiore alla quota di sgancio**. Un punto basso più alto dello sgancio non è
utilizzabile: il codice può sovrastimare il guadagno.

## Lacune di copertura (non implementato)

- **Diamanti (art. 7)**: meta 300 km su andata/ritorno o triangolo, distanza 500 km,
  quota 5000 m. Nessuna delle tre.
- **Diplomi 750 km e oltre a passi di 250 km (art. 8)**.
- **Geometrie di percorso (art. 13.1)**: il codice tratta ogni dichiarazione come una
  polilinea. Non distingue linea retta / con meta / max 3 virate / andata e ritorno /
  triangolo, e non applica la regola 13.6a (distanza del triangolo = somma dei lati fra
  i **punti di virata**, non del percorso dalla partenza).
- **Motoalianti**: art. 5.1a e 14.1a fissano l'inizio prestazione allo **spegnimento del
  motore**; `detect_release` gestisce solo traino/verricello. Art. 9.1 rende obbligatoria
  la registrazione ENL/MOP se il motore non è sigillato: oggi `engine_suspected` produce
  solo un warning con soglia ENL 500 arbitraria, e l'assenza totale di ENL su un
  motoaliante non viene segnalata.
- **Cadenza di registrazione (art. 9.1)**: minimo un fix al minuto. Nessun controllo
  sull'intervallo fra fix.
- **Contenuto della dichiarazione (art. 10.2)**: nome pilota, tipo e marche dell'aliante,
  coordinate dei WP. Il codice controlla solo che `declared_at` preceda il primo fix
  (`validator.py:304`). Manca anche la regola «vale l'ultima dichiarazione prima del decollo».
- **Distanza d'Argento senza assistenza radio/navigazione (art. 5.1a)**: non verificabile
  da IGC, ma andrebbe almeno riportato come nota nel report.

## Cose corrette da confermare

- Durata dallo sgancio all'atterraggio (art. 11.1) ✔
- Argento: punto più lontano fra i fix registrati, oltre 50 km sia dallo sgancio sia dal
  luogo di decollo (art. 5.1a) ✔
- Argento: perdita di quota > 1% invalida — corretto **solo per voli ≤ 100 km**
  (art. 17.2); oltre i 100 km vale il difetto n. 1
- Riferimenti di quota per la perdita: sgancio → fix d'arrivo (art. 17.3) ✔
- Massimo 3 punti di virata (art. 13.4) ✔
- G-record / firma non verificata, dichiarata nel report ✔ (nota: art. 9.1 ammette per
  Argento e Oro semplici PRs, quindi il warning «non utilizzabile per omologazione» è
  più duro del regolamento; il vincolo reale è art. 18.3, file IGC non modificato)

## Livello UI

`src/silverc/Validazione.py` e `src/silverc/pages/1_Criteri.py` non duplicano soglie né
logica di verdetto: leggono `Requirement`/`Verdict` dal validatore. `1_Criteri.py` però
ricopia il **testo** di `REQUISITI.md`, quindi ne eredita gli errori (in particolare la
dichiarazione obbligatoria per l'Oro e l'1% di perdita di quota su 300 km): va aggiornato
insieme alla documentazione.

## Documentazione da aggiornare

`rules.py` è tutto marcato `TO VERIFY` con la nota «il PDF ufficiale non è stato
consultabile»; `README.md` e `REQUISITI.md` ripetono la stessa avvertenza. Con il
regolamento in `data/` i riferimenti vanno sostituiti con gli articoli reali
(5.1, 6.1, 11.1, 12.1, 13.x, 15.x, 17.x). La penalizzazione GNSS di 100 m
(`gnss_altitude_penalty_m`) **non compare** in questo regolamento: va ricondotta allo
Sporting Code o rimossa; in particolare la sottrazione di 100 m dal limite di perdita di
quota (`validator.py:152` e `:268`) è un'invenzione senza base regolamentare.

## Priorità suggerita

1. Perdita di quota oltre i 100 km (§1) — verdetti sbagliati in entrambe le direzioni,
   su Oro e su Argento oltre i 100 km. Fix locale, nessuna dipendenza.
2. ~~Distanza d'Oro in linea retta senza dichiarazione (§6)~~ — fatto.
3. Vincolo sul punto basso del guadagno di quota (§7). Fix locale.
4. Linee di partenza/arrivo da 1 km (§4).
5. Classificazione delle geometrie di percorso (13.1–13.6): prerequisito del punto
   successivo.
6. Ordine e uso facoltativo dei punti di virata sulla sola geometria 13.4 (§2), con
   riscrittura di `test_turnpoints_must_be_in_declared_order`.
7. Settore FAI 90° (§5) **insieme a** la riduzione di 0,5 km per ZO barattolo (§3).
8. Diamanti e Diplomi.
