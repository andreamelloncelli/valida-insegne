# Audit 1 — Regole comuni ad Argento e Oro

Confronto fra il codice (`src/silverc/`) e il **FAI Sporting Code Section 3, ed. 2025**
([`FAI_SC3_2025.pdf`](FAI_SC3_2025.pdf), fonte in [FONTI.md](FONTI.md)). Stato al 2026-10-19.
Le regole valgono per entrambe le insegne; le soglie e la geometria della distanza propria
di ciascuna sono in [Audit 2 — Argento](AUDIT_2_ARGENTO.md) e [Audit 3 — Oro](AUDIT_3_ORO.md).
Diamanti, diplomi e record sono fuori ambito.

I riferimenti `§` sono allo SC3, unico regolamento di riferimento: il Regolamento Insegne
AeCI non si considera. Le voci che rimandano all'Annex C (SC3C, non scaricato) sono da
verificare.

Legenda: ✅ conforme · 🟡 parziale · ❌ mancante o errato.
Codici: **T** trasversali, **D** durata, **Q** guadagno di quota, **K** distanza.

## Requisiti per prova (tabella §1.4.4)

| Prova | Dichiarazione | Partenza | Arrivo |
| --- | --- | --- | --- |
| Durata | non richiesta per le 5 h (§2.3) | sgancio o fix scelto dopo il volo (§1.3.1b) | atterraggio, avvio del motore o fix scelto, il primo dei tre (§1.3.2c) |
| Guadagno di quota | sì: pilota e marche (§1.1.4) | sgancio | qualsiasi |
| Distanza | sì; coordinate dei punti salvo la linea retta dallo sgancio (§2.3) | dipende dal percorso: vedi Argento e Oro | dipende dal percorso |

## Regole trasversali

| # | Tema | SC3 | Stato |
| --- | --- | --- | --- |
| GT1 | Registratore: FR approvato livello 1–3 oppure PR approvato dalla NAC | §2.2.6a, §2.5 | 🟡 |
| GT2 | Quota GNSS con margine di 100 m su **tutti** i requisiti di quota quando manca la taratura barometrica | §2.4.3c, §2.4.6a | ✅ |
| GT3 | Correzione della quota barometrica con la curva di taratura | §2.4.3a, §4.3.4c | ❌ |
| GT4 | Cadenza di almeno un fix al minuto | §2.4.1 | ✅ |
| GT5 | Continuità: nessun atterraggio intermedio, buchi oltre 1 min da segnalare | §2.4.5, §4.3.5b | ✅ |
| GT6 | Nessun uso del motore durante la prova | §2.4.5, §2.4.7 | 🟡 |
| GT7 | Sgancio ricavato dalla traccia (inizio della discesa o della virata stretta) | §2.4.2a | ✅ |
| GT8 | Sgancio inseribile a mano anche dall'interfaccia web | Maurizio | ✅ |
| GT9 | Identificativo dell'aliante: marche **oppure** sigla di gara | §1.1.3 | ✅ |
| GT10 | Pilota o marche mancanti o errati: correggibili con certificato dell'OO | §2.3b, §4.4.2c | ✅ |
| GT11 | Dichiarazione pre-volo (anche via internet, se ammessa dalla NAC) | §1.1.4, §2.3a | ✅ |
| GT12 | Distanze sull'ellissoide WGS84 | §1.3.7 | ✅ |
| GT13 | Imprecisioni di misura al massimo svantaggio del pilota | §4.3.4b | ✅ |
| GT14 | Firma del file (G-record) verificata col programma IGC | §4.3.4a | 🟡 |
| GT15 | Versione hardware del registratore (HFRHW) nel report | Maurizio | ✅ |
| GT16 | Riferimenti AeCI e `TO VERIFY` sostituiti con i paragrafi SC3 | — | ✅ |

**GT1 — Registratore.** Il codice distingue FR e PR dal codice costruttore, dal G-record e
da HFFTY. Non può verificare il livello di approvazione né la lista PR della NAC: lo dice
nel report e va bene così. Con un PR va ricordato che la stima dei fix deve essere
disattivata (§2.5e, certificato §4.4.2f).

**GT2 — Margine dei 100 m: è legato alla taratura, non al tipo di registratore.**
Il §2.4.6a applica il §2.4.3c a «FR o PR senza dati di taratura». Il codice usava la
quota GNSS con margine **solo** per i PR:

- FR senza certificato di taratura: il codice usa la barometrica senza margine, ed è
  **troppo permissivo**;
