"""Costanti regolamentari FAI Sporting Code Section 3 - Gliding, ed. 2025.

I riferimenti `§` sono ai paragrafi dello SC3 2025 (`data/FAI_SC3_2025.pdf`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BadgeRules:
    """Soglie di un'insegna."""

    name: str = "argento"

    # §2.2.1a (argento), §2.2.2a (oro)
    min_distance_m: float = 50_000.0

    # §2.2.1b, §2.2.2b
    min_duration_s: int = 5 * 3600

    # §2.2.1c, §2.2.2c
    min_height_gain_m: float = 1_000.0

    # §2.2.2a: l'oro ammette i percorsi §1.4.2d-h, che salvo la linea retta
    # dallo sgancio richiedono le coordinate dichiarate (§2.3). L'argento e'
    # solo linea retta dallo sgancio (§2.2.1a).
    accepts_declared_task: bool = False

    # §2.2.1a: il fix d'arrivo d'argento dev'essere ad almeno 50 km sia dallo
    # sgancio sia dal fix d'inizio della corsa di decollo. Per l'oro la linea
    # retta (§1.4.2d) non pone la seconda condizione.
    requires_distance_from_takeoff: bool = True

    # Tabella §1.4.4: al massimo 3 punti di virata dichiarati.
    max_turnpoints: int = 3

    # SC3 §2.4.4 - perdita di quota fra partenza e arrivo. Fino a 100 km di
    # distanza il limite e' l'1% e superarlo invalida la prova; oltre i 100 km
    # il limite e' fisso e l'eccesso non invalida ma accorcia la distanza di
    # 100 volte tanto. Con la quota GNSS entrambi i limiti scendono di
    # `gnss_altitude_penalty_m`.
    loss_of_height_ratio: float = 0.01
    loss_of_height_long_course_m: float = 100_000.0
    loss_of_height_long_limit_m: float = 1_000.0
    loss_of_height_excess_factor: float = 100.0

    # Margine sulla quota GNSS (SC3 §2.4.3c, §2.4.4): si aggiunge alla soglia
    # di guadagno di quota e si toglie dai limiti di perdita di quota.
    # Obbligatorio con un Position Recorder, non dovuto con un Flight Recorder
    # approvato.
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

    # Zone di osservazione del percorso dichiarato. Il cilindro da 500 m sulle
    # virate e' una delle due zone del §1.2.6; l'altra, il settore a 90 gradi
    # di raggio illimitato, non e' ancora gestita. Il cilindro di 1 km su
    # partenza e arrivo e' un'approssimazione: il §1.2.12 chiede una linea di
    # 1 km perpendicolare alla tratta (vedi Audit 3, OK6).
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
