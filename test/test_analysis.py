from __future__ import annotations

from pathlib import Path

import pytest

from flights import GROUND_ALT, RELEASE_T, TAKEOFF_T, TOW_TOP_ALT, build_flight, climbing_profile, descending_profile
from silverc.analysis import analyse, compute_height_gain, geodesic_distance_m, parse_release_time
from silverc.igc import Fix, parse_igc

START = 36000


def _seconds_from_start(moment) -> int:
    return moment.hour * 3600 + moment.minute * 60 + moment.second - START


def test_release_detected_at_end_of_tow(tmp_path):
    path = build_flight(
        tmp_path / "t.igc",
        soaring_duration_s=3600,
        distance_m=20_000,
        altitude=descending_profile(),
    )
    analysis = analyse(parse_igc(path))

    assert _seconds_from_start(analysis.release.time) == RELEASE_T
    assert analysis.release_confidence == "alta"
    # Il decollo e' l'ultimo fix da fermo prima della corsa di decollo.
    assert abs(_seconds_from_start(analysis.takeoff.time) - TAKEOFF_T) <= 30


def test_landing_excludes_trailing_ground_fixes(tmp_path):
    path = build_flight(
        tmp_path / "t.igc",
        soaring_duration_s=3600,
        distance_m=20_000,
        altitude=descending_profile(),
        trailing_ground_s=600,
    )
    analysis = analyse(parse_igc(path))

    assert _seconds_from_start(analysis.landing.time) == RELEASE_T + 3600
    assert analysis.duration_s == 3600


def test_manual_release_time_overrides_heuristic(tmp_path):
    from datetime import datetime, timezone

    path = build_flight(
        tmp_path / "t.igc",
        soaring_duration_s=3600,
        distance_m=20_000,
        altitude=descending_profile(),
    )
    flight = parse_igc(path)
    manual = datetime(2025, 6, 15, 10, 5, 0, tzinfo=timezone.utc)
    analysis = analyse(flight, release_time=manual)

    assert _seconds_from_start(analysis.release.time) == 300
    assert "utente" in analysis.release_source


def _fix(seconds: int, alt: int) -> Fix:
    from datetime import datetime, timezone

    return Fix(
        time=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).replace(
            hour=seconds // 3600, minute=seconds % 3600 // 60, second=seconds % 60
        ),
        lat=45.0,
        lon=9.0,
        valid=True,
        pressure_alt=alt,
        gnss_alt=alt,
    )


def test_height_gain_requires_low_point_before_high_point():
    # Massimo globale (2500) PRIMA del minimo globale (400): max-min darebbe 2100.
    altitudes = [2500, 1000, 1400, 400, 700, 1300]
    fixes = [_fix(i * 60, alt) for i, alt in enumerate(altitudes)]

    gain = compute_height_gain(fixes, 0, use_gnss=False)

    # max(alt) - min(alt) darebbe 2100 m, ma il massimo precede il minimo.
    assert gain.gain_m == pytest.approx(900.0)
    assert gain.low.fix.pressure_alt == 400
    assert gain.high.fix.pressure_alt == 1300


def test_height_gain_ignores_fixes_before_release():
    altitudes = [100, 3000, 500, 900]
    fixes = [_fix(i * 60, alt) for i, alt in enumerate(altitudes)]

    gain = compute_height_gain(fixes, 2, use_gnss=False)

    assert gain.gain_m == pytest.approx(400.0)


def test_geodesic_distance_is_plausible():
    a = _fix(0, 0)
    b = Fix(time=a.time, lat=45.0, lon=9.0 + 1.0, valid=True, pressure_alt=0, gnss_alt=0)

    distance, model = geodesic_distance_m(a, b)

    assert 78_000 < distance < 79_000
    assert model


def test_engine_noise_is_flagged(tmp_path):
    path = build_flight(
        tmp_path / "t.igc",
        soaring_duration_s=3600,
        distance_m=20_000,
        altitude=climbing_profile(1200),
        with_enl=True,
        enl_after_release=800,
    )
    analysis = analyse(parse_igc(path))

    assert analysis.engine_suspected is True
    assert analysis.max_enl == 800


def test_parse_release_time_uses_flight_date(tmp_path):
    path = build_flight(
        tmp_path / "t.igc",
        soaring_duration_s=3600,
        distance_m=20_000,
        altitude=descending_profile(),
    )
    flight = parse_igc(path)
    moment = parse_release_time("10:07:00", flight)

    assert moment.date() == flight.flight_date
    assert (moment.hour, moment.minute, moment.second) == (10, 7, 0)
    assert parse_release_time("10:07", flight) == moment


def test_parse_release_time_rejects_bad_input(tmp_path):
    path = build_flight(
        tmp_path / "t.igc",
        soaring_duration_s=3600,
        distance_m=20_000,
        altitude=descending_profile(),
    )
    with pytest.raises(ValueError):
        parse_release_time("dopo pranzo", parse_igc(path))


def test_normal_cadence_is_not_warned(tmp_path):
    path = build_flight(
        tmp_path / "t.igc",
        soaring_duration_s=3600,
        distance_m=20_000,
        altitude=descending_profile(),
    )
    analysis = analyse(parse_igc(path))

    assert analysis.median_fix_interval_s == 30
    assert not any("§2.4.1" in n for n in analysis.notes)


def test_sparse_cadence_is_warned(tmp_path):
    path = build_flight(
        tmp_path / "t.igc",
        soaring_duration_s=3600,
        distance_m=20_000,
        altitude=descending_profile(),
    )
    lines = Path(path).read_text(encoding="latin-1").splitlines()
    b_records = [i for i, line in enumerate(lines) if line.startswith("B")]
    # Tiene un B-record su tre: un fix ogni 90 s durante il veleggiamento.
    dropped = {i for n, i in enumerate(b_records) if n > 30 and n % 3}
    Path(path).write_text(
        "\n".join(line for i, line in enumerate(lines) if i not in dropped) + "\n",
        encoding="latin-1",
    )
    analysis = analyse(parse_igc(path))

    # Con fix radi l'atterraggio non va anticipato al primo intervallo lungo.
    assert analysis.duration_s > 3000
    assert analysis.median_fix_interval_s > 60
    assert any("§2.4.1" in n for n in analysis.notes)
