"""Interfaccia a riga di comando del validatore."""

from __future__ import annotations

import argparse
import logging
import sys

from silverc.analysis import analyse, parse_release_time
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
    parser.add_argument(
        "--internet-declaration",
        action="store_true",
        help="il pilota ha usato una dichiarazione via internet, che sostituisce quella "
        "del registratore (SC3 §2.3a)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log di dettaglio su stderr")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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

    release_time = None
    if args.release_time is not None:
        try:
            release_time = parse_release_time(args.release_time, flight)
        except ValueError as exc:
            parser.error(str(exc))

    analysis = analyse(
        flight,
        release_time=release_time,
        use_gnss_altitude=args.gnss_altitude,
        recorder_kind=_RECORDER_CHOICES[args.recorder],
        calibrated=args.calibrated,
    )
    report = validate_badge(
        flight, analysis, BADGES[args.badge], internet_declaration=args.internet_declaration
    )
    sys.stdout.write(render(report) + "\n")
    return EXIT_OK if report.complete else EXIT_NOT_VALID


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