- PR con quota barometrica tarata: il codice impone GNSS e margine, ed è **troppo severo**.

Risolto: `analyse(calibrated=...)`, `--calibrated` da riga di comando e una casella nella
pagina web. Il default è «nessun dato di taratura» (§4.3.4b): quota GNSS e margine per FR e
PR; con la taratura si usa la barometrica senza margine. Il margine vale anche
per il limite di perdita di quota della distanza (§2.4.4), applicato da GK1 con la stessa
condizione sulla quota GNSS.

**GT3 — Correzione di taratura.** Con taratura disponibile, la quota barometrica va
corretta con la curva quando è determinante (§2.4.3a). Il codice usa la quota ISA grezza.
Basta, per cominciare, accettare una tabella di correzione opzionale.

**GT4 — Cadenza dei fix.** Risolto: se l'intervallo mediano fra sgancio e atterraggio
supera i 60 s il report avverte che la cadenza impostata non rispetta il §2.4.1. I singoli
buchi oltre il minuto sono un problema di continuità (GT5). Con fix radi il rilevamento
dell'atterraggio non si ferma più al primo intervallo oltre la finestra di sosta.

**GT5 — Continuità.** L'atterraggio è l'ultima sosta della traccia. Una sosta intermedia
(atterraggio fuori campo e ripartenza) non viene rilevata. Un buco di dati oltre 1 minuto
richiede la traccia di un secondo registratore (§4.3.5b): va almeno segnalato.
Risolto: i buchi oltre 60 s fra sgancio e atterraggio sono fra le avvertenze; un tratto in
cui l'aliante resta fermo dopo lo sgancio rende NON DETERMINABILI le tre prove, con il
rimando all'OO (§2.4.5).

**GT6 — Motore.** C'è solo un'avvertenza con soglia ENL arbitraria (500). Per un
motoaliante va segnalata anche l'**assenza** di ENL/MOP e la prova finisce all'avvio del
motore (GD3). Con motore sigillato decide l'OO (§2.4.7).

**GT8 — Sgancio dall'interfaccia web.** Risolto: la pagina web ha un campo HH:MM:SS UTC,
letto con `analysis.parse_release_time` come `--release-time` da riga di comando.

**GT9 — Identificativo dell'aliante.** Risolto in `documentation.check_registration`: la
sigla di gara sostituisce le marche mancanti, e il tipo di aliante mancante è lasciato
all'OO. Per il §1.1.3 basta una fra marche e sigla di gara.
Il codice esige le marche (HFGID) e tratta la sigla come facoltativa: un file con sola
sigla risulta incompleto a torto. Il tipo di aliante (HFGTY) non fa parte della
dichiarazione: lo conferma l'OO al decollo (§4.3.1).

**GT10 — Errori nell'intestazione.** Per Argento e Oro un nome o un identificativo
sbagliati non annullano la prova: l'OO allega un certificato di correzione. Il report non
deve presentarli come bloccanti. Risolto: `documentation.check_headers` aggiunge a ogni
controllo fallito su pilota o identificativo che l'OO può allegare il certificato.

**GT11 — Dichiarazione.** Risolto: l'orario della dichiarazione si confronta col decollo
e non col primo fix. Una dichiarazione via internet sostituisce quella del registratore
(§2.3a) e non è nel file: si indica con `--internet-declaration` o con una casella nella
pagina web, e il report ricorda cosa allegare.

**GT12 — WGS84.** `geographiclib` è già una dipendenza obbligatoria, quindi di norma il
calcolo è conforme. Resta però il ripiego sulla sfera FAI se la libreria manca, che lo SC3
non ammette più: va tolto, o in quel caso va bloccato il verdetto. Risolto: il ripiego è
stato tolto e `geographiclib` si importa senza alternative.

**GT13 — Esito «al limite».** La banda dello 0,5% sulla distanza e sulla quota è una
scelta del codice. Il §4.3.4b chiede di risolvere ogni dubbio a sfavore del pilota: il
report deve dire che «al limite» non è un esito valido per la richiesta. Risolto: ogni
prova al limite lo dice nelle motivazioni.

**GT15 — Versione hardware.** Risolto: HFRHW è letto e mostrato accanto a costruttore e
modello nel report e nella pagina web, per riconoscere il dispositivo nella lista FAI.

**GT16 — Riferimenti normativi.** Risolto: `rules.py`, i messaggi del report, la pagina
Criteri, README e REQUISITI citano i paragrafi SC3 al posto degli articoli AeCI e dei
`TO VERIFY`. Il messaggio sulla linea retta per l'Oro ora dice che la dichiarazione
(pilota e identificativo) non deve contenere le coordinate (§1.4.2d, §2.3).

