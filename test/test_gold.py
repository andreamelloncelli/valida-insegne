"""Distanza d'oro: percorso dichiarato e punti di virata."""

from __future__ import annotations

import math

from igc_builder import IGCBuilder, offset_lat, offset_lon
from silverc.analysis import analyse
from silverc.igc import parse_igc
from silverc.rules import GOLD
from silverc.report import render
from silverc.validator import Verdict, validate_badge

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


def test_missed_turnpoint_fails(tmp_path):
    # Il volo si ferma a 150 km: la virata dichiarata a 160 km non viene toccata.
    short = [(3000.0, 0.0), (0.0, 0.0), (150_000.0, 0.0), (0.0, 0.0)]
    path = build_gold_flight(tmp_path / "g.igc", legs=short, declared=_DECLARED)
    req, report = _requirement(path)

    assert req.verdict is Verdict.FAIL
    assert report.analysis.task_check.missed[0].label == "Virata 1"
    assert "NON raggiunto" in " ".join(req.reasons)


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
    # Art. 13.2: linea retta con partenza allo sgancio, senza dichiarazione.
    straight = [(3000.0, 0.0), (310_000.0, 0.0)]
    path = build_gold_flight(tmp_path / "g.igc", legs=straight, declared=[])
    req, report = _requirement(path)

    assert report.analysis.task_check is None
    assert req.verdict is Verdict.PASS
    assert float(req.measured.split()[0]) > 300
    assert "13.2" in " ".join(req.reasons)


def test_short_straight_line_without_declaration_fails(tmp_path):
    # Senza dichiarazione conta il punto piu' lontano: 160 km, non i 320 volati.
    path = build_gold_flight(tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=[])
    req, _ = _requirement(path)

    assert req.verdict is Verdict.FAIL
    assert float(req.measured.split()[0]) < 300


def test_gold_straight_line_ignores_distance_from_takeoff(tmp_path):
    # L'art. 5.1a (50 km anche dal luogo di decollo) vale solo per l'argento.
    straight = [(3000.0, 0.0), (310_000.0, 0.0)]
    path = build_gold_flight(tmp_path / "g.igc", legs=straight, declared=[])
    req, _ = _requirement(path)

    assert "aeroporto di decollo" not in " ".join(req.reasons + req.method)


def test_declaration_after_takeoff_is_warned(tmp_path):
    path = build_gold_flight(
        tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=_DECLARED, declared_hhmmss="110000"
    )
    _, report = _requirement(path)

    assert any("prima del volo" in w for w in report.warnings)


def test_silver_thresholds_still_apply_to_silver(tmp_path):
    path = build_gold_flight(tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=_DECLARED)
    flight = parse_igc(path)
    silver = validate_badge(flight, analyse(flight))
    req = next(r for r in silver.requirements if r.code == "distanza")

    # Per l'argento conta il punto piu' lontano, non il percorso dichiarato.
    assert req.verdict is Verdict.PASS
    assert float(req.measured.split()[0]) > 155


def test_report_shows_declared_course(tmp_path):
    path = build_gold_flight(tmp_path / "g.igc", legs=_OUT_AND_RETURN, declared=_DECLARED)
    _, report = _requirement(path)
    text = render(report)

    assert "PERCORSO DICHIARATO" in text
    assert "VIRATA EST" in text
    assert "INSEGNA D'ORO" in text
