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
from silverc.rules import RULES

logger = logging.getLogger(__name__)

# I record C scrivono le coordinate al millesimo di primo (~2 m): due punti
# "identici" (§1.2.11) hanno le stesse cifre, quindi la stessa coordinata.
_IDENTICAL_DEG = 1e-6

# §1.4.2f: distanza via una, due o tre virate dichiarate.
_MAX_THREE_TP = 3

_EARTH_RADIUS_M = 6_371_000.0


class CourseType(str, Enum):
    STRAIGHT = "linea retta dalla partenza dichiarata (§1.4.2d)"
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
    # Correzione per le virate raggiunte solo col cilindro (§1.3.6).
    cylinder_correction_m: float = 0.0
    # Verifica nella geometria dichiarata, quando la scelta e' un'altra.
    in_order: TaskCheck | None = None

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


Neighbors = tuple[Waypoint | None, Waypoint | None]


def sector_axis(tp: Waypoint, previous: Waypoint, following: Waypoint) -> tuple[float, float] | None:
    """Asse del settore: opposto alla bisettrice fra tratta in entrata e in uscita (§1.2.6b).

    Restituisce None quando l'orientamento non e' determinato: tratte di
    lunghezza nulla o virata in linea retta, dove la bisettrice ammette due
    versi. In quei casi vale solo il cilindro (§4.3.4b).
    """
    ax, ay = _local_xy(tp, previous.lat, previous.lon)
    bx, by = _local_xy(tp, following.lat, following.lon)
    la, lb = math.hypot(ax, ay), math.hypot(bx, by)
    if la < 1.0 or lb < 1.0:
        return None
    sx, sy = ax / la + bx / lb, ay / la + by / lb
    norm = math.hypot(sx, sy)
    if norm < 1e-6:
        return None
    return -sx / norm, -sy / norm


def _cross(ux: float, uy: float, vx: float, vy: float) -> float:
    return ux * vy - uy * vx


def _segment_hits_ray(
    a: tuple[float, float], b: tuple[float, float], ray: tuple[float, float]
) -> bool:
    """Il segmento a-b tocca la semiretta dall'origine in direzione `ray`?"""
    ex, ey = b[0] - a[0], b[1] - a[1]
    denominator = _cross(ex, ey, ray[0], ray[1])
    if abs(denominator) < 1e-9:
        return False
    t = -_cross(a[0], a[1], ray[0], ray[1]) / denominator
    along = _cross(a[0], a[1], ex, ey) / -denominator
    return 0.0 <= t <= 1.0 and along >= 0.0


