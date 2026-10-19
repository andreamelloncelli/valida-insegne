"""Scenari di volo sintetici condivisi dai test."""

from __future__ import annotations

from typing import Callable

from igc_builder import IGCBuilder, offset_lat, offset_lon

LAT, LON = 45.0, 9.0
GROUND_ALT = 200
TOW_TOP_ALT = 800
TAKEOFF_T = 120
RELEASE_T = 420
_TOW_STEP = 30
_SOAR_STEP = 30


def build_flight(
    path,
    *,
    soaring_duration_s: int,
    distance_m: float,
    altitude: Callable[[float], int],
    landing_alt: int | None = None,
    out_and_return: bool = False,
    trailing_ground_s: int = 180,
    start_time_s: int = 36000,
    date_ddmmyy: str = "150625",
    with_enl: bool = False,
    enl_after_release: int = 0,
    with_g_record: bool = True,
    **header: str,
) -> str:
    """Genera una traccia: rullaggio, traino, sgancio, veleggiamento, atterraggio.

    `altitude` riceve la frazione di veleggiamento trascorsa (0..1) e
    restituisce la quota barometrica in metri. `header` sovrascrive i campi
    d'intestazione di `IGCBuilder` (record A, pilota, aliante, marche...).
    """
    builder = IGCBuilder(
        date_ddmmyy=date_ddmmyy, with_enl=with_enl, with_g_record=with_g_record, **header
    )

    for t in range(0, TAKEOFF_T, 20):
        builder.fix(start_time_s + t, LAT, LON, GROUND_ALT)

    tow_span = RELEASE_T - TAKEOFF_T
    for t in range(TAKEOFF_T, RELEASE_T + 1, _TOW_STEP):
        frac = (t - TAKEOFF_T) / tow_span
        alt = int(GROUND_ALT + (TOW_TOP_ALT - GROUND_ALT) * frac)
        builder.fix(start_time_s + t, LAT, offset_lon(LON, LAT, 3000 * frac), alt)

    soar_end = RELEASE_T + soaring_duration_s
    steps = list(range(RELEASE_T + _SOAR_STEP, soar_end + 1, _SOAR_STEP))
    for index, t in enumerate(steps):
        frac = (t - RELEASE_T) / soaring_duration_s
        # Oscillazione laterale: simula le spirali in termica, altrimenti la
        # velocita' al suolo media sarebbe sotto la soglia di "fermo".
        wobble = 0.0 if t == steps[-1] else (150.0 if index % 2 else -150.0)
        along = distance_m * (2 * frac if frac <= 0.5 else 2 * (1 - frac)) if out_and_return else distance_m * frac
        builder.fix(
            start_time_s + t,
            offset_lat(LAT, wobble),
            offset_lon(LON, LAT, along),
            altitude(frac),
            enl=enl_after_release,
        )

    final_alt = altitude(1.0) if landing_alt is None else landing_alt
    final_along = 0.0 if out_and_return else distance_m
    for t in range(soar_end + 20, soar_end + trailing_ground_s + 1, 20):
        builder.fix(
            start_time_s + t,
            LAT,
            offset_lon(LON, LAT, final_along),
            final_alt,
            enl=enl_after_release,
        )

    return builder.write(path)


def descending_profile(top: int = TOW_TOP_ALT, bottom: int = GROUND_ALT) -> Callable[[float], int]:
    """Discesa lineare: il primo fix dopo lo sgancio scende, come nella realta'."""

    def profile(frac: float) -> int:
        return int(top - (top - bottom) * frac)

    return profile


def climbing_profile(peak_gain: int) -> Callable[[float], int]:
    """Discesa iniziale a 400 m, poi salita fino a 400 + peak_gain."""

    def profile(frac: float) -> int:
        if frac < 0.25:
            return int(TOW_TOP_ALT - (TOW_TOP_ALT - 400) * (frac / 0.25))
        return int(400 + peak_gain * ((frac - 0.25) / 0.75))

    return profile
