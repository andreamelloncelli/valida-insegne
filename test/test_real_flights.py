"""Test funzionali finali sui voli reali di `data/VoliTest`.

Vedi `real_flights.py` per le fonti delle aspettative. Gli `xfail` sono
discordanze fra la prova tentata e l'esito del validatore ancora da
verificare: sono `strict`, quindi una correzione che li fa passare obbliga ad
aggiornare il catalogo.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from real_flights import (
    ALL_IGC,
    AMIDEO,
    CLAIMS,
    DATA_DIR,
    GHIRINGHELLI_500,
    GUGGIARI_50,
    GUGGIARI_500,
    GUGGIARI_750,
    LOCURCIO,
    LORO_5H,
    LORO_GAIN,
    MATTEI_FRAGMENT,
    ORLANDI_300,
    SILVER_COMPLETE,
    SILVER_INCOMPLETE,
    SQUADRITO_50,
    ZARA_300,
    ZARA_50,
    ZERO_DECLARATIONS,
    FlightCase,
    km,
    load,
    report,
    requirement,
)
from silverc import cli
from silverc.analysis import analyse
from silverc.documentation import RecorderKind, check_headers
from silverc.report import render
from silverc.rules import RECORDERS
from silverc.validator import Verdict

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATA_DIR.is_dir(), reason=f"{DATA_DIR} assente (non versionata)"),
]

BADGES = ("argento", "oro")


def _seconds(hms: str) -> int:
    """'5h 03m 25s' -> secondi."""
    h, m, s = (int(part[:-1]) for part in hms.split())
    return h * 3600 + m * 60 + s


def _headers(path: str) -> dict[str, bool | None]:
    return {check.label: check.ok for check in check_headers(load(path)[0])}


def _at_utc(flight, hhmmss: str) -> datetime:
    h, m, s = map(int, hhmmss.split(":"))
    day = flight.fixes[0].time
    return day.replace(hour=h, minute=m, second=s, microsecond=0, tzinfo=timezone.utc)


# --- 1. Robustezza su tutti i file -------------------------------------------


@pytest.mark.parametrize("path", ALL_IGC)
def test_parses_analyses_and_renders(path):
    for badge in BADGES:
        rep = report(path, badge)
        assert len(rep.requirements) == 3
        assert render(rep).strip()


@pytest.mark.parametrize("path", ALL_IGC)
def test_invariants(path):
    flight, analysis = load(path)
    first, last = flight.fixes[0].time, flight.fixes[-1].time

    assert first <= analysis.release.time <= last
    assert analysis.release.time <= analysis.landing.time
    assert 0 <= analysis.duration_s <= (last - first).total_seconds()
    assert analysis.height_gain.gain_m >= 0
    assert analysis.distance_m >= 0
    for badge in BADGES:
        rep = report(path, badge)
        assert all(isinstance(r.verdict, Verdict) for r in rep.requirements)
        assert rep.complete == all(r.verdict is Verdict.PASS for r in rep.requirements)


@pytest.mark.parametrize("path", ALL_IGC)
def test_recorder_kind_follows_manufacturer_code(path):
    flight, analysis = load(path)
    code = flight.manufacturer_code

    if code.startswith(RECORDERS.unapproved_prefix):
        assert analysis.recorder.kind is RecorderKind.POSITION_RECORDER
    elif code in RECORDERS.approved_manufacturers and flight.has_g_record:
        assert analysis.recorder.kind is RecorderKind.FLIGHT_RECORDER


@pytest.mark.parametrize("path", ALL_IGC)
def test_uncalibrated_recorder_uses_gnss_with_100m_margin(path):
    """§2.4.6a: senza taratura, FR o PR, quota GNSS e soglia +100 m."""
    assert load(path)[1].altitude_source == "GNSS"
    assert requirement(report(path, "argento"), "quota").required == "1100 m"
    assert requirement(report(path, "oro"), "quota").required == "3100 m"


def test_calibrated_flight_recorder_uses_barometric_altitude_without_margin():
    from silverc.rules import SILVER
    from silverc.validator import check_height_gain

    flight, _ = load(SILVER_INCOMPLETE[1])
    analysis = analyse(flight, calibrated=True)

    assert analysis.altitude_source.startswith("barometrica")
    assert check_height_gain(analysis, SILVER).required == "1000 m"


# --- 2. Oracolo della perizia ------------------------------------------------


def test_perizia_zara_50km():
    """START50 10:43:23, END50 a 42 km: distanza insufficiente; 5h e quota ok."""
    flight, analysis = load(ZARA_50)
    rep = report(ZARA_50, "argento")

    assert abs((analysis.release.time - _at_utc(flight, "10:43:23")).total_seconds()) <= 60
    distance = requirement(rep, "distanza")
    assert distance.verdict is Verdict.FAIL
    assert km(distance.measured) == pytest.approx(42.0, abs=1.0)
    assert requirement(rep, "durata").verdict is Verdict.PASS
    assert requirement(rep, "quota").verdict is Verdict.PASS
    assert analysis.height_gain.gain_m >= 1810 - 100
    assert analysis.recorder.kind is RecorderKind.POSITION_RECORDER


def test_perizia_squadrito_50km():
    """Valido per le 3 prove: 51.5 km, 5h, guadagno 2737 m. Marche mancanti."""
    _, analysis = load(SQUADRITO_50)
    rep = report(SQUADRITO_50, "argento")

    distance = requirement(rep, "distanza")
    assert distance.verdict is Verdict.PASS
    assert km(distance.measured) == pytest.approx(51.5, abs=1.0)
    # La perizia misura 5:44 da un altro istante: si confronta solo il verdetto.
    assert requirement(rep, "durata").verdict is Verdict.PASS
    assert requirement(rep, "quota").verdict is Verdict.PASS
    assert analysis.height_gain.gain_m == pytest.approx(2737, abs=100)
    assert analysis.recorder.kind is RecorderKind.POSITION_RECORDER
    # Corrispondenza parziale: la perizia dice "mancano", il validatore
    # trova 'DUO DISCUS-1' e chiede di verificarlo.
    assert _headers(SQUADRITO_50)["Marche"] is not True


def test_perizia_guggiari_50km():
    """72 km dallo sgancio, guadagno 2395 m."""
    _, analysis = load(GUGGIARI_50)
    rep = report(GUGGIARI_50, "argento")

    distance = requirement(rep, "distanza")
    assert distance.verdict is Verdict.PASS
    assert km(distance.measured) == pytest.approx(72.0, abs=2.0)
    assert analysis.height_gain.gain_m == pytest.approx(2395, abs=100)
    assert analysis.recorder.kind is RecorderKind.POSITION_RECORDER


def test_perizia_zara_300km():
    """Tema dichiarato e aggirato correttamente, dichiarazione completa."""
    _, analysis = load(ZARA_300)
    distance = requirement(report(ZARA_300, "oro"), "distanza")

    assert distance.verdict is Verdict.PASS
    assert km(distance.measured) >= 300
    assert all(_headers(ZARA_300)[label] for label in ("Pilota", "Tipo di aliante", "Marche"))
    assert analysis.recorder.kind is RecorderKind.POSITION_RECORDER


@pytest.mark.xfail(
    strict=True,
    reason="da verificare: per il validatore la partenza dichiarata e' attraversata "
    "solo prima dello sgancio (§1.3.1), la perizia la considera aggirata",
)
def test_perizia_zara_300km_declared_course_flown():
    task_check = load(ZARA_300)[1].task_check
    flown = task_check.in_order or task_check

    assert flown.completed
    assert flown.distance_m / 1000 == pytest.approx(301.7, abs=1.0)


def test_perizia_guggiari_500km():
    """Tema di 500.7 km valido; mancano tipo d'aliante e marche."""
    _, analysis = load(GUGGIARI_500)
    distance = requirement(report(GUGGIARI_500, "oro"), "distanza")
    declared = analysis.task_check.in_order or analysis.task_check

    assert distance.verdict is Verdict.PASS
    assert declared.distance_m / 1000 == pytest.approx(500.7, abs=1.0)
    headers = _headers(GUGGIARI_500)
    assert headers["Pilota"] is True
    # Il tipo non e' richiesto in dichiarazione (§4.3.1): segnalato da verificare.
    assert headers["Tipo di aliante"] is not True
    assert headers["Marche"] is False