class _TurnpointZones:
    """Indici dei fix che raggiungono ogni zona di osservazione (§1.2.6, §2.4.2c).

    Un fix dentro la zona o un segmento fra due fix consecutivi che la
    attraversa: con fix radi un passaggio reale cadrebbe altrimenti fra due
    fix esterni. In quel caso conta il secondo fix. Le coordinate piane dei
    fix attorno a ogni virata si calcolano una volta sola.
    """

    def __init__(self, fixes: list[Fix], start: int, end: int) -> None:
        self._fixes = fixes
        self._start = start
        self._end = end
        self._xy: dict[tuple[float, float], list[tuple[float, float]]] = {}
        self._cylinders: dict[tuple[float, float], list[int]] = {}
        self._sectors: dict[tuple, list[int]] = {}

    def _points(self, tp: Waypoint) -> list[tuple[float, float]]:
        key = (tp.lat, tp.lon)
        if key not in self._xy:
            self._xy[key] = [
                _local_xy(tp, fix.lat, fix.lon) for fix in self._fixes[self._start : self._end + 1]
            ]
        return self._xy[key]

    def cylinder(self, tp: Waypoint) -> list[int]:
        key = (tp.lat, tp.lon)
        if key not in self._cylinders:
            radius = RULES.turnpoint_cylinder_m
            points = self._points(tp)
            indices: list[int] = []
            for offset, (x, y) in enumerate(points):
                inside = math.hypot(x, y) <= radius
                if not inside and offset > 0:
                    px, py = points[offset - 1]
                    dx, dy = x - px, y - py
                    span = dx * dx + dy * dy
                    t = 0.0 if span == 0 else max(0.0, min(1.0, -(px * dx + py * dy) / span))
                    inside = math.hypot(px + t * dx, py + t * dy) <= radius
                if inside:
                    indices.append(self._start + offset)
            self._cylinders[key] = indices
        return self._cylinders[key]

    def sector(self, tp: Waypoint, neighbors: Neighbors) -> list[int]:
        previous, following = neighbors
        if previous is None or following is None:
            return []
        key = (tp.lat, tp.lon, previous.lat, previous.lon, following.lat, following.lon)
        if key not in self._sectors:
            axis = sector_axis(tp, previous, following)
            self._sectors[key] = [] if axis is None else self._scan_sector(tp, axis)
        return self._sectors[key]

    def _scan_sector(self, tp: Waypoint, axis: tuple[float, float]) -> list[int]:
        half = math.radians(RULES.sector_angle_deg / 2)
        cos_half = math.cos(half)
        rays = [
            (
                axis[0] * math.cos(angle) - axis[1] * math.sin(angle),
                axis[0] * math.sin(angle) + axis[1] * math.cos(angle),
            )
            for angle in (half, -half)
        ]
        points = self._points(tp)
        indices: list[int] = []
        for offset, (x, y) in enumerate(points):
            radius = math.hypot(x, y)
            inside = radius == 0 or (x * axis[0] + y * axis[1]) / radius >= cos_half - 1e-12
            if not inside and offset > 0:
                inside = any(_segment_hits_ray(points[offset - 1], (x, y), ray) for ray in rays)
            if inside:
                indices.append(self._start + offset)
        return indices

    def union(self, tp: Waypoint, neighbors: Neighbors) -> list[int]:
        sector = self.sector(tp, neighbors)
        cylinder = self.cylinder(tp)
        return sorted(set(cylinder) | set(sector)) if sector else cylinder

    def sector_used(self, tp: Waypoint, neighbors: Neighbors, low: int, high: int) -> bool:
        """La traccia entra nel settore fra `low` e `high` inclusi?"""
        found = _first_after(self.sector(tp, neighbors), low)
        return found is not None and found <= high


def turnpoint_indices(fixes: list[Fix], waypoint: Waypoint, start: int, end: int) -> list[int]:
    """Indici dei fix che raggiungono il cilindro della virata (§1.2.6a, §2.4.2c)."""
    return _TurnpointZones(fixes, start, end).cylinder(waypoint)


def sector_indices(
    fixes: list[Fix], tp: Waypoint, previous: Waypoint, following: Waypoint, start: int, end: int
) -> list[int]:
    """Indici dei fix che raggiungono il settore della virata (§1.2.6b, §2.4.2c)."""
    return _TurnpointZones(fixes, start, end).sector(tp, (previous, following))


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


def _turnpoint_zone(by_sector: bool) -> str:
    if by_sector:
        return f"settore a {RULES.sector_angle_deg:.0f} gradi"
    return (
        f"solo cilindro di {RULES.turnpoint_cylinder_m:.0f} m: "
        f"-{RULES.cylinder_correction_m / 1000:.0f} km (§1.3.6)"
    )


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


