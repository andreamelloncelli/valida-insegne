"""Verifica dei tre requisiti dell'insegna d'argento (Silver C)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from silverc.analysis import FlightAnalysis
from silverc.igc import Flight
from silverc.rules import GOLD, RULES, SILVER, BadgeRules

logger = logging.getLogger(__name__)


class Verdict(str, Enum):
    PASS = "SODDISFATTO"
    FAIL = "NON SODDISFATTO"
    MARGINAL = "AL LIMITE"
    UNDETERMINED = "NON DETERMINABILE"


@dataclass
class Requirement:
    code: str
    title: str
    verdict: Verdict
    measured: str
    required: str
    reasons: list[str] = field(default_factory=list)
    method: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    flight: Flight
    analysis: FlightAnalysis
    requirements: list[Requirement]
    warnings: list[str] = field(default_factory=list)
    badge: str = "argento"

    @property
    def satisfied(self) -> list[Requirement]:
        return [r for r in self.requirements if r.verdict is Verdict.PASS]

    @property
    def complete(self) -> bool:
        """Vero se questo singolo volo copre tutti e tre i requisiti."""
        return len(self.satisfied) == len(self.requirements)


def _threshold_verdict(measured: float, required: float, band: float) -> Verdict:
    """`band` e' l'incertezza di misura della grandezza; 0 se la misura e' esatta."""
    if band > 0 and abs(measured - required) <= band:
        return Verdict.MARGINAL
    return Verdict.PASS if measured >= required else Verdict.FAIL


def _height_threshold(base: float, analysis: FlightAnalysis) -> tuple[float, str | None]:
    if analysis.altitude_source.startswith("GNSS"):
        return base + RULES.gnss_altitude_penalty_m, (
            f"Quota GNSS al posto di quella barometrica: soglia maggiorata di "
            f"{RULES.gnss_altitude_penalty_m:.0f} m come margine d'errore."
        )
    return base, None


