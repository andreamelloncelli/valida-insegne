"""Riconoscimento del tipo di percorso dichiarato."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from silverc.course import (
    CourseType,
    classify_course,
    is_closed,
    line_crossings,
    sector_axis,
    sector_indices,
    turnpoint_indices,
)
from silverc.igc import DeclaredTask, Fix, Waypoint

HOME = Waypoint(45.0, 9.0, "CASA")
NORTH = Waypoint(46.0, 9.0, "NORD")
EAST = Waypoint(45.0, 10.0, "EST")
FAR = Waypoint(45.0, 13.0, "LONTANO")


def _task(start: Waypoint, turnpoints: list[Waypoint], finish: Waypoint) -> DeclaredTask:
    return DeclaredTask(declared_at=None, start=start, turnpoints=turnpoints, finish=finish)


def test_no_turnpoints_is_goal():
    assert classify_course(_task(HOME, [], FAR)) is CourseType.GOAL


def test_closed_with_one_turnpoint_is_out_and_return():
    assert classify_course(_task(HOME, [EAST], HOME)) is CourseType.OUT_AND_RETURN


def test_closed_with_two_or_three_turnpoints_is_triangle():
    assert classify_course(_task(HOME, [EAST, NORTH], HOME)) is CourseType.TRIANGLE
    assert classify_course(_task(HOME, [EAST, FAR, NORTH], HOME)) is CourseType.TRIANGLE


def test_open_course_with_turnpoints_is_three_tp_distance():
    assert classify_course(_task(HOME, [NORTH, EAST], FAR)) is CourseType.THREE_TP


def test_nearly_identical_start_and_finish_is_not_closed():
    # §1.2.11: le coordinate devono essere identiche, non solo vicine.
    near_home = Waypoint(45.0001, 9.0, "QUASI CASA")
    task = _task(HOME, [EAST], near_home)

    assert is_closed(task) is False
    assert classify_course(task) is CourseType.THREE_TP


def _fix(seconds: int, east_m: float, north_m: float, alt: int) -> Fix:
    lat = 45.0 + north_m / 111_195.0
    lon = 9.0 + east_m / (111_195.0 * math.cos(math.radians(45.0)))
    return Fix(
        time=datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc) + timedelta(seconds=seconds),
        lat=lat,
        lon=lon,
        valid=True,
        pressure_alt=alt,
        gnss_alt=alt,
    )


def _crossings(fixes: list[Fix]):
    # Linea di partenza in CASA, prima tratta verso EST.
    return line_crossings(fixes, HOME, HOME, EAST, 0, len(fixes) - 1, use_gnss=False)


def test_line_crossed_in_leg_direction_with_interpolated_altitude():
    fixes = [_fix(0, -100, 0, 1000), _fix(10, 300, 0, 1400)]
    crossings = _crossings(fixes)

    assert len(crossings) == 1
    # Attraversamento a un quarto del segmento: 1000 + 0,25 * 400.
    assert crossings[0].altitude_m == pytest.approx(1100, abs=2)
    assert crossings[0].time == fixes[0].time + timedelta(seconds=2.5)


def test_line_crossed_backwards_does_not_count():
    assert _crossings([_fix(0, 300, 0, 1000), _fix(10, -100, 0, 1000)]) == []


def test_passage_beside_the_line_does_not_count():
    # 600 m a nord del centro: oltre i 500 m per lato.
    assert _crossings([_fix(0, -100, 600, 1000), _fix(10, 300, 600, 1000)]) == []


def test_turnpoint_reached_by_segment_between_fixes():
    # Due fix a 1 km dalla virata, uno per parte: il segmento passa a 100 m.
    tp = Waypoint(45.0, 9.0, "VIRATA")
    fixes = [_fix(0, -1000, 100, 1000), _fix(60, 1000, 100, 1000)]

    assert turnpoint_indices(fixes, tp, 0, 1) == [1]


def test_segment_missing_the_zone_does_not_count():
    tp = Waypoint(45.0, 9.0, "VIRATA")
    fixes = [_fix(0, -1000, 700, 1000), _fix(60, 1000, 700, 1000)]

    assert turnpoint_indices(fixes, tp, 0, 1) == []


def test_out_and_return_sector_points_away_from_home():
    tp = Waypoint(45.0, 9.0, "VIRATA")
    home = Waypoint(45.0, 8.0, "CASA")
    axis = sector_axis(tp, home, home)

    assert axis == pytest.approx((1.0, 0.0), abs=1e-6)


def test_straight_through_turnpoint_has_no_sector():
    tp = Waypoint(45.0, 9.0, "VIRATA")

    assert sector_axis(tp, Waypoint(45.0, 8.0, "OVEST"), Waypoint(45.0, 10.0, "EST")) is None


def test_sector_has_unlimited_radius():
    # Andata e ritorno verso est: il settore si apre a est della virata.
    tp = Waypoint(45.0, 9.0, "VIRATA")
    home = Waypoint(45.0, 8.0, "CASA")
    far_beyond = [_fix(0, 4000, -200, 1000), _fix(60, 5000, 200, 1000)]
    beside = [_fix(0, -200, 5000, 1000), _fix(60, 200, 5000, 1000)]

    assert sector_indices(far_beyond, tp, home, home, 0, 1) == [0, 1]
    assert sector_indices(beside, tp, home, home, 0, 1) == []
