"""Tipi di percorso dichiarato dello SC3 (§1.4.2d-h) e loro riconoscimento."""

from __future__ import annotations

from enum import Enum

from silverc.igc import DeclaredTask, Waypoint

# I record C scrivono le coordinate al millesimo di primo (~2 m): due punti
# "identici" (§1.2.11) hanno le stesse cifre, quindi la stessa coordinata.
_IDENTICAL_DEG = 1e-6


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