def _windows(indices: list[int]) -> list[tuple[int, int]]:
    """Per ogni virata, l'intervallo fra il passaggio precedente e il successivo.

    `indices` contiene partenza, virate e arrivo; una virata mancata vale -1 e
    il suo intervallo non conta.
    """
    return [(indices[k - 1], indices[k + 1]) for k in range(1, len(indices) - 1)]


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
    zones = _TurnpointZones(fixes, release.index, last_index)
    neighbors = [(points[k], points[k + 2]) for k in range(len(task.turnpoints))]

    found: list[int | None] = []
    search_from = cursor
    for waypoint, around in zip(task.turnpoints, neighbors):
        index = _first_after(zones.union(waypoint, around), search_from)
        found.append(index)
        if index is not None:
            cursor, search_from = index, index + 1
    passages = [index for index in found if index is not None]

    finish = _first_crossing_after(finish_line, cursor + 1)
    windows = _windows(
        [first_start.point.index if first_start else release.index]
        + [index if index is not None else -1 for index in found]
        + [finish.point.index if finish else last_index]
    )
    turnpoints: list[WaypointCheck] = []
    cylinder_only = 0
    for number, (waypoint, around, index, window) in enumerate(
        zip(task.turnpoints, neighbors, found, windows), start=1
    ):
        label = f"Virata {number}"
        if index is None:
            turnpoints.append(
                _missed(fixes, waypoint, label, _turnpoint_zone(False), release.index, last_index)
            )
            continue
        by_sector = zones.sector_used(waypoint, around, *window)
        cylinder_only += not by_sector
        turnpoints.append(
            _at_fix(waypoint, label, Point(index, fixes[index]), _turnpoint_zone(by_sector), use_gnss)
        )

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
        cylinder_correction_m=cylinder_only * RULES.cylinder_correction_m,
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
    (tabella §1.4.4). Linee e settori seguono le tratte rivendicate, quindi
    cambiano con la sequenza. Con l'arrivo a un fix scelto dopo il volo la
    tratta finale non e' nota in anticipo: per l'ultima virata vale solo il
    cilindro (§4.3.4b).
    """
    last_index = min(end_index, len(fixes) - 1)
    zones = _TurnpointZones(fixes, release.index, last_index)
    release_waypoint = _fix_waypoint(release, "SGANCIO")
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
                    origin, cursor = release_waypoint, release.index
                else:
                    first_start = _first_crossing_after(start_lines[first], release.index)
                    if first_start is None:
                        continue
                    origin, cursor = task.start, first_start.point.index
                for to_line in (True, False):
                    route = [origin, *turnpoints, task.finish if to_line else None]
                    neighbors = [(route[k], route[k + 2]) for k in range(len(turnpoints))]
                    passages: list[int] = []
                    search_from = cursor
                    for waypoint, around in zip(turnpoints, neighbors):
                        index = _first_after(zones.union(waypoint, around), search_from)
                        if index is None:
                            break
                        passages.append(index)
                        search_from = index + 1
                    if len(passages) < len(turnpoints):
                        continue
                    candidate = _three_tp_candidate(
                        fixes, task, release, last_index, use_gnss, zones, declared,
                        sequence, neighbors, passages, from_release,
                        start_lines[first], finish_lines[last] if to_line else None,
                    )
                    if candidate is not None:
                        candidates.append(candidate)
    return candidates


def _three_tp_candidate(
    fixes: list[Fix],
    task: DeclaredTask,
    release: Point,
    last_index: int,
    use_gnss: bool,
    zones: _TurnpointZones,
    declared: CourseType,
    sequence: tuple[int, ...],
    neighbors: list[Neighbors],
    passages: list[int],
    from_release: bool,
    start_line: list[Crossing],
    finish_line: list[Crossing] | None,
) -> TaskCheck | None:
    """Una sequenza di virate gia' raggiunte, con la sua partenza e il suo arrivo."""
    turnpoints = [task.turnpoints[tp] for tp in sequence]
    if from_release:
        start_check = _at_fix(
            _fix_waypoint(release, "SGANCIO"), "Sgancio", release, "sgancio", use_gnss
        )
        start_index = release.index
    else:
        start = _last_crossing_until(start_line, passages[0])
        start_check = _crossed(task.start, "Partenza", start)
        start_index = start.point.index
    prefix = _path_m(
        [(start_check.waypoint.lat, start_check.waypoint.lon)]
        + [(w.lat, w.lon) for w in turnpoints]
    )

    if finish_line is not None:
        finish = _first_crossing_after(finish_line, passages[-1] + 1)
        if finish is None:
            return None
        finish_check = _crossed(task.finish, "Arrivo", finish)
        finish_index = finish.point.index
    else:
        if passages[-1] >= last_index:
            return None
        fix_point = _best_finish_fix(
            fixes, turnpoints[-1], prefix, start_check.altitude_m,
            passages[-1] + 1, last_index, use_gnss,
        )
        finish_check = _at_fix(
            _fix_waypoint(fix_point, "FIX"), "Fix d'arrivo", fix_point,
            "fix scelto dopo il volo", use_gnss,
        )
        finish_index = fix_point.index

    windows = _windows([start_index, *passages, finish_index])
    tp_checks: list[WaypointCheck] = []
    cylinder_only = 0
    for k, (waypoint, around, index, window) in enumerate(
        zip(turnpoints, neighbors, passages, windows), start=1
    ):
        by_sector = zones.sector_used(waypoint, around, *window)
        cylinder_only += not by_sector
        tp_checks.append(
            _at_fix(waypoint, f"Virata {k}", Point(index, fixes[index]), _turnpoint_zone(by_sector), use_gnss)
        )
    waypoints = [start_check, *tp_checks, finish_check]
    return TaskCheck(
        task=task,
        waypoints=waypoints,
        distance_m=prefix
        + geodesic_distance_ll(
            turnpoints[-1].lat, turnpoints[-1].lon,
            finish_check.waypoint.lat, finish_check.waypoint.lon,
        ),
        loss_of_height_m=_loss(waypoints),
        course=CourseType.THREE_TP,
        declared_course=declared,
        closed=is_closed(task),
        unused=[w for k, w in enumerate(task.turnpoints) if k not in sequence],
        cylinder_correction_m=cylinder_only * RULES.cylinder_correction_m,
    )


