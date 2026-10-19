"""Interfaccia a riga di comando del validatore."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from silverc.analysis import analyse
from silverc.documentation import RecorderKind
from silverc.igc import IGCParseError, parse_igc
from silverc.report import render
from silverc.rules import BADGES
from silverc.validator import validate_badge

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_NOT_VALID = 1
EXIT_ERROR = 2

_RECORDER_CHOICES = {
    "auto": None,
    "fr": RecorderKind.FLIGHT_RECORDER,
    "pr": RecorderKind.POSITION_RECORDER,
}


def _parse_release_time(value: str) -> datetime:
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=timezone.utc)
    raise argparse.ArgumentTypeError("orario di sgancio atteso come HH:MM:SS (UTC)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="silverc",
        description="Valida un file IGC rispetto ai requisiti delle insegne FAI.",
    )
    parser.add_argument("igc_file", help="percorso del file IGC da analizzare")
    parser.add_argument(
        "--badge",
        choices=sorted(BADGES),
        default="argento",
        help="insegna da verificare (default: argento)",
    )
    parser.add_argument(
        "--release-time",
        type=_parse_release_time,
        metavar="HH:MM:SS",
        help="orario UTC di sgancio dal traino; se assente viene stimato dalla traccia",
    )
    parser.add_argument(
        "--gnss-altitude",
        action="store_true",
        help="usa la quota GNSS invece di quella barometrica (con penalizzazione)",
    )
    parser.add_argument(
        "--recorder",
        choices=sorted(_RECORDER_CHOICES),
        default="auto",
        help="tipo di registratore: fr (Flight Recorder approvato IGC), pr (Position "
        "Recorder), auto (ricavato dal file; default)",
    )
    parser.add_argument(
        "--calibrated",
        action="store_true",
        help="il registratore ha dati di taratura barometrica: usa la quota barometrica "
        "senza margine; altrimenti quota GNSS e margine di 100 m (SC3 §2.4.6)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log di dettaglio su stderr")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s - %(name)s - %(message)s",
        stream=sys.stderr,
    )

    try:
        flight = parse_igc(args.igc_file)
    except IGCParseError as exc:
        sys.stderr.write(f"Errore: {exc}\n")
        return EXIT_ERROR

    release_time = args.release_time
    if release_time is not None and flight.flight_date is not None:
        release_time = release_time.replace(
            year=flight.flight_date.year,
            month=flight.flight_date.month,
            day=flight.flight_date.day,
        )
    elif release_time is not None and flight.fixes:
        first = flight.fixes[0].time
        release_time = release_time.replace(year=first.year, month=first.month, day=first.day)

    analysis = analyse(
        flight,
        release_time=release_time,
        use_gnss_altitude=args.gnss_altitude,
        recorder_kind=_RECORDER_CHOICES[args.recorder],
        calibrated=args.calibrated,
    )
    report = validate_badge(flight, analysis, BADGES[args.badge])
    sys.stdout.write(render(report) + "\n")
    return EXIT_OK if report.complete else EXIT_NOT_VALID


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
