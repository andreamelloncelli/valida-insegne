"""Percorsi dichiarati dello SC3 (§1.4.2d-h): riconoscimento e verifica sulla traccia."""

from __future__ import annotations

import bisect
import logging
import time
from dataclasses import dataclass, field
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
from silverc.rules import PARAMS

logger = logging.getLogger(__name__)

# I record C scrivono le coordinate al millesimo di primo (~2 m): due punti
# "identici" (§1.2.11) hanno le stesse cifre, quindi la stessa coordinata.
_IDENTICAL_DEG = 1e-6

# §1.4.2f: distanza via una, due o tre virate dichiarate.
_MAX_THREE_TP = 3


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
    radius_m: float
    reached: bool
    closest_m: float
    point: Point | None


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


def _labels(task: DeclaredTask) -> list[str]:
    return (
        ["Partenza"]
        + [f"Virata {i}" for i in range(1, len(task.turnpoints) + 1)]
        + ["Arrivo"]
    )


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


def _zone_indices(
    fixes: list[Fix], waypoint: Waypoint, radius: float, start: int, end: int
) -> list[int]:
    return [
        i
        for i in range(start, end + 1)
        if fast_distance_ll(waypoint.lat, waypoint.lon, fixes[i].lat, fixes[i].lon) <= radius
    ]


def _first_after(indices: list[int], cursor: int) -> int | None:
    position = bisect.bisect_left(indices, cursor)
    return indices[position] if position < len(indices) else None


def _verify_in_order(
    fixes: list[Fix],
    task: DeclaredTask,
    start_index: int,
    end_index: int,
    use_gnss: bool,
) -> TaskCheck:
    """Percorso dichiarato volato nell'ordine dichiarato, con partenza e arrivo dichiarati."""
    labels = _labels(task)
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
            distance = fast_distance_ll(waypoint.lat, waypoint.lon, fixes[i].lat, fixes[i].lon)
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
    start_before_release = not start_check.reached and any(
        fast_distance_ll(task.start.lat, task.start.lon, fixes[i].lat, fixes[i].lon)
        <= start_check.radius_m
        for i in range(0, min(start_index, len(fixes)))
    )
    loss = 0.0
    if start_check.reached and finish_check.reached and start_check.point and finish_check.point:
        start_alt = altitude(start_check.point.fix, use_gnss)
        finish_alt = altitude(finish_check.point.fix, use_gnss)
        if start_alt is not None and finish_alt is not None:
            loss = float(start_alt - finish_alt)

    declared = classify_course(task)
    return TaskCheck(
        task=task,
        waypoints=checks,
        distance_m=declared_task_distance_m(task),
        loss_of_height_m=loss,
        course=declared,
        declared_course=declared,
        closed=is_closed(task),
        start_before_release=start_before_release,
    )


def _fix_waypoint(point: Point, name: str) -> Waypoint:
    return Waypoint(point.fix.lat, point.fix.lon, f"{name} {point.time:%H:%M:%S}")


def _reached(waypoint: Waypoint, label: str, point: Point, radius: float) -> WaypointCheck:
    return WaypointCheck(
        waypoint=waypoint,
        label=label,
        radius_m=radius,
        reached=True,
        closest_m=fast_distance_ll(waypoint.lat, waypoint.lon, point.fix.lat, point.fix.lon),
        point=point,
    )


