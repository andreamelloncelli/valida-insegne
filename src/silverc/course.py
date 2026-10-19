"""Percorsi dichiarati dello SC3 (§1.4.2d-h): riconoscimento e verifica sulla traccia."""

from __future__ import annotations

import bisect
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from itertools import permutations

from silverc.geo import (
    Point,
    altitude,
    fast_distance_ll,
    geodesic_distance_ll,
    loss_of_height,
)
from silverc.igc import DeclaredTask, Fix, Waypoint
from silverc.rules import PARAMS, RULES

logger = logging.getLogger(__name__)

# I record C scrivono le coordinate al millesimo di primo (~2 m): due punti
# "identici" (§1.2.11) hanno le stesse cifre, quindi la stessa coordinata.
_IDENTICAL_DEG = 1e-6

# §1.4.2f: distanza via una, due o tre virate dichiarate.
_MAX_THREE_TP = 3

_EARTH_RADIUS_M = 6_371_000.0


class CourseType(str, Enum):
    GOAL = "meta (§1.4.2e)"
    THREE_TP = "fino a 3 virate (§1.4.2f)"
    OUT_AND_RETURN = "andata e ritorno (§1.4.2g)"
    TRIANGLE = "triangolo (§1.4.2h)"


def same_point(a: Waypoint, b: Waypoint) -> bool:
    """Coordinate identiche nel senso del §1.2.11."""
    return abs(a.lat - b.lat) < _IDENTICAL_DEG and abs(a.lon - b.lon) < _IDENTICAL_DEG


def is_closed(task: DeclaredTask) -> bool:
    """Percorso chiuso: partenza e arrivo con le stesse coordinate (§1.2.11)."""
    return same_point(task.start, task.finish)


def classify_course(task: DeclaredTask) -> CourseType:
    """Tipo di percorso dal numero di virate e dalla chiusura (§1.4.2e-h).

    Senza virate e' una meta. Un percorso chiuso con una virata e' un andata e
    ritorno, con due o tre un triangolo. Ogni altro percorso con virate e'
    una distanza fino a 3 virate.
    """
    turnpoints = len(task.turnpoints)
    if turnpoints == 0:
        return CourseType.GOAL
    if is_closed(task):
        return CourseType.OUT_AND_RETURN if turnpoints == 1 else CourseType.TRIANGLE
    return CourseType.THREE_TP


@dataclass
class WaypointCheck:
    """Esito del passaggio su un punto del percorso."""

    waypoint: Waypoint
    label: str
    zone: str
    reached: bool
    closest_m: float
    point: Point | None
    # Istante e quota del passaggio: interpolati sulle linee (§2.4.3b).
    time: datetime | None = None
    altitude_m: float | None = None


@dataclass
class TaskCheck:
    """Esito del percorso dichiarato, nella geometria che da' il risultato migliore."""

    task: DeclaredTask
    waypoints: list[WaypointCheck]
    distance_m: float
    loss_of_height_m: float
    # Geometria valutata: quella dichiarata o la distanza fino a 3 virate.
    course: CourseType = CourseType.THREE_TP
    declared_course: CourseType = CourseType.THREE_TP
    closed: bool = False
    # La partenza e' stata attraversata solo prima dello sgancio (§1.3.1).
    start_before_release: bool = False
    # Virate dichiarate ma non usate nella geometria valutata (§1.4.2f).
    unused: list[Waypoint] = field(default_factory=list)

    @property
    def completed(self) -> bool:
        return all(w.reached for w in self.waypoints)

    @property
    def missed(self) -> list[WaypointCheck]:
        return [w for w in self.waypoints if not w.reached]


@dataclass(frozen=True)
class Crossing:
    """Attraversamento di una linea fra due fix consecutivi."""

    point: Point
    time: datetime
    altitude_m: float | None


def _path_m(points: list[tuple[float, float]]) -> float:
    return sum(
        geodesic_distance_ll(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:])
    )


def declared_task_distance_m(task: DeclaredTask) -> float:
    """Distanza del percorso dichiarato.

    Nel triangolo a 3 virate e' la somma dei lati fra le virate (§1.4.2h); in
    ogni altro percorso la somma delle tratte fra partenza, virate e arrivo.
    """
    if classify_course(task) is CourseType.TRIANGLE and len(task.turnpoints) == 3:
        corners = [(w.lat, w.lon) for w in task.turnpoints]
        return _path_m(corners + corners[:1])
    return _path_m([(w.lat, w.lon) for w in task.points])


