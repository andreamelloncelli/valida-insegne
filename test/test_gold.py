"""Distanza d'oro: percorso dichiarato e punti di virata."""

from __future__ import annotations

import math

from igc_builder import IGCBuilder, offset_lat, offset_lon
from silverc.analysis import analyse
from silverc.igc import parse_igc
from silverc.rules import GOLD
from silverc.report import render
from silverc.validator import Verdict, check_declared_distance, validate_badge

LAT, LON = 45.0, 9.0
START = 36000
_STEP = 30


def _coord(east_m: float, north_m: float) -> tuple[float, float]:
    return offset_lat(LAT, north_m), offset_lon(LON, LAT, east_m)


def _altitude(frac: float) -> int:
    if frac < 0.1:
        return int(800 - 4000 * frac)
    if frac < 0.6:
        return int(400 + 3300 * (frac - 0.1) / 0.5)
    return 3700


def build_gold_flight(
    path,
    *,
    legs: list[tuple[float, float]],
    declared: list[tuple[float, float, str]],
    soaring_s: int = 6 * 3600,
    declared_hhmmss: str = "090000",
) -> str:
    """Volo che percorre `legs` (offset est/nord in metri) dopo lo sgancio."""
    builder = IGCBuilder()
    if declared:
        builder.declare(
            [(*_coord(east, north), name) for east, north, name in declared],
            declared_hhmmss=declared_hhmmss,
        )

    for t in range(0, 120, 20):
        builder.fix(START + t, LAT, LON, 200)
    for t in range(120, 421, _STEP):
        frac = (t - 120) / 300
        lat, lon = _coord(3000 * frac, 0)
        builder.fix(START + t, lat, lon, int(200 + 600 * frac))

    spans = [math.dist(a, b) for a, b in zip(legs, legs[1:])]
    total = sum(spans)
    elapsed = 0.0
    t = 421
    for (start_leg, end_leg), span in zip(zip(legs, legs[1:]), spans):
        steps = max(2, int(soaring_s * span / total / _STEP))
        for k in range(1, steps + 1):
            ratio = k / steps
            east = start_leg[0] + (end_leg[0] - start_leg[0]) * ratio
            north = start_leg[1] + (end_leg[1] - start_leg[1]) * ratio
            elapsed += _STEP
            t += _STEP
            lat, lon = _coord(east, north)
            builder.fix(START + t, lat, lon, _altitude(elapsed / soaring_s))

    lat, lon = _coord(*legs[-1])
    for ground in range(t + 20, t + 200, 20):
        builder.fix(START + ground, lat, lon, _altitude(1.0))
    return builder.write(path)


# Andata e ritorno dichiarato: casa -> 160 km a est -> casa = 320 km.
_OUT_AND_RETURN = [(3000.0, 0.0), (0.0, 0.0), (160_000.0, 0.0), (0.0, 0.0)]
_DECLARED = [
    (0.0, 0.0, "DECOLLO"),
    (0.0, 0.0, "PARTENZA"),
    (160_000.0, 0.0, "VIRATA EST"),
    (0.0, 0.0, "ARRIVO"),
    (0.0, 0.0, "ATTERRAGGIO"),
]


def _requirement(path, code: str = "distanza"):
    flight = parse_igc(path)
    report = validate_badge(flight, analyse(flight), GOLD)
    return next(r for r in report.requirements if r.code == code), report


def test_declared_task_is_parsed(tmp_path):
    path = build_gold_flight(tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=_DECLARED)
    task = parse_igc(path).task

    assert task is not None
    assert len(task.turnpoints) == 1
    assert task.turnpoints[0].name == "VIRATA EST"
    assert task.start.name == "PARTENZA"
    assert task.finish.name == "ARRIVO"


def test_completed_300km_task_passes(tmp_path):
    path = build_gold_flight(tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=_DECLARED)
    req, report = _requirement(path)

    assert req.verdict is Verdict.PASS
    assert report.analysis.task_check.completed is True
    assert 318 < report.analysis.task_check.distance_m / 1000 < 322
    assert "VIRATA EST" in " ".join(req.reasons)


def test_long_loss_of_height_shortens_declared_distance(tmp_path):
    # 320 km con 2000 m di perdita: con l'1% sarebbe entro i 3200 m, per il
    # §2.4.4 1000 m di eccesso tolgono 100 km e restano ~220 km.
    path = build_gold_flight(tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=_DECLARED)
    flight = parse_igc(path)
    analysis = analyse(flight, calibrated=True)
    analysis.task_check.loss_of_height_m = 2000.0
    report = validate_badge(flight, analysis, GOLD)
    req = next(r for r in report.requirements if r.code == "distanza")

    assert req.verdict is Verdict.FAIL
    assert 218 < float(req.measured.split()[0]) < 222
    assert "eccesso di 1000 m" in " ".join(req.reasons)


