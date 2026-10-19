# Audit codice vs. Regolamento Insegne FAI — Volo a Vela (ed. 1° novembre 2025)

Confronto fra il regolamento in `data/2025 - 1. Volo a Vela - REGOLAMENTO INSEGNE FAI.pdf`
e l'implementazione in `src/silverc/` + `test/`.

## Sintesi

Le tre soglie base (5 h, 50 km, 1000 m / 300 km, 3000 m) sono corrette e confermate
dagli artt. 5.1 e 6.1. Le lacune stanno tutte nelle **regole di percorso** (artt. 13–17),
dove il codice è in alcuni punti più severo del regolamento e in altri più permissivo.

## Difetti che producono verdetti sbagliati

### 1. Perdita di quota per voli > 100 km: regola sbagliata (art. 17.1) — Oro e Argento lungo
`validator.check_declared_distance` e `check_distance` applicano sempre
`max_loss = distanza × 1%` e in caso di superamento invalidano la prova.
Il regolamento distingue:
- **≤ 100 km** (art. 17.2): perdita > 1% ⇒ prova **non valida** — quello che fa il codice, corretto per l'Argento.
- **> 100 km** (art. 17.1): il limite assoluto è **1000 m** e il superamento **non invalida**:
  la distanza valida diventa `volata − 100 × eccedenza`.

L'errore va in una sola direzione per ciascuna insegna (nessun test copre il caso):

- **Oro — troppo permissivo.** 300 km con 2000 m di perdita: il codice usa il limite
  dell'1% (3000 m) e dà SODDISFATTO; per l'art. 17.1 l'eccedenza di 1000 m toglie
  100 km, restano 200 km ⇒ NON SODDISFATTO. Il caso opposto (bocciato a torto) non può
  verificarsi: una perdita oltre l'1% su 300 km comporta già più di 200 km di penalità.
- **Argento oltre i 100 km — troppo severo.** 130 km con 1500 m di perdita: il codice
  supera l'1% (1300 m) e dà NON SODDISFATTO; per l'art. 17.1 l'eccedenza di 500 m toglie
  50 km, restano 80 km ⇒ SODDISFATTO. Il caso opposto (promosso a torto) non può
  verificarsi.

In generale, con soglia d'insegna T, il codice boccia a torto solo se T < 100 km e
promuove a torto solo se T > 100 km.

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
vengono bocciati. (Il commento su `turnpoint_zone_radius_m` in `rules.py` parla di «settore FAI di 90 gradi e
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
  coordinate dei WP. Dal 2026-10-19 nome e cognome del pilota, tipo e marche sono
  controllati sull'intestazione IGC (`documentation.check_headers`); resta da controllare
  che `declared_at` preceda il **decollo** e non solo il primo fix, e la regola «vale
  l'ultima dichiarazione prima del decollo» (art. 10.3).
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
  più duro del regolamento; il vincolo reale è art. 18.3, file IGC non modificato).
  Dal 2026-10-19 il G-record concorre anche alla classificazione FR/PR.

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
(`gnss_altitude_penalty_m`) **non compare** in questo regolamento: la regola è stata
riferita da Maurizio (Position Recorder → quota GNSS e soglia di guadagno +100 m; Flight
Recorder approvato → nessuna maggiorazione) e resta da verificare sullo Sporting Code.
~~La sottrazione di 100 m dal limite di perdita di quota~~ è stata rimossa: non aveva base
regolamentare e, con la quota GNSS forzata sui Position Recorder, avrebbe ristretto in
silenzio il limite su tutti i voli di distanza fatti con un PR.

## Requisiti emersi con Maurizio (ottobre 2026)

Regole raccolte dalla spiegazione di Maurizio, non ancora un elenco concordato. Per
ciascuna: dove compare in questo audit e a che punto è il codice.

| Requisito | Nell'audit | Stato |
|-----------|------------|-------|
| File IGC: nome e cognome del pilota, tipo di aliante, marche; sigla di gara facoltativa | nuovo | ✅ `documentation.check_headers`; segnalato nel report, non incide sull'esito |
| Flight Recorder vs Position Recorder; con PR quota GNSS e guadagno +100 m | nuovo | ✅ `documentation.classify_recorder`, codici costruttore dalla IGC FR Technical Specification 2023 (A2.5.6) |
| Leggere la *hardware version* (HFRHW) | nuovo, §M1 | ❌ |
| Chiedere conferma all'utente quando il tipo di registratore non è chiaro | nuovo, §M2 | 🟡 oggi si assume PR e l'utente può cambiarlo, ma non gli viene chiesto |
| Riconoscere il tipo di tema e verificare che il volo lo soddisfi | Geometrie di percorso, §2 | ❌ |
| Start e finish alternativi (sgancio, atterraggio) solo dove il tema li ammette | §4 (16.2b), §2 (arrivo 13.4) | ❌ |
| Linee di start e finish con le dimensioni del regolamento, non quelle del pilota | §4 | ❌ dimensioni proprie ma sbagliate (cilindro r = 1 km invece di linea da 1 km) |
| Lo sgancio deve precedere lo start | nuovo, §M3 | 🟡 lo start è cercato dopo lo sgancio, ma il report non lo dichiara |
| Sgancio da valutare a mano se il «dentino» non è visibile | nuovo, §M4 | 🟡 `--release-time` solo da riga di comando, manca nell'interfaccia web |
| Settore FAI o cilindro da 500 m; accorciamento della distanza con i cilindri | §5 + §3 | ❌ |
| Volo effettivo: un tema dichiarato ma non volato non vale | nuovo | ✅ già applicato da `verify_declared_task`; motivazione e test aggiunti |
| Motoalianti: il logger deve avere il rilevatore del motore | Motoalianti | ❌ |
| Motoalianti: niente prova di accensione per le insegne (solo per i record) | coerente | ✅ non richiesta |