def _local_xy(origin: Waypoint, lat: float, lon: float) -> tuple[float, float]:
    """Proiezione piana locale (metri est, nord) attorno a `origin`."""
    x = math.radians(lon - origin.lon) * math.cos(math.radians(origin.lat)) * _EARTH_RADIUS_M
    y = math.radians(lat - origin.lat) * _EARTH_RADIUS_M
    return x, y


def _interpolate(a: int | None, b: int | None, fraction: float) -> float | None:
    if a is None or b is None:
        return None
    return a + (b - a) * fraction


def line_crossings(
    fixes: list[Fix],
    center: Waypoint,
    leg_from: Waypoint,
    leg_to: Waypoint,
    start: int,
    end: int,
    use_gnss: bool,
) -> list[Crossing]:
    """Attraversamenti della linea di partenza o d'arrivo (§1.2.12).

    La linea e' lunga `RULES.start_finish_line_m`, centrata su `center` e
    perpendicolare alla tratta `leg_from` -> `leg_to`; vale solo
    l'attraversamento nel verso della tratta (§1.3.1a, §1.3.2b). Istante e
    quota si interpolano linearmente fra i due fix (§2.4.3b).
    """
    lx, ly = _local_xy(center, leg_to.lat, leg_to.lon)
    fx, fy = _local_xy(center, leg_from.lat, leg_from.lon)
    dx, dy = lx - fx, ly - fy
    length = math.hypot(dx, dy)
    if length < 1.0:
        return []
    ux, uy = dx / length, dy / length
    half = RULES.start_finish_line_m / 2
    crossings: list[Crossing] = []
    previous: tuple[float, float] | None = None
    for i in range(max(start, 0), min(end, len(fixes) - 1) + 1):
        x, y = _local_xy(center, fixes[i].lat, fixes[i].lon)
        along, across = x * ux + y * uy, -x * uy + y * ux
        if previous is not None and previous[0] < 0 <= along:
            fraction = -previous[0] / (along - previous[0])
            if abs(previous[1] + (across - previous[1]) * fraction) <= half:
                before, after = fixes[i - 1], fixes[i]
                crossings.append(
                    Crossing(
                        point=Point(i, after),
                        time=before.time + (after.time - before.time) * fraction,
                        altitude_m=_interpolate(
                            altitude(before, use_gnss), altitude(after, use_gnss), fraction
                        ),
                    )
                )
        previous = (along, across)
    return crossings


def _segment_distance(origin: Waypoint, a: Fix, b: Fix) -> float:
    """Distanza minima da `origin` del segmento fra due fix, nel piano locale."""
    ax, ay = _local_xy(origin, a.lat, a.lon)
    bx, by = _local_xy(origin, b.lat, b.lon)
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    t = 0.0 if span == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / span))
    return math.hypot(ax + t * dx, ay + t * dy)


def turnpoint_indices(fixes: list[Fix], waypoint: Waypoint, start: int, end: int) -> list[int]:
    """Indici dei fix con cui la virata e' raggiunta (§2.4.2c).

    Basta un fix dentro la zona di osservazione o un segmento fra due fix
    consecutivi che la attraversa: con fix radi un passaggio reale cadrebbe
    altrimenti fra due fix esterni. In quel caso conta il secondo fix.
    """
    radius = PARAMS.turnpoint_zone_radius_m
    indices: list[int] = []
    previous: float | None = None
    for i in range(start, end + 1):
        distance = fast_distance_ll(waypoint.lat, waypoint.lon, fixes[i].lat, fixes[i].lon)
        if distance <= radius:
            indices.append(i)
        elif previous is not None:
            span = fast_distance_ll(fixes[i - 1].lat, fixes[i - 1].lon, fixes[i].lat, fixes[i].lon)
            # Un segmento non puo' avvicinarsi al punto piu' di quanto dica la
            # disuguaglianza triangolare: si evita il calcolo quasi sempre.
            if min(distance, previous) - span <= radius and (
                _segment_distance(waypoint, fixes[i - 1], fixes[i]) <= radius
            ):
                indices.append(i)
        previous = distance
    return indices


