from __future__ import annotations

from pathlib import Path

from flights import build_flight, climbing_profile, descending_profile
from silverc.analysis import analyse
from silverc.igc import parse_igc
from silverc.report import render
from silverc.validator import Verdict, _loss_of_height, validate_silver

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


def test_silver_distance_notes_flight_without_guidance(tmp_path):
    path = build_flight(
        tmp_path / "x.igc",
        soaring_duration_s=7200,
        distance_m=60_000,
        altitude=descending_profile(top=800, bottom=500),
    )
    req = _by_code(_report(path), "distanza")

    assert "guida di un altro pilota" in " ".join(req.method)


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


def test_loss_of_height_short_course_gnss_limit():
    # 60 km con quota GNSS: limite 600 - 100 = 500 m, 550 m invalidano.
    check = _loss_of_height(60_000, 550, gnss=True)

    assert check.limit_m == 500
    assert check.invalid is True


def test_loss_of_height_short_course_barometric_limit():
    check = _loss_of_height(60_000, 550, gnss=False)

    assert check.limit_m == 600
    assert check.invalid is False
    assert check.official_m == 60_000


def test_loss_of_height_long_course_shortens_distance():
    # 130 km con 1500 m di perdita: 500 m di eccesso tolgono 50 km.
    check = _loss_of_height(130_000, 1500, gnss=False)

    assert check.invalid is False
    assert check.official_m == 80_000


def test_loss_of_height_long_course_gnss_limit():
    check = _loss_of_height(300_000, 1000, gnss=True)

    assert check.limit_m == 900
    assert check.official_m == 290_000


def test_loss_of_height_at_100km_uses_the_ratio():
    # 100 km esatti sono ancora nella regola dell'1%: 1001 m invalidano.
    check = _loss_of_height(100_000, 1001, gnss=False)

    assert check.limit_m == 1000
    assert check.invalid is True


def test_loss_of_height_rule_follows_flown_distance():
    # 101 km con 1500 m di perdita scendono a 51 km, ma restano nella regola
    # oltre i 100 km: nessuna invalidita', solo la riduzione.
    check = _loss_of_height(101_000, 1500, gnss=False)

    assert check.invalid is False
    assert check.official_m == 51_000


def test_loss_of_height_gain_is_not_penalised():
    check = _loss_of_height(130_000, -200, gnss=False)

    assert check.excess_m == 0
    assert check.official_m == 130_000


def test_long_silver_distance_is_shortened_not_invalidated(tmp_path):
    # 130 km con 1500 m di perdita: con l'1% sarebbe bocciato, per il §2.4.4
    # valgono 80 km, oltre i 50 richiesti.
    path = build_flight(
        tmp_path / "x.igc",
        soaring_duration_s=7200,
        distance_m=130_000,
        altitude=descending_profile(top=800, bottom=500),
    )
    flight = parse_igc(path)
    analysis = analyse(flight, calibrated=True)
    analysis.loss_of_height_m = 1500.0
    req = _by_code(validate_silver(flight, analysis), "distanza")

    assert analysis.distance_m > 100_000
    assert req.verdict is Verdict.PASS
    assert req.measured == f"{(analysis.distance_m - 50_000) / 1000:.2f} km"
    assert "eccesso di 500 m" in " ".join(req.reasons)


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
    # Sposta artificialmente il decollo accanto al punto piu' lontano; nessun
    # altro fix e' candidato.
    analysis.distance_from_takeoff_m = 4_000.0
    analysis.balanced_finish = None
    req = _by_code(validate_silver(flight, analysis), "distanza")

    assert req.verdict is Verdict.FAIL
    assert "corsa di decollo" in " ".join(req.reasons)


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


def _edit_b_records(path, edit) -> None:
    lines = Path(path).read_text(encoding="latin-1").splitlines()
    b_index = [i for i, line in enumerate(lines) if line.startswith("B")]
    edit(lines, b_index)
    Path(path).write_text("\n".join(line for line in lines if line is not None) + "\n", encoding="latin-1")


def test_recording_gap_is_warned(tmp_path):
    path = build_flight(
        tmp_path / "g.igc",
        soaring_duration_s=FIVE_HOURS + 600,
        distance_m=60_000,
        altitude=climbing_profile(1500),
    )

    def drop(lines, b_index):
        # Cinque fix consecutivi in meno a meta' volo: un buco di 180 s.
        for i in b_index[300:305]:
            lines[i] = None

    _edit_b_records(path, drop)
    report = _report(path)

    assert any("buchi di registrazione" in w and "180 s" in w for w in report.warnings)
    assert report.complete is True


def test_intermediate_stop_makes_requirements_undetermined(tmp_path):
    path = build_flight(
        tmp_path / "s.igc",
        soaring_duration_s=FIVE_HOURS + 600,
        distance_m=60_000,
        altitude=climbing_profile(1500),
    )

    def park(lines, b_index):
        # Dieci minuti fermi nella stessa posizione a meta' volo.
        anchor = lines[b_index[300]]
        for i in b_index[301:321]:
            lines[i] = lines[i][:7] + anchor[7:24] + lines[i][24:]

    _edit_b_records(path, park)
    report = _report(path)

    assert report.analysis.intermediate_stops
    assert all(r.verdict is not Verdict.PASS for r in report.requirements)
    assert "§2.4.5" in " ".join(_by_code(report, "durata").reasons)
