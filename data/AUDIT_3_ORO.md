# Audit 3 — Insegna d'Oro

Solo le regole proprie dell'Oro; tutto il resto è in
[Audit 1 — Generale](AUDIT_1_GENERALE.md). Confronto con lo SC3 ed. 2025, stato al
2026-10-19. Legenda come nell'Audit 1.

## Durata

| # | Tema | SC3 | Stato |
| --- | --- | --- | --- |
| OD1 | Almeno 5 h | §2.2.2b | ✅ |

## Distanza

Almeno **300 km** su uno qualsiasi dei percorsi §1.4.2d–h. Requisiti dalla tabella §1.4.4:

| Percorso | Virate | Partenza | Arrivo | Coordinate dichiarate |
| --- | --- | --- | --- | --- |
| Linea retta (d) | — | sgancio o linea di partenza | solo un fix | no, se parte dallo sgancio |
| Meta (e) | 0 | linea di partenza | linea d'arrivo | sì |
| Fino a 3 virate (f) | 1–3, ordine libero | sgancio o linea di partenza | atterraggio, fix o linea | sì |
| Andata e ritorno (g) | 1 | linea di partenza | linea d'arrivo | sì |
| Triangolo (h) | 2 o 3, ordine dichiarato | linea di partenza | linea d'arrivo | sì |

Nel triangolo a 3 virate la distanza è la somma dei lati **fra le virate** (§1.4.2h). I
percorsi chiusi hanno partenza e arrivo con coordinate identiche (§1.2.11).

| # | Tema | SC3 | Stato |
| --- | --- | --- | --- |
| OK1 | Linea retta dallo sgancio senza coordinate dichiarate | §1.4.2d, §2.3 | ✅ |
| OK2 | Riconoscimento del tipo di percorso | §1.4.2d–h | ✅ |
| OK3 | Al massimo 3 virate | §1.4.4 | ✅ |
| OK4 | Ordine libero delle virate solo nel percorso (f) | §1.4.2f | ✅ |
| OK5 | Partenze e arrivi ammessi secondo il percorso | §1.4.4 | ✅ |
| OK6 | Linee di partenza e d'arrivo da 1 km perpendicolari alla tratta | §1.2.12, §1.3.1a, §1.3.2b | ✅ |
| OK7 | Quota al passaggio della linea interpolata fra i due fix | §2.4.3b | ✅ |
| OK8 | Zone di virata: cilindro da 500 m **o** settore a 90° di raggio illimitato | §1.2.6 | 🟡 |
| OK9 | −1 km per ogni virata raggiunta solo col cilindro | §1.3.6 | ❌ |
| OK10 | Virata raggiunta anche se il segmento fra due fix attraversa la zona | §2.4.2c | ✅ |
| OK11 | Distanza ufficiale = percorso − correzioni zona − penalità di quota | §1.3.7 | 🟡 |
| OK12 | Percorso chiuso: partenza e arrivo con le stesse coordinate | §1.2.11 | ✅ |
| OK13 | Percorso dichiarato non completato: ripiego sulla linea retta | §2.2, §1.4.4 | ✅ |
| OK14 | Sgancio prima della partenza, indicato nel report | Maurizio | ✅ |
| OK15 | Linea retta da una linea di partenza dichiarata | §1.4.2d | ❌ |

**OK2 — Tipo di percorso.** Ogni dichiarazione è trattata come una spezzata da percorrere
in ordine. Va distinto il percorso dal numero di virate e dalla coincidenza fra partenza
e arrivo. È il prerequisito di OK4, OK5 e OK12. Risolto in `course.classify_course`: il
report indica il tipo di percorso riconosciuto.

**OK4 — Ordine delle virate.** Solo nel percorso (f) le virate si girano in qualsiasi
ordine. Oggi il codice esige sempre l'ordine dichiarato, e
`test_turnpoints_must_be_in_declared_order` lo codifica.

**OK4 + OK5 — Risolti in `course.verify_declared_task`.** Ogni percorso dichiarato con 1–3
virate si valuta, oltre che nella geometria dichiarata, come distanza fino a 3 virate (f):
virate in qualsiasi ordine, partenza dichiarata o sgancio, arrivo dichiarato o un fix
(tabella §1.4.4). Vale l'esito migliore (§2.2). Per un'insegna non servono valutatori a
parte per andata e ritorno (g) e triangolo (h): richiedono linee di partenza e arrivo e
l'ordine dichiarato, mentre (f) ammette tutto questo e altro, quindi sullo stesso volo la
sua distanza non è mai inferiore (per il triangolo a 3 virate per la disuguaglianza
triangolare). L'ordine dichiarato di g e h conta solo per i diamanti, fuori ambito. Si
ammette anche di rivendicare solo alcune delle virate dichiarate («via one, two, or three
declared turn points», colonne «declared» e «claimed» della tabella §1.4.4): è
un'interpretazione e il report lo dice. Il test sull'ordine è stato invertito
(`test_turnpoints_in_any_order_count_as_three_tp_distance`).

