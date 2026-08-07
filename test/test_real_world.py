"""Regressioni sui comportamenti dei logger reali, non riprodotti dagli
scenari sintetici a campionamento lento."""

from __future__ import annotations

import math
import random

from igc_builder import IGCBuilder, offset_lat, offset_lon
from silverc.analysis import analyse
from silverc.igc import parse_igc
from silverc.validator import Verdict, validate_silver

LAT, LON = 45.0, 9.0
START = 36000
FIVE_HOURS = 5 * 3600


def _jittery_flight(path, *, soaring_s: int, trailing_ground_s: int, baro_zero: bool = False):
    """Traccia a 1 Hz con rumore GPS di +/-4 m, come un logger reale."""
    rng = random.Random(42)
    builder = IGCBuilder()

    def jitter() -> float:
        return rng.uniform(-4.0, 4.0)

    def add(t: int, lat: float, lon: float, alt: int) -> None:
        builder.fix(
            START + t,
            offset_lat(lat, jitter()),
            offset_lon(lon, lat, jitter()),
            0 if baro_zero else alt,
            gnss_alt=alt,
        )

    for t in range(0, 120):
        add(t, LAT, LON, 200)
    for t in range(120, 421):
        frac = (t - 120) / 300
        add(t, LAT, offset_lon(LON, LAT, 3000 * frac), int(200 + 600 * frac))
    for t in range(421, 421 + soaring_s):
        frac = (t - 421) / soaring_s
        # Spirale in termica: raggio 120 m, periodo 40 s.
        angle = (t % 40) / 40 * 2 * math.pi
        add(
            t,
            offset_lat(LAT, 120 * math.sin(angle)),
            offset_lon(LON, LAT, 30_000 * frac + 120 * math.cos(angle)),
            int(400 + 1200 * frac) if frac > 0.1 else int(800 - 4000 * frac),
        )
    end = 421 + soaring_s
    for t in range(end, end + trailing_ground_s):
        add(t, LAT, offset_lon(LON, LAT, 30_000), 400)
    return builder.write(path)


def test_landing_ignores_ten_minutes_of_ground_recording_at_1hz(tmp_path):
    path = _jittery_flight(tmp_path / "j.igc", soaring_s=FIVE_HOURS - 300, trailing_ground_s=600)
    analysis = analyse(parse_igc(path))

    seconds = (
        analysis.landing.time.hour * 3600
        + analysis.landing.time.minute * 60
        + analysis.landing.time.second
        - START
    )
    assert abs(seconds - (421 + FIVE_HOURS - 300)) <= 60


def test_short_flight_with_long_ground_recording_still_fails_duration(tmp_path):
    path = _jittery_flight(tmp_path / "j.igc", soaring_s=FIVE_HOURS - 900, trailing_ground_s=1800)
    flight = parse_igc(path)
    report = validate_silver(flight, analyse(flight))
    duration = next(r for r in report.requirements if r.code == "durata")

    assert duration.verdict is Verdict.FAIL


def test_zero_pressure_altitude_falls_back_to_gnss(tmp_path):
    path = _jittery_flight(
        tmp_path / "z.igc", soaring_s=7200, trailing_ground_s=120, baro_zero=True
    )
    flight = parse_igc(path)
    analysis = analyse(flight)
    report = validate_silver(flight, analysis)
    gain = next(r for r in report.requirements if r.code == "quota")

    assert analysis.altitude_source == "GNSS"
    assert analysis.height_gain.gain_m > 1000
    assert gain.verdict is Verdict.PASS
    assert any("GNSS" in n for n in analysis.notes)


def test_release_time_before_takeoff_is_undetermined(tmp_path):
    from datetime import datetime, timezone

    path = _jittery_flight(tmp_path / "r.igc", soaring_s=FIVE_HOURS + 600, trailing_ground_s=120)
    flight = parse_igc(path)
    analysis = analyse(flight, release_time=datetime(2025, 6, 15, 10, 0, 10, tzinfo=timezone.utc))
    report = validate_silver(flight, analysis)
    duration = next(r for r in report.requirements if r.code == "durata")

    assert analysis.release_confidence == "bassa"
    assert duration.verdict is Verdict.UNDETERMINED
