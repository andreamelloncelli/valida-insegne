"""Geometria di base della traccia: distanze, quota e perdita di quota."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from geographiclib.geodesic import Geodesic

from silverc.igc import Fix
from silverc.rules import RULES

# §1.3.7: le distanze si misurano sull'ellissoide WGS84, senza ripiego sulla
# sfera FAI.
GEODESIC_MODEL = "WGS84 (geographiclib)"

# Solo per i confronti approssimati interni alla traccia, mai per le distanze
# ufficiali.
_FAI_SPHERE_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class Point:
    """Un fix con il suo indice nella traccia."""

    index: int
    fix: Fix

    @property
    def time(self) -> datetime:
        return self.fix.time


def geodesic_distance_ll(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return float(Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)["s12"])


def geodesic_distance_m(a: Fix, b: Fix) -> tuple[float, str]:
    """Distanza fra due fix; restituisce anche il modello geodetico usato."""
    return geodesic_distance_ll(a.lat, a.lon, b.lat, b.lon), GEODESIC_MODEL


def fast_distance_ll(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approssimazione equirettangolare, per i confronti interni alla traccia.

    Errore trascurabile sotto il chilometro ed evita centinaia di migliaia di
    chiamate al calcolo geodetico completo su una traccia a 1 Hz.
    """
    mean_lat = math.radians((lat1 + lat2) / 2.0)
    dx = math.radians(lon2 - lon1) * math.cos(mean_lat)
    dy = math.radians(lat2 - lat1)
    return math.hypot(dx, dy) * _FAI_SPHERE_RADIUS_M


def fast_distance_m(a: Fix, b: Fix) -> float:
    return fast_distance_ll(a.lat, a.lon, b.lat, b.lon)


def altitude(fix: Fix, use_gnss: bool) -> int | None:
    return fix.gnss_alt if use_gnss else fix.pressure_alt


@dataclass(frozen=True)
class LossOfHeight:
    """Esito del limite di perdita di quota del §2.4.4 su una distanza."""

    flown_m: float
    loss_m: float
    limit_m: float
    invalid: bool
    official_m: float

    @property
    def excess_m(self) -> float:
        return max(0.0, self.loss_m - self.limit_m)


def loss_of_height(distance_m: float, loss_m: float, gnss: bool) -> LossOfHeight:
    """Limite di perdita di quota del §2.4.4 e distanza che ne risulta."""
    margin = RULES.gnss_altitude_penalty_m if gnss else 0.0
    # La regola si sceglie sulla distanza volata, non su quella corretta: un
    # volo di 130 km penalizzato a 80 km resta nella regola oltre i 100 km.
    if distance_m <= RULES.loss_of_height_long_course_m:
        limit = distance_m * RULES.loss_of_height_ratio - margin
        return LossOfHeight(distance_m, loss_m, limit, loss_m > limit, distance_m)
    limit = RULES.loss_of_height_long_limit_m - margin
    penalty = RULES.loss_of_height_excess_factor * max(0.0, loss_m - limit)
    return LossOfHeight(distance_m, loss_m, limit, False, distance_m - penalty)
