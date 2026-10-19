"""Tabella di taratura barometrica."""

from __future__ import annotations

import pytest

from flights import build_flight, climbing_profile
from silverc.analysis import analyse
from silverc.calibration import CalibrationError, load_calibration, parse_calibration
from silverc.igc import parse_igc
from silverc.validator import Verdict, validate_silver

FIVE_HOURS = 5 * 3600


def test_table_interpolates_between_points():
    table = parse_calibration("indicata;vera\n0;0\n1000;950\n2000;1900\n")

    assert table.correct(500) == pytest.approx(475)
    assert table.correct(1500) == pytest.approx(1425)


def test_table_extrapolates_with_end_segments():
    table = parse_calibration("0,0\n1000,950\n")

    assert table.correct(2000) == pytest.approx(1900)


def test_table_needs_two_numeric_points():
    with pytest.raises(CalibrationError):
        parse_calibration("0,0\n")
    with pytest.raises(CalibrationError):
        parse_calibration("0,0\nmille,950\n")


def test_missing_file_raises(tmp_path):
    with pytest.raises(CalibrationError):
        load_calibration(tmp_path / "manca.csv")


def test_calibration_corrects_the_height_gain(tmp_path):
    # Il sensore legge il 10% in piu': 1050 m indicati sono 955 m veri.
    path = build_flight(
        tmp_path / "q.igc",
        soaring_duration_s=FIVE_HOURS,
        distance_m=5_000,
        altitude=climbing_profile(1050),
    )
    table = parse_calibration("0,0\n10000,9090.9\n")
    flight = parse_igc(path)
    analysis = analyse(flight, calibration=table)
    req = next(r for r in validate_silver(flight, analysis).requirements if r.code == "quota")

    assert analysis.calibrated is True
    assert "taratura" in analysis.altitude_source
    assert req.required == "1000 m"
    assert req.verdict is Verdict.FAIL
