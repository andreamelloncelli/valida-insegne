"""Riconoscimento del tipo di percorso dichiarato."""

from __future__ import annotations

from silverc.course import CourseType, classify_course, is_closed
from silverc.igc import DeclaredTask, Waypoint

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
