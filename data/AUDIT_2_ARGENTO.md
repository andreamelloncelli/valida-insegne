# Audit 2 — Insegna d'Argento

Solo le regole proprie dell'Argento; tutto il resto è in
[Audit 1 — Generale](AUDIT_1_GENERALE.md). Confronto con lo SC3 ed. 2025, stato al
2026-10-19. Legenda come nell'Audit 1.

## Durata

| # | Tema | SC3 | Stato |
| --- | --- | --- | --- |
| AD1 | Almeno 5 h | §2.2.1b | ✅ |

## Distanza

La distanza d'argento è **solo** in linea retta dallo sgancio a un fix d'arrivo, non
all'atterraggio (§2.2.1a). La dichiarazione non richiede coordinate (§2.3).

| # | Tema | SC3 | Stato |
| --- | --- | --- | --- |
| AK1 | Almeno 50 km in linea retta dallo sgancio a un fix della traccia | §2.2.1a, §1.4.4 | ✅ |
| AK2 | Lo stesso fix a ≥ 50 km anche dal fix d'inizio della corsa di decollo | §2.2.1a | ✅ |
| AK3 | Distanza valutata anche se il file contiene un percorso dichiarato | §1.4.4, nota | ✅ |
| AK4 | Nota: volo senza guida di un altro pilota | §2.2.1a (informativo) | ✅ |

**AK2 — Scelta del fix d'arrivo.** Il codice prende il fix più lontano dallo sgancio e
poi controlla che sia oltre 50 km anche dal decollo. Se quel fix non lo è, il volo è
bocciato, ma un altro fix potrebbe soddisfare entrambe le condizioni. Il codice è
**troppo severo**: va cercato un fix che massimizzi la minore delle due distanze.
Risolto: `analysis.find_balanced_point` trova quel fix e `check_distance` lo usa quando il
più lontano dallo sgancio non basta.

**AK4 — Guida di un altro pilota.** Testo in corsivo, quindi informativo (§1.0.2), e non
verificabile dalla traccia. Risolto con una nota nel metodo della prova di distanza, che
cita il testo SC3.

## Guadagno di quota

| # | Tema | SC3 | Stato |
| --- | --- | --- | --- |
| AQ1 | Almeno 1000 m | §2.2.1c | ✅ |

## Ordine di lavoro suggerito

Nessuna voce aperta.