def _fmt_hms(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:d}h {total % 3600 // 60:02d}m {total % 60:02d}s"


def check_duration(analysis: FlightAnalysis, rules: BadgeRules = SILVER) -> Requirement:
    measured = analysis.duration_s
    # Fissato l'istante di sgancio, la durata e' esatta: nessuna banda di
    # incertezza. L'unico dubbio possibile e' sullo sgancio, gestito sotto.
    verdict = _threshold_verdict(measured, rules.min_duration_s, band=0.0)
    reasons: list[str] = []
    method = [
        f"Inizio conteggio allo sgancio delle {analysis.release.time:%H:%M:%S} UTC "
        f"({analysis.release_source}).",
        f"Fine conteggio all'atterraggio delle {analysis.landing.time:%H:%M:%S} UTC, "
        "individuato scartando i fix finali registrati da fermo.",
    ]
    if analysis.release_confidence in {"bassa", "nulla"}:
        verdict = Verdict.UNDETERMINED
        reasons.append(
            "L'istante di sgancio non e' ricavabile con sicurezza dalla traccia "
            "(l'IGC non lo registra). Ripetere l'analisi indicando --release-time."
        )
    else:
        reasons.append(
            f"Durata misurata {_fmt_hms(measured)} contro le 5h richieste "
            f"(scarto {_fmt_hms(abs(measured - rules.min_duration_s))})."
        )
    return Requirement(
        code="durata",
        title="Durata: 5 ore di volo dopo lo sgancio",
        verdict=verdict,
        measured=_fmt_hms(measured),
        required=_fmt_hms(rules.min_duration_s),
        reasons=reasons,
        method=method,
    )


def check_height_gain(analysis: FlightAnalysis, rules: BadgeRules = SILVER) -> Requirement:
    gain = analysis.height_gain
    required, penalty_note = _height_threshold(rules.min_height_gain_m, analysis)
    verdict = _threshold_verdict(gain.gain_m, required, band=required * RULES.marginal_ratio)
    method = [
        "Guadagno calcolato come massima differenza fra un punto alto e un punto "
        "basso che lo precede, entrambi successivi allo sgancio.",
        f"Quota di riferimento: {analysis.altitude_source}.",
    ]
    reasons: list[str] = []
    if gain.low is not None and gain.high is not None:
        reasons.append(
            f"Punto basso {gain.low.time:%H:%M:%S} UTC, punto alto "
            f"{gain.high.time:%H:%M:%S} UTC: guadagno di {gain.gain_m:.0f} m "
            f"contro i {required:.0f} m richiesti."
        )
    else:
        verdict = Verdict.UNDETERMINED
        reasons.append("Dati di quota insufficienti dopo lo sgancio.")
    if penalty_note:
        reasons.append(penalty_note)
    if analysis.release_confidence in {"bassa", "nulla"}:
        reasons.append(
            "Il punto basso e' vincolato a un istante di sgancio stimato: "
            "confermarlo con --release-time."
        )
    return Requirement(
        code="quota",
        title=f"Guadagno di quota: {rules.min_height_gain_m:.0f} m",
        verdict=verdict,
        measured=f"{gain.gain_m:.0f} m",
        required=f"{required:.0f} m",
        reasons=reasons,
        method=method,
    )


def check_distance(analysis: FlightAnalysis, rules: BadgeRules = SILVER) -> Requirement:
    distance = analysis.distance_m
    # Banda dovuta al modello geodetico (sfera FAI vs ellissoide WGS84).
    verdict = _threshold_verdict(
        distance, rules.min_distance_m, band=rules.min_distance_m * RULES.marginal_ratio
    )
    max_loss = distance * RULES.max_loss_of_height_ratio
    if analysis.altitude_source.startswith("GNSS"):
        max_loss = max(0.0, max_loss - RULES.gnss_altitude_penalty_m)
    from_takeoff = analysis.distance_from_takeoff_m
    method = [
        "Punto d'arrivo: il fix piu' lontano dallo sgancio fra tutti quelli "
        "della traccia (non l'atterraggio).",
        "Distanza in linea retta dal punto di sgancio a quel punto.",
        f"Modello geodetico: {analysis.geodesic_model}.",
        f"Perdita di quota ammessa: {RULES.max_loss_of_height_ratio:.0%} della distanza.",
    ]
    if rules.requires_distance_from_takeoff:
        method.insert(
            2,
            f"Il punto piu' lontano deve superare i {rules.min_distance_m / 1000:.0f} km "
            "sia dallo sgancio sia dall'aeroporto di decollo (art. 5.1a).",
        )
    reasons = [
        f"Punto piu' lontano raggiunto alle {analysis.farthest.time:%H:%M:%S} UTC: "
        f"{distance / 1000:.2f} km dallo sgancio contro i "
        f"{rules.min_distance_m / 1000:.0f} km richiesti."
    ]
    if rules.accepts_declared_task:
        reasons.append(
            "Percorso valutato come distanza in linea retta con partenza allo "
            "sgancio: l'art. 13.2 non richiede la dichiarazione pre-volo per "
            "questa geometria."
        )

    if rules.requires_distance_from_takeoff:
        if from_takeoff < rules.min_distance_m:
            verdict = Verdict.FAIL
            reasons.append(
                f"Dall'aeroporto di decollo il punto piu' lontano dista pero' solo "
                f"{from_takeoff / 1000:.2f} km, sotto i {rules.min_distance_m / 1000:.0f} km richiesti."
            )
        else:
            reasons.append(
                f"Distanza dall'aeroporto di decollo: {from_takeoff / 1000:.2f} km, "
                "anch'essa oltre la soglia."
            )
    if analysis.loss_of_height_m > max_loss:
        verdict = Verdict.FAIL
        reasons.append(
            f"Perdita di quota fra partenza e arrivo di {analysis.loss_of_height_m:.0f} m, "
            f"oltre il limite di {max_loss:.0f} m: il volo non e' omologabile come distanza."
        )
    elif analysis.loss_of_height_m < 0:
        reasons.append(
            f"Nessuna perdita di quota: l'arrivo e' {-analysis.loss_of_height_m:.0f} m "
            f"piu' alto della partenza (limite: {max_loss:.0f} m)."
        )
    else:
        reasons.append(
            f"Perdita di quota di {analysis.loss_of_height_m:.0f} m, entro il limite "
            f"di {max_loss:.0f} m."
        )
    return Requirement(
        code="distanza",
        title=f"Distanza: {rules.min_distance_m / 1000:.0f} km, punto piu' lontano",
        verdict=verdict,
        measured=f"{distance / 1000:.2f} km",
        required=f"{rules.min_distance_m / 1000:.0f} km",
        reasons=reasons,
        method=method,
    )


def check_declared_distance(analysis: FlightAnalysis, rules: BadgeRules = GOLD) -> Requirement:
    """Distanza su percorso dichiarato prima del volo (record C dell'IGC)."""
    required_km = rules.min_distance_m / 1000
    method = [
        "Percorso dichiarato letto dai record C del file IGC.",
        "Distanza calcolata sommando le tratte fra i punti dichiarati "
        "(partenza, virate, arrivo).",
        "Ogni punto dev'essere toccato nell'ordine dichiarato, entrando nella "
        "sua zona di osservazione.",
        f"Perdita di quota ammessa: {RULES.max_loss_of_height_ratio:.0%} della distanza.",
    ]
    check = analysis.task_check

    if check is None:
        return Requirement(
            code="distanza",
            title=f"Distanza: {required_km:.0f} km su percorso dichiarato",
            verdict=Verdict.UNDETERMINED,
            measured="n/d",
            required=f"{required_km:.0f} km",
            reasons=[
                "Il file non contiene alcuna dichiarazione di percorso (record C): "
                "la distanza d'oro dev'essere dichiarata prima del volo."
            ],
            method=method,
        )

    distance = check.distance_m
    verdict = _threshold_verdict(
        distance, rules.min_distance_m, band=rules.min_distance_m * RULES.marginal_ratio
    )
    reasons = [
        f"Percorso dichiarato di {distance / 1000:.2f} km su "
        f"{len(check.task.turnpoints)} punti di virata, contro i "
        f"{required_km:.0f} km richiesti."
    ]

    if len(check.task.turnpoints) > rules.max_turnpoints:
        verdict = Verdict.FAIL
        reasons.append(
            f"Il percorso dichiara {len(check.task.turnpoints)} punti di virata, "
            f"oltre il massimo di {rules.max_turnpoints}."
        )

    for waypoint in check.waypoints:
        if waypoint.reached and waypoint.point is not None:
            reasons.append(
                f"{waypoint.label} '{waypoint.waypoint.name}': raggiunto alle "
                f"{waypoint.point.time:%H:%M:%S} UTC (passaggio a "
                f"{waypoint.closest_m:.0f} m, zona {waypoint.radius_m:.0f} m)."
            )
        else:
            verdict = Verdict.FAIL
            reasons.append(
                f"{waypoint.label} '{waypoint.waypoint.name}': NON raggiunto, "
                f"avvicinamento minimo {waypoint.closest_m / 1000:.2f} km contro "
                f"una zona di {waypoint.radius_m:.0f} m."
            )

    max_loss = distance * RULES.max_loss_of_height_ratio
    if analysis.altitude_source.startswith("GNSS"):
        max_loss = max(0.0, max_loss - RULES.gnss_altitude_penalty_m)
    if check.completed and check.loss_of_height_m > max_loss:
        verdict = Verdict.FAIL
        reasons.append(
            f"Perdita di quota fra partenza e arrivo di {check.loss_of_height_m:.0f} m, "
            f"oltre il limite di {max_loss:.0f} m."
        )

    return Requirement(
        code="distanza",
        title=f"Distanza: {required_km:.0f} km su percorso dichiarato",
        verdict=verdict,
        measured=f"{distance / 1000:.2f} km",
        required=f"{required_km:.0f} km",
        reasons=reasons,
        method=method,
    )


def validate_badge(
    flight: Flight, analysis: FlightAnalysis, rules: BadgeRules = SILVER
) -> ValidationReport:
    """Valuta i tre requisiti di un'insegna su un singolo volo."""
    # Art. 13.2: senza dichiarazione il volo si valuta come distanza in linea
    # retta con partenza allo sgancio, geometria ammessa anche per l'Oro.
    distance = (
        check_declared_distance(analysis, rules)
        if rules.accepts_declared_task and analysis.task_check is not None
        else check_distance(analysis, rules)
    )
    requirements = [
        check_duration(analysis, rules),
        distance,
        check_height_gain(analysis, rules),
    ]
    warnings: list[str] = list(analysis.notes)

    task = flight.task
    if task is not None and task.declared_at is not None and flight.fixes:
        if task.declared_at > flight.fixes[0].time:
            warnings.append(
                "La dichiarazione del percorso porta un orario successivo al primo "
                "fix registrato: va depositata prima del volo."
            )

    if not flight.has_g_record:
        warnings.append(
            "Il file non contiene il G-record: la traccia non e' firmata "
            "digitalmente e non e' utilizzabile per un'omologazione ufficiale."
        )
    else:
        warnings.append(
            "G-record presente ma NON verificato: la firma va controllata con "
            "il programma vali-*.exe del costruttore del logger."
        )
    if flight.rejected:
        warnings.append(
            f"{len(flight.rejected)} fix scartati durante il parsing "
            f"(primo: {flight.rejected[0][1]})."
        )
    if analysis.engine_suspected:
        warnings.append(
            f"ENL massimo dopo lo sgancio pari a {analysis.max_enl}: possibile uso "
            "del motore, il volo potrebbe non essere un volo a vela puro."
        )
    invalid = sum(1 for f in flight.fixes if not f.valid)
    if invalid:
        warnings.append(f"{invalid} fix con validita' 'V' (fix 2D o non valido).")

    logger.debug(
        "Validazione insegna d'%s: %s | soddisfatti %d/3",
        rules.name,
        ", ".join(f"{r.code}={r.verdict.name}" for r in requirements),
        len([r for r in requirements if r.verdict is Verdict.PASS]),
    )
    return ValidationReport(
        flight=flight,
        analysis=analysis,
        requirements=requirements,
        warnings=warnings,
        badge=rules.name,
    )


def validate_silver(flight: Flight, analysis: FlightAnalysis) -> ValidationReport:
    """Valuta i tre requisiti dell'insegna d'argento su un singolo volo."""
    return validate_badge(flight, analysis, SILVER)


def validate_gold(flight: Flight, analysis: FlightAnalysis) -> ValidationReport:
    """Valuta i tre requisiti dell'insegna d'oro su un singolo volo."""
    return validate_badge(flight, analysis, GOLD)