@pytest.mark.xfail(
    strict=True,
    reason="da verificare: la perizia taglia la partenza a 1692 m e l'arrivo a "
    "1109 m (583 m); il validatore non riconosce la partenza dopo lo sgancio",
)
def test_perizia_guggiari_500km_loss_of_height():
    task_check = load(GUGGIARI_500)[1].task_check
    declared = task_check.in_order or task_check

    assert declared.completed
    assert declared.loss_of_height_m == pytest.approx(583, abs=30)


# --- 3. Prove tentate secondo la cartella ------------------------------------


def _claim_param(case: FlightCase):
    marks = [pytest.mark.xfail(strict=True, reason=case.xfail)] if case.xfail else []
    return pytest.param(case, id=case.id, marks=marks)


@pytest.mark.parametrize("case", [_claim_param(c) for c in CLAIMS])
def test_folder_claim(case: FlightCase):
    req = requirement(report(case.path, case.badge), case.code)

    assert req.verdict is case.expected, f"[{case.source}] {req.measured}: {req.reasons}"


# --- 4. Stesso volo in piu' file ---------------------------------------------


@pytest.mark.parametrize("pair", [LORO_GAIN, LORO_5H, GHIRINGHELLI_500], ids=str)
def test_copies_of_the_same_file_give_the_same_report(pair):
    for badge in BADGES:
        a, b = (report(path, badge) for path in pair)
        assert [(r.verdict, r.measured) for r in a.requirements] == [
            (r.verdict, r.measured) for r in b.requirements
        ]