def test_report_names_the_course_type(tmp_path):
    path = build_gold_flight(tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=_DECLARED)
    req, _ = _requirement(path)

    assert "andata e ritorno (§1.4.2g)" in " ".join(req.reasons)


def test_start_crossed_only_before_release_is_explained(tmp_path):
    # La partenza dichiarata e' sotto il traino: dopo lo sgancio non si ripassa.
    declared = [
        (0.0, 0.0, "DECOLLO"),
        (1500.0, 0.0, "PARTENZA"),
        (310_000.0, 0.0, "META"),
        (310_000.0, 0.0, "ATTERRAGGIO"),
    ]
    legs = [(3000.0, 0.0), (312_000.0, 0.0)]
    path = build_gold_flight(tmp_path / "g.igc", legs=legs, declared=declared)
    flight = parse_igc(path)
    analysis = analyse(flight)

    assert analysis.task_check.start_before_release is True
    reasons = " ".join(check_declared_distance(analysis, GOLD).reasons)
    assert "prima dello sgancio" in reasons


def test_missed_turnpoint_fails(tmp_path):
    # Il volo si ferma a 150 km: la virata dichiarata a 160 km non viene toccata.
    short = [(3000.0, 0.0), (0.0, 0.0), (150_000.0, 0.0), (0.0, 0.0)]
    path = build_gold_flight(tmp_path / "g.igc", legs=short, declared=_DECLARED)
    req, report = _requirement(path)

    assert req.verdict is Verdict.FAIL
    assert report.analysis.task_check.missed[0].label == "Virata 1"
    assert "NON raggiunto" in " ".join(req.reasons)


def test_declared_task_not_flown_is_not_accepted(tmp_path):
    # Dichiarazione corretta e oltre i 300 km, ma la traccia non torna
    # all'arrivo: la dichiarazione da sola non basta.
    no_return = [(3000.0, 0.0), (0.0, 0.0), (165_000.0, 0.0), (100_000.0, 0.0)]
    path = build_gold_flight(tmp_path / "g.igc", legs=no_return, declared=_DECLARED)
    req, report = _requirement(path)

    assert report.analysis.task_check.distance_m > GOLD.min_distance_m
    assert req.verdict is Verdict.FAIL
    assert [w.label for w in report.analysis.task_check.missed] == ["Arrivo"]
    assert "effettivamente volato" in " ".join(req.reasons)


def test_missed_task_falls_back_to_straight_line(tmp_path):
    # Virata dichiarata a nord mai raggiunta, ma 310 km in linea retta verso
    # est: per il §2.2 il volo vale come linea retta dallo sgancio.
    declared = [
        (0.0, 0.0, "DECOLLO"),
        (0.0, 0.0, "PARTENZA"),
        (0.0, 160_000.0, "VIRATA NORD"),
        (0.0, 0.0, "ARRIVO"),
        (0.0, 0.0, "ATTERRAGGIO"),
    ]
    straight = [(3000.0, 0.0), (313_000.0, 0.0)]
    path = build_gold_flight(tmp_path / "g.igc", legs=straight, declared=declared)
    req, report = _requirement(path)
    reasons = " ".join(req.reasons)

    assert report.analysis.task_check.completed is False
    assert req.verdict is Verdict.PASS
    assert float(req.measured.split()[0]) > 300
    assert "Percorso dichiarato: NON SODDISFATTO" in reasons
    assert "VIRATA NORD" in reasons


def test_failed_task_reports_straight_line_too(tmp_path):
    short = [(3000.0, 0.0), (0.0, 0.0), (150_000.0, 0.0), (0.0, 0.0)]
    path = build_gold_flight(tmp_path / "g.igc", legs=short, declared=_DECLARED)
    req, _ = _requirement(path)

    assert req.verdict is Verdict.FAIL
    assert "In linea retta dallo sgancio" in " ".join(req.reasons)


def test_turnpoints_must_be_in_declared_order(tmp_path):
    # Percorso dichiarato con due virate, volate in ordine invertito.
    declared = [
        (0.0, 0.0, "DECOLLO"),
        (0.0, 0.0, "PARTENZA"),
        (160_000.0, 0.0, "VIRATA A"),
        (0.0, 160_000.0, "VIRATA B"),
        (0.0, 0.0, "ARRIVO"),
        (0.0, 0.0, "ATTERRAGGIO"),
    ]
    legs = [(3000.0, 0.0), (0.0, 0.0), (0.0, 160_000.0), (160_000.0, 0.0), (0.0, 0.0)]
    path = build_gold_flight(tmp_path / "g.igc", legs=legs, declared=declared)
    req, report = _requirement(path)

    assert req.verdict is Verdict.FAIL
    assert [w.label for w in report.analysis.task_check.missed] == ["Virata 2"]