def _first_after(indices: list[int], cursor: int) -> int | None:
    position = bisect.bisect_left(indices, cursor)
    return indices[position] if position < len(indices) else None


def _first_crossing_after(crossings: list[Crossing], cursor: int) -> Crossing | None:
    return next((c for c in crossings if c.point.index >= cursor), None)


def _last_crossing_until(crossings: list[Crossing], limit: int) -> Crossing | None:
    return next((c for c in reversed(crossings) if c.point.index <= limit), None)


def _closest(fixes: list[Fix], waypoint: Waypoint, start: int, end: int) -> tuple[float, Point | None]:
    best, best_at = float("inf"), None
    for i in range(start, end + 1):
        distance = fast_distance_ll(waypoint.lat, waypoint.lon, fixes[i].lat, fixes[i].lon)
        if distance < best:
            best, best_at = distance, Point(i, fixes[i])
    return (best if best_at is not None else 0.0), best_at


def _line_zone() -> str:
    return f"linea di {RULES.start_finish_line_m:.0f} m"


def _cylinder_zone() -> str:
    return f"cilindro di {PARAMS.turnpoint_zone_radius_m:.0f} m"


def _crossed(waypoint: Waypoint, label: str, crossing: Crossing) -> WaypointCheck:
    return WaypointCheck(
        waypoint=waypoint,
        label=label,
        zone=_line_zone(),
        reached=True,
        closest_m=fast_distance_ll(
            waypoint.lat, waypoint.lon, crossing.point.fix.lat, crossing.point.fix.lon
        ),
        point=crossing.point,
        time=crossing.time,
        altitude_m=crossing.altitude_m,
    )


def _at_fix(waypoint: Waypoint, label: str, point: Point, zone: str, use_gnss: bool) -> WaypointCheck:
    alt = altitude(point.fix, use_gnss)
    return WaypointCheck(
        waypoint=waypoint,
        label=label,
        zone=zone,
        reached=True,
        closest_m=fast_distance_ll(waypoint.lat, waypoint.lon, point.fix.lat, point.fix.lon),
        point=point,
        time=point.time,
        altitude_m=float(alt) if alt is not None else None,
    )


def _missed(
    fixes: list[Fix], waypoint: Waypoint, label: str, zone: str, start: int, end: int
) -> WaypointCheck:
    closest, closest_at = _closest(fixes, waypoint, start, end)
    return WaypointCheck(
        waypoint=waypoint,
        label=label,
        zone=zone,
        reached=False,
        closest_m=closest,
        point=closest_at,
    )


def _loss(waypoints: list[WaypointCheck]) -> float:
    start, finish = waypoints[0].altitude_m, waypoints[-1].altitude_m
    return float(start - finish) if start is not None and finish is not None else 0.0


def _verify_in_order(
    fixes: list[Fix],
    task: DeclaredTask,
    release: Point,
    end_index: int,
    use_gnss: bool,
) -> TaskCheck:
    """Percorso dichiarato volato nell'ordine dichiarato, fra le linee dichiarate."""
    points = task.points
    last_index = min(end_index, len(fixes) - 1)
    start_line = line_crossings(
        fixes, task.start, points[0], points[1], release.index, last_index, use_gnss
    )
    finish_line = line_crossings(
        fixes, task.finish, points[-2], points[-1], release.index, last_index, use_gnss
    )
    first_start = start_line[0] if start_line else None
    cursor = first_start.point.index if first_start else release.index

    turnpoints: list[WaypointCheck] = []
    passages: list[int] = []
    for number, waypoint in enumerate(task.turnpoints, start=1):
        label = f"Virata {number}"
        zone = turnpoint_indices(fixes, waypoint, cursor, last_index)
        if not zone:
            turnpoints.append(_missed(fixes, waypoint, label, _cylinder_zone(), cursor, last_index))
            continue
        turnpoints.append(
            _at_fix(waypoint, label, Point(zone[0], fixes[zone[0]]), _cylinder_zone(), use_gnss)
        )
        passages.append(zone[0])
        cursor = zone[0]

    finish = _first_crossing_after(finish_line, cursor + 1)
    # Vale l'ultimo attraversamento della partenza prima della prima virata
    # (o dell'arrivo, in una meta).
    limit = passages[0] if passages else (finish.point.index if finish else last_index)
    start = _last_crossing_until(start_line, limit)
    start_check = (
        _crossed(task.start, "Partenza", start)
        if start is not None
        else _missed(fixes, task.start, "Partenza", _line_zone(), release.index, last_index)
    )
    finish_check = (
        _crossed(task.finish, "Arrivo", finish)
        if finish is not None
        else _missed(fixes, task.finish, "Arrivo", _line_zone(), cursor, last_index)
    )
    waypoints = [start_check, *turnpoints, finish_check]
    start_before_release = start is None and bool(
        line_crossings(fixes, task.start, points[0], points[1], 0, release.index, use_gnss)
    )
    declared = classify_course(task)
    return TaskCheck(
        task=task,
        waypoints=waypoints,
        distance_m=declared_task_distance_m(task),
        loss_of_height_m=_loss(waypoints) if start and finish else 0.0,
        course=declared,
        declared_course=declared,
        closed=is_closed(task),
        start_before_release=start_before_release,
    )