def _assert_same_flight(pair, *, duration_s: float = 120, gain_m: float = 150):
    (_, a), (_, b) = (load(path) for path in pair)

    assert a.distance_m / 1000 == pytest.approx(b.distance_m / 1000, abs=1.0)
    assert a.duration_s == pytest.approx(b.duration_s, abs=duration_s)
    assert a.height_gain.gain_m == pytest.approx(b.height_gain.gain_m, abs=gain_m)


def test_same_flight_on_flight_recorder_and_position_recorder():
    _assert_same_flight(LOCURCIO)


def test_same_flight_across_gps_week_rollover():
    _assert_same_flight(AMIDEO)
    (f_1999, _), (f_2019, _) = (load(path) for path in AMIDEO)
    # Rollover della settimana GPS: 1024 settimane.
    assert (f_2019.flight_date - f_1999.flight_date).days == 1024 * 7


@pytest.mark.xfail(
    strict=True,
    reason="da verificare: sgancio alle 06:01:36 sul LX (fix ogni 12 s) e alle "
    "06:07:23 su XCSoar (fix ogni secondo), durate diverse di 6 minuti",
)
def test_same_flight_on_two_loggers_guggiari_750():
    _assert_same_flight(GUGGIARI_750)


# --- 5. Casi limite ----------------------------------------------------------


def test_fragment_has_undetermined_duration():
    _, analysis = load(MATTEI_FRAGMENT)
    duration = requirement(report(MATTEI_FRAGMENT, "argento"), "durata")

    assert analysis.release_confidence in {"bassa", "nulla"}
    assert duration.verdict is Verdict.UNDETERMINED


def test_declared_distance_just_over_300km_is_marginal():
    distance = requirement(report(ORLANDI_300, "oro"), "distanza")

    assert distance.verdict is Verdict.MARGINAL
    assert km(distance.measured) == pytest.approx(300.9, abs=0.1)


@pytest.mark.parametrize("path", ZERO_DECLARATIONS)
@pytest.mark.xfail(
    strict=True,
    reason="da decidere: una dichiarazione con coordinate tutte a zero e' un "
    "segnaposto del logger e andrebbe trattata come assente",
)
def test_zero_coordinate_declaration_is_treated_as_missing(path):
    assert load(path)[1].task_check is None


def test_missing_pilot_name_is_flagged():
    assert _headers(LORO_5H[0])["Pilota"] is False


# --- 6. CLI end-to-end -------------------------------------------------------


@pytest.mark.parametrize("path", SILVER_COMPLETE)
def test_cli_exit_ok_on_complete_silver(path, capsys):
    assert cli.main([str(DATA_DIR / path)]) == cli.EXIT_OK
    assert capsys.readouterr().out.strip()


@pytest.mark.parametrize("path", SILVER_INCOMPLETE)
def test_cli_exit_not_valid_on_incomplete_silver(path, capsys):
    assert cli.main([str(DATA_DIR / path)]) == cli.EXIT_NOT_VALID


def test_cli_gold_badge(capsys):
    """Tommaso Guggiari 500: distanza d'oro valida, guadagno di 3000 m mancante."""
    assert cli.main([str(DATA_DIR / GUGGIARI_500), "--badge", "oro"]) == cli.EXIT_NOT_VALID
    assert "300 km" in capsys.readouterr().out


def test_cli_release_time_override(capsys):
    cli.main([str(DATA_DIR / ZARA_50), "--release-time", "10:43:23"])

    out = capsys.readouterr().out
    assert "10:43:23" in out
    assert "dichiarato dall'utente" in out