### M1. Versione hardware del registratore non letta
`Flight` espone tipo (HFFTY) e costruttore (record A) ma non HFRHW. Va letta e mostrata
accanto al tipo nella sezione Documentazione, come elemento per riconoscere il modello
nella lista FAI.

### M2. Tipo di registratore incerto: si decide al posto dell'utente
Quando la classificazione non è netta `classify_recorder` ricade sul PR in silenzio.
Nell'interfaccia web va chiesta conferma esplicita (con il PR come proposta) prima di
dare l'esito sul guadagno di quota; da riga di comando basta l'avvertenza con
`--recorder`.

### M3. Sgancio prima dello start non dichiarato
`verify_declared_task` cerca la partenza a partire dall'indice di sgancio, quindi un
attraversamento precedente non conta: la regola è applicata di fatto. Il report però non
lo dice, e un pilota che vede «Partenza NON raggiunta» non capisce che il problema è un
attraversamento prima dello sgancio. Va aggiunta la motivazione esplicita e un test.

### M4. Orario di sgancio non inseribile dall'interfaccia web
`Validazione.py` chiama `analyse` senza `release_time`. Quando l'euristica ha confidenza
bassa, l'utente web non ha modo di correggerla: serve un campo HH:MM:SS (UTC).

## Priorità suggerita

Stato aggiornato al 2026-10-19.

| # | Voce | Stato | Note |
|---|------|-------|------|
| — | Distanza d'Oro in linea retta senza dichiarazione (§6) | ✅ fatto | commit `967be60` |
| — | Detrazione di 100 m dal limite di perdita di quota con quota GNSS | ✅ fatto | rimossa il 2026-10-19, coperta da test |
| — | File IGC, registratore FR/PR, volo effettivo (requisiti di Maurizio) | ✅ fatto | 2026-10-19 |
| 1 | Perdita di quota oltre i 100 km (§1) | ❌ da fare | Oro troppo permissivo, Argento lungo troppo severo. Fix locale, nessuna dipendenza |
| 2 | Vincolo sul punto basso del guadagno di quota (§7) | ❌ da fare | fix locale |
| 3 | Campo orario di sgancio nell'interfaccia web (§M4) | ❌ da fare | fix locale, utile subito |
| 4 | Sgancio prima dello start dichiarato nel report (§M3) | 🟡 in parte | regola già applicata, manca la motivazione |
| 5 | Versione hardware e conferma del tipo di registratore (§M1, §M2) | 🟡 in parte | |
| 6 | Linee di partenza/arrivo da 1 km (§4) | ❌ da fare | serve la direzione della prima e dell'ultima tratta |
| 7 | Classificazione delle geometrie di percorso (13.1–13.6) | ❌ da fare | prerequisito di 8 e dei start/finish alternativi |
| 8 | Ordine e uso facoltativo dei punti di virata sulla sola geometria 13.4 (§2) | ❌ da fare | riscrivere `test_turnpoints_must_be_in_declared_order`; chiarire con Maurizio il rapporto con il «volo effettivo» |
| 9 | Settore FAI 90° (§5) **insieme a** riduzione di 0,5 km per ZO barattolo (§3) | ❌ da fare | |
| 10 | Dichiarazione: ultima prima del decollo, prima del decollo e non del primo fix (art. 10.2–10.3) | 🟡 in parte | intestazione controllata, dichiarazione no |
| 11 | Cadenza minima di un fix al minuto (art. 9.1) | ❌ da fare | |
| 12 | Motoalianti: ENL/MOP obbligatori, inizio prova allo spegnimento del motore | ❌ da fare | |
| 13 | Riferimenti `TO VERIFY` in `rules.py` da sostituire con gli articoli | 🟡 in parte | aggiornati codici costruttore e nota sui 100 m |
| 14 | Diamanti e Diplomi | ❌ da fare | funzionalità nuove, non correzioni |
