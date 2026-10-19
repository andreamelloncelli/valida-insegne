"""Verifica dei tre requisiti dell'insegna d'argento (Silver C)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from silverc.analysis import FinishFix, FlightAnalysis
from silverc.documentation import DocumentCheck, check_headers
from silverc.geo import LossOfHeight, geodesic_distance_ll, loss_of_height
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
    documentation: list[DocumentCheck] = field(default_factory=list)

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
    if _uses_gnss(analysis):
        why = (
            "quota GNSS al posto di quella barometrica"
            if analysis.calibrated
            else "nessun dato di taratura barometrica, §2.4.6a"
        )
        return base + RULES.gnss_altitude_penalty_m, (
            f"Soglia maggiorata di {RULES.gnss_altitude_penalty_m:.0f} m ({why}): "
            f"{base:.0f} + {RULES.gnss_altitude_penalty_m:.0f} m sulla quota GNSS (§2.4.3c)."
        )
    return base, (
        "Registratore con dati di taratura: quota barometrica, soglia senza "
        "maggiorazione (§2.4.6b)."
    )


def _loss_of_height_method(gnss: bool) -> str:
    margin = f" meno {RULES.gnss_altitude_penalty_m:.0f} m (quota GNSS)" if gnss else ""
    long_limit = RULES.loss_of_height_long_limit_m - (
        RULES.gnss_altitude_penalty_m if gnss else 0.0
    )
    return (
        f"Perdita di quota ammessa (§2.4.4): fino a "
        f"{RULES.loss_of_height_long_course_m / 1000:.0f} km "
        f"{RULES.loss_of_height_ratio:.0%} della distanza{margin}, oltre il quale la "
        f"prova non e' valida; oltre i {RULES.loss_of_height_long_course_m / 1000:.0f} km "
        f"{long_limit:.0f} m, e ogni metro in eccesso toglie "
        f"{RULES.loss_of_height_excess_factor:.0f} m alla distanza."
    )


def _loss_of_height_reason(check: LossOfHeight) -> str:
    if check.invalid:
        return (
            f"Perdita di quota fra partenza e arrivo di {check.loss_m:.0f} m, oltre il "
            f"limite di {check.limit_m:.0f} m: fino a "
            f"{RULES.loss_of_height_long_course_m / 1000:.0f} km la prova non e' valida "
            "(§2.4.4)."
        )
    if check.excess_m > 0:
        return (
            f"Perdita di quota fra partenza e arrivo di {check.loss_m:.0f} m, oltre il "
            f"limite di {check.limit_m:.0f} m: l'eccesso di {check.excess_m:.0f} m "
            f"toglie {(check.flown_m - check.official_m) / 1000:.2f} km, la distanza "
            f"passa da {check.flown_m / 1000:.2f} a {check.official_m / 1000:.2f} km "
            "(§2.4.4)."
        )
    if check.loss_m < 0:
        return (
            f"Nessuna perdita di quota: l'arrivo e' {-check.loss_m:.0f} m piu' alto "
            f"della partenza (limite: {check.limit_m:.0f} m)."
        )
    return (
        f"Perdita di quota di {check.loss_m:.0f} m, entro il limite di "
        f"{check.limit_m:.0f} m."
    )


def _uses_gnss(analysis: FlightAnalysis) -> bool:
    return analysis.altitude_source.startswith("GNSS")


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
        (
            f"Fine conteggio all'avvio del motore delle {analysis.engine_start.time:%H:%M:%S} "
            "UTC, che precede l'atterraggio (§1.3.2c)."
            if analysis.engine_start is not None
            else f"Fine conteggio all'atterraggio delle {analysis.landing.time:%H:%M:%S} UTC, "
            "individuato scartando i fix finali registrati da fermo."
        ),
    ]
    if analysis.release_confidence in {"bassa", "nulla"}:
        verdict = Verdict.UNDETERMINED
        reasons.append(
            "L'istante di sgancio non e' ricavabile con sicurezza dalla traccia "
            "(l'IGC non lo registra). Ripetere l'analisi indicando l'orario di sgancio "
            "(--release-time o campo nella pagina web)."
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
    if not analysis.altitude_usable:
        verdict = Verdict.UNDETERMINED
        reasons.append(
            "Quota GNSS assente o costante: senza dati di taratura il guadagno "
            "di quota si misura sulla quota GNSS (§2.4.6a), che il file non registra."
        )
    elif gain.low is not None and gain.high is not None:
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
            "confermarlo indicando l'orario di sgancio (--release-time o pagina web)."
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
    gnss = _uses_gnss(analysis)
    chosen = (
        analysis.silver_finish
        if rules.requires_distance_from_takeoff
        else analysis.straight_finish
    ) or FinishFix(
        analysis.farthest,
        analysis.distance_m,
        analysis.distance_from_takeoff_m,
        analysis.loss_of_height_m,
    )
    finish_time = chosen.point.time
    flown = chosen.distance_m
    from_takeoff = chosen.from_takeoff_m
    loss_m = chosen.loss_of_height_m
    reasons: list[str] = []
    if chosen.point.index != analysis.farthest.index:
        reasons.append(
            f"Il punto piu' lontano dallo sgancio ({analysis.distance_m / 1000:.2f} km "
            f"alle {analysis.farthest.time:%H:%M:%S} UTC) da' un esito peggiore: "
            "scelto come arrivo un altro fix della traccia (§1.2.10c)."
        )
    loss = loss_of_height(flown, loss_m, gnss)
    distance = loss.official_m
    # Banda d'incertezza della posizione GNSS: vedi RULES.marginal_ratio.
    verdict = _threshold_verdict(
        distance, rules.min_distance_m, band=rules.min_distance_m * RULES.marginal_ratio
    )
    method = [
        "Fix d'arrivo scelto dopo il volo fra tutti quelli della traccia "
        "(§1.2.10c): quello con la distanza ufficiale migliore, scartando i fix "
        "che superano il limite di perdita di quota.",
        "Distanza in linea retta dal punto di sgancio a quel punto.",
        f"Modello geodetico: {analysis.geodesic_model}.",
        _loss_of_height_method(gnss),
    ]
    if rules.requires_distance_from_takeoff:
        method.insert(
            2,
            f"Il fix d'arrivo deve superare i {rules.min_distance_m / 1000:.0f} km "
            "sia dallo sgancio sia dal fix d'inizio della corsa di decollo (§2.2.1a): "
            "si sceglie il fix che massimizza la minore delle due.",
        )
        method.append(
            "La distanza d'argento dovrebbe essere volata senza la guida di un altro "
            "pilota (§2.2.1a, testo informativo): la traccia non permette di "
            "verificarlo."
        )
    reasons.append(
        f"Fix d'arrivo alle {finish_time:%H:%M:%S} UTC: "
        f"{flown / 1000:.2f} km dallo sgancio contro i "
        f"{rules.min_distance_m / 1000:.0f} km richiesti."
    )
    if rules.accepts_declared_task:
        reasons.append(
            "Percorso valutato come distanza in linea retta con partenza allo "
            "sgancio (§1.4.2d): per questa geometria la dichiarazione (pilota e "
            "identificativo dell'aliante) non deve contenere le coordinate dei "
            "punti (§2.3)."
        )

    if rules.requires_distance_from_takeoff:
        if from_takeoff < rules.min_distance_m:
            verdict = Verdict.FAIL
            reasons.append(
                f"Dal fix d'inizio della corsa di decollo il fix d'arrivo dista pero' solo "
                f"{from_takeoff / 1000:.2f} km, sotto i {rules.min_distance_m / 1000:.0f} km richiesti."
            )
        else:
            reasons.append(
                f"Distanza dal fix d'inizio della corsa di decollo: {from_takeoff / 1000:.2f} km, "
                "anch'essa oltre la soglia."
            )
    if loss.invalid:
        verdict = Verdict.FAIL
    reasons.append(_loss_of_height_reason(loss))
    return Requirement(
        code="distanza",
        title=f"Distanza: {rules.min_distance_m / 1000:.0f} km in linea retta dallo sgancio",
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
        "Geometria dichiarata: virate toccate nell'ordine dichiarato entrando nella "
        "zona di osservazione, partenza e arrivo su linee di 1 km perpendicolari "
        "alla prima e all'ultima tratta, attraversate nel verso della tratta "
        "(§1.2.12, §1.3.1a, §1.3.2b). Vale l'ultimo attraversamento della partenza "
        "dopo lo sgancio e prima della prima virata. Nel triangolo a 3 virate "
        "contano solo i lati fra le virate (§1.4.2h).",
        "Quota al passaggio delle linee interpolata fra il fix prima e quello "
        "dopo l'attraversamento (§2.4.3b).",
        "Con 1-3 virate il volo si valuta anche come distanza fino a 3 virate "
        "(§1.4.2f): virate in qualsiasi ordine, anche solo alcune delle dichiarate, "
        "partenza dichiarata o sgancio, arrivo dichiarato o un fix scelto dopo il "
        "volo (tabella §1.4.4). Vale la geometria con la distanza ufficiale "
        "migliore (§2.2); per un'insegna non e' mai inferiore ad andata e ritorno "
        "o triangolo sullo stesso volo.",
        "Virate: zona di osservazione a settore di 90 gradi con raggio illimitato, "
        "orientato sulle tratte rivendicate, oppure cilindro di 500 m (§1.2.6); "
        "basta un fix nella zona o un segmento fra due fix che la attraversa "
        "(§2.4.2c). Se l'orientamento del settore non e' determinato (arrivo a un "
        "fix, virata in linea retta) vale solo il cilindro.",
        "Distanza ufficiale: tratte fra i punti rivendicati, meno 1 km per ogni "
        "virata raggiunta solo col cilindro (§1.3.6) e meno la correzione per la "
        "perdita di quota (§1.3.7).",
        _loss_of_height_method(_uses_gnss(analysis)),
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

    # La perdita di quota si misura solo fra partenza e arrivo raggiunti.
    loss = (
        loss_of_height(check.distance_m, check.loss_of_height_m, _uses_gnss(analysis))
        if check.completed
        else None
    )
    distance = (
        loss.official_m - check.cylinder_correction_m if loss is not None else check.distance_m
    )
    verdict = _threshold_verdict(
        distance, rules.min_distance_m, band=rules.min_distance_m * RULES.marginal_ratio
    )
    reasons = [
        f"Percorso di {check.distance_m / 1000:.2f} km su "
        f"{len(check.waypoints) - 2} punti di virata, contro i "
        f"{required_km:.0f} km richiesti.",
        f"Percorso dichiarato: {check.declared_course.value}; geometria valutata: "
        f"{check.course.value}.",
    ]
    if check.unused:
        reasons.append(
            "Virate dichiarate non usate: "
            + ", ".join(f"'{w.name}'" for w in check.unused)
            + ". Lo SC3 ammette di rivendicare una, due o tre delle virate "
            "dichiarate (§1.4.2f): e' un'interpretazione, da confermare con l'OO."
        )
    start_finish_m = geodesic_distance_ll(
        check.task.start.lat, check.task.start.lon, check.task.finish.lat, check.task.finish.lon
    )
    if not check.closed and check.task.turnpoints and start_finish_m <= 1_000:
        reasons.append(
            f"Partenza e arrivo distano {start_finish_m:.0f} m ma non hanno le stesse "
            "coordinate: non e' un percorso chiuso (§1.2.11)."
        )
    if check.start_before_release:
        reasons.append(
            "La partenza e' stata attraversata solo prima dello sgancio: non conta, "
            "la prova inizia dopo lo sgancio (§1.3.1)."
        )

    if len(check.task.turnpoints) > rules.max_turnpoints:
        verdict = Verdict.FAIL
        reasons.append(
            f"Il percorso dichiara {len(check.task.turnpoints)} punti di virata, "
            f"oltre il massimo di {rules.max_turnpoints}."
        )

    if not check.completed:
        reasons.append(
            "Il percorso e' dichiarato correttamente ma la traccia non lo "
            "documenta: la prova vale solo se ogni punto e' stato effettivamente "
            "volato."
        )
    for waypoint in check.waypoints:
        if waypoint.reached and waypoint.point is not None:
            moment = waypoint.time or waypoint.point.time
            height = (
                f", quota {waypoint.altitude_m:.0f} m" if waypoint.altitude_m is not None else ""
            )
            reasons.append(
                f"{waypoint.label} '{waypoint.waypoint.name}': raggiunto alle "
                f"{moment:%H:%M:%S} UTC ({waypoint.zone}{height})."
            )
        else:
            verdict = Verdict.FAIL
            reasons.append(
                f"{waypoint.label} '{waypoint.waypoint.name}': NON raggiunto "
                f"({waypoint.zone}), avvicinamento minimo "
                f"{waypoint.closest_m / 1000:.2f} km."
            )

    if loss is not None:
        if loss.invalid:
            verdict = Verdict.FAIL
        reasons.append(_loss_of_height_reason(loss))
        if check.cylinder_correction_m:
            reasons.append(
                f"Correzione di {check.cylinder_correction_m / 1000:.0f} km per le virate "
                f"raggiunte solo col cilindro (§1.3.6): distanza ufficiale "
                f"{distance / 1000:.2f} km."
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


_VERDICT_RANK = {
    Verdict.FAIL: 0,
    Verdict.UNDETERMINED: 1,
    Verdict.MARGINAL: 2,
    Verdict.PASS: 3,
}


def check_best_distance(analysis: FlightAnalysis, rules: BadgeRules = GOLD) -> Requirement:
    """Distanza col percorso dichiarato e, in alternativa, in linea retta dallo sgancio.

    Per il §2.2 un volo vale per ogni prova di cui soddisfa i requisiti: un
    percorso dichiarato e non completato non esclude la linea retta dallo
    sgancio (§1.4.2d), che non richiede coordinate dichiarate (§2.3). Le
    distanze libere (§1.4.2i-l) non sono un'alternativa: valgono solo per i
    record (tabella §1.4.4).
    """
    declared = check_declared_distance(analysis, rules)
    if declared.verdict is Verdict.PASS:
        return declared
    straight = check_distance(analysis, rules)
    if _VERDICT_RANK[straight.verdict] > _VERDICT_RANK[declared.verdict]:
        straight.reasons = (
            [
                f"Percorso dichiarato: {declared.verdict.value} "
                f"({declared.measured}). Il volo vale comunque come distanza in "
                "linea retta dallo sgancio (§2.2, §1.4.2d)."
            ]
            + straight.reasons
            + [f"Percorso dichiarato — {reason}" for reason in declared.reasons]
        )
        straight.method = straight.method + [
            "Valutato anche il percorso dichiarato; vale la geometria con l'esito migliore."
        ]
        straight.title = (
            f"Distanza: {rules.min_distance_m / 1000:.0f} km, linea retta dallo sgancio"
        )
        return straight
    declared.reasons.append(
        f"In linea retta dallo sgancio (§1.4.2d): {straight.measured}, "
        f"{straight.verdict.value}."
    )
    return declared


def validate_badge(
    flight: Flight,
    analysis: FlightAnalysis,
    rules: BadgeRules = SILVER,
    internet_declaration: bool = False,
) -> ValidationReport:
    """Valuta i tre requisiti di un'insegna su un singolo volo.

    `internet_declaration` indica che il pilota ha usato una dichiarazione via
    internet, che sostituisce quella del registratore (§2.3a) e non e' nel file.
    """
    # Senza percorso dichiarato il volo si valuta come distanza in linea retta
    # con partenza allo sgancio (§1.4.2d), ammessa anche per l'oro (§2.2.2a).
    distance = (
        check_best_distance(analysis, rules)
        if rules.accepts_declared_task and analysis.task_check is not None
        else check_distance(analysis, rules)
    )
    requirements = [
        check_duration(analysis, rules),
        distance,
        check_height_gain(analysis, rules),
    ]
    for requirement in requirements:
        if requirement.verdict is Verdict.MARGINAL:
            requirement.reasons.append(
                f"Esito al limite: lo scarto dalla soglia e' entro l'incertezza di misura "
                f"({RULES.marginal_ratio:.1%}). Il §4.3.4b chiede di risolvere ogni dubbio "
                "a sfavore del pilota: senza una verifica dell'OO questo esito non vale "
                "per la richiesta."
            )
    if analysis.intermediate_stops:
        stops = ", ".join(
            f"{start.time:%H:%M:%S}-{end.time:%H:%M:%S}"
            for start, end in analysis.intermediate_stops
        )
        for requirement in requirements:
            if requirement.verdict in {Verdict.PASS, Verdict.MARGINAL}:
                requirement.verdict = Verdict.UNDETERMINED
            requirement.reasons.append(
                f"La traccia mostra l'aliante fermo dopo lo sgancio ({stops} UTC): "
                "possibile atterraggio intermedio, che il §2.4.5 esclude. La "
                "continuita' del volo va confermata dall'OO."
            )
    warnings: list[str] = list(analysis.notes)

    task = flight.task
    if internet_declaration:
        warnings.append(
            "Dichiarazione via internet indicata dall'utente: sostituisce quella del "
            "registratore (§2.3a) e non e' verificabile dal file. Va allegata alla "
            "richiesta (§2.4b) con pilota, identificativo dell'aliante, punti "
            "richiesti, nome dell'OO e tipo e numero di serie di ogni registratore."
        )
    elif task is not None and task.declared_at is not None:
        # La dichiarazione deve precedere il decollo (§1.1.4), non il primo fix:
        # il registratore puo' essere acceso a terra prima di dichiarare.
        if task.declared_at > analysis.takeoff.time:
            warnings.append(
                f"La dichiarazione del percorso porta l'orario "
                f"{task.declared_at:%H:%M:%S} UTC, successivo al decollo delle "
                f"{analysis.takeoff.time:%H:%M:%S} UTC: va fatta prima del volo (§1.1.4)."
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
            f"ENL o MOP oltre soglia dopo lo sgancio (ENL massimo {analysis.max_enl}): "
            "possibile uso del motore, vietato durante le prove (§2.4.5). Se "
            "l'aliante ha un motore indicarlo (--motorglider o casella nella pagina "
            "web): le prove finiranno al suo avvio."
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
        documentation=check_headers(flight),
    )


def validate_silver(flight: Flight, analysis: FlightAnalysis) -> ValidationReport:
    """Valuta i tre requisiti dell'insegna d'argento su un singolo volo."""
    return validate_badge(flight, analysis, SILVER)


def validate_gold(flight: Flight, analysis: FlightAnalysis) -> ValidationReport:
    """Valuta i tre requisiti dell'insegna d'oro su un singolo volo."""
    return validate_badge(flight, analysis, GOLD)
