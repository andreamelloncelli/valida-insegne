"""Costanti regolamentari FAI Sporting Code Section 3 (Class D - Alianti).

ATTENZIONE: i valori qui raccolti provengono da fonti secondarie (guide NAC,
riassunti pubblici del Sporting Code). Il PDF ufficiale non e' stato
consultabile durante lo sviluppo. Ogni voce riporta il riferimento da
verificare sull'edizione in vigore prima di usare il report per una richiesta
ufficiale di omologazione.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BadgeRules:
    """Soglie di un'insegna."""

    name: str = "argento"

    # SC3 §1.4.2 (distanza) - TO VERIFY
    min_distance_m: float = 50_000.0

    # SC3 §1.4.1 (durata) - TO VERIFY
    min_duration_s: int = 5 * 3600

    # SC3 §1.4.3 (guadagno di quota) - TO VERIFY
    min_height_gain_m: float = 1_000.0

    # Art. 13.3-13.6: le geometrie con meta, virate, andata e ritorno o
    # triangolo vanno dichiarate prima del volo. Non e' un obbligo dell'insegna
    # ma della geometria: l'art. 13.2 ammette la linea retta con partenza allo
    # sgancio, senza dichiarazione, anche per l'Insegna d'Oro.
    accepts_declared_task: bool = False

    # Art. 5.1a: la distanza d'argento dev'essere di almeno 50 km sia dallo
    # sgancio sia dal luogo di decollo. L'art. 13.2 non pone la seconda
    # condizione per le altre insegne.
    requires_distance_from_takeoff: bool = True

    # Numero massimo di punti di virata ammessi nella dichiarazione. - TO VERIFY
    max_turnpoints: int = 3

    # SC3 - perdita di quota massima ammessa fra punto di partenza e di
    # arrivo: 1% della distanza percorsa. - TO VERIFY (verificare se
    # l'edizione in vigore applica un tetto massimo alla percentuale)
    max_loss_of_height_ratio: float = 0.01

    # Maggiorazione della soglia di guadagno di quota quando si usa la quota
    # GNSS: obbligatoria con un Position Recorder (art. 9.1 ammette i PR per
    # Argento e Oro), non dovuta con un Flight Recorder approvato. Regola
    # riferita da Maurizio; non compare nel Regolamento
    # Insegne AeCI 2025. - TO VERIFY sul Sporting Code Sect. 3
    gnss_altitude_penalty_m: float = 100.0

    # Non regolamentare: soglia oltre la quale il verdetto e' MARGINAL perche'
    # l'incertezza del modello geodetico / del sensore puo' ribaltarlo.
    marginal_ratio: float = 0.005


@dataclass(frozen=True)
class AnalysisParams:
    """Parametri euristici dell'analisi della traccia (non regolamentari)."""

    # Velocita' verticale oltre la quale un fix e' considerato un artefatto.
    max_plausible_vertical_speed_ms: float = 25.0

    # L'aliante e' "fermo" se in `stationary_window_s` non si allontana mai
    # oltre `stationary_radius_m` dalla posizione corrente. Criterio basato
    # sullo spostamento netto e non sulla velocita' fra fix consecutivi:
    # a 1 Hz il rumore GPS produce velocita' apparenti di diversi m/s.
    stationary_radius_m: float = 40.0
    stationary_window_s: int = 60

    # Sgancio: caduta di quota sotto il massimo corrente che chiude la salita
    # al traino. Sopra la turbolenza tipica del traino, sotto la prima discesa.
    release_drop_m: float = 50.0

    # Salita al traino minima perche' l'euristica sia considerata affidabile.
    min_tow_climb_m: float = 150.0

    # ENL medio oltre il quale si sospetta uso del motore.
    enl_running_threshold: int = 500

    # Escursione minima della quota barometrica sotto la quale il campo e'
    # considerato non compilato (loggers GPS che scrivono 00000).
    min_barometric_spread_m: int = 50

    # Distanza massima ammessa fra l'orario di sgancio dichiarato e il fix
    # piu' vicino, oltre la quale il dato non e' considerato affidabile.
    max_release_time_mismatch_s: float = 120.0

    # Zone di osservazione del percorso dichiarato: cilindro attorno al punto
    # di virata e alle linee di partenza/arrivo. Il Sporting Code ammette anche
    # il settore FAI di 90 gradi e raggio 3 km per i punti di virata. - TO VERIFY
    turnpoint_zone_radius_m: float = 500.0
    start_finish_zone_radius_m: float = 1_000.0


@dataclass(frozen=True)
class RecorderRules:
    """Criteri per distinguere un Flight Recorder approvato da un Position Recorder."""

    # Codici costruttore (record A, 3 caratteri) dei produttori di Flight
    # Recorder approvati IGC: tabella "IGC-approved flight recorders -
    # manufacturer codes" della IGC GNSS FR Technical Specification, 2nd
    # edition with AL8 (2023), A2.5.6. Il codice identifica il produttore, non
    # il modello: un produttore approvato puo' avere anche dispositivi non
    # approvati, per cui serve anche il G-record e il modello va confrontato
    # con https://www.fai.org/page/igc-approved-flight-recorders
    approved_manufacturers: frozenset[str] = frozenset(
        {
            "ACT", "AVX", "CAM", "CNI", "DSX", "EWA", "FIL", "FLA", "FLY", "GCS",
            "IMI", "LGS", "LXN", "LXV", "NAV", "NKL", "NTE", "PES", "PFE", "PRT",
            "RCE", "SCH", "SDI", "TRI", "ZAN",
        }
    )

    # A2.5.6, nota 2: il prefisso X designa un dispositivo non approvato IGC
    # (XCSoar, XCTrack, app per smartphone...).
    unapproved_prefix: str = "X"

    # Valori di HFFTY che non identificano un dispositivo.
    placeholder_types: frozenset[str] = frozenset({"", "N/D", "NKN", "UNKNOWN", "NONE"})


SILVER = BadgeRules(name="argento")
GOLD = BadgeRules(
    name="oro",
    min_distance_m=300_000.0,
    min_duration_s=5 * 3600,
    min_height_gain_m=3_000.0,
    accepts_declared_task=True,
    requires_distance_from_takeoff=False,
)
BADGES = {SILVER.name: SILVER, GOLD.name: GOLD}

RULES = SILVER
PARAMS = AnalysisParams()
RECORDERS = RecorderRules()