## Durata

Identica per le due insegne: 5 h (§2.2.1b, §2.2.2b).

| # | Tema | SC3 | Stato |
| --- | --- | --- | --- |
| GD1 | Inizio allo sgancio | §1.3.1b | ✅ |
| GD2 | 5 h senza tolleranza | §2.2.1b, §2.2.2b | ✅ |
| GD3 | Fine al primo fra atterraggio e avvio del motore | §1.3.2c | ❌ |
| GD4 | Dichiarazione non richiesta | §2.3 | ✅ |
| GD5 | Cadenza di almeno un fix al minuto | §2.4.1 | ✅ (= GT4) |

**GD3 — Motoalianti.** La durata finisce all'atterraggio. Se il motore viene avviato
prima, la prova finisce lì. Dipende da GT6.

Il volo senza registratore, controllato a vista dall'OO (§2.4.1, §4.3.2), è fuori
dall'ambito di uno strumento che analizza file IGC.

## Guadagno di quota

Identico per le due insegne salvo la soglia (1000 m Argento, 3000 m Oro).

| # | Tema | SC3 | Stato |
| --- | --- | --- | --- |
| GQ1 | Punto alto meno un punto basso precedente, dopo lo sgancio | §1.3.5, §1.4.4 | ✅ |
| GQ2 | Margine di 100 m con quota GNSS | §2.4.3c | ✅ (= GT2) |
| GQ3 | Quota barometrica corretta con la taratura | §2.4.3a | ❌ (= GT3) |
| GQ4 | Nessun vincolo sul punto basso oltre a seguire lo sgancio | §1.3.5 | ✅ |
| GQ5 | Dichiarazione con pilota e identificativo | §1.4.4 | ✅ (= GT11) |

**GQ4 — Punto basso.** Lo SC3 non vincola il punto basso alla quota di sgancio: basta che
preceda il punto alto (§1.3.5). Il codice fa già così.

## Distanza: regole comuni

La geometria della distanza è diversa per le due insegne (vedi Argento e Oro). In comune
c'è il limite di perdita di quota.

| # | Tema | SC3 | Stato |
| --- | --- | --- | --- |
| GK1 | Limite di perdita di quota secondo la distanza e la fonte di quota | §2.4.4 | ✅ |
| GK2 | Perdita di quota = quota di partenza − quota d'arrivo | §1.3.4 | ✅ |

**GK1 — Perdita di quota.** Risolto: `validator._loss_of_height` applica il §2.4.4 sia
alla linea retta sia al percorso dichiarato, scegliendo la regola sulla distanza volata. Il
verdetto si dà sulla distanza ridotta. Prima il codice usava sempre l'1% della distanza e
bocciava se superato. Il §2.4.4 prevede:

| Distanza | Quota barometrica | Quota GNSS | Se superato |
| --- | --- | --- | --- |
| ≤ 100 km | 1% della distanza | 1% della distanza − 100 m | prova non valida |
| > 100 km | 1000 m | 900 m | distanza − 100 × eccesso |

Il codice sbagliava in più direzioni (casi ora coperti da test):

- con quota GNSS non toglie i 100 m, quindi è troppo permissivo.
  > Argento, 60 km con 550 m di perdita in GNSS. Codice: entro i 600 m ⇒ **SODDISFATTO**.
  > SC3: limite 500 m ⇒ **NON SODDISFATTO**.
- oltre i 100 km sull'Argento è troppo severo.
  > 130 km con 1500 m di perdita. Codice: oltre i 1300 m ⇒ **NON SODDISFATTO**.
  > SC3: 500 m di eccesso ⇒ −50 km ⇒ 80 km validi ⇒ **SODDISFATTO**.
- sull'Oro è troppo permissivo.
  > 300 km con 2000 m di perdita. Codice: entro i 3000 m ⇒ **SODDISFATTO**.
  > SC3: 1000 m di eccesso ⇒ −100 km ⇒ 200 km validi ⇒ **NON SODDISFATTO**.

## Fuori ambito

- Diamanti, diplomi, record e distanze libere (§1.4.2i–l).
- Pilota solo a bordo (§2.0d) e rispetto delle norme di volo (§4.3.4d): non verificabili
  dalla traccia.
- Verifica crittografica del G-record: richiede il programma `vali-*` del costruttore.