def _fix_waypoint(point: Point, name: str) -> Waypoint:
    return Waypoint(point.fix.lat, point.fix.lon, f"{name} {point.time:%H:%M:%S}")


def _best_finish_fix(
    fixes: list[Fix],
    last: Waypoint,
    prefix_m: float,
    start_alt: float | None,
    after: int,
    end: int,
    use_gnss: bool,
) -> Point:
    """Fix d'arrivo (§1.2.10c) dopo l'ultima virata col miglior esito ufficiale."""
    best_key: tuple[bool, float] | None = None
    best = after
    for i in range(after, end + 1):
        alt = altitude(fixes[i], use_gnss)
        loss = float(start_alt - alt) if start_alt is not None and alt is not None else 0.0
        check = loss_of_height(
            prefix_m + fast_distance_ll(last.lat, last.lon, fixes[i].lat, fixes[i].lon),
            loss,
            use_gnss,
        )
        key = (not check.invalid, check.official_m)
        if best_key is None or key > best_key:
            best_key, best = key, i
    return Point(best, fixes[best])


def _three_tp_candidates(
    fixes: list[Fix],
    task: DeclaredTask,
    release: Point,
    end_index: int,
    use_gnss: bool,
) -> list[TaskCheck]:
    """Valutazioni come distanza fino a 3 virate (§1.4.2f).

    Le virate si girano in qualsiasi ordine e se ne possono rivendicare una,
    due o tre fra le dichiarate; si parte dalla linea di partenza dichiarata o
    dallo sgancio e si arriva alla linea d'arrivo dichiarata o a un fix
    (tabella §1.4.4). Le linee sono perpendicolari alla prima e all'ultima
    tratta rivendicate, quindi cambiano con la sequenza.
    """
    last_index = min(end_index, len(fixes) - 1)
    tp_zones = [
        turnpoint_indices(fixes, tp, release.index, last_index) for tp in task.turnpoints
    ]
    start_lines: dict[int, list[Crossing]] = {}
    finish_lines: dict[int, list[Crossing]] = {}
    declared = classify_course(task)
    candidates: list[TaskCheck] = []

    for size in range(1, len(task.turnpoints) + 1):
        for sequence in permutations(range(len(task.turnpoints)), size):
            turnpoints = [task.turnpoints[tp] for tp in sequence]
            first, last = sequence[0], sequence[-1]
            if first not in start_lines:
                start_lines[first] = line_crossings(
                    fixes, task.start, task.start, task.turnpoints[first],
                    release.index, last_index, use_gnss,
                )
            if last not in finish_lines:
                finish_lines[last] = line_crossings(
                    fixes, task.finish, task.turnpoints[last], task.finish,
                    release.index, last_index, use_gnss,
                )
            for from_release in (True, False):
                if from_release:
                    cursor = release.index
                else:
                    first_start = _first_crossing_after(start_lines[first], release.index)
                    if first_start is None:
                        continue
                    cursor = first_start.point.index
                passages: list[int] = []
                search_from = cursor
                for tp in sequence:
                    found = _first_after(tp_zones[tp], search_from)
                    if found is None:
                        break
                    passages.append(found)
                    cursor, search_from = found, found + 1
                if len(passages) < len(sequence):
                    continue
                if from_release:
                    start_check = _at_fix(
                        _fix_waypoint(release, "SGANCIO"), "Sgancio", release, "sgancio", use_gnss
                    )
                else:
                    start = _last_crossing_until(start_lines[first], passages[0])
                    start_check = _crossed(task.start, "Partenza", start)
                prefix = _path_m(
                    [(start_check.waypoint.lat, start_check.waypoint.lon)]
                    + [(w.lat, w.lon) for w in turnpoints]
                )
                tp_checks = [
                    _at_fix(w, f"Virata {k}", Point(i, fixes[i]), _cylinder_zone(), use_gnss)
                    for k, (w, i) in enumerate(zip(turnpoints, passages), start=1)
                ]

                finish_checks: list[WaypointCheck] = []
                finish = _first_crossing_after(finish_lines[last], cursor + 1)
                if finish is not None:
                    finish_checks.append(_crossed(task.finish, "Arrivo", finish))
                if cursor < last_index:
                    fix_point = _best_finish_fix(
                        fixes, turnpoints[-1], prefix, start_check.altitude_m,
                        cursor + 1, last_index, use_gnss,
                    )
                    finish_checks.append(
                        _at_fix(
                            _fix_waypoint(fix_point, "FIX"), "Fix d'arrivo", fix_point,
                            "fix scelto dopo il volo", use_gnss,
                        )
                    )

                for finish_check in finish_checks:
                    waypoints = [start_check, *tp_checks, finish_check]
                    candidates.append(
                        TaskCheck(
                            task=task,
                            waypoints=waypoints,
                            distance_m=prefix
                            + geodesic_distance_ll(
                                turnpoints[-1].lat,
                                turnpoints[-1].lon,
                                finish_check.waypoint.lat,
                                finish_check.waypoint.lon,
                            ),
                            loss_of_height_m=_loss(waypoints),
                            course=CourseType.THREE_TP,
                            declared_course=declared,
                            closed=is_closed(task),
                            unused=[
                                w for k, w in enumerate(task.turnpoints) if k not in sequence
                            ],
                        )
                    )
    return candidates