def test_straight_line_300km_without_declaration_passes(tmp_path):
    # §1.4.2d: linea retta con partenza allo sgancio, senza coordinate dichiarate.
    straight = [(3000.0, 0.0), (310_000.0, 0.0)]
    path = build_gold_flight(tmp_path / "g.igc", legs=straight, declared=[])
    req, report = _requirement(path)

    assert report.analysis.task_check is None
    assert req.verdict is Verdict.PASS
    assert float(req.measured.split()[0]) > 300
    assert "1.4.2d" in " ".join(req.reasons)


def test_short_straight_line_without_declaration_fails(tmp_path):
    # Senza dichiarazione conta il punto piu' lontano: 160 km, non i 320 volati.
    path = build_gold_flight(tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=[])
    req, _ = _requirement(path)

    assert req.verdict is Verdict.FAIL
    assert float(req.measured.split()[0]) < 300


def test_gold_straight_line_ignores_distance_from_takeoff(tmp_path):
    # Il §2.2.1a (50 km anche dal fix di decollo) vale solo per l'argento.
    straight = [(3000.0, 0.0), (310_000.0, 0.0)]
    path = build_gold_flight(tmp_path / "g.igc", legs=straight, declared=[])
    req, _ = _requirement(path)

    assert "corsa di decollo" not in " ".join(req.reasons + req.method)


def test_declaration_after_takeoff_is_warned(tmp_path):
    path = build_gold_flight(
        tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=_DECLARED, declared_hhmmss="110000"
    )
    _, report = _requirement(path)

    assert any("prima del volo" in w for w in report.warnings)


def test_declaration_on_ground_before_takeoff_is_accepted(tmp_path):
    # Logger acceso alle 10:00, dichiarazione alle 10:01, decollo alle 10:02.
    path = build_gold_flight(
        tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=_DECLARED, declared_hhmmss="100100"
    )
    _, report = _requirement(path)

    assert not any("prima del volo" in w for w in report.warnings)


def test_internet_declaration_is_reported(tmp_path):
    path = build_gold_flight(
        tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=_DECLARED, declared_hhmmss="110000"
    )
    flight = parse_igc(path)
    report = validate_badge(flight, analyse(flight), GOLD, internet_declaration=True)

    assert any("§2.3a" in w for w in report.warnings)
    assert not any("prima del volo" in w for w in report.warnings)


def test_silver_thresholds_still_apply_to_silver(tmp_path):
    path = build_gold_flight(tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=_DECLARED)
    flight = parse_igc(path)
    silver = validate_badge(flight, analyse(flight))
    req = next(r for r in silver.requirements if r.code == "distanza")

    # Per l'argento conta il punto piu' lontano, non il percorso dichiarato.
    assert req.verdict is Verdict.PASS
    assert float(req.measured.split()[0]) > 155


def _silver_distance(path):
    flight = parse_igc(path)
    report = validate_badge(flight, analyse(flight))
    return next(r for r in report.requirements if r.code == "distanza"), report


def test_silver_far_point_too_close_to_takeoff_fails(tmp_path):
    # Lo sgancio e' 3 km a est del decollo; verso ovest il punto piu' lontano
    # dista 52,5 km dallo sgancio ma solo 49,5 km dal decollo.
    legs = [(3000.0, 0.0), (-49_500.0, 0.0)]
    path = build_gold_flight(tmp_path / "s.igc", legs=legs, declared=[])
    req, report = _silver_distance(path)

    assert report.analysis.distance_m > 50_000
    assert req.verdict is Verdict.FAIL
    assert "corsa di decollo" in " ".join(req.reasons)


def test_silver_picks_a_fix_far_from_both_origins(tmp_path):
    # Il punto piu' lontano dallo sgancio (ovest) e' a 49,5 km dal decollo,
    # ma prima il volo passa per un fix a nord a ~51 km da entrambi.
    legs = [(3000.0, 0.0), (1500.0, 51_000.0), (-49_500.0, 0.0)]
    path = build_gold_flight(tmp_path / "s.igc", legs=legs, declared=[])
    req, report = _silver_distance(path)

    assert report.analysis.distance_from_takeoff_m < 50_000
    assert req.verdict is Verdict.PASS
    assert 50 < float(req.measured.split()[0]) < 52
    assert "§1.2.10c" in " ".join(req.reasons)


def test_report_shows_declared_course(tmp_path):
    path = build_gold_flight(tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=_DECLARED)
    _, report = _requirement(path)
    text = render(report)

    assert "PERCORSO DICHIARATO" in text
    assert "VIRATA EST" in text
    assert "INSEGNA D'ORO" in text