**OK5 — Partenze e arrivi.** Lo sgancio come partenza è ammesso solo per (d) e (f);
l'atterraggio come arrivo solo per (f). Meta, andata e ritorno e triangolo esigono le
linee.

**OK6 — Linee.** Il codice usa un cilindro di 1 km di raggio attorno ai punti di partenza
e arrivo. Per le insegne lo SC3 non ammette cilindri di partenza o d'arrivo, di nessun
raggio: chiede una **linea** lunga 1 km in totale (500 m per lato dal punto),
perpendicolare alla prima (o ultima) tratta e attraversata nel verso della tratta. Il
cilindro va sostituito con la linea, non ridotto a 500 m: oggi si accettano passaggi che
non attraversano la linea, per esempio di fianco o nel verso sbagliato. Risolto con
`course.line_crossings`, insieme a OK7: la linea è perpendicolare alla prima o all'ultima
tratta rivendicata, vale solo l'attraversamento nel verso della tratta e istante e quota si
interpolano fra i due fix. Della partenza vale l'ultimo attraversamento dopo lo sgancio e
prima della prima virata.

**OK8 + OK9 — Zone di virata.** Esiste solo il cilindro da 500 m, senza la correzione di
1 km. Le due voci vanno rilasciate insieme: col solo OK9 i voli girati a settore
verrebbero penalizzati a torto.

> Esempio: triangolo dichiarato da 300,5 km, tre virate prese col cilindro. Codice:
> 300,5 km ⇒ **SODDISFATTO**. SC3: 300,5 − 3 = 297,5 km ⇒ **NON SODDISFATTO**.

Il commento in `rules.py` parla di un settore di raggio 3 km: lo SC3 2025 lo vuole
illimitato.

**OK10 — Attraversamento fra due fix.** Il codice esige un fix dentro la zona. Con fix
radi un passaggio reale può risultare mancato: il codice è troppo severo. Risolto in
`course.turnpoint_indices`.

**OK11 — Distanza ufficiale.** Somma la correzione delle zone (OK9) e la penalità di
perdita di quota (GK1) sul percorso dichiarato. La geometria si sceglie già sulla distanza
ufficiale con la penalità di quota; manca la correzione delle zone, che arriva con OK9.

**OK12 — Percorso chiuso.** Risolto: un percorso è chiuso solo se partenza e arrivo hanno
le stesse coordinate (`course.is_closed`); se distano meno di 1 km ma non coincidono il
report lo segnala e il percorso è trattato come (f).

**OK13 — Ripiego sulla linea retta.** Il §2.2 dice che un volo vale per ogni prova di cui
soddisfa i requisiti. Oggi, se il file ha una dichiarazione, si valuta solo il percorso
dichiarato: un volo che manca una virata ma fa 300 km in linea retta dallo sgancio viene
bocciato. Deciso il 2026-10-19: il percorso dichiarato e non volato non vale, ma il volo
si valuta anche come linea retta dallo sgancio (§1.4.2d), che non richiede coordinate
(§2.3). Le distanze libere (§1.4.2i–l) non sono un ripiego possibile: la tabella §1.4.4
le ammette solo per i record. Fatto in `validator.check_best_distance`: vale la geometria con l'esito migliore e il report riporta anche l'esito dell'altra.

**OK14 — Sgancio prima della partenza.** La partenza si cerca già dopo lo sgancio. Risolto:
se la partenza è stata attraversata solo prima dello sgancio il report lo spiega.

**OK15 — Linea retta con partenza dichiarata.** Il percorso (d) ammette anche una linea di
partenza dichiarata invece dello sgancio. Non è gestito; dipende da OK2 e OK6.

## Guadagno di quota

| # | Tema | SC3 | Stato |
| --- | --- | --- | --- |
| OQ1 | Almeno 3000 m | §2.2.2c | ✅ |

## Ordine di lavoro suggerito

OK14 → OK2 → OK4 e OK5 → OK6 e OK7 → OK8 e OK9 → OK10 → OK11 → OK12 → OK15.
OK13 fatto.
