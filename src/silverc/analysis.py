"""Estrazione dei punti notevoli del volo dalla traccia IGC."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from silverc.documentation import RecorderInfo, RecorderKind, classify_recorder
from silverc.igc import DeclaredTask, Fix, Flight, Waypoint
from silverc.rules import PARAMS

logger = logging.getLogger(__name__)

try:
    from geographiclib.geodesic import Geodesic

    _GEODESIC_MODEL = "WGS84 (geographiclib)"
except ImportError:  # pragma: no cover - dipende dall'ambiente
    Geodesic = None
    _GEODESIC_MODEL = "sfera FAI r=6371000 m (geographiclib assente)"

_FAI_SPHERE_RADIUS_M = 6_371_000.0

RELEASE_SOURCE_MANUAL = "dichiarato dall'utente"
RELEASE_SOURCE_HEURISTIC = "euristica sulla traccia"


@dataclass(frozen=True)
class Point:
    """Un fix con il suo indice nella traccia."""

    index: int
    fix: Fix

    @property
    def time(self) -> datetime:
        return self.fix.time


@dataclass
class HeightGain:
    low: Point | None
    high: Point | None
    gain_m: float


@dataclass
class FinishFix:
    """Fix d'arrivo candidato con le distanze dai due punti di riferimento."""

    point: Point
    distance_m: float
    from_takeoff_m: float
    loss_of_height_m: float


@dataclass
class FlightAnalysis:
    takeoff: Point
    landing: Point
    release: Point
    release_source: str
    release_confidence: str
    tow_climb_m: float
    height_gain: HeightGain
    farthest: Point
    distance_m: float
    distance_from_takeoff_m: float
    geodesic_model: str
    loss_of_height_m: float
    altitude_source: str
    engine_suspected: bool
    max_enl: int | None
    notes: list[str]
    task_check: "TaskCheck | None" = None
    recorder: RecorderInfo | None = None
    altitude_usable: bool = True
    calibrated: bool = False
    balanced_finish: FinishFix | None = None

    @property
    def duration_s(self) -> float:
        return (self.landing.time - self.release.time).total_seconds()


def geodesic_distance_ll(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    if Geodesic is not None:
        return float(Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)["s12"])
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _FAI_SPHERE_RADIUS_M * math.asin(math.sqrt(h))


def geodesic_distance_m(a: Fix, b: Fix) -> tuple[float, str]:
    """Distanza fra due fix; restituisce anche il modello geodetico usato."""
    return geodesic_distance_ll(a.lat, a.lon, b.lat, b.lon), _GEODESIC_MODEL


