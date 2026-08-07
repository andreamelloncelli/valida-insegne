from __future__ import annotations

import pytest

from igc_builder import IGCBuilder
from silverc.igc import IGCParseError, parse_igc

LAT, LON = 45.0, 9.0


def test_parse_header_and_fix(tmp_path):
    builder = IGCBuilder()
    builder.fix(36000, LAT, LON, 1234)
    path = builder.write(tmp_path / "a.igc")

    flight = parse_igc(path)

    assert len(flight.fixes) == 1
    fix = flight.fixes[0]
    assert fix.time.strftime("%H:%M:%S") == "10:00:00"
    assert fix.pressure_alt == 1234
    assert fix.valid is True
    assert flight.pilot == "Mario Rossi"
    assert flight.flight_date.isoformat() == "2025-06-15"
    assert flight.has_g_record is True
    assert abs(fix.lat - LAT) < 1e-6
    assert abs(fix.lon - LON) < 1e-6


def test_southern_western_hemisphere(tmp_path):
    builder = IGCBuilder()
    builder.fix(36000, -33.5, -70.25, 500)
    flight = parse_igc(builder.write(tmp_path / "s.igc"))

    assert flight.fixes[0].lat == pytest.approx(-33.5, abs=1e-5)
    assert flight.fixes[0].lon == pytest.approx(-70.25, abs=1e-5)


def test_midnight_rollover(tmp_path):
    builder = IGCBuilder()
    for offset in range(0, 600, 60):
        builder.fix(86100 + offset, LAT, LON, 1000)
    flight = parse_igc(builder.write(tmp_path / "m.igc"))

    span = (flight.fixes[-1].time - flight.fixes[0].time).total_seconds()
    assert span == 540


def test_altitude_spike_is_rejected(tmp_path):
    builder = IGCBuilder()
    builder.fix(36000, LAT, LON, 1000)
    builder.fix(36005, LAT, LON, 99999)
    builder.fix(36010, LAT, LON, 1010)
    flight = parse_igc(builder.write(tmp_path / "spike.igc"))

    assert [f.pressure_alt for f in flight.fixes] == [1000, 1010]
    assert len(flight.rejected) == 1


def test_enl_extension_is_read(tmp_path):
    builder = IGCBuilder(with_enl=True)
    builder.fix(36000, LAT, LON, 1000, enl=750)
    flight = parse_igc(builder.write(tmp_path / "enl.igc"))

    assert flight.has_enl is True
    assert flight.fixes[0].enl == 750


def test_empty_file_raises(tmp_path):
    path = tmp_path / "empty.igc"
    path.write_text("AXXX001\n", encoding="latin-1")

    with pytest.raises(IGCParseError):
        parse_igc(path)