def _official_key(check: TaskCheck, use_gnss: bool) -> tuple[bool, float]:
    result = loss_of_height(check.distance_m, check.loss_of_height_m, use_gnss)
    return not result.invalid, result.official_m


def verify_declared_task(
    fixes: list[Fix],
    task: DeclaredTask,
    release: Point,
    end_index: int,
    use_gnss: bool = False,
) -> TaskCheck:
    """Verifica il percorso dichiarato e sceglie la geometria con l'esito migliore.

    Per il §2.2 un volo vale per ogni prova di cui soddisfa i requisiti. Oltre
    alla geometria dichiarata, volata nell'ordine dichiarato fra le linee di
    partenza e d'arrivo, un percorso con 1-3 virate si valuta come distanza
    fino a 3 virate (§1.4.2f), che ammette ordine libero, sgancio come
    partenza e un fix come arrivo. Per una richiesta d'insegna questa
    geometria vale almeno quanto andata e ritorno e triangolo sullo stesso
    volo, che quindi non serve valutare a parte. Se nessuna geometria e'
    completata si restituisce la verifica nell'ordine dichiarato, che mostra
    cosa manca.
    """
    started = time.perf_counter()
    in_order = _verify_in_order(fixes, task, release, end_index, use_gnss)
    candidates = [in_order] if in_order.completed else []
    if 1 <= len(task.turnpoints) <= _MAX_THREE_TP:
        candidates += _three_tp_candidates(fixes, task, release, end_index, use_gnss)
    result = max(candidates, key=lambda c: _official_key(c, use_gnss)) if candidates else in_order
    result.start_before_release = in_order.start_before_release
    logger.debug(
        "Percorso dichiarato: %d virate, tipo=%s, candidati=%d | %.1fms | scelto %s, "
        "distanza=%.1fkm, completato=%s, mancati=%s",
        len(task.turnpoints),
        in_order.declared_course.name,
        len(candidates),
        (time.perf_counter() - started) * 1000,
        result.course.name,
        result.distance_m / 1000,
        result.completed,
        [w.label for w in result.missed],
    )
    return result