def _fast_distance_ll(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approssimazione equirettangolare, per i confronti interni alla traccia.

    Errore trascurabile sotto il chilometro ed evita centinaia di migliaia di
    chiamate al calcolo geodetico completo su una traccia a 1 Hz.
    """
    mean_lat = math.radians((lat1 + lat2) / 2.0)
    dx = math.radians(lon2 - lon1) * math.cos(mean_lat)
    dy = math.radians(lat2 - lat1)
    return math.hypot(dx, dy) * _FAI_SPHERE_RADIUS_M


def _fast_distance_m(a: Fix, b: Fix) -> float:
    return _fast_distance_ll(a.lat, a.lon, b.lat, b.lon)


def _sampling_stride(fixes: list[Fix], window_s: int) -> int:
    span = (fixes[-1].time - fixes[0].time).total_seconds()
    if span <= 0 or len(fixes) < 2:
        return 1
    interval = span / (len(fixes) - 1)
    per_window = window_s / max(interval, 1e-6)
    return max(1, int(per_window // 12))


def _moving_flags(fixes: list[Fix]) -> list[bool]:
    """Per ogni fix: l'aliante si allontana dalla posizione entro la finestra?"""
    stride = _sampling_stride(fixes, PARAMS.stationary_window_s)
    flags = [False] * len(fixes)
    for i, fix in enumerate(fixes):
        limit = fix.time.timestamp() + PARAMS.stationary_window_s
        j = i + 1
        while j < len(fixes) and fixes[j].time.timestamp() <= limit:
            if _fast_distance_m(fix, fixes[j]) >= PARAMS.stationary_radius_m:
                flags[i] = True
                break
            j += stride
    return flags


def _altitude(fix: Fix, use_gnss: bool) -> int | None:
    return fix.gnss_alt if use_gnss else fix.pressure_alt


def detect_takeoff(fixes: list[Fix], moving: list[bool] | None = None) -> Point:
    """Primo fix a partire dal quale l'aliante lascia la posizione di sosta."""
    flags = moving if moving is not None else _moving_flags(fixes)
    for i, flag in enumerate(flags):
        if flag:
            return Point(i, fixes[i])
    return Point(0, fixes[0])


def detect_landing(fixes: list[Fix], moving: list[bool] | None = None) -> Point:
    """Primo fix della sosta finale: i successivi sono registrazione a terra."""
    flags = moving if moving is not None else _moving_flags(fixes)
    last = len(fixes) - 1
    for i in range(last, -1, -1):
        if flags[i]:
            return Point(min(i + 1, last), fixes[min(i + 1, last)])
    return Point(last, fixes[last])


def detect_release(fixes: list[Fix], takeoff: Point, use_gnss: bool) -> tuple[Point, str, float]:
    """Euristica di sgancio: fine della salita continua iniziale.

    Cerca il primo massimo di quota dopo il decollo seguito, entro una breve
    finestra, da una discesa significativa. Funziona sul traino aereo e sul
    verricello; non distingue un decollo autonomo a motore.
    """
    peak_alt: int | None = None
    peak_point: Point | None = None
    takeoff_alt = _altitude(takeoff.fix, use_gnss)
    for i in range(takeoff.index, len(fixes)):
        alt = _altitude(fixes[i], use_gnss)
        if alt is None:
            continue
        if peak_alt is None or alt > peak_alt:
            peak_alt, peak_point = alt, Point(i, fixes[i])
            continue
        if peak_point is None or peak_alt - alt < PARAMS.release_drop_m:
            continue
        climb = peak_alt - (takeoff_alt if takeoff_alt is not None else peak_alt)
        confidence = "alta" if climb >= PARAMS.min_tow_climb_m else "bassa"
        logger.debug(
            "Sgancio euristico: t=%s, quota=%dm, salita al traino=%dm, confidenza=%s",
            peak_point.time.strftime("%H:%M:%S"),
            peak_alt,
            climb,
            confidence,
        )
        return peak_point, confidence, float(climb)
    return takeoff, "nulla", 0.0


def find_farthest_point(fixes: list[Fix], origin: Fix, start_index: int, end_index: int) -> Point:
    """Punto della traccia piu' lontano dall'origine, fra due indici inclusi.

    Il candidato si sceglie con la distanza approssimata (una passata su tutti
    i fix); la distanza definitiva sul candidato si calcola poi in geodetica.
    """
    best_index = start_index
    best_distance = -1.0
    for i in range(start_index, min(end_index + 1, len(fixes))):
        distance = _fast_distance_m(origin, fixes[i])
        if distance > best_distance:
            best_distance, best_index = distance, i
    return Point(best_index, fixes[best_index])


def find_balanced_point(
    fixes: list[Fix], release: Fix, takeoff: Fix, start_index: int, end_index: int
) -> Point:
    """Fix che massimizza la minore fra la distanza dallo sgancio e dal decollo.

    E' il miglior candidato per la distanza d'argento (§2.2.1a), che chiede
    lo stesso fix d'arrivo lontano da entrambi: il fix piu' lontano dallo
    sgancio puo' non esserlo abbastanza dal decollo.
    """
    best_index = start_index
    best_distance = -1.0
    for i in range(start_index, min(end_index + 1, len(fixes))):
        distance = min(_fast_distance_m(release, fixes[i]), _fast_distance_m(takeoff, fixes[i]))
        if distance > best_distance:
            best_distance, best_index = distance, i
    return Point(best_index, fixes[best_index])


@dataclass
class WaypointCheck:
    """Esito del passaggio su un punto del percorso dichiarato."""

    waypoint: Waypoint
    label: str
    radius_m: float
    reached: bool
    closest_m: float
    point: Point | None


@dataclass
class TaskCheck:
    """Esito complessivo del percorso dichiarato."""

    task: DeclaredTask
    waypoints: list[WaypointCheck]
    distance_m: float
    loss_of_height_m: float

    @property
    def completed(self) -> bool:
        return all(w.reached for w in self.waypoints)

    @property
    def missed(self) -> list[WaypointCheck]:
        return [w for w in self.waypoints if not w.reached]


def _task_labels(task: DeclaredTask) -> list[str]:
    return (
        ["Partenza"]
        + [f"Virata {i}" for i in range(1, len(task.turnpoints) + 1)]
        + ["Arrivo"]
    )


def declared_task_distance_m(task: DeclaredTask) -> float:
    """Somma delle tratte fra i punti dichiarati."""
    points = task.points
    return sum(
        geodesic_distance_ll(a.lat, a.lon, b.lat, b.lon)
        for a, b in zip(points, points[1:])
    )


def verify_declared_task(
    fixes: list[Fix],
    task: DeclaredTask,
    start_index: int,
    end_index: int,
    use_gnss: bool = False,
) -> TaskCheck:
    """Verifica che la traccia tocchi i punti dichiarati **nell'ordine previsto**.

    Ogni punto e' considerato raggiunto quando un fix cade dentro la sua zona
    di osservazione; la ricerca del punto successivo riparte da li'.
    """
    labels = _task_labels(task)
    points = task.points
    last_index = min(end_index, len(fixes) - 1)
    checks: list[WaypointCheck] = []
    cursor = start_index

    for order, (waypoint, label) in enumerate(zip(points, labels)):
        is_edge = order in (0, len(points) - 1)
        radius = (
            PARAMS.start_finish_zone_radius_m if is_edge else PARAMS.turnpoint_zone_radius_m
        )
        reached_at: Point | None = None
        closest = float("inf")
        closest_at: Point | None = None
        for i in range(cursor, last_index + 1):
            distance = _fast_distance_ll(waypoint.lat, waypoint.lon, fixes[i].lat, fixes[i].lon)
            if distance < closest:
                closest, closest_at = distance, Point(i, fixes[i])
            if distance <= radius:
                reached_at = Point(i, fixes[i])
                break
        checks.append(
            WaypointCheck(
                waypoint=waypoint,
                label=label,
                radius_m=radius,
                reached=reached_at is not None,
                closest_m=closest if closest != float("inf") else 0.0,
                point=reached_at or closest_at,
            )
        )
        if reached_at is not None:
            cursor = reached_at.index

    start_check, finish_check = checks[0], checks[-1]
    loss = 0.0
    if start_check.reached and finish_check.reached and start_check.point and finish_check.point:
        start_alt = _altitude(start_check.point.fix, use_gnss)
        finish_alt = _altitude(finish_check.point.fix, use_gnss)
        if start_alt is not None and finish_alt is not None:
            loss = float(start_alt - finish_alt)

    result = TaskCheck(
        task=task,
        waypoints=checks,
        distance_m=declared_task_distance_m(task),
        loss_of_height_m=loss,
    )
    logger.debug(
        "Percorso dichiarato: %d punti, distanza=%.1fkm, completato=%s, mancati=%s",
        len(checks),
        result.distance_m / 1000,
        result.completed,
        [w.label for w in result.missed],
    )
    return result


def parse_release_time(value: str, flight: Flight) -> datetime:
    """Orario di sgancio HH:MM[:SS] UTC indicato dall'utente, alla data del volo."""
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
        moment = parsed.replace(tzinfo=timezone.utc)
        day = flight.flight_date or (flight.fixes[0].time.date() if flight.fixes else None)
        if day is not None:
            moment = moment.replace(year=day.year, month=day.month, day=day.day)
        return moment
    raise ValueError("orario di sgancio atteso come HH:MM:SS (UTC)")


def find_point_at(fixes: list[Fix], moment: datetime) -> Point:
    """Fix piu' vicino a un istante dato."""
    best = min(range(len(fixes)), key=lambda i: abs((fixes[i].time - moment).total_seconds()))
    return Point(best, fixes[best])


def compute_height_gain(
    fixes: list[Fix], start_index: int, use_gnss: bool, end_index: int | None = None
) -> HeightGain:
    """Massimo guadagno di quota con punto basso precedente al punto alto."""
    low: Point | None = None
    running_low: Point | None = None
    high: Point | None = None
    best = 0.0
    stop = len(fixes) if end_index is None else min(end_index + 1, len(fixes))
    for i in range(start_index, stop):
        alt = _altitude(fixes[i], use_gnss)
        if alt is None:
            continue
        current = Point(i, fixes[i])
        running_alt = _altitude(running_low.fix, use_gnss) if running_low else None
        if running_alt is None or alt < running_alt:
            running_low = current
            running_alt = alt
        gain = alt - running_alt
        if gain > best:
            best, low, high = float(gain), running_low, current
    return HeightGain(low=low, high=high, gain_m=best)


def analyse(
    flight: Flight,
    release_time: datetime | None = None,
    use_gnss_altitude: bool = False,
    recorder_kind: RecorderKind | None = None,
    calibrated: bool = False,
) -> FlightAnalysis:
    """Calcola tutte le grandezze necessarie alla validazione.

    `recorder_kind` forza il tipo di registratore; se assente si ricava dal file.
    `calibrated` indica che il registratore ha dati di taratura barometrica:
    solo allora si usa la quota barometrica senza margine (§2.4.6).
    """
    started = time.perf_counter()
    fixes = flight.fixes
    notes: list[str] = []
    recorder = classify_recorder(flight, recorder_kind)

    baro = [f.pressure_alt for f in fixes if f.pressure_alt is not None]
    gnss = [f.gnss_alt for f in fixes if f.gnss_alt is not None]
    altitude_usable = True
    if not use_gnss_altitude and not calibrated:
        # §2.4.6a: senza dati di taratura, FR o PR che sia, vale il §2.4.3c:
        # quota GNSS con un margine di 100 m su tutti i requisiti di quota.
        use_gnss_altitude = True
        notes.append(
            "Nessun dato di taratura barometrica dichiarato: usata la quota GNSS "
            "con il margine di 100 m sui requisiti di quota (§2.4.6a, §2.4.3c)."
        )
    elif not use_gnss_altitude and (
        not baro or max(baro) - min(baro) < PARAMS.min_barometric_spread_m
    ):
        use_gnss_altitude = True
        notes.append(
            "Quota barometrica assente o costante (campo non compilato dal "
            "logger): usata la quota GNSS con il margine di 100 m (§2.4.3c)."
        )
    if use_gnss_altitude and (not gnss or max(gnss) - min(gnss) < PARAMS.min_barometric_spread_m):
        altitude_usable = False
        notes.append(
            "Quota GNSS assente o costante: senza una quota barometrica tarata "
            "i requisiti di quota non sono determinabili."
        )
    altitude_source = "GNSS" if use_gnss_altitude else "barometrica (ISA 1013.25 hPa)"

    moving = _moving_flags(fixes)
    takeoff = detect_takeoff(fixes, moving)
    landing = detect_landing(fixes, moving)

    if release_time is not None:
        release = find_point_at(fixes, release_time)
        release_source, confidence, tow_climb = RELEASE_SOURCE_MANUAL, "alta", 0.0
        delta = abs((release.time - release_time).total_seconds())
        if delta > PARAMS.max_release_time_mismatch_s:
            confidence = "bassa"
            notes.append(
                f"L'orario di sgancio indicato dista {delta:.0f}s dal fix piu' "
                "vicino: verificare che si riferisca a questo volo."
            )
        if release.index < takeoff.index:
            confidence = "bassa"
            notes.append(
                "L'orario di sgancio indicato precede il decollo rilevato "
                f"({takeoff.time:%H:%M:%S} UTC)."
            )
    else:
        release, confidence, tow_climb = detect_release(fixes, takeoff, use_gnss_altitude)
        release_source = RELEASE_SOURCE_HEURISTIC

    gain = compute_height_gain(fixes, release.index, use_gnss_altitude, landing.index)

    farthest = find_farthest_point(fixes, release.fix, release.index, landing.index)
    distance, model = geodesic_distance_m(release.fix, farthest.fix)
    distance_from_takeoff, _ = geodesic_distance_m(takeoff.fix, farthest.fix)

    release_alt = _altitude(release.fix, use_gnss_altitude)
    far_alt = _altitude(farthest.fix, use_gnss_altitude)
    loss = float(release_alt - far_alt) if release_alt is not None and far_alt is not None else 0.0

    balanced = find_balanced_point(fixes, release.fix, takeoff.fix, release.index, landing.index)
    balanced_alt = _altitude(balanced.fix, use_gnss_altitude)
    balanced_finish = FinishFix(
        point=balanced,
        distance_m=geodesic_distance_m(release.fix, balanced.fix)[0],
        from_takeoff_m=geodesic_distance_m(takeoff.fix, balanced.fix)[0],
        loss_of_height_m=(
            float(release_alt - balanced_alt)
            if release_alt is not None and balanced_alt is not None
            else 0.0
        ),
    )

    enl_values = [f.enl for f in fixes[release.index : landing.index + 1] if f.enl is not None]
    max_enl = max(enl_values) if enl_values else None
    engine_suspected = bool(
        max_enl is not None and max_enl >= PARAMS.enl_running_threshold
    )

    analysis = FlightAnalysis(
        takeoff=takeoff,
        landing=landing,
        release=release,
        release_source=release_source,
        release_confidence=confidence,
        tow_climb_m=tow_climb,
        height_gain=gain,
        farthest=farthest,
        distance_m=distance,
        distance_from_takeoff_m=distance_from_takeoff,
        geodesic_model=model,
        loss_of_height_m=loss,
        altitude_source=altitude_source,
        engine_suspected=engine_suspected,
        max_enl=max_enl,
        notes=notes,
        task_check=(
            verify_declared_task(
                fixes, flight.task, release.index, landing.index, use_gnss_altitude
            )
            if flight.task is not None
            else None
        ),
        recorder=recorder,
        altitude_usable=altitude_usable,
        calibrated=calibrated,
        balanced_finish=balanced_finish,
    )
    logger.debug(
        "Analisi volo: fixes=%d, sgancio=%s (%s), atterraggio=%s | durata=%.0fs, "
        "guadagno=%.0fm, distanza=%.0fm | %.1fms",
        len(fixes),
        release.time.strftime("%H:%M:%S"),
        release_source,
        landing.time.strftime("%H:%M:%S"),
        analysis.duration_s,
        gain.gain_m,
        distance,
        (time.perf_counter() - started) * 1000,
    )
    return analysis