def _straight_from_start(
    fixes: list[Fix],
    task: DeclaredTask,
    release: Point,
    end_index: int,
    use_gnss: bool,
) -> TaskCheck | None:
    """Linea retta dalla partenza dichiarata a un fix (§1.4.2d).

    La linea di partenza e' quella dichiarata, perpendicolare alla prima
    tratta dichiarata: la tratta effettiva finisce a un fix scelto dopo il
    volo e non e' nota in anticipo. Per ogni attraversamento dopo lo sgancio
    si sceglie il fix d'arrivo migliore; vale l'esito migliore.
    """
    last_index = min(end_index, len(fixes) - 1)
    crossings = line_crossings(
        fixes, task.start, task.start, task.points[1], release.index, last_index, use_gnss
    )
    best: TaskCheck | None = None
    for crossing in crossings:
        if crossing.point.index >= last_index:
            continue
        fix_point = _best_finish_fix(
            fixes, task.start, 0.0, crossing.altitude_m, crossing.point.index, last_index, use_gnss
        )
        waypoints = [
            _crossed(task.start, "Partenza", crossing),
            _at_fix(
                _fix_waypoint(fix_point, "FIX"), "Fix d'arrivo", fix_point,
                "fix scelto dopo il volo", use_gnss,
            ),
        ]
        candidate = TaskCheck(
            task=task,
            waypoints=waypoints,
            distance_m=geodesic_distance_ll(
                task.start.lat, task.start.lon, fix_point.fix.lat, fix_point.fix.lon
            ),
            loss_of_height_m=_loss(waypoints),
            course=CourseType.STRAIGHT,
            declared_course=classify_course(task),
            closed=is_closed(task),
            unused=list(task.turnpoints),
        )
        if best is None or _official_key(candidate, use_gnss) > _official_key(best, use_gnss):
            best = candidate
    return best


def _official_key(check: TaskCheck, use_gnss: bool) -> tuple[bool, float]:
    result = loss_of_height(check.distance_m, check.loss_of_height_m, use_gnss)
    return not result.invalid, result.official_m - check.cylinder_correction_m


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
    volo, che quindi non serve valutare a parte. Ogni percorso si valuta
    anche come linea retta dalla partenza dichiarata a un fix (§1.4.2d). Se
    nessuna geometria e' completata si restituisce la verifica nell'ordine
    dichiarato, che mostra cosa manca.
    """
    started = time.perf_counter()
    in_order = _verify_in_order(fixes, task, release, end_index, use_gnss)
    candidates = [in_order] if in_order.completed else []
    if 1 <= len(task.turnpoints) <= _MAX_THREE_TP:
        candidates += _three_tp_candidates(fixes, task, release, end_index, use_gnss)
    straight = _straight_from_start(fixes, task, release, end_index, use_gnss)
    if straight is not None:
        candidates.append(straight)
    result = max(candidates, key=lambda c: _official_key(c, use_gnss)) if candidates else in_order
    result.start_before_release = in_order.start_before_release
    if result is not in_order:
        result.in_order = in_order
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
