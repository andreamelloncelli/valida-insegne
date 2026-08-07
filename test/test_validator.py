from __future__ import annotations

from flights import build_flight, climbing_profile, descending_profile
from silverc.analysis import analyse
from silverc.igc import parse_igc
from silverc.report import render
from silverc.validator import Verdict, validate_silver

FIVE_HOURS = 5 * 3600


def _report(path):
    flight = parse_igc(path)
    return validate_silver(flight, analyse(flight))


def _by_code(report, code):
    return next(r for r in report.requirements if r.code == code)


def test_duration_pass(tmp_path):
    path = build_flight(
        tmp_path / "d.igc",
        soaring_duration_s=FIVE_HOURS + 600,
        distance_m=5_000,
        altitude=climbing_profile(600),
    )
    req = _by_code(_report(path), "durata")

    assert req.verdict is Verdict.PASS
    assert "5h" in req.required


def test_duration_fail_just_short(tmp_path):
    path = build_flight(
        tmp_path / "d.igc",
        soaring_duration_s=FIVE_HOURS - 3600,
        distance_m=5_000,
        altitude=climbing_profile(600),
    )
    req = _by_code(_report(path), "durata")

    assert req.verdict is Verdict.FAIL


def test_duration_has_no_tolerance_band(tmp_path):
    # 4h59m e' NON SODDISFATTO, non "al limite": fissato lo sgancio la durata
    # e' una misura esatta e un margine indurrebbe il pilota in errore.
    path = build_flight(
        tmp_path / "d.igc",
        soaring_duration_s=FIVE_HOURS - 60,
        distance_m=5_000,
        altitude=climbing_profile(600),
    )
    req = _by_code(_report(path), "durata")

    assert req.verdict is Verdict.FAIL


def test_height_gain_pass(tmp_path):
    path = build_flight(
        tmp_path / "h.igc",
        soaring_duration_s=7200,
        distance_m=5_000,
        altitude=climbing_profile(1200),
    )
    req = _by_code(_report(path), "quota")

    assert req.verdict is Verdict.PASS
    assert "1200 m" in req.measured or "1199 m" in req.measured


def test_height_gain_fail(tmp_path):
    path = build_flight(
        tmp_path / "h.igc",
        soaring_duration_s=7200,
        distance_m=5_000,
        altitude=climbing_profile(600),
    )
    req = _by_code(_report(path), "quota")

    assert req.verdict is Verdict.FAIL


def test_distance_pass(tmp_path):
    path = build_flight(
        tmp_path / "x.igc",
        soaring_duration_s=7200,
        distance_m=60_000,
        altitude=descending_profile(top=800, bottom=500),
    )
    req = _by_code(_report(path), "distanza")

    assert req.verdict is Verdict.PASS
    assert "entro il limite" in " ".join(req.reasons)


def test_distance_fails_on_excessive_loss_of_height(tmp_path):
    # 60 km => perdita massima ammessa 600 m; qui si scendono 780 m.
    path = build_flight(
        tmp_path / "x.igc",
        soaring_duration_s=7200,
        distance_m=60_000,
        altitude=descending_profile(top=800, bottom=20),
    )
    req = _by_code(_report(path), "distanza")

    assert req.verdict is Verdict.FAIL
    assert "oltre il limite" in " ".join(req.reasons)


def test_out_and_return_measures_the_farthest_point(tmp_path):
    # Andata e ritorno al campo: la distanza sgancio->atterraggio sarebbe ~0,
    # quella corretta e' fino al punto piu' lontano.
    path = build_flight(
        tmp_path / "oar.igc",
        soaring_duration_s=7200,
        distance_m=62_000,
        out_and_return=True,
        altitude=climbing_profile(1500),
    )
    flight = parse_igc(path)
    analysis = analyse(flight)
    req = _by_code(validate_silver(flight, analysis), "distanza")

    assert analysis.distance_m / 1000 > 55
    assert analysis.farthest.index < analysis.landing.index
    assert req.verdict is Verdict.PASS


def test_far_point_close_to_takeoff_airfield_fails(tmp_path):
    # Punto piu' lontano oltre 50 km dallo sgancio ma vicino al campo di
    # decollo: non e' una distanza valida.
    path = build_flight(
        tmp_path / "near.igc",
        soaring_duration_s=7200,
        distance_m=51_000,
        altitude=descending_profile(top=800, bottom=700),
    )
    flight = parse_igc(path)
    analysis = analyse(flight)
    # Sposta artificialmente il decollo accanto al punto piu' lontano.
    analysis.distance_from_takeoff_m = 4_000.0
    req = _by_code(validate_silver(flight, analysis), "distanza")

    assert req.verdict is Verdict.FAIL
    assert "aeroporto di decollo" in " ".join(req.reasons)


def test_distance_too_short(tmp_path):
    path = build_flight(
        tmp_path / "x.igc",
        soaring_duration_s=7200,
        distance_m=30_000,
        altitude=descending_profile(top=800, bottom=600),
    )
    req = _by_code(_report(path), "distanza")

    assert req.verdict is Verdict.FAIL


def test_complete_flight_satisfies_all_three(tmp_path):
    path = build_flight(
        tmp_path / "full.igc",
        soaring_duration_s=FIVE_HOURS + 1800,
        distance_m=60_000,
        altitude=climbing_profile(1500),
    )
    report = _report(path)

    assert report.complete is True
    assert "VALIDO" in render(report)


def test_missing_g_record_is_warned(tmp_path):
    path = build_flight(
        tmp_path / "nog.igc",
        soaring_duration_s=3600,
        distance_m=10_000,
        altitude=climbing_profile(300),
        with_g_record=False,
    )
    report = _report(path)

    assert any("G-record" in w for w in report.warnings)


def test_report_contains_method_and_reasons(tmp_path):
    path = build_flight(
        tmp_path / "r.igc",
        soaring_duration_s=3600,
        distance_m=10_000,
        altitude=climbing_profile(300),
    )
    text = render(_report(path))

    assert "Come e' stato verificato" in text
    assert "Motivazione" in text
    assert "ESITO COMPLESSIVO" in text
