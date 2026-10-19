"""Controlli documentali: intestazione IGC, tipo di registratore e quota."""

from __future__ import annotations

from pathlib import Path

from flights import build_flight, climbing_profile, descending_profile
from silverc.analysis import analyse
from silverc.documentation import RecorderKind, check_headers, classify_recorder
from silverc.igc import parse_igc
from silverc.report import render
from silverc.validator import Verdict, validate_silver

FIVE_HOURS = 5 * 3600


def _flight(tmp_path, **header):
    path = build_flight(
        tmp_path / "f.igc",
        soaring_duration_s=3600,
        distance_m=5_000,
        altitude=descending_profile(),
        **header,
    )
    return parse_igc(path)


def _gain_report(tmp_path, gain: int, **kwargs):
    header = {k: v for k, v in kwargs.items() if k in {"a_record", "fr_type"}}
    flight_kwargs = {k: v for k, v in kwargs.items() if k not in header}
    path = build_flight(
        tmp_path / "q.igc",
        soaring_duration_s=FIVE_HOURS,
        distance_m=5_000,
        altitude=climbing_profile(gain),
        **header,
    )
    flight = parse_igc(path)
    report = validate_silver(flight, analyse(flight, **flight_kwargs))
    return next(r for r in report.requirements if r.code == "quota"), report


def _checks(flight):
    return {c.label: c for c in check_headers(flight)}


def test_approved_manufacturer_with_g_record_is_flight_recorder(tmp_path):
    info = classify_recorder(_flight(tmp_path))

    assert info.kind is RecorderKind.FLIGHT_RECORDER
    assert info.manufacturer == "LXV"


def test_x_manufacturer_is_position_recorder(tmp_path):
    info = classify_recorder(_flight(tmp_path, a_record="AXCSAAA XCSoar"))

    assert info.kind is RecorderKind.POSITION_RECORDER
    assert "X iniziale" in " ".join(info.reasons)


def test_approved_manufacturer_without_g_record_is_position_recorder(tmp_path):
    info = classify_recorder(_flight(tmp_path, with_g_record=False))

    assert info.kind is RecorderKind.POSITION_RECORDER
    assert "G-record assente" in " ".join(info.reasons)


def test_vague_recorder_type_falls_back_to_position_recorder(tmp_path):
    info = classify_recorder(_flight(tmp_path, fr_type="NKN"))

    assert info.kind is RecorderKind.POSITION_RECORDER


def test_user_override_wins_over_file(tmp_path):
    flight = _flight(tmp_path, a_record="AXCSAAA XCSoar")
    info = classify_recorder(flight, RecorderKind.FLIGHT_RECORDER)

    assert info.kind is RecorderKind.FLIGHT_RECORDER
    assert info.source == "indicato dall'utente"


def test_flight_recorder_uses_barometric_threshold(tmp_path):
    # 1050 m di guadagno: sopra i 1000 m richiesti con un FR approvato.
    req, report = _gain_report(tmp_path, 1050)

    assert report.analysis.altitude_source.startswith("barometrica")
    assert req.verdict is Verdict.PASS
    assert req.required == "1000 m"


def test_position_recorder_requires_100m_more_on_gnss(tmp_path):
    # Stesso volo con un Position Recorder: servono 1100 m sulla quota GNSS.
    req, report = _gain_report(tmp_path, 1050, a_record="AXCSAAA XCSoar")

    assert report.analysis.altitude_source == "GNSS"
    assert req.required == "1100 m"
    assert req.verdict is Verdict.FAIL
    assert "Position Recorder" in " ".join(req.reasons)


def test_position_recorder_without_gnss_altitude_is_undetermined(tmp_path):
    path = build_flight(
        tmp_path / "q.igc",
        soaring_duration_s=FIVE_HOURS,
        distance_m=5_000,
        altitude=climbing_profile(1500),
        a_record="AXCSAAA XCSoar",
    )
    text = Path(path).read_text(encoding="latin-1").splitlines()
    # Azzera la colonna GNSS dei B-record, come fanno alcuni logger.
    zeroed = [line[:30] + "00000" + line[35:] if line.startswith("B") else line for line in text]
    Path(path).write_text("\n".join(zeroed) + "\n", encoding="latin-1")
    flight = parse_igc(path)
    report = validate_silver(flight, analyse(flight))
    req = next(r for r in report.requirements if r.code == "quota")

    assert req.verdict is Verdict.UNDETERMINED


def test_loss_of_height_limit_has_no_gnss_deduction(tmp_path):
    # Con un PR la quota e' GNSS, ma il limite di perdita resta l'1% della
    # distanza: la maggiorazione di 100 m riguarda solo il guadagno di quota.
    path = build_flight(
        tmp_path / "d.igc",
        soaring_duration_s=3 * 3600,
        distance_m=60_000,
        altitude=descending_profile(top=800, bottom=500),
        a_record="AXCSAAA XCSoar",
    )
    flight = parse_igc(path)
    report = validate_silver(flight, analyse(flight))
    req = next(r for r in report.requirements if r.code == "distanza")
    expected = round(report.analysis.distance_m * 0.01)

    assert report.analysis.altitude_source == "GNSS"
    assert f"limite di {expected} m" in " ".join(req.reasons)


def test_position_recorder_passes_with_margin(tmp_path):
    req, _ = _gain_report(tmp_path, 1150, a_record="AXCSAAA XCSoar")

    assert req.verdict is Verdict.PASS


def test_override_to_position_recorder_applies_penalty(tmp_path):
    req, _ = _gain_report(tmp_path, 1050, recorder_kind=RecorderKind.POSITION_RECORDER)

    assert req.required == "1100 m"


def test_complete_header_passes(tmp_path):
    checks = _checks(_flight(tmp_path))

    assert all(c.ok for c in checks.values())
    assert checks["Sigla di gara"].value == "n/d"


def test_pilot_needs_name_and_surname(tmp_path):
    checks = _checks(_flight(tmp_path, pilot="Rossi"))

    assert checks["Pilota"].ok is False


def test_missing_glider_type_fails(tmp_path):
    checks = _checks(_flight(tmp_path, glider_type=""))

    assert checks["Tipo di aliante"].ok is False


def test_missing_registration_fails(tmp_path):
    checks = _checks(_flight(tmp_path, registration=""))

    assert checks["Marche"].ok is False


def test_unusual_registration_is_flagged_not_failed(tmp_path):
    checks = _checks(_flight(tmp_path, registration="ROSSI GLIDER"))

    assert checks["Marche"].ok is None


def test_competition_id_is_optional(tmp_path):
    checks = _checks(_flight(tmp_path, competition_id="MR"))

    assert checks["Sigla di gara"].ok is True
    assert checks["Sigla di gara"].value == "MR"


def test_report_shows_documentation_section(tmp_path):
    flight = _flight(tmp_path, pilot="Rossi", a_record="AXCSAAA XCSoar")
    text = render(validate_silver(flight, analyse(flight)))

    assert "DOCUMENTAZIONE DEL FILE IGC" in text
    assert "Position Recorder" in text
    assert "[NO] Pilota" in text
