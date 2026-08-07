"""Composizione del report testuale destinato all'utente."""

from __future__ import annotations

from silverc.validator import Requirement, ValidationReport, Verdict

_MARKS = {
    Verdict.PASS: "[OK]",
    Verdict.FAIL: "[NO]",
    Verdict.MARGINAL: "[??]",
    Verdict.UNDETERMINED: "[--]",
}


def _rule(char: str = "-", width: int = 72) -> str:
    return char * width


def _coords(point) -> str:
    fix = point.fix
    lat_hemi = "N" if fix.lat >= 0 else "S"
    lon_hemi = "E" if fix.lon >= 0 else "W"
    alt = fix.pressure_alt if fix.pressure_alt is not None else fix.gnss_alt
    return (
        f"{abs(fix.lat):.5f}{lat_hemi} {abs(fix.lon):.5f}{lon_hemi}"
        f"  quota {alt if alt is not None else 'n/d'} m"
    )


def _requirement_block(req: Requirement) -> list[str]:
    lines = [
        f"{_MARKS[req.verdict]} {req.title}",
        f"     Esito     : {req.verdict.value}",
        f"     Misurato  : {req.measured}   (richiesto: {req.required})",
        "     Come e' stato verificato:",
    ]
    lines += [f"       - {m}" for m in req.method]
    lines.append("     Motivazione:")
    lines += [f"       - {r}" for r in req.reasons]
    return lines


def render(report: ValidationReport) -> str:
    """Report leggibile: esito, metodo di verifica e motivazioni."""
    flight = report.flight
    analysis = report.analysis
    lines: list[str] = [
        _rule("="),
        "VALIDAZIONE INSEGNA D'ARGENTO FAI (Silver C)",
        _rule("="),
        f"File      : {flight.source}",
        f"Data volo : {flight.flight_date or 'n/d'}",
        f"Pilota    : {flight.pilot}",
        f"Aliante   : {flight.glider}",
        f"Logger    : {flight.recorder}",
        f"Fix usati : {len(flight.fixes)}",
        "",
        "PUNTI NOTEVOLI DEL VOLO (orari UTC)",
        _rule(),
        f"Decollo      : {analysis.takeoff.time:%H:%M:%S}  {_coords(analysis.takeoff)}",
        f"Sgancio      : {analysis.release.time:%H:%M:%S}  {_coords(analysis.release)}",
        f"               ({analysis.release_source}, confidenza {analysis.release_confidence})",
        f"Punto max    : {analysis.farthest.time:%H:%M:%S}  {_coords(analysis.farthest)}",
        f"               {analysis.distance_m / 1000:.2f} km dallo sgancio, "
        f"{analysis.distance_from_takeoff_m / 1000:.2f} km dal decollo",
        f"Atterraggio  : {analysis.landing.time:%H:%M:%S}  {_coords(analysis.landing)}",
        f"Quota usata  : {analysis.altitude_source}",
        "",
        "REQUISITI",
        _rule(),
    ]

    for req in report.requirements:
        lines += _requirement_block(req)
        lines.append("")

    lines += ["ESITO COMPLESSIVO", _rule()]
    satisfied = report.satisfied
    if report.complete:
        lines.append(
            "VALIDO: questo singolo volo soddisfa tutti e tre i requisiti "
            "dell'insegna d'argento."
        )
    elif satisfied:
        nomi = ", ".join(r.code for r in satisfied)
        lines.append(
            f"PARZIALE: il volo soddisfa {len(satisfied)}/3 requisiti ({nomi})."
        )
        lines.append(
            "I tre requisiti possono essere ottenuti in voli distinti: i restanti "
            "vanno documentati con altre tracce."
        )
    else:
        lines.append("NON VALIDO: il volo non soddisfa nessuno dei tre requisiti.")

    if report.warnings:
        lines += ["", "AVVERTENZE", _rule()]
        lines += [f"  ! {w}" for w in report.warnings]

    lines += [
        "",
        _rule(),
        "Questo report e' un ausilio all'analisi, non un'omologazione. Le soglie",
        "applicate provengono da fonti secondarie del FAI Sporting Code Sect. 3:",
        "verificarle sull'edizione in vigore e far convalidare il volo da un",
        "Osservatore Ufficiale.",
        _rule(),
    ]
    return "\n".join(lines)