def _best_finish_fix(
    fixes: list[Fix],
    last: Waypoint,
    prefix_m: float,
    start_alt: int | None,
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
    due o tre fra le dichiarate; si parte dalla partenza dichiarata o dallo
    sgancio e si arriva all'arrivo dichiarato o a un fix (tabella §1.4.4).
    """
    last_index = min(end_index, len(fixes) - 1)
    tp_radius = PARAMS.turnpoint_zone_radius_m
    edge_radius = PARAMS.start_finish_zone_radius_m
    tp_zones = [
        _zone_indices(fixes, tp, tp_radius, release.index, last_index) for tp in task.turnpoints
    ]
    start_zone = _zone_indices(fixes, task.start, edge_radius, release.index, last_index)
    finish_zone = _zone_indices(fixes, task.finish, edge_radius, release.index, last_index)
    declared = classify_course(task)
    candidates: list[TaskCheck] = []

    for size in range(1, len(task.turnpoints) + 1):
        for sequence in permutations(range(len(task.turnpoints)), size):
            for from_release in (True, False):
                if from_release:
                    start_point = release
                    cursor = release.index
                else:
                    first_start = _first_after(start_zone, release.index)
                    if first_start is None:
                        continue
                    cursor = first_start
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
                if not from_release:
                    # Vale l'ultimo passaggio sulla partenza prima della prima virata.
                    last_start = bisect.bisect_right(start_zone, passages[0]) - 1
                    start_point = Point(start_zone[last_start], fixes[start_zone[last_start]])
                start_waypoint = (
                    _fix_waypoint(start_point, "SGANCIO") if from_release else task.start
                )
                turnpoints = [task.turnpoints[tp] for tp in sequence]
                corners = [(start_waypoint.lat, start_waypoint.lon)] + [
                    (w.lat, w.lon) for w in turnpoints
                ]
                prefix = _path_m(corners)
                start_alt = altitude(start_point.fix, use_gnss)

                finishes: list[tuple[Waypoint, str, Point, float]] = []
                declared_finish = _first_after(finish_zone, cursor + 1)
                if declared_finish is not None:
                    finishes.append(
                        (task.finish, "Arrivo", Point(declared_finish, fixes[declared_finish]), edge_radius)
                    )
                if cursor < last_index:
                    fix_point = _best_finish_fix(
                        fixes, turnpoints[-1], prefix, start_alt, cursor + 1, last_index, use_gnss
                    )
                    finishes.append(
                        (_fix_waypoint(fix_point, "FIX"), "Fix d'arrivo", fix_point, 0.0)
                    )

                for finish_waypoint, finish_label, finish_point, finish_radius in finishes:
                    finish_alt = altitude(finish_point.fix, use_gnss)
                    loss = (
                        float(start_alt - finish_alt)
                        if start_alt is not None and finish_alt is not None
                        else 0.0
                    )
                    waypoints = [
                        _reached(
                            start_waypoint,
                            "Sgancio" if from_release else "Partenza",
                            start_point,
                            0.0 if from_release else edge_radius,
                        )
                    ]
                    waypoints += [
                        _reached(w, f"Virata {k}", Point(i, fixes[i]), tp_radius)
                        for k, (w, i) in enumerate(zip(turnpoints, passages), start=1)
                    ]
                    waypoints.append(
                        _reached(finish_waypoint, finish_label, finish_point, finish_radius)
                    )
                    candidates.append(
                        TaskCheck(
                            task=task,
                            waypoints=waypoints,
                            distance_m=prefix
                            + geodesic_distance_ll(
                                turnpoints[-1].lat,
                                turnpoints[-1].lon,
                                finish_waypoint.lat,
                                finish_waypoint.lon,
                            ),
                            loss_of_height_m=loss,
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
    alla geometria dichiarata, volata nell'ordine dichiarato fra partenza e
    arrivo dichiarati, un percorso con 1-3 virate si valuta come distanza fino
    a 3 virate (§1.4.2f), che ammette ordine libero, sgancio come partenza e
    un fix come arrivo. Per una richiesta d'insegna questa geometria vale
    almeno quanto andata e ritorno e triangolo sullo stesso volo, che quindi
    non serve valutare a parte. Se nessuna geometria e' completata si
    restituisce la verifica nell'ordine dichiarato, che mostra cosa manca.
    """
    started = time.perf_counter()
    in_order = _verify_in_order(fixes, task, release.index, end_index, use_gnss)
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
